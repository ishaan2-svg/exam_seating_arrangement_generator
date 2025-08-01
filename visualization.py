import html

def create_simple_html_visualization(room_name, seating_arrangement, metadata, room_config):
    departments = list(set([v.get('Department', 'Unknown') for v in metadata.values()]))
    years = sorted(set([v.get('Year', '') for v in metadata.values() if 'Year' in v]))
    branches = sorted(set([v.get('Branch', '') for v in metadata.values() if 'Branch' in v]))

    colors = ['#636efa', '#ef553b', '#00cc96', '#ab63fa', '#ffa15a',
              '#19d3f3', '#ff6692', '#b6e880', '#ff97ff', '#fecb52']
    dept_colors = {dept: colors[i % len(colors)] for i, dept in enumerate(departments)}

    time_symbols = {'Morning': '☀️', 'Afternoon': '⛅', 'Evening': '🌙'}

    max_x = max([seat['x'] for seat in seating_arrangement]) if seating_arrangement else 0
    max_y = max([seat['y'] for seat in seating_arrangement]) if seating_arrangement else 0

    grid = {(seat['x'], seat['y']): seat for seat in seating_arrangement}

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{room_name} Seating Chart</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background-color: #f8fafc; 
            padding: 20px; 
            margin: 0;
        }}
        h1, h3 {{ 
            text-align: center; 
            color: #1e293b;
        }}
        .header-controls {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 20px 0;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .mode-toggle, .download-pdf-button {{
            background: #3b82f6;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
            text-decoration: none; /* For download PDF button */
            display: inline-block; /* For download PDF button */
        }}
        .mode-toggle:hover, .download-pdf-button:hover {{
            background: #2563eb;
        }}
        .mode-toggle.active {{
            background: #ef4444;
        }}
        .download-pdf-button {{
            background: #ef4444; /* Red color for PDF */
        }}
        .download-pdf-button:hover {{
            background: #dc2626; /* Darker red on hover */
        }}
        .grid {{
            display: grid; 
            grid-template-columns: repeat({int(max_x) + 1}, 120px);
            gap: 15px; 
            margin: 20px auto; 
            max-width: {(int(max_x) + 1) * 135}px;
        }}
        .seat {{
            position: relative;
            width: 120px; 
            height: 120px; 
            background: white; 
            border-radius: 15px;
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center;
            text-align: center; 
            border: 2px solid #cbd5e1; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            transition: all 0.3s ease;
            cursor: pointer;
        }}
        .seat:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.1);
        }}
        .seat.selected {{
            border-color: #ef4444;
            background: #fef2f2;
            box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.2);
        }}
        .seat.swap-mode {{
            cursor: pointer;
        }}
        .seat.swap-mode:hover {{
            border-color: #3b82f6;
            background: #eff6ff;
        }}
        .seat-number {{ 
            position: absolute; 
            top: 8px; 
            left: 8px; 
            font-size: 11px; 
            font-weight: 600;
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            color: #64748b;
        }}
        .student-info {{ 
            font-size: 13px; 
            padding: 5px; 
            line-height: 1.3;
        }}
        .student-info strong {{
            color: #1e293b;
        }}
        .student-info small {{
            color: #64748b;
        }}
        .tooltip {{
            visibility: hidden;
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
            color: white;
            text-align: left;
            border-radius: 12px;
            padding: 12px;
            position: absolute;
            z-index: 9999; /* Increased z-index */
            top: auto; /* Changed from bottom */
            bottom: 100%; /* Position above the seat */
            margin-bottom: 10px; /* Space between seat and tooltip */
            left: 50%;
            transform: translateX(-50%);
            width: 220px;
            font-size: 12px;
            white-space: pre-line;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }}
        .tooltip::before {{
            content: '';
            position: absolute;
            bottom: -8px; /* Changed from top */
            left: 50%;
            transform: translateX(-50%);
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-top: 8px solid #1e293b; /* Changed from border-bottom */
        }}
        .seat:hover .tooltip {{
            visibility: visible;
        }}
        .filter-controls {{
            display: flex; 
            justify-content: center; 
            gap: 15px; 
            flex-wrap: wrap; 
            margin-bottom: 20px;
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        select, input[type="text"] {{
            padding: 10px 15px; 
            border-radius: 8px; 
            border: 1px solid #d1d5db;
            font-size: 14px;
            transition: border-color 0.2s;
        }}
        select:focus, input[type="text"]:focus {{
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }}
        .legend {{
            display: flex; 
            justify-content: center; 
            flex-wrap: wrap; 
            gap: 15px; 
            margin: 20px 0;
            background: white;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }}
        .legend-color {{ 
            width: 20px; 
            height: 20px; 
            border-radius: 50%; 
            display: inline-block; 
        }}
        .constraint-display {{
            margin: 20px 0; 
            text-align: center;
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .constraint-grid {{
            display: flex; 
            justify-content: center; 
            gap: 30px; 
            margin-top: 10px;
            flex-wrap: wrap;
        }}
        .constraint-item {{
            background: #f8fafc;
            padding: 10px 15px;
            border-radius: 8px;
            font-weight: 500;
            color: #475569;
        }}
        .swap-status {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: #3b82f6;
            color: white;
            padding: 15px 20px;
            border-radius: 12px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            display: none;
            z-index: 1001;
        }}
        .swap-status.active {{
            display: block;
        }}
        .swap-status.selecting {{
            background: #f59e0b;
        }}
        @media (max-width: 768px) {{
            .grid {{
                grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
                max-width: 100%;
            }}
            .seat {{
                width: 100px;
                height: 100px;
            }}
        }}
    </style>
</head>
<body>
    <h1>{room_name} Seating Arrangement</h1>

    <div class="header-controls">
        <button class="mode-toggle" id="modeToggle" onclick="toggleSwapMode()">
            🔄 Enable Swap Mode
        </button>
        <div class="swap-status" id="swapStatus">
            Click on two seats to swap their positions
        </div>
    </div>

    <div class="constraint-display">
        <h3>Room Constraints</h3>
        <div class="constraint-grid">
            <div class="constraint-item">Max Subjects: {room_config['max_subjects']}</div>
            <div class="constraint-item">Max Branches: {room_config['max_branches']}</div>
            <div class="constraint-item">Allowed Years: {', '.join(map(str, room_config['allowed_years']))}</div>
        </div>
    </div>

    <div class="filter-controls">
        <input type="text" id="searchInput" placeholder="🔍 Search by ID or Name...">
        <select id="timeFilter">
            <option value="">All Times</option>
            <option value="Morning">Morning ☀️</option>
            <option value="Afternoon">Afternoon ⛅</option>
            <option value="Evening">Evening 🌙</option>
        </select>
        <select id="yearFilter">
            <option value="all">All Years</option>
            {''.join([f'<option value="{y}">{y}</option>' for y in map(str, years)])}
        </select>
        <select id="branchFilter">
            <option value="all">All Branches</option>
            {''.join([f'<option value="{b}">{b}</option>' for b in branches])}
        </select>
    </div>

    <div class="legend">
        {''.join([f'<div class="legend-item"><span class="legend-color" style="background:{dept_colors[d]};"></span><span>{d}</span></div>' for d in dept_colors])}
    </div>

    <div class="grid" id="seatingGrid">
"""
    
    for y in range(int(max_y) + 1):
        for x in range(int(max_x) + 1):
            seat = grid.get((x, y))
            if seat:
                student_id = seat['student_id']
                info = metadata.get(student_id, {})
                name = html.escape(info.get('Name', f"Student-{student_id}"))
                dept = html.escape(info.get('Department', 'Unknown'))
                subject = html.escape(info.get('Subject', 'Unknown'))
                exam_time = info.get('ExamTime', 'Morning')
                year = info.get('Year', '')
                branch = info.get('Branch', '')
                color = dept_colors.get(dept, '#cbd5e1')
                symbol = time_symbols.get(exam_time, '☀️')

                tooltip = f"Name: {name}\\nSubject: {subject}\\nTime: {exam_time}\\nDept: {dept}\\nYear: {year}\\nBranch: {branch}"
                html_content += f"""
                <div class="seat" style="border-color: {color};"
                    data-year="{str(year)}" data-branch="{branch}" data-subject="{subject}"
                    data-id="{student_id}" data-name="{name.lower()}" data-time="{exam_time}"
                    data-seat-no="{seat['seat_no']}" data-position="{x},{y}"
                    onclick="handleSeatClick(this)">
                    <div class="seat-number">#{seat['seat_no']}</div>
                    <div>{symbol}</div>
                    <div class="student-info">
                        <strong>{student_id}</strong><br>{name}<br><small>{subject}</small>
                    </div>
                    <div class="tooltip">{tooltip}</div>
                </div>
                """
            else:
                html_content += '<div></div>'

    html_content += """
    </div>

    <script>
    let swapMode = false;
    let selectedSeats = [];
    
    function isTeacherMode() {
        return new URLSearchParams(window.location.search).get("teacher") === "1";
    }
    
    function getHighlightedStudent() {
        return new URLSearchParams(window.location.search).get("highlight");
    }
    
    function toggleSwapMode() {
        swapMode = !swapMode;
        const button = document.getElementById('modeToggle');
        const status = document.getElementById('swapStatus');
        const grid = document.getElementById('seatingGrid');
        
        if (swapMode) {
            button.textContent = '❌ Exit Swap Mode';
            button.classList.add('active');
            status.classList.add('active');
            grid.classList.add('swap-mode');
        } else {
            button.textContent = '🔄 Enable Swap Mode';
            button.classList.remove('active');
            status.classList.remove('active');
            grid.classList.remove('swap-mode');
            clearSelection();
        }
    }
    
    function clearSelection() {
        selectedSeats = [];
        document.querySelectorAll('.seat.selected').forEach(seat => {
            seat.classList.remove('selected');
        });
        updateSwapStatus();
    }
    
    function updateSwapStatus() {
        const status = document.getElementById('swapStatus');
        if (selectedSeats.length === 0) {
            status.textContent = 'Click on two seats to swap their positions';
            status.classList.remove('selecting');
        } else if (selectedSeats.length === 1) {
            const seatInfo = selectedSeats[0].dataset.id;
            status.textContent = `Selected: ${seatInfo} - Click another seat to swap`;
            status.classList.add('selecting');
        }
    }
    
    function handleSeatClick(seatElement) {
        if (!swapMode) return;
        
        if (seatElement.classList.contains('selected')) {
            // Deselect if already selected
            seatElement.classList.remove('selected');
            selectedSeats = selectedSeats.filter(seat => seat !== seatElement);
        } else {
            // Select seat
            if (selectedSeats.length < 2) {
                seatElement.classList.add('selected');
                selectedSeats.push(seatElement);
            }
        }
        
        // If two seats are selected, perform swap
        if (selectedSeats.length === 2) {
            performSwap(selectedSeats[0], selectedSeats[1]);
        }
        
        updateSwapStatus();
    }
    
    function performSwap(seat1, seat2) {
        const student1 = {
            id: seat1.dataset.id,
            name: seat1.dataset.name,
            seatNo: seat1.dataset.seatNo
        };
        const student2 = {
            id: seat2.dataset.id,
            name: seat2.dataset.name,
            seatNo: seat2.dataset.seatNo
        };
        
        if (confirm(`Swap positions of ${student1.id} (Seat #${student1.seatNo}) and ${student2.id} (Seat #${student2.seatNo})?`)) {
            // Swap the visual content
            swapSeatContent(seat1, seat2);
            
            // Show success message
            const status = document.getElementById('swapStatus');
            status.textContent = `✅ Swapped ${student1.id} ↔ ${student2.id}`;
            status.style.background = '#10b981';
            
            setTimeout(() => {
                status.style.background = '#3b82f6';
                updateSwapStatus();
            }, 2000);
        }
        
        clearSelection();
    }
    
    function swapSeatContent(seat1, seat2) {
        // Store all the data attributes and content
        const seat1Data = {
            id: seat1.dataset.id,
            name: seat1.dataset.name,
            year: seat1.dataset.year,
            branch: seat1.dataset.branch,
            subject: seat1.dataset.subject,
            time: seat1.dataset.time,
            innerHTML: seat1.innerHTML
        };
        
        const seat2Data = {
            id: seat2.dataset.id,
            name: seat2.dataset.name,
            year: seat2.dataset.year,
            branch: seat2.dataset.branch,
            subject: seat2.dataset.subject,
            time: seat2.dataset.time,
            innerHTML: seat2.innerHTML
        };
        
        // Swap data attributes
        seat1.dataset.id = seat2Data.id;
        seat1.dataset.name = seat2Data.name;
        seat1.dataset.year = seat2Data.year;
        seat1.dataset.branch = seat2Data.branch;
        seat1.dataset.subject = seat2Data.subject;
        seat1.dataset.time = seat2Data.time;
        
        seat2.dataset.id = seat1Data.id;
        seat2.dataset.name = seat1Data.name;
        seat2.dataset.year = seat1Data.year;
        seat2.dataset.branch = seat1Data.branch;
        seat2.dataset.subject = seat1Data.subject;
        seat2.dataset.time = seat1Data.time;
        
        // Swap visual content (but keep seat numbers)
        const seat1SeatNo = seat1.querySelector('.seat-number').textContent;
        const seat2SeatNo = seat2.querySelector('.seat-number').textContent;
        
        seat1.innerHTML = seat2Data.innerHTML;
        seat2.innerHTML = seat1Data.innerHTML;
        
        // Restore original seat numbers
        seat1.querySelector('.seat-number').textContent = seat1SeatNo;
        seat2.querySelector('.seat-number').textContent = seat2SeatNo;
    }

    function filterSeats() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const time = document.getElementById('timeFilter').value;
        const year = document.getElementById('yearFilter').value;
        const branch = document.getElementById('branchFilter').value;

        document.querySelectorAll('.seat').forEach(seat => {
            if (!seat.dataset.id) return; // Skip empty seats
            
            const id = seat.dataset.id.toLowerCase();
            const name = seat.dataset.name.toLowerCase();
            const seatTime = seat.dataset.time;
            const seatYear = seat.dataset.year;
            const seatBranch = seat.dataset.branch;

            const matchesSearch = id.includes(searchTerm) || name.includes(searchTerm);
            const matchesTime = !time || seatTime === time;
            const matchesYear = year === "all" || seatYear === year;
            const matchesBranch = branch === "all" || seatBranch === branch;

            if (matchesSearch && matchesTime && matchesYear && matchesBranch) {
                seat.style.opacity = '1';
                seat.style.filter = 'none';
            } else {
                seat.style.opacity = '0.3';
                seat.style.filter = 'grayscale(100%)';
            }
        });
    }

    // Event listeners
    document.getElementById('searchInput').addEventListener('input', filterSeats);
    document.getElementById('timeFilter').addEventListener('change', filterSeats);
    document.getElementById('yearFilter').addEventListener('change', filterSeats);
    document.getElementById('branchFilter').addEventListener('change', filterSeats);

    // Initialize
    window.addEventListener('load', function() {
        // Show swap mode controls only for teachers
        if (isTeacherMode()) {
            document.getElementById('modeToggle').style.display = 'block';
        } else {
            document.getElementById('modeToggle').style.display = 'none';
        }
        
        // Highlight specific student if requested
        const highlightId = getHighlightedStudent();
        if (highlightId) {
            const targetSeat = document.querySelector(`[data-id="${highlightId}"]`);
            if (targetSeat) {
                targetSeat.style.border = '3px solid #f59e0b';
                targetSeat.style.boxShadow = '0 0 0 5px rgba(245, 158, 11, 0.3)';
                targetSeat.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    });
    </script>
</body>
</html>
"""
    return html_content