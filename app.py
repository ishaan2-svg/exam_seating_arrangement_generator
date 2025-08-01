from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify, flash
import pandas as pd
import os
import qrcode
import pyotp
import qrcode.image.svg
import glob
from datetime import datetime, timedelta
import json
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from main import run_seating_pipeline

app = Flask(__name__)
app.secret_key = 'enhanced_secretkey_2025'

# Configure secure session settings
app.config.update(
    SESSION_COOKIE_SECURE=True,    # Only send cookies over HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # Prevent client-side JS access
    SESSION_COOKIE_SAMESITE='Lax',  # CSRF protection
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),  # Session timeout
    SESSION_REFRESH_EACH_REQUEST=True  # Update session timestamp on each request
)

# Configuration
CSV_PATH = os.path.abspath('data/students.csv')
UPLOAD_FOLDER = os.path.abspath('static/uploads')
QR_FOLDER = os.path.abspath('static/qrcodes')
DB_PATH = os.path.abspath('data/system.db')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
os.makedirs('data', exist_ok=True)

def get_or_create_shared_totp_secret():
    """Get or create a shared TOTP secret for admin and teachers"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if there's already a shared secret in the system_config table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    cursor.execute('SELECT value FROM system_config WHERE key = ?', ('shared_totp_secret',))
    result = cursor.fetchone()
    
    if result:
        shared_secret = result[0]
    else:
        # Generate new shared secret
        shared_secret = pyotp.random_base32()
        cursor.execute('INSERT INTO system_config (key, value) VALUES (?, ?)', 
                      ('shared_totp_secret', shared_secret))
        conn.commit()
    
    conn.close()
    return shared_secret

def init_database():
    """Initialize SQLite database for system data"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            totp_secret TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT NOT NULL UNIQUE,
            capacity INTEGER NOT NULL,
            max_subjects INTEGER,
            max_branches INTEGER,
            allowed_years TEXT,
            allowed_branches TEXT,
            layout_columns INTEGER DEFAULT 6,
            layout_rows INTEGER DEFAULT 5
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_username TEXT NOT NULL,
            room_name TEXT NOT NULL,
            UNIQUE (teacher_username)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Get shared TOTP secret
    shared_secret = get_or_create_shared_totp_secret()
    
    # Add an admin user if not exists
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        hashed_password = generate_password_hash('adminpass')
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, totp_secret)
            VALUES (?, ?, ?, ?)
        ''', ('admin', hashed_password, 'admin', shared_secret))
    else:
        # Update existing admin to use shared secret
        cursor.execute('''
            UPDATE users SET totp_secret = ? WHERE username = ? AND role = ?
        ''', (shared_secret, 'admin', 'admin'))
    
    # Add default room configurations if they don't exist
    default_rooms = [
        ('Room-A', 30, 15, 5, '2,3', 'CS,EC,ME', 6, 5),
        ('Room-B', 40, 15, 5, '2,3', 'CS,EC,ME', 8, 5),
        ('Room-C', 25, 10, 3, '2,3,4', 'CS,EC', 5, 5)
    ]
    
    for room_data in default_rooms:
        cursor.execute('SELECT * FROM room_configs WHERE room_name = ?', (room_data[0],))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO room_configs 
                (room_name, capacity, max_subjects, max_branches, allowed_years, allowed_branches, layout_columns, layout_rows)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', room_data)
    
    conn.commit()
    conn.close()

def get_rooms_config_from_db():
    """Get room configurations from database in the format expected by main.py"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT room_name, capacity, max_subjects, max_branches, allowed_years, 
               allowed_branches, layout_columns, layout_rows 
        FROM room_configs ORDER BY room_name
    ''')
    rooms_data = cursor.fetchall()
    conn.close()
    
    rooms_config = []
    for row in rooms_data:
        room_config = {
            'room_name': row[0],
            'capacity': row[1],
            'max_subjects': row[2],
            'max_branches': row[3],
            'allowed_years': [int(y) for y in row[4].split(',') if y.strip()] if row[4] else [],
            'allowed_branches': row[5].split(',') if row[5] else [],
            'layout_columns': row[6] or 6,
            'layout_rows': row[7] or 5
        }
        rooms_config.append(room_config)
    
    return rooms_config

# Decorator for login required
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator for admin required
def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator for teacher required
def require_teacher(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'teacher':
            flash('Teacher access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Mock student data for demonstration
def load_student_data():
    if os.path.exists(CSV_PATH):
        try:
            return pd.read_csv(CSV_PATH)
        except Exception as e:
            print(f"Error loading students.csv: {e}")
            return pd.DataFrame()
    return pd.DataFrame({
        'StudentID': ['1001', '1002', '1003', '1004', '1005', '1006', '1007', '1008', '1009', '1010', '1011', '1012'],
        'Name': ['Alice Smith', 'Bob Johnson', 'Charlie Brown', 'Diana Prince', 'Eve Adams', 'Frank White', 'Grace Lee', 'Harry Kim', 'Ivy Green', 'Jack Black', 'Kevin Blue', 'Linda Red'],
        'Department': ['CSE', 'ECE', 'ME', 'CSE', 'ECE', 'ME', 'CSE', 'ECE', 'ME', 'CSE', 'ECE', 'ME'],
        'Branch': ['CS', 'EC', 'ME', 'CS', 'EC', 'ME', 'CS', 'EC', 'ME', 'CS', 'EC', 'ME'],
        'Batch': ['2022', '2022', '2022', '2023', '2023', '2023', '2022', '2022', '2023', '2023', '2022', '2023'],
        'Year': [2, 2, 2, 3, 3, 3, 2, 2, 3, 3, 2, 3],
        'Semester': [4, 4, 4, 6, 6, 6, 4, 4, 6, 6, 4, 6],
        'Subject': ['DSA', 'VLSI', 'Thermodynamics', 'AI', 'DSP', 'Fluid Mech', 'OS', 'Signals', 'Robotics', 'Networks', 'Embedded Sys', 'Compilers'],
        'ExamDate': ['2025-06-01', '2025-06-01', '2025-06-02', '2025-06-02', '2025-06-03', '2025-06-03', '2025-06-01', '2025-06-01', '2025-06-02', '2025-06-02', '2025-06-03', '2025-06-03'],
        'ExamTime': ['Morning', 'Morning', 'Afternoon', 'Afternoon', 'Morning', 'Morning', 'Afternoon', 'Afternoon', 'Morning', 'Morning', 'Afternoon', 'Afternoon'],
        'PhotoPath': [f'/static/uploads/student_{i}.jpg' for i in range(1, 13)],
        'Gender': ['M', 'F', 'M', 'F', 'M', 'F', 'M', 'F', 'M', 'F', 'M', 'F']
    })

# Initialize student data
df_students = load_student_data()

# Import functions from main.py with fallback
try:
    from main import get_colored_groups, extract_student_metadata, assign_rooms_to_groups, assign_seats_in_room, create_index_page, create_simple_html_visualization
except ImportError:
    print("Error: main.py not found or functions not importable.")
    get_colored_groups = extract_student_metadata = assign_rooms_to_groups = assign_seats_in_room = create_index_page = create_simple_html_visualization = None

# Routes
@app.route('/')
def index():
    print(f"DEBUG: Index route accessed")
    print(f"DEBUG: Session logged_in: {'logged_in' in session}")
    if 'logged_in' in session:
        print(f"DEBUG: User role: {session.get('role')}")
        print(f"DEBUG: Username: '{session.get('username')}'")
        
        # Safety check for students - verify they exist in CSV before redirecting
        if session['role'] == 'student':
            student_info = get_student_by_id(session['username'])
            if not student_info:
                print(f"DEBUG: Student '{session['username']}' not found in CSV - clearing session")
                session.clear()
                flash('Student record not found. Please register or contact admin.', 'warning')
                return redirect(url_for('login'))
            print(f"DEBUG: Redirecting to student_dashboard with student_id: '{session['username']}'")
            return redirect(url_for('student_dashboard', student_id=session['username']))
        
        elif session['role'] == 'admin':
            print("DEBUG: Redirecting to admin_dashboard")
            return redirect(url_for('admin_dashboard'))
        elif session['role'] == 'teacher':
            print("DEBUG: Redirecting to teacher_dashboard")
            return redirect(url_for('teacher_dashboard'))
    
    print("DEBUG: Redirecting to login")
    return redirect(url_for('login'))

@app.route('/run')
def run_pipeline():
    run_seating_pipeline()
    return "Pipeline executed successfully!"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        totp_code = request.form.get('totp')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND role = ?', (username, role))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            # Only require 2FA for admin login
            if role == 'admin':
                if user[4]:  # user[4] is totp_secret
                    totp = pyotp.TOTP(user[4])
                    if not totp.verify(totp_code):
                        flash('Invalid 2FA code.', 'danger')
                        return render_template('enhanced_login.html')
                else:
                    flash('Admin account requires 2FA setup. Please contact support.', 'danger')
                    return render_template('enhanced_login.html')

            # For students, verify they exist in CSV
            if role == 'student':
                student_data = get_student_by_id(username)
                if not student_data:
                    flash('Student ID not found in system records. Please contact admin.', 'danger')
                    return render_template('enhanced_login.html')

            session['logged_in'] = True
            session['username'] = username
            session['role'] = role
            session['user_id'] = user[0]

            flash(f'Logged in as {role}!', 'success')
            if role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            elif role == 'student':
                return redirect(url_for('student_dashboard', student_id=username))
        else:
            flash('Invalid username, password, or role.', 'danger')
    return render_template('enhanced_login.html')

@app.route('/visualizations/<path:filename>')
@require_admin
def serve_visualization_file(filename):
    return send_from_directory('visualizations', filename)

@app.route('/seating_dashboard')
@require_admin
def seating_dashboard():
    return redirect(url_for('serve_visualization_file', filename='index.html'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Load available rooms from database
    cursor.execute('SELECT room_name, capacity FROM room_configs ORDER BY room_name')
    available_rooms = [{'room_name': row[0], 'capacity': row[1]} for row in cursor.fetchall()]

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form.get('role', 'student')
        assigned_room = request.form.get('assigned_room')
        student_id = request.form.get('student_id', '')  # Changed from full_name to student_id

        # Validation
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            conn.close()
            return render_template('register.html', available_rooms=available_rooms)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            conn.close()
            return render_template('register.html', available_rooms=available_rooms)

        # Special validation for students
        if role == 'student':
            if not student_id:
                flash('Student ID is required for student registration.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)
            
            # Validate Student ID format (only alphanumeric, no spaces)
            if not student_id.replace('_', '').replace('-', '').isalnum():
                flash('Student ID can only contain letters, numbers, hyphens, and underscores (no spaces).', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)
            
            # Check if student exists in CSV by Student ID
            student_data = get_student_by_id(student_id)
            if not student_data:
                flash(f'Student ID "{student_id}" not found in system records. Please contact admin to add your information first.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)
            
            # Use the Student ID as username (this ensures URL-safe usernames)
            username = str(student_id).strip()
            
            # Check if this student ID is already registered
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                flash(f'Student with ID {username} is already registered. Please login instead.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)

        if role == 'teacher':
            if not assigned_room:
                flash('Please select a room for the teacher.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)

            # Check if room is already assigned to another teacher
            cursor.execute('SELECT teacher_username FROM teacher_rooms WHERE room_name = ?', (assigned_room,))
            existing_assignment = cursor.fetchone()
            if existing_assignment:
                flash(f'Room {assigned_room} is already assigned to teacher {existing_assignment[0]}.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)

        # Check for existing username (for non-students or if username was manually entered)
        if role != 'student':
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                flash('Username already exists.', 'danger')
                conn.close()
                return render_template('register.html', available_rooms=available_rooms)

        hashed_password = generate_password_hash(password)

        try:
            if role == 'teacher':
                # Use shared TOTP secret for teacher
                shared_secret = get_or_create_shared_totp_secret()
                
                # Insert user with shared TOTP
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, totp_secret)
                    VALUES (?, ?, ?, ?)
                ''', (username, hashed_password, role, shared_secret))
                
                user_id = cursor.lastrowid
                
                # Assign room to teacher
                cursor.execute('''
                    INSERT INTO teacher_rooms (teacher_username, room_name)
                    VALUES (?, ?)
                ''', (username, assigned_room))
                
                conn.commit()
                
                # Generate QR code for 2FA setup using shared secret
                totp_uri = pyotp.utils.build_uri(shared_secret, "SharedAccount", "ExamSeatingSystem")
                qr_filename = f"shared_2fa_setup.svg"
                qr_filepath = os.path.join(QR_FOLDER, qr_filename)
                
                img = qrcode.make(totp_uri, image_factory=qrcode.image.svg.SvgImage)
                with open(qr_filepath, "wb") as f:
                    img.save(f)
                
                # Store setup info in session for display
                session['teacher_setup'] = {
                    'username': username,
                    'totp_secret': shared_secret,
                    'qr_path': url_for('static', filename=f'qrcodes/{qr_filename}'),
                    'assigned_room': assigned_room
                }
                
                flash('Teacher registered successfully! Please set up 2FA using the shared QR code below.', 'success')
                conn.close()
                return redirect(url_for('teacher_setup_2fa'))
                
            else:  # Student registration
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role)
                    VALUES (?, ?, ?)
                ''', (username, hashed_password, role))
                
                conn.commit()
                flash(f'Student registration successful! Your username is {username} (Student ID). Please log in.', 'success')
                conn.close()
                return redirect(url_for('login'))
                
        except sqlite3.IntegrityError as e:
            flash(f'Registration failed: {str(e)}', 'danger')
            conn.rollback()
        except Exception as e:
            flash(f'An error occurred during registration: {str(e)}', 'danger')
            conn.rollback()

    conn.close()
    return render_template('register.html', available_rooms=available_rooms)

@app.route('/teacher_setup_2fa')
def teacher_setup_2fa():
    """Display 2FA setup page for newly registered teachers"""
    if 'teacher_setup' not in session:
        flash('No teacher setup information found.', 'danger')
        return redirect(url_for('register'))
    
    setup_info = session['teacher_setup']
    return render_template('teacher_setup_2fa.html', setup_info=setup_info)

@app.route('/complete_teacher_setup', methods=['POST'])
def complete_teacher_setup():
    """Verify 2FA setup and complete teacher registration"""
    if 'teacher_setup' not in session:
        flash('No teacher setup information found.', 'danger')
        return redirect(url_for('register'))
    
    setup_info = session['teacher_setup']
    verification_code = request.form.get('verification_code')
    
    if not verification_code:
        flash('Please enter the verification code from your authenticator app.', 'danger')
        return render_template('teacher_setup_2fa.html', setup_info=setup_info)
    
    # Verify the TOTP code
    totp = pyotp.TOTP(setup_info['totp_secret'])
    if totp.verify(verification_code):
        # Clear setup session
        session.pop('teacher_setup', None)
        flash('2FA setup completed successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    else:
        flash('Invalid verification code. Please try again.', 'danger')
        return render_template('teacher_setup_2fa.html', setup_info=setup_info)

@app.route('/admin_dashboard')
@require_admin
def admin_dashboard():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get shared TOTP secret to display QR code
    shared_secret = get_or_create_shared_totp_secret()
    qr_code_svg = None
    if shared_secret:
        totp_uri = pyotp.utils.build_uri(shared_secret, "SharedAccount", "ExamSeatingSystem")
        img = qrcode.make(totp_uri, image_factory=qrcode.image.svg.SvgImage)
        buffer = BytesIO()
        img.save(buffer)
        qr_code_svg = buffer.getvalue().decode('utf-8')

    admin_data = {
        'totp_secret': shared_secret,
        'qr_code_svg': qr_code_svg
    }

    # Fetch all users with their assigned rooms
    cursor.execute('''
        SELECT u.id, u.username, u.role, tr.room_name 
        FROM users u 
        LEFT JOIN teacher_rooms tr ON u.username = tr.teacher_username 
        ORDER BY u.role, u.username
    ''')
    user_rows = cursor.fetchall()
    users = []
    for row in user_rows:
        user_data = {
            'id': row[0],
            'username': row[1],
            'role': row[2],
            'email': f'{row[1]}@example.com',
            'assigned_room': row[3] if row[3] else 'N/A'
        }
        users.append(user_data)

    # Fetch room info from database
    cursor.execute('SELECT room_name, capacity FROM room_configs ORDER BY room_name')
    global_room_configs_from_db = [{'room_name': r[0], 'capacity': r[1]} for r in cursor.fetchall()]

    # Student metrics
    df = load_student_data()
    total_students = len(df)
    active_exams = df['Subject'].nunique() if not df.empty else 0
    exam_time_dict = df['ExamTime'].value_counts().to_dict() if not df.empty else {}
    exam_time_distribution = SimpleNamespace(**exam_time_dict)

    conn.close()

    return render_template(
        'admin_dashboard.html',
        username=session['username'],
        admin_data=admin_data,
        users=users,
        total_students=total_students,
        active_exams=active_exams,
        exam_time_distribution=exam_time_distribution,
        global_room_configs_from_db=global_room_configs_from_db
    )

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@require_admin
def admin_delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get user info before deletion
        cursor.execute('SELECT username, role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('User not found.', 'danger')
            conn.close()
            return redirect(url_for('admin_dashboard'))
        
        username, role = user
        
        # Don't allow deleting the current admin
        if username == session['username'] and role == 'admin':
            flash('Cannot delete your own admin account.', 'danger')
            conn.close()
            return redirect(url_for('admin_dashboard'))
        
        # Delete teacher room assignment if exists
        if role == 'teacher':
            cursor.execute('DELETE FROM teacher_rooms WHERE teacher_username = ?', (username,))
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        
        flash(f'User {username} deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'danger')
        conn.rollback()
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@require_admin
def admin_edit_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if request.method == 'POST':
        new_room = request.form.get('assigned_room')
        
        # Get user info
        cursor.execute('SELECT username, role FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('User not found.', 'danger')
            conn.close()
            return redirect(url_for('admin_dashboard'))
        
        username, role = user
        
        if role == 'teacher':
            try:
                # Check if new room is already assigned to another teacher
                if new_room:
                    cursor.execute('SELECT teacher_username FROM teacher_rooms WHERE room_name = ? AND teacher_username != ?', 
                                 (new_room, username))
                    existing_assignment = cursor.fetchone()
                    if existing_assignment:
                        flash(f'Room {new_room} is already assigned to {existing_assignment[0]}.', 'danger')
                        conn.close()
                        return redirect(url_for('admin_edit_user', user_id=user_id))
                
                # Update room assignment
                cursor.execute('DELETE FROM teacher_rooms WHERE teacher_username = ?', (username,))
                if new_room:
                    cursor.execute('INSERT INTO teacher_rooms (teacher_username, room_name) VALUES (?, ?)', 
                                 (username, new_room))
                
                conn.commit()
                flash(f'Teacher {username} room assignment updated successfully.', 'success')
                conn.close()
                return redirect(url_for('admin_dashboard'))
                
            except Exception as e:
                flash(f'Error updating user: {str(e)}', 'danger')
                conn.rollback()
    
    # GET request - show edit form
    cursor.execute('''
        SELECT u.username, u.role, tr.room_name 
        FROM users u 
        LEFT JOIN teacher_rooms tr ON u.username = tr.teacher_username 
        WHERE u.id = ?
    ''', (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        flash('User not found.', 'danger')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    
    # Get available rooms
    cursor.execute('SELECT room_name, capacity FROM room_configs ORDER BY room_name')
    available_rooms = [{'room_name': row[0], 'capacity': row[1]} for row in cursor.fetchall()]
    
    # Get assigned rooms to exclude current user's room
    cursor.execute('SELECT room_name, teacher_username FROM teacher_rooms WHERE teacher_username != ?', (user_data[0],))
    assigned_rooms = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    user_info = {
        'id': user_id,
        'username': user_data[0],
        'role': user_data[1],
        'assigned_room': user_data[2]
    }
    
    return render_template('admin_edit_user.html', 
                         user=user_info, 
                         available_rooms=available_rooms,
                         assigned_rooms=assigned_rooms)

@app.route('/admin/exam_schedule')
@require_admin
def admin_exam_schedule():
    df = load_student_data()
    if df.empty:
        flash('No student data loaded.', 'info')
        return render_template('admin_exam_schedule.html', exam_time_distribution={}, exam_date_subjects={})

    exam_time_distribution = df['ExamTime'].value_counts().to_dict()
    exam_date_subjects = df.groupby('ExamDate')['Subject'].apply(lambda x: x.tolist()).to_dict()

    return render_template('admin_exam_schedule.html',
                           exam_time_distribution=exam_time_distribution,
                           exam_date_subjects=exam_date_subjects)

@app.route('/admin/seating_rules')
@require_admin
def admin_seating_rules():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM room_configs ORDER BY room_name')
    rooms_data = cursor.fetchall()
    conn.close()

    room_constraints = []
    for room in rooms_data:
        room_constraints.append({
            'room_name': room[1],
            'capacity': room[2],
            'max_subjects': room[3],
            'max_branches': room[4],
            'allowed_years': room[5].split(',') if room[5] else [],
            'allowed_branches': room[6].split(',') if room[6] else []
        })
    return render_template('admin_seating_rules.html', room_constraints=room_constraints)

@app.route('/admin/rooms_config')
@require_admin
def admin_rooms_config():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get rooms data
    cursor.execute('SELECT * FROM room_configs ORDER BY room_name')
    rooms = cursor.fetchall()
    
    # Get users data with room assignments
    cursor.execute('''
        SELECT u.id, u.username, u.role, tr.room_name 
        FROM users u 
        LEFT JOIN teacher_rooms tr ON u.username = tr.teacher_username 
        ORDER BY u.role, u.username
    ''')
    user_rows = cursor.fetchall()
    users = []
    for row in user_rows:
        user_data = {
            'id': row[0],
            'username': row[1],
            'role': row[2],
            'assigned_room': row[3] if row[3] else None
        }
        users.append(user_data)
    
    conn.close()
    return render_template('admin_rooms_config.html', rooms=rooms, users=users)

@app.route('/admin/add_room_config', methods=['GET', 'POST'])
@require_admin
def admin_add_room_config():
    if request.method == 'POST':
        room_name = request.form['room_name']
        capacity = int(request.form['capacity'])
        max_subjects = request.form.get('max_subjects')
        max_branches = request.form.get('max_branches')
        allowed_years = request.form.getlist('allowed_years')
        allowed_branches = request.form.getlist('allowed_branches')
        layout_columns = int(request.form.get('layout_columns', 6))
        layout_rows = int(request.form.get('layout_rows', 5))

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO room_configs 
                (room_name, capacity, max_subjects, max_branches, allowed_years, allowed_branches, layout_columns, layout_rows)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (room_name, capacity, 
                  max_subjects if max_subjects else None, 
                  max_branches if max_branches else None,
                  ','.join(allowed_years), 
                  ','.join(allowed_branches),
                  layout_columns, layout_rows))
            conn.commit()
            flash('Room configuration added successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Room name already exists.', 'danger')
        conn.close()
        return redirect(url_for('admin_rooms_config'))
    return render_template('admin_add_room_config.html')

@app.route('/admin/edit_room_config/<int:room_id>', methods=['GET', 'POST'])
@require_admin
def admin_edit_room_config(room_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if request.method == 'POST':
        capacity = int(request.form['capacity'])
        max_subjects = request.form.get('max_subjects')
        max_branches = request.form.get('max_branches')
        allowed_years = request.form.getlist('allowed_years')
        allowed_branches = request.form.getlist('allowed_branches')
        layout_columns = int(request.form.get('layout_columns', 6))
        layout_rows = int(request.form.get('layout_rows', 5))

        cursor.execute('''
            UPDATE room_configs SET 
            capacity = ?, max_subjects = ?, max_branches = ?, 
            allowed_years = ?, allowed_branches = ?, layout_columns = ?, layout_rows = ?
            WHERE id = ?
        ''', (capacity, 
              max_subjects if max_subjects else None, 
              max_branches if max_branches else None,
              ','.join(allowed_years), 
              ','.join(allowed_branches),
              layout_columns, layout_rows, room_id))
        conn.commit()
        flash('Room configuration updated successfully!', 'success')
        conn.close()
        return redirect(url_for('admin_rooms_config'))

    cursor.execute('SELECT * FROM room_configs WHERE id = ?', (room_id,))
    room = cursor.fetchone()
    conn.close()

    if room:
        room_dict = {
            'id': room[0],
            'room_name': room[1],
            'capacity': room[2],
            'max_subjects': room[3],
            'max_branches': room[4],
            'allowed_years': room[5].split(',') if room[5] else [],
            'allowed_branches': room[6].split(',') if room[6] else [],
            'layout_columns': room[7] if len(room) > 7 else 6,
            'layout_rows': room[8] if len(room) > 8 else 5
        }
        return render_template('admin_edit_room_config.html', room=room_dict)
    else:
        flash('Room not found.', 'danger')
        return redirect(url_for('admin_rooms_config'))

@app.route('/admin/delete_room_config/<int:room_id>', methods=['POST'])
@require_admin
def admin_delete_room_config(room_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get room name for feedback
        cursor.execute('SELECT room_name FROM room_configs WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        
        if not room:
            flash('Room not found.', 'danger')
            conn.close()
            return redirect(url_for('admin_rooms_config'))
        
        room_name = room[0]
        
        # Check if room is assigned to any teacher
        cursor.execute('SELECT teacher_username FROM teacher_rooms WHERE room_name = ?', (room_name,))
        assigned_teacher = cursor.fetchone()
        
        if assigned_teacher:
            flash(f'Cannot delete room {room_name}. It is assigned to teacher {assigned_teacher[0]}. Please reassign the teacher first.', 'danger')
            conn.close()
            return redirect(url_for('admin_rooms_config'))
        
        # Delete room configuration
        cursor.execute('DELETE FROM room_configs WHERE id = ?', (room_id,))
        conn.commit()
        
        flash(f'Room {room_name} deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting room: {str(e)}', 'danger')
        conn.rollback()
    
    conn.close()
    return redirect(url_for('admin_rooms_config'))

@app.route('/teacher_dashboard')
@require_login
def teacher_dashboard():
    # Load student data if needed
    df = load_student_data()
    students_data = df.to_dict(orient='records')

    # Fetch rooms assigned to this teacher only
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT room_name FROM teacher_rooms WHERE teacher_username = ?
    ''', (session['username'],))
    rooms_config_db = [row[0] for row in cursor.fetchall()]
    conn.close()

    seating_plan_exists = 'final_seating_layout' in session and session['final_seating_layout'] is not None

    return render_template(
        'enhanced_teacher_dashboard.html',
        username=session['username'],
        students=students_data,
        rooms_config=rooms_config_db,
        seating_plan_exists=seating_plan_exists
    )

def get_student_seating_info(student_id):
    """
    Get student's room and seat assignment from the exports CSV files
    Returns: dict with 'room', 'seat_no', 'seat_x', 'seat_y' or None if not found
    """
    exports_dir = 'exports'
    
    if not os.path.exists(exports_dir):
        print(f"DEBUG: Exports directory '{exports_dir}' does not exist")
        return None
    
    # Look for all CSV files in exports directory
    csv_files = glob.glob(os.path.join(exports_dir, "*_seating.csv"))
    
    if not csv_files:
        print(f"DEBUG: No seating CSV files found in '{exports_dir}' directory")
        return None
    
    print(f"DEBUG: Found {len(csv_files)} seating CSV files")
    
    # Search for the student in all CSV files
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            
            # Convert StudentID column to string for comparison
            if 'StudentID' in df.columns:
                df['StudentID'] = df['StudentID'].astype(str)
                
                # Look for the student
                student_row = df[df['StudentID'] == str(student_id)]
                
                if not student_row.empty:
                    row_data = student_row.iloc[0]
                    seating_info = {
                        'room': row_data.get('Room', 'Unknown'),
                        'seat_no': row_data.get('Seat_No', 'Unknown'),
                        'seat_x': row_data.get('Seat_X', 'Unknown'),
                        'seat_y': row_data.get('Seat_Y', 'Unknown')
                    }
                    print(f"DEBUG: Found student {student_id} in {csv_file}: {seating_info}")
                    return seating_info
                    
        except Exception as e:
            print(f"DEBUG: Error reading {csv_file}: {e}")
            continue
    
    print(f"DEBUG: Student {student_id} not found in any seating CSV files")
    return None

def get_room_seating_data(room_name):
    """
    Get all students assigned to a specific room
    Returns: DataFrame or None if not found
    """
    exports_dir = 'exports'
    csv_file = os.path.join(exports_dir, f"{room_name}_seating.csv")
    
    if os.path.exists(csv_file):
        try:
            return pd.read_csv(csv_file)
        except Exception as e:
            print(f"Error reading {csv_file}: {e}")
            return None
    
    return None

def refresh_seating_exports():
    """
    Regenerate all seating CSV exports from current session data
    Call this if the exports are out of date
    """
    final_seating_layout = session.get('final_seating_layout')
    student_metadata = session.get('student_metadata')
    
    if not final_seating_layout or not student_metadata:
        print("No seating data in session to export")
        return False
    
    exports_dir = 'exports'
    os.makedirs(exports_dir, exist_ok=True)
    
    for room_name, room_seats in final_seating_layout.items():
        if not room_seats:
            continue
            
        room_data = []
        for seat in room_seats:
            student_id = seat['student_id']
            info = student_metadata.get(student_id, {})
            room_data.append({
                'StudentID': student_id,
                'Name': info.get('Name', 'Unknown'),
                'Department': info.get('Department', 'Unknown'),
                'Branch': info.get('Branch', 'Unknown'),
                'Year': info.get('Year', 'Unknown'),
                'Subject': info.get('Subject', 'Unknown'),
                'ExamDate': info.get('ExamDate', 'Unknown'),
                'ExamTime': info.get('ExamTime', 'Unknown'),
                'Room': room_name,
                'Seat_X': seat['x'],
                'Seat_Y': seat['y'],
                'Seat_No': seat['seat_no']
            })
        
        if room_data:
            df = pd.DataFrame(room_data)
            csv_path = os.path.join(exports_dir, f"{room_name}_seating.csv")
            df.to_csv(csv_path, index=False)
            print(f"Updated {csv_path}")
    
    return True

@app.route('/student_dashboard/<student_id>')
@require_login
def student_dashboard(student_id):
    print(f"DEBUG: Student dashboard accessed with student_id: '{student_id}'")
    print(f"DEBUG: Session username: '{session.get('username')}'")
    print(f"DEBUG: Session role: '{session.get('role')}'")
    
    # Verify the logged-in user can access this student dashboard
    if session['role'] == 'student' and session['username'] != student_id:
        print(f"DEBUG: Access denied - session username '{session['username']}' != student_id '{student_id}'")
        flash('Access denied. You can only view your own dashboard.', 'danger')
        print(f"DEBUG: Redirecting back to student_dashboard with session username: '{session['username']}'")
        return redirect(url_for('student_dashboard', student_id=session['username']))
    
    print(f"DEBUG: Access granted, looking up student info for: '{student_id}'")
    
    # Get student info from CSV
    student_info = get_student_by_id(student_id)
    
    if not student_info:
        print(f"DEBUG: Student not found in CSV: '{student_id}' - Logging out user")
        # Clear the session and redirect to login instead of creating a loop
        session.clear()
        flash('Student record not found in system. Please contact admin or register again.', 'warning')
        return redirect(url_for('login'))

    print(f"DEBUG: Student found: {student_info.get('Name', 'Unknown')}")

    # Get seating information from exports CSV files
    seating_info = get_student_seating_info(student_id)
    
    # Placeholder for QR code generation
    qr_path = None
    if 'qr_code_data' in session and session['qr_code_data'].get('student_id') == student_id:
        qr_path = session['qr_code_data'].get('path')

    # Create exam details from student info with actual seating data
    room_info = 'TBD'
    seat_info = 'TBD'
    
    if seating_info:
        room_info = seating_info['room']
        seat_info = f"Seat {seating_info['seat_no']} (Position: {seating_info['seat_x']}, {seating_info['seat_y']})"
    
    exams = [{
        'subject': student_info.get('Subject', 'N/A'),
        'department': student_info.get('Department', 'N/A'),
        'date': student_info.get('ExamDate', 'N/A'),
        'time': student_info.get('ExamTime', 'N/A'),
        'room': room_info,
        'seat_no': seat_info
    }]

    print(f"DEBUG: Rendering student dashboard template with seating info: {seating_info}")
    return render_template('student_dashboard.html',
                           name=student_info.get('Name', 'Student'),
                           student_id=student_id,
                           photo_path=student_info.get('PhotoPath'),
                           qr_path=qr_path,
                           exams=exams,
                           seating_info=seating_info)


def get_student_by_id(student_id):
    """Get student info from CSV by StudentID"""
    try:
        df = pd.read_csv(CSV_PATH)
        # Handle column mapping
        if 'Branch' not in df.columns and 'Batch' in df.columns:
            df['Branch'] = df['Batch']
        
        # Convert StudentID column to string for comparison
        df['StudentID'] = df['StudentID'].astype(str)
        
        student = df[df['StudentID'] == str(student_id)]
        if not student.empty:
            return student.iloc[0].to_dict()
        return None
    except Exception as e:
        print(f"Error reading student data: {e}")
        return None

@app.route('/generate_qr_code/<student_id>', methods=['POST'])
@require_login
def generate_qr_code(student_id):
    # Ensure student_id is for the logged-in student or admin is requesting
    if session['role'] == 'student' and session['username'] != student_id:
        flash('Unauthorized QR code generation request.', 'danger')
        return redirect(url_for('student_dashboard', student_id=session['username']))

    qr_data = f"StudentID:{student_id}|ExamSystem"
    qr_filename = f"student_{student_id}_qr.svg"
    qr_filepath = os.path.join(QR_FOLDER, qr_filename)

    try:
        img = qrcode.make(qr_data, image_factory=qrcode.image.svg.SvgImage)
        with open(qr_filepath, "wb") as f:
            img.save(f)
        qr_url = url_for('static', filename=f'qrcodes/{qr_filename}')
        session['qr_code_data'] = {'student_id': student_id, 'path': qr_url}
        flash('QR Code generated successfully!', 'success')
    except Exception as e:
        flash(f'Error generating QR Code: {e}', 'danger')

    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('student_dashboard', student_id=student_id))

@app.route('/process_seating_plan', methods=['POST'])
@require_teacher
def process_seating_plan():
    global df_students

    uploaded_file = request.files.get('student_data_file')
    if uploaded_file and uploaded_file.filename != '':
        file_path = os.path.join(UPLOAD_FOLDER, 'students.csv')
        uploaded_file.save(file_path)
        df_students = pd.read_csv(file_path)
        flash('Student data uploaded and reloaded successfully!', 'success')
    else:
        flash('Using existing student data.', 'info')
        df_students = load_student_data()

    if df_students.empty:
        flash('No student data available to generate seating plan.', 'danger')
        return redirect(url_for('teacher_dashboard'))

    # Load room configurations from database (dynamic)
    current_rooms_config = get_rooms_config_from_db()
    
    if not current_rooms_config:
        flash('No room configurations found. Please configure rooms in the admin dashboard.', 'danger')
        return redirect(url_for('teacher_dashboard'))

    try:
        # Step 1: Extract student metadata
        student_metadata = extract_student_metadata(df_students)
        print("✅ Student metadata extracted.")

        # Step 2: Get colored groups (conflict resolution)
        colored_groups = get_colored_groups(student_metadata)
        print(f"✅ Generated {len(colored_groups)} conflict-free groups.")

        # Step 3: Assign rooms to groups
        room_assignments = assign_rooms_to_groups(colored_groups, student_metadata, current_rooms_config)
        print("✅ Rooms assigned to groups.")

        # Step 4: Assign seats within rooms
        final_seating_layout = assign_seats_in_room(room_assignments, student_metadata, {r['room_name']:r for r in current_rooms_config})
        print("✅ Seats assigned within rooms.")

        # Store results in session
        session['final_seating_layout'] = final_seating_layout
        session['student_metadata'] = student_metadata
        session['rooms_config_for_seating'] = current_rooms_config

        # Step 5: Automatically generate CSV exports
        print("🔄 Generating CSV exports...")
        exports_dir = 'exports'
        os.makedirs(exports_dir, exist_ok=True)
        
        exported_rooms = []
        for room_name, seats in final_seating_layout.items():
            if seats:  # Only export rooms with students
                room_data = []
                for seat in seats:
                    student_id = seat['student_id']
                    info = student_metadata.get(student_id, {})
                    room_data.append({
                        'StudentID': student_id,
                        'Name': info.get('Name', 'Unknown'),
                        'Department': info.get('Department', 'Unknown'),
                        'Branch': info.get('Branch', 'Unknown'),
                        'Year': info.get('Year', 'Unknown'),
                        'Subject': info.get('Subject', 'Unknown'),
                        'ExamDate': info.get('ExamDate', 'Unknown'),
                        'ExamTime': info.get('ExamTime', 'Unknown'),
                        'Room': room_name,
                        'Seat_X': seat['x'],
                        'Seat_Y': seat['y'],
                        'Seat_No': seat['seat_no']
                    })
                
                if room_data:
                    df_export = pd.DataFrame(room_data)
                    csv_path = os.path.join(exports_dir, f"{room_name}_seating.csv")
                    df_export.to_csv(csv_path, index=False)
                    exported_rooms.append(room_name)
                    print(f"✅ Exported {room_name} with {len(room_data)} students")
        
        print(f"✅ Generated CSV exports for {len(exported_rooms)} rooms: {exported_rooms}")
        flash(f'Seating plan generated successfully! CSV exports created for {len(exported_rooms)} rooms.', 'success')
        return redirect(url_for('view_seating_results'))

    except Exception as e:
        flash(f'Error generating seating plan: {e}', 'danger')
        return redirect(url_for('teacher_dashboard'))

@app.route('/api/student_seating/<student_id>')
@require_login
def api_get_student_seating(student_id):
    """
    API endpoint to get student's seating information
    """
    # Security check - students can only access their own data
    if session['role'] == 'student' and session['username'] != student_id:
        return jsonify({'error': 'Access denied'}), 403
    
    seating_info = get_student_seating_info(student_id)
    
    if seating_info:
        return jsonify({
            'success': True,
            'student_id': student_id,
            'seating_info': seating_info
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Seating assignment not found'
        })

@app.route('/api/refresh_seating_exports', methods=['POST'])
@require_teacher
def api_refresh_seating_exports():
    """
    API endpoint to refresh/regenerate seating CSV exports
    Only teachers can trigger this
    """
    success = refresh_seating_exports()
    
    if success:
        return jsonify({
            'success': True,
            'message': 'Seating exports refreshed successfully'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'No seating data available to export'
        })

@app.route('/api/room_students/<room_name>')
@require_login  
def api_get_room_students(room_name):
    """
    API endpoint to get all students in a specific room
    """
    room_data = get_room_seating_data(room_name)
    
    if room_data is not None:
        students = room_data.to_dict('records')
        return jsonify({
            'success': True,
            'room_name': room_name,
            'students': students,
            'total_students': len(students)
        })
    else:
        return jsonify({
            'success': False,
            'message': f'No seating data found for room {room_name}'
        })

@app.route('/generate_seating_exports', methods=['POST'])
@require_teacher
def generate_seating_exports():
    """
    Manually trigger generation of seating CSV exports
    """
    success = refresh_seating_exports()
    
    if success:
        flash('Seating exports generated successfully!', 'success')
    else:
        flash('No seating data available. Please generate a seating plan first.', 'warning')
    
    return redirect(url_for('view_seating_results'))

@app.route('/view_seating_results')
@require_teacher
def view_seating_results():
    final_seating_layout = session.get('final_seating_layout')
    student_metadata = session.get('student_metadata')
    rooms_config_for_seating = session.get('rooms_config_for_seating')

    if not final_seating_layout or not student_metadata or not rooms_config_for_seating:
        flash('No seating plan found. Please generate one first.', 'info')
        return redirect(url_for('teacher_dashboard'))

    # Generate HTML visualizations and collect links
    visualization_links = []
    output_dir = 'visualizations'
    os.makedirs(output_dir, exist_ok=True)

    for room_name, seats in final_seating_layout.items():
        room_config = next((r for r in rooms_config_for_seating if r['room_name'] == room_name), None)
        if room_config and seats:
            html_content = create_simple_html_visualization(
                room_name=room_name,
                seating_arrangement=seats,
                metadata=student_metadata,
                room_config=room_config
            )
            html_filename = f"{room_name}.html"
            with open(os.path.join(output_dir, html_filename), "w") as f:
                f.write(html_content)
            visualization_links.append({'room_name': room_name, 'url': url_for('static_html', filename=html_filename)})

    # Create index page
    room_names_list = [link['room_name'] for link in visualization_links]
    if room_names_list:
        index_html_content = create_index_page(room_names_list, final_seating_layout, student_metadata)
        with open(os.path.join(output_dir, "index.html"), "w") as f:
            f.write(index_html_content)
        visualization_links.append({'room_name': 'Overall Dashboard', 'url': url_for('static_html', filename='index.html')})

    return render_template('seating_results.html', visualization_links=visualization_links)

@app.route('/static_html/<path:filename>')
def static_html(filename):
    return send_from_directory('visualizations', filename)

@app.route('/export_room_csv/<room_name>')
@require_teacher
def export_room_csv(room_name):
    final_seating_layout = session.get('final_seating_layout')
    student_metadata = session.get('student_metadata')

    if not final_seating_layout or not student_metadata:
        flash('No seating plan available to export.', 'danger')
        return redirect(url_for('view_seating_results'))

    room_seats = final_seating_layout.get(room_name)
    if not room_seats:
        flash(f'No seating information for {room_name}.', 'info')
        return redirect(url_for('view_seating_results'))

    room_data = []
    for seat in room_seats:
        student_id = seat['student_id']
        info = student_metadata.get(student_id, {})
        room_data.append({
            'StudentID': student_id,
            'Name': info.get('Name', 'Unknown'),
            'Department': info.get('Department', 'Unknown'),
            'Branch': info.get('Branch', 'Unknown'),
            'Year': info.get('Year', 'Unknown'),
            'Subject': info.get('Subject', 'Unknown'),
            'ExamDate': info.get('ExamDate', 'Unknown'),
            'ExamTime': info.get('ExamTime', 'Unknown'),
            'Room': room_name,
            'Seat_X': seat['x'],
            'Seat_Y': seat['y'],
            'Seat_No': seat['seat_no']
        })

    df = pd.DataFrame(room_data)
    exports_dir = 'exports'
    os.makedirs(exports_dir, exist_ok=True)
    csv_path = os.path.join(exports_dir, f"{room_name}_seating.csv")
    df.to_csv(csv_path, index=False)

    return send_from_directory(exports_dir, f"{room_name}_seating.csv", as_attachment=True)

@app.route('/get_student_details/<student_id>')
@require_login
def get_student_details(student_id):
    metadata = session.get('student_metadata')
    if not metadata:
        df = load_student_data()
        metadata = extract_student_metadata(df)
        session['student_metadata'] = metadata

    student_info = metadata.get(student_id)
    if student_info:
        return jsonify(student_info)
    return jsonify({'error': 'Student not found'}), 404

@app.route('/room_config/<room_id>', methods=['GET', 'POST'])
@require_admin
def room_config(room_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if request.method == 'POST':
        max_subjects = request.form.get('max_subjects', type=int)
        max_branches = request.form.get('max_branches', type=int)
        allowed_years = ','.join(request.form.getlist('allowed_years'))
        allowed_branches = ','.join(request.form.getlist('allowed_branches'))
        
        cursor.execute('''
            UPDATE room_configs
            SET max_subjects = ?, max_branches = ?, allowed_years = ?, allowed_branches = ?
            WHERE id = ?
        ''', (max_subjects, max_branches, allowed_years, allowed_branches, room_id))
        conn.commit()
        flash('Room constraints updated successfully', 'success')
    
    cursor.execute('SELECT * FROM room_configs WHERE id = ?', (room_id,))
    room = cursor.fetchone()
    conn.close()
    
    return render_template('room_config.html',
                         room=room,
                         year_options=range(1, 5),
                         branch_options=['CS', 'EE', 'ME', 'CE'])

@app.route('/api/room/constraints/<room_name>')
@require_admin
def get_room_constraints(room_name):
    """API endpoint for room constraints"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT max_subjects, max_branches, allowed_years, allowed_branches 
        FROM room_configs 
        WHERE room_name = ?
    ''', (room_name,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return jsonify({
            'max_subjects': result[0],
            'max_branches': result[1],
            'allowed_years': result[2].split(',') if result[2] else [],
            'allowed_branches': result[3].split(',') if result[3] else []
        })
    return jsonify({'error': 'Room not found'}), 404

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Initialize database
init_database()

if __name__ == '__main__':
    app.run(debug=True)