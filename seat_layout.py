from collections import defaultdict, deque
import random

def assign_seats_in_room(room_assignment, metadata, room_config):
    """Assign seats with year grouping and branch/subject distribution"""
    seating = {}
    
    for room, students in room_assignment.items():
        if not students:  # Skip empty rooms
            continue
            
        print(f"🪑 Assigning seats for {room} ({len(students)} students)")
        
        # Group students by year first
        year_groups = defaultdict(list)
        for sid in students:
            info = metadata.get(sid, {})
            year = info.get('Year', 'Unknown')
            year_groups[year].append(sid)
        
        print(f"   Year distribution: {dict((k, len(v)) for k, v in year_groups.items())}")
        
        # Create interleaved queue
        queue = interleave_groups(year_groups.values())
        
        # Get room layout configuration
        if isinstance(room_config, dict) and room in room_config:
            # New format: room_config[room_name] = room_dict
            layout_info = room_config[room]
            if 'layout_columns' in layout_info:
                cols = layout_info['layout_columns']
                rows = layout_info['layout_rows']
            else:
                cols = layout_info.get('columns', 6)
                rows = layout_info.get('rows', 5)
        else:
            # Fallback to default layout
            cols = 6
            rows = 5
        
        print(f"   Layout: {rows} rows × {cols} columns = {rows * cols} seats")
        
        # Generate seating coordinates
        seats = []
        for idx, student_id in enumerate(queue):
            if idx >= rows * cols:
                print(f"   ⚠️ Warning: Room capacity exceeded! Only placing first {rows * cols} students")
                break  # Room capacity exceeded
                
            x = idx % cols
            y = idx // cols
            student_info = metadata.get(student_id, {})
            
            seat_data = {
                'x': x,
                'y': y,
                'student_id': student_id,
                'seat_no': idx + 1,
                'Name': student_info.get('Name', 'Unknown'),
                'Department': student_info.get('Department', 'Unknown'),
                'Branch': student_info.get('Branch', 'Unknown'),
                'Year': student_info.get('Year', 'Unknown'),
                'Subject': student_info.get('Subject', 'Unknown'),
                'ExamTime': student_info.get('ExamTime', 'Unknown')
            }
            seats.append(seat_data)
        
        seating[room] = seats
        print(f"   ✅ Assigned {len(seats)} seats")
    
    return seating

def interleave_groups(groups):
    """Interleave students from different groups while maintaining year clusters"""
    # Filter out empty groups
    non_empty_groups = [group for group in groups if group]
    
    if not non_empty_groups:
        return []
    
    # Create queues from groups
    queues = [deque(group) for group in non_empty_groups]
    result = []
    
    # Round-robin through queues
    while any(queues):
        for q in queues:
            if q:
                result.append(q.popleft())
    
    # Add some randomization within the result to avoid too much clustering
    # But keep it minimal to maintain year grouping benefits
    return result