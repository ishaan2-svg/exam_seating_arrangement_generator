import pandas as pd
import os
import sqlite3
from conflict_graph import get_colored_groups, extract_student_metadata
from room_assignment import assign_rooms_to_groups
from seat_layout import assign_seats_in_room
from visualization import create_simple_html_visualization

def get_or_create_shared_totp_secret():
    """Get or create a shared TOTP secret for admin and teachers"""
    db_path = 'data/system.db'
    
    try:
        conn = sqlite3.connect(db_path)
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
            print(f"🔑 Using existing shared TOTP secret: {shared_secret}")
        else:
            # Generate new shared secret
            import pyotp
            shared_secret = pyotp.random_base32()
            cursor.execute('INSERT INTO system_config (key, value) VALUES (?, ?)', 
                          ('shared_totp_secret', shared_secret))
            conn.commit()
            print(f"🆕 Generated new shared TOTP secret: {shared_secret}")
            print(f"📱 Use this secret in Google Authenticator for admin/teacher 2FA")
        
        conn.close()
    except Exception as e:
        print(f"Error in get_or_create_shared_totp_secret: {e}")
        shared_secret = None
    return shared_secret
def get_rooms_config_from_db(db_path='data/system.db'):
    """Get room configurations from database"""
    try:
        conn = sqlite3.connect(db_path)
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
    except Exception as e:
        print(f"Error loading room config from database: {e}")
        # Fallback to default configuration
        return [
            {
                'room_name': 'Room-A',
                'capacity': 30,
                'allowed_years': [2, 3],
                'max_subjects': 15,
                'max_branches': 5,
                'layout_columns': 6,
                'layout_rows': 5
            },
            {
                'room_name': 'Room-B',
                'capacity': 40,
                'allowed_years': [2, 3],
                'max_subjects': 15,
                'max_branches': 5,
                'layout_columns': 8,
                'layout_rows': 5
            }
        ]

def init_database_if_needed():
    """Initialize database with default room configurations if needed"""
    db_path = 'data/system.db'
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Check if database exists and has room_configs table
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create room_configs table if it doesn't exist
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
        
        # Check if table is empty and populate with defaults
        cursor.execute('SELECT COUNT(*) FROM room_configs')
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("📦 Initializing database with default room configurations...")
            default_rooms = [
                ('Room-A', 30, 15, 5, '2,3', 'CS,EC,ME', 6, 5),
                ('Room-B', 40, 15, 5, '2,3', 'CS,EC,ME', 8, 5),
                ('Room-C', 25, 10, 3, '2,3,4', 'CS,EC', 5, 5)
            ]
            
            for room_data in default_rooms:
                cursor.execute('''
                    INSERT INTO room_configs 
                    (room_name, capacity, max_subjects, max_branches, allowed_years, allowed_branches, layout_columns, layout_rows)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', room_data)
            
            print(f"✅ Added {len(default_rooms)} default room configurations")
        
        conn.commit()
        conn.close()
        
        # Initialize/show shared TOTP secret
        print("\n🔐 Initializing security settings...")
        shared_secret = get_or_create_shared_totp_secret()
        if shared_secret:
            print(f"🔗 TOTP URI: otpauth://totp/ExamSeatingSystem:SharedAccount?secret={shared_secret}&issuer=ExamSeatingSystem")
            print("📋 Copy the secret above to Google Authenticator manually, or scan the QR code in the admin web panel")
        
    except Exception as e:
        print(f"⚠️ Error initializing database: {e}")
        print("Using fallback room configuration...")

# For backward compatibility, set ROOMS_CONFIG to load from database
def load_rooms_config():
    """Load room configurations with database initialization"""
    init_database_if_needed()
    return get_rooms_config_from_db()

ROOMS_CONFIG = load_rooms_config()

def create_index_page(room_names, final_layout, metadata, output_path="visualizations/index.html"):
    """Create a searchable dashboard of all students"""
    # Create a searchable database of all students
    student_database = []
    for room, seats in final_layout.items():
        for seat in seats:
            student_id = seat['student_id']
            info = metadata.get(student_id, {})
            student_database.append({
                'id': student_id,
                'name': info.get('Name', 'Unknown'),
                'branch': info.get('Branch', 'Unknown'),
                'subject': info.get('Subject', 'Unknown'),
                'room': room,
                'seat_no': seat['seat_no'],
                'year': info.get('Year', 'Unknown'),
                'department': info.get('Department', 'Unknown')
            })
    
    with open(output_path, "w") as f:
        f.write(f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Seating Dashboard</title>
  <style>
    body {{
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      margin: 0;
      background: #f9fafb;
      color: #111827;
    }}
    header {{
      background-color: #1f2937;
      color: white;
      padding: 2rem;
      text-align: center;
      font-size: 2rem;
    }}
    .container {{
      max-width: 1000px;
      margin: 2rem auto;
      padding: 1rem;
    }}
    .search-box {{
      margin-bottom: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}
    .search-filters {{
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
    }}
    input[type="text"], select {{
      padding: 0.75rem;
      font-size: 1rem;
      border-radius: 0.5rem;
      border: 1px solid #d1d5db;
      flex: 1;
      min-width: 200px;
    }}
    .results {{
      margin-top: 1rem;
    }}
    .result-item {{
      padding: 1rem;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 0.5rem;
      margin-bottom: 0.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .student-info {{
      flex: 1;
    }}
    .student-info h3 {{
      margin: 0 0 0.5rem 0;
      color: #1f2937;
    }}
    .student-details {{
      color: #6b7280;
      font-size: 0.9rem;
    }}
    .room-actions {{
        display: flex;
        gap: 0.5rem;
    }}
    .room-link {{
      text-decoration: none;
      color: #2563eb;
      font-weight: 600;
      padding: 0.5rem 1rem;
      background: #eff6ff;
      border-radius: 0.25rem;
      border: 1px solid #2563eb;
      transition: all 0.2s;
      white-space: nowrap;
    }}
    .room-link:hover {{
      background: #2563eb;
      color: white;
    }}
    .no-results {{
      text-align: center;
      color: #6b7280;
      font-style: italic;
      padding: 2rem;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .stat-card {{
      background: white;
      padding: 1rem;
      border-radius: 0.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
      text-align: center;
    }}
    .stat-number {{
      font-size: 2rem;
      font-weight: bold;
      color: #2563eb;
    }}
    .stat-label {{
      color: #6b7280;
      font-size: 0.9rem;
    }}
  </style>
</head>
<body>
  <header>
    🎓 Exam Seating Dashboard
  </header>
  <div class="container">
    <div class="stats">
      <div class="stat-card">
        <div class="stat-number">{len(student_database)}</div>
        <div class="stat-label">Total Students</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{len(room_names)}</div>
        <div class="stat-label">Active Rooms</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{len(set([s['subject'] for s in student_database]))}</div>
        <div class="stat-label">Subjects</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{len(set([s['branch'] for s in student_database]))}</div>
        <div class="stat-label">Branches</div>
      </div>
    </div>
    
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="Search by student name, ID, branch, subject, or room...">
      <div class="search-filters">
        <select id="roomSelect">
          <option value="">All Rooms</option>""")
        
        for room in room_names:
            f.write(f'          <option value="{room}">{room}</option>\n')
        
        f.write("""        </select>
        <select id="branchSelect">
          <option value="">All Branches</option>""")
        
        branches = sorted(set([s['branch'] for s in student_database if s['branch'] != 'Unknown']))
        for branch in branches:
            f.write(f'          <option value="{branch}">{branch}</option>\n')
        
        f.write("""        </select>
        <select id="subjectSelect">
          <option value="">All Subjects</option>""")
        
        subjects = sorted(set([s['subject'] for s in student_database if s['subject'] != 'Unknown']))
        for subject in subjects:
            f.write(f'          <option value="{subject}">{subject}</option>\n')
        
        f.write(f"""        </select>
      </div>
    </div>
    <div class="results" id="results"></div>
  </div>
  <script>
    const students = {str(student_database).replace("'", '"')};
    const rooms = [""")
        
        for room in room_names:
            f.write(f"      {{ name: '{room}', html_url: '{room}.html?teacher=1' }},\n")
        
        f.write("""
    ];

    document.getElementById("searchInput").addEventListener("input", updateResults);
    document.getElementById("roomSelect").addEventListener("change", updateResults);
    document.getElementById("branchSelect").addEventListener("change", updateResults);
    document.getElementById("subjectSelect").addEventListener("change", updateResults);

    function updateResults() {
      const query = document.getElementById("searchInput").value.toLowerCase();
      const selectedRoom = document.getElementById("roomSelect").value;
      const selectedBranch = document.getElementById("branchSelect").value;
      const selectedSubject = document.getElementById("subjectSelect").value;
      
      let filtered = students;
      
      // Apply room filter first if a room is selected
      if (selectedRoom) {
        filtered = filtered.filter(student => student.room === selectedRoom);
      } else {
        // If no room is selected, clear results unless a search query is present
        // This makes sure the list is empty by default
        if (!query && !selectedBranch && !selectedSubject) {
            document.getElementById("results").innerHTML = '<div class="no-results">Please select a room or enter a search query to find students.</div>';
            return;
        }
      }

      if (query) {
        filtered = filtered.filter(student => 
          student.name.toLowerCase().includes(query) ||
          student.id.toLowerCase().includes(query) ||
          student.branch.toLowerCase().includes(query) ||
          student.subject.toLowerCase().includes(query) ||
          student.room.toLowerCase().includes(query) ||
          student.department.toLowerCase().includes(query)
        );
      }
      
      // Apply other filters only if a room is selected or if there's a search query
      if (selectedBranch) {
        filtered = filtered.filter(student => student.branch === selectedBranch);
      }
      
      if (selectedSubject) {
        filtered = filtered.filter(student => student.subject === selectedSubject);
      }

      const resultsDiv = document.getElementById("results");
      resultsDiv.innerHTML = '';

      if (filtered.length === 0) {
        resultsDiv.innerHTML = '<div class="no-results">No students found matching your search criteria.</div>';
        return;
      }

      filtered.forEach(student => {
        const div = document.createElement("div");
        div.className = "result-item";
        div.innerHTML = `
          <div class="student-info">
            <h3>${{student.name}} (${{student.id}})</h3>
            <div class="student-details">
              ${{student.branch}} • ${{student.subject}} • Seat #${{student.seat_no}} • Year ${{student.year}}
            </div>
          </div>
          <div class="room-actions">
            <a href="${{student.room}}.html?teacher=1&highlight=${{student.id}}" class="room-link">View Room</a>
          </div>
        `;
        resultsDiv.appendChild(div);
      }});
    }}

    // Initial load: no results by default until a room is selected or search initiated
    document.addEventListener('DOMContentLoaded', () => {{
        document.getElementById("results").innerHTML = '<div class="no-results">Please select a room or enter a search query to find students.</div>';
    }});
  </script>
</body>
</html>
""")

def main():
    INPUT_FILE = 'data/students.csv'

    print("📚 Starting Exam Seating Arrangement System...\n")

    # Create output directories
    os.makedirs('visualizations', exist_ok=True)
    os.makedirs('exports', exist_ok=True)
    os.makedirs('data', exist_ok=True)

    # Check if input file exists
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: {INPUT_FILE} not found!")
        print("Creating a sample CSV file for you...")
        
        # Create sample data
        sample_data = {
            'StudentID': ['1001', '1002', '1003', '1004', '1005', '1006', '1007', '1008', '1009', '1010'],
            'Name': ['Alice Smith', 'Bob Johnson', 'Charlie Brown', 'Diana Prince', 'Eve Adams', 
                    'Frank White', 'Grace Lee', 'Harry Kim', 'Ivy Green', 'Jack Black'],
            'Department': ['CSE', 'ECE', 'ME', 'CSE', 'ECE', 'ME', 'CSE', 'ECE', 'ME', 'CSE'],
            'Branch': ['CS', 'EC', 'ME', 'CS', 'EC', 'ME', 'CS', 'EC', 'ME', 'CS'],
            'Batch': ['2022', '2022', '2022', '2023', '2023', '2023', '2022', '2022', '2023', '2023'],
            'Year': [2, 2, 2, 3, 3, 3, 2, 2, 3, 3],
            'Semester': [4, 4, 4, 6, 6, 6, 4, 4, 6, 6],
            'Subject': ['DSA', 'VLSI', 'Thermodynamics', 'AI', 'DSP', 'Fluid Mech', 'OS', 'Signals', 'Robotics', 'Networks'],
            'ExamDate': ['2025-06-01', '2025-06-01', '2025-06-02', '2025-06-02', '2025-06-03', 
                        '2025-06-03', '2025-06-01', '2025-06-01', '2025-06-02', '2025-06-02'],
            'ExamTime': ['Morning', 'Morning', 'Afternoon', 'Afternoon', 'Morning', 
                        'Morning', 'Afternoon', 'Afternoon', 'Morning', 'Morning'],
            'PhotoPath': [f'/static/uploads/student_{i}.jpg' for i in range(1, 11)],
            'Gender': ['F', 'M', 'M', 'F', 'F', 'M', 'F', 'M', 'F', 'M']
        }
        
        sample_df = pd.DataFrame(sample_data)
        sample_df.to_csv(INPUT_FILE, index=False)
        print(f"✅ Created sample data file: {INPUT_FILE}")
        print("You can now edit this file with your actual student data and run the script again.")
        return

    # Step 1: Load CSV data first
    print("🔍 Loading student data...")
    try:
        # Load the CSV file into a DataFrame
        df_students = pd.read_csv(INPUT_FILE)
        print(f"✅ Loaded {len(df_students)} student records from {INPUT_FILE}")
        
        # Validate and map columns
        print("🔍 Validating CSV structure...")
        required_columns = ['StudentID', 'Name', 'Department', 'Year', 'Subject', 'ExamDate', 'ExamTime']
        
        # Check for required columns
        missing_columns = [col for col in required_columns if col not in df_students.columns]
        
        if missing_columns:
            print(f"❌ Error: Missing required columns: {missing_columns}")
            print(f"Required columns: {required_columns}")
            print(f"Found columns: {list(df_students.columns)}")
            return
        
        # Handle column mapping - your CSV uses 'Batch' instead of 'Branch'
        if 'Branch' not in df_students.columns and 'Batch' in df_students.columns:
            print("📝 Mapping 'Batch' column to 'Branch' for compatibility...")
            df_students['Branch'] = df_students['Batch']
        
        # Add missing optional columns with default values if they don't exist
        optional_columns = {
            'PhotoPath': '/static/uploads/default.jpg',
            'Gender': 'U',  # Unknown
            'Semester': df_students.get('Semester', df_students.get('Year', 1) * 2)  # Estimate semester from year
        }
        
        for col, default_value in optional_columns.items():
            if col not in df_students.columns:
                df_students[col] = default_value
        
        print(f"✅ CSV validation complete. Processed {len(df_students)} students")
        
        # Extract metadata and get conflict groups
        print("🔍 Detecting conflicts and extracting metadata...")
        
        # Try with DataFrame first, if that fails, try with file path
        try:
            metadata = extract_student_metadata(df_students)
            groups = get_colored_groups(df_students)
        except (AttributeError, TypeError) as e:
            print("🔄 Trying with file path instead of DataFrame...")
            metadata = extract_student_metadata(INPUT_FILE)
            groups = get_colored_groups(INPUT_FILE)
        
    except FileNotFoundError:
        print(f"❌ Error: File {INPUT_FILE} not found!")
        return
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        print(f"Please check that {INPUT_FILE} exists and has the correct format.")
        print(f"Available columns in your CSV: {list(pd.read_csv(INPUT_FILE).columns) if os.path.exists(INPUT_FILE) else 'File not readable'}")
        return

    print("\n🧮 Summary of groups and room capacities:")
    total_students = 0
    for key, group in groups.items():
        print(f"Group {key}: {len(group)} students")
        total_students += len(group)
    
    print(f"\n📊 Total students: {total_students}")
    
    # Load dynamic room configuration from database
    print("🏗️ Loading room configurations from database...")
    current_rooms_config = get_rooms_config_from_db()
    
    print("\n🏠 Available rooms:")
    total_capacity = 0
    for room in current_rooms_config:
        print(f"  {room['room_name']}: {room['capacity']} seats (Years: {room['allowed_years']}, Layout: {room['layout_columns']}×{room['layout_rows']})")
        total_capacity += room['capacity']
    print(f"📊 Total capacity: {total_capacity}")

    if total_students > total_capacity:
        print(f"⚠️ Warning: Total students ({total_students}) exceed room capacity ({total_capacity})")
        print("💡 Consider adding more rooms or increasing existing room capacities via admin panel")

    # Step 2: Assign rooms with constraint checking
    print("\n🏫 Assigning groups to classrooms...")
    try:
        room_assignment = assign_rooms_to_groups(
            groups=groups,
            student_metadata=metadata,
            rooms_config=current_rooms_config
        )
        
        print("\n✅ Room assignment successful!")
        for room, students in room_assignment.items():
            if students:
                print(f"  {room}: {len(students)} students assigned")
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("\n💡 Suggestions to fix:")
        print("1. Use admin panel to increase room capacities")
        print("2. Use admin panel to increase max_subjects or max_branches limits")
        print("3. Use admin panel to add more rooms")
        print("4. Check if year/branch constraints are too restrictive in admin panel")
        return
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return

    # Step 3: Create seat layout
    print("\n💺 Generating seat numbers...")
    try:
        room_config_dict = {room['room_name']: room for room in current_rooms_config}
        final_layout = assign_seats_in_room(
            room_assignment=room_assignment,
            metadata=metadata,
            room_config=room_config_dict
        )
    except Exception as e:
        print(f"❌ Error in seat assignment: {e}")
        return

    # Step 4: Export CSV files
    print("\n📊 Exporting room data to CSV...")
    for room, seats in final_layout.items():
        if not seats:
            continue
            
        room_data = []
        for seat in seats:
            student_id = seat['student_id']
            info = metadata.get(student_id, {})
            room_data.append({
                'SeatNo': seat['seat_no'],
                'StudentID': student_id,
                'Name': info.get('Name', 'Unknown'),
                'Department': info.get('Department', 'Unknown'),
                'Branch': info.get('Branch', 'Unknown'),
                'Batch': info.get('Batch', 'Unknown'),
                'Year': info.get('Year', 'Unknown'),
                'Semester': info.get('Semester', 'Unknown'),
                'Subject': info.get('Subject', 'Unknown'),
                'ExamDate': info.get('ExamDate', 'Unknown'),
                'ExamTime': info.get('ExamTime', 'Unknown'),
                'Room': room,
                'Position_X': seat['x'],
                'Position_Y': seat['y']
            })
        
        if room_data:
            df = pd.DataFrame(room_data)
            csv_path = f"exports/{room}_seating.csv"
            df.to_csv(csv_path, index=False)
            print(f"  ✅ {room}: {len(room_data)} students exported to {csv_path}")

    # Step 5: Create visualizations
    print("\n🎨 Generating interactive classroom maps...")
    room_names = []
    for room, seats in final_layout.items():
        if not seats:
            continue
        try:
            room_config = next(rc for rc in current_rooms_config if rc['room_name'] == room)
            html_content = create_simple_html_visualization(
                room_name=room,
                seating_arrangement=seats,
                metadata=metadata,
                room_config=room_config
            )
            with open(f"visualizations/{room}.html", "w") as f:
                f.write(html_content)
            print(f"  ✅ {room}: HTML saved to visualizations/{room}.html")
            room_names.append(room)
        except Exception as e:
            print(f"❌ Error creating visualization for {room}: {e}")

    if room_names:
        create_index_page(room_names, final_layout, metadata)
        print(f"📁 Interactive layouts: visualizations/index.html")

    print("\n✅ Success!")
    print(f"📁 Room data exports: exports/ folder")
    print(f"📊 Check the CSV files for detailed seating arrangements")
    print(f"🌐 View interactive layouts in visualizations/ folder")
    print(f"⚙️ Manage room configurations via admin web panel")

def reload_rooms_config():
    """Reload room configurations from database (for use by Flask app)"""
    global ROOMS_CONFIG
    ROOMS_CONFIG = get_rooms_config_from_db()
    return ROOMS_CONFIG

def run_seating_pipeline():
    main()

if __name__ == '__main__':
    main()