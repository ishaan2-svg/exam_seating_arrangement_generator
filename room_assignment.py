from collections import defaultdict, Counter
from typing import List, Dict

class Student:
    def __init__(self, student_id: str, metadata: dict):
        self.id = student_id
        self.year = int(metadata.get('Year'))
        self.subject = metadata.get('Subject')
        self.department = metadata.get('Department')
        self.branch = metadata.get('Branch', metadata.get('Batch', 'Unknown'))
        self.batch = metadata.get('Batch', 'Unknown')

class RoomConfig:
    def __init__(self, config: dict):
        self.room_id = config['room_name']
        self.capacity = config['capacity']
        self.max_subjects = config['max_subjects']
        self.max_branches = config['max_branches']
        if isinstance(config['allowed_years'], str):
            self.allowed_years = set(map(int, config['allowed_years'].split(',')))
        elif isinstance(config['allowed_years'], list):
            # Handle both string and int lists
            self.allowed_years = set(int(year) if isinstance(year, str) else year for year in config['allowed_years'])
        else:
            self.allowed_years = set(config['allowed_years'])

def assign_rooms_to_groups(
    groups: Dict[int, List[str]],
    student_metadata: Dict[str, dict],
    rooms_config: List[dict]
) -> Dict[str, List[str]]:
    """
    Main entry point for room assignment
    Args:
        groups: Dictionary of colored groups {color: [student_ids]}
        student_metadata: Dictionary of student metadata {student_id: info}
        rooms_config: List of room configuration dictionaries
    Returns:
        Dictionary of {room_id: [student_ids]}
    """
    # Convert rooms config to RoomConfig objects
    room_objects = [RoomConfig(rc) for rc in rooms_config]
    
    # Convert student groups to Student objects
    student_groups = defaultdict(list)
    for color, student_ids in groups.items():
        student_groups[color] = [
            Student(sid, student_metadata[sid]) for sid in student_ids
        ]
    
    print("\n🔍 Group Analysis:")
    total_students = 0
    for color, students in student_groups.items():
        subjects = len({s.subject for s in students})
        branches = len({s.branch for s in students})
        years = {s.year for s in students}
        total_students += len(students)
        print(f"Group {color}: {len(students)} students | Years: {sorted(years)} | Subjects: {subjects} | Branches: {branches}")
    
    print(f"\n📊 Total students to assign: {total_students}")
    total_capacity = sum(room.capacity for room in room_objects)
    print(f"📊 Total room capacity: {total_capacity}")
    
    if total_students > total_capacity:
        raise ValueError(f"Not enough room capacity! Need {total_students} seats, have {total_capacity}")
    
    # Try modified FFD first
    print("\n🎯 Trying First-Fit Decreasing algorithm...")
    ffd_result = first_fit_decreasing(student_groups, room_objects)
    if ffd_result is not None: # Check for None to handle potential failure of FFD
        print("✅ FFD successful!")
        return ffd_result
    
    # Fallback to backtracking
    print("❌ FFD failed, trying backtracking algorithm...")
    try:
        bt_result = backtracking_assign(student_groups, room_objects)
        print("✅ Backtracking successful!")
        return bt_result
    except ValueError as e:
        print(f"❌ Backtracking also failed: {e}")
        raise

def first_fit_decreasing(
    groups: Dict[int, List[Student]],
    rooms: List[RoomConfig]
) -> Dict[str, List[str]]:
    """Modified First-Fit Decreasing algorithm with flexible constraints"""
    sorted_groups = sorted(groups.values(), key=lambda x: len(x), reverse=True)
    assignments = defaultdict(list)
    room_status = {
        room.room_id: {
            'remaining_capacity': room.capacity,
            'subjects': set(),
            'branches': set(),
            'years': set(),
            'students': []
        } for room in rooms
    }

    print(f"🔄 Processing {len(sorted_groups)} groups...")
    
    all_groups_placed_successfully = True # Flag to track overall success of FFD

    for i, group in enumerate(sorted_groups):
        placed_current_group = False # Renamed 'placed' to be more specific
        group_years = {s.year for s in group}
        group_subjects = {s.subject for s in group}
        group_branches = {s.branch for s in group}
        print(f" 📦 Group {i}: {len(group)} students, Years: {sorted(group_years)}, Subjects: {len(group_subjects)}, Branches: {len(group_branches)}")

        # Try each room, sorted by remaining capacity (prefer less full rooms)
        sorted_rooms = sorted(rooms, key=lambda x: room_status[x.room_id]['remaining_capacity'], reverse=True)
        
        for room in sorted_rooms:
            status = room_status[room.room_id]

            # Check capacity
            if len(group) > status['remaining_capacity']:
                continue

            # Check year constraints
            if not group_years.issubset(room.allowed_years):
                continue
            
            # Check subject constraints
            if room.max_subjects > 0 and len(status['subjects'].union(group_subjects)) > room.max_subjects:
                continue

            # Check branch constraints
            if room.max_branches > 0 and len(status['branches'].union(group_branches)) > room.max_branches:
                continue

            # If all constraints met, assign students to this room
            status['remaining_capacity'] -= len(group)
            status['subjects'].update(group_subjects)
            status['branches'].update(group_branches)
            status['years'].update(group_years)
            assignments[room.room_id].extend([s.id for s in group])
            status['students'].extend([s.id for s in group])
            placed_current_group = True
            print(f" ✅ Placed group in {room.room_id}. Remaining capacity: {status['remaining_capacity']}")
            # IMPORTANT: Ensure no 'return room.room_id' or similar is here.
            break # Exit inner loop, move to next group

        if not placed_current_group:
            print(f" ⚠️ Could not place group of {len(group)} students. No suitable room found.")
            all_groups_placed_successfully = False # Mark overall FFD as failed
            break # Exit outer loop if a group cannot be placed
    
    if not all_groups_placed_successfully:
        return None # Return None if FFD failed for any group
    
    # If all groups were placed successfully, return the accumulated assignments
    final_assignments = {rid: s_ids for rid, s_ids in assignments.items() if s_ids}
    return final_assignments

def backtracking_assign(
    groups: Dict[int, List[Student]],
    rooms: List[RoomConfig]
) -> Dict[str, List[str]]:
    """Backtracking algorithm for room assignment with flexible constraints."""
    sorted_groups = sorted(groups.values(), key=lambda x: len(x), reverse=True)
    room_assignments = defaultdict(list)
    room_status = {
        room.room_id: {
            'remaining_capacity': room.capacity,
            'subjects': set(),
            'branches': set(),
            'years': set()
        } for room in rooms
    }

    def can_place(room_id, group_students):
        room_config = next(r for r in rooms if r.room_id == room_id)
        status = room_status[room_id]
        
        group_years = {s.year for s in group_students}
        group_subjects = {s.subject for s in group_students}
        group_branches = {s.branch for s in group_students}

        if len(group_students) > status['remaining_capacity']:
            return False
        
        if not group_years.issubset(room_config.allowed_years):
            return False
        
        if room_config.max_subjects > 0 and len(status['subjects'].union(group_subjects)) > room_config.max_subjects:
            return False
        
        if room_config.max_branches > 0 and len(status['branches'].union(group_branches)) > room_config.max_branches:
            return False
        
        return True

    def dfs(index):
        if index == len(sorted_groups):
            return True # All groups assigned

        group = sorted_groups[index]
        group_years = {s.year for s in group}
        group_subjects = {s.subject for s in group}
        group_branches = {s.branch for s in group}

        for room in rooms:
            if can_place(room.room_id, group):
                original_status = { # Store original status for backtracking
                    'remaining_capacity': room_status[room.room_id]['remaining_capacity'],
                    'subjects': room_status[room.room_id]['subjects'].copy(),
                    'branches': room_status[room.room_id]['branches'].copy(),
                    'years': room_status[room.room_id]['years'].copy()
                }

                # Make assignment
                room_status[room.room_id]['remaining_capacity'] -= len(group)
                room_status[room.room_id]['subjects'].update(group_subjects)
                room_status[room.room_id]['branches'].update(group_branches)
                room_status[room.room_id]['years'].update(group_years)
                room_assignments[room.room_id].extend([s.id for s in group])

                # Recurse
                if dfs(index + 1):
                    return True

                # Backtrack
                room_status[room.room_id]['remaining_capacity'] = original_status['remaining_capacity']
                room_status[room.room_id]['subjects'] = original_status['subjects']
                room_status[room.room_id]['branches'] = original_status['branches']
                room_status[room.room_id]['years'] = original_status['years']
                room_assignments[room.room_id] = [
                    sid for sid in room_assignments[room.room_id]
                    if sid not in [s.id for s in group]
                ]

        return False

    if dfs(0):
        result = {rid: students for rid, students in room_assignments.items() if students}
        print(f"\n📋 Backtracking Assignment Summary:")
        for room_id, students in result.items():
            if students:
                # status = room_status[room_id] # This variable was not used after fetching.
                print(f"  {room_id}: {len(students)} students")
        return result
    
    raise ValueError("No valid room assignment possible with current constraints")