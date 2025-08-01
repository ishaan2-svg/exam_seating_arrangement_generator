import pandas as pd
import networkx as nx
from collections import defaultdict

def dsatur_coloring(G):
    if len(G.nodes) == 0:
        return {}
        
    colors = {}
    saturation = defaultdict(set)
    degrees = dict(G.degree())

    current = max(degrees, key=lambda x: degrees[x]) if degrees else list(G.nodes)[0]
    colors[current] = 0

    while len(colors) < len(G.nodes):
        for node in G.nodes:
            if node not in colors:
                saturation[node] = {colors[nbr] for nbr in G.neighbors(node) if nbr in colors}

        uncolored = [node for node in G.nodes if node not in colors]
        if not uncolored:
            break
            
        next_node = max(
            uncolored,
            key=lambda x: (len(saturation[x]), degrees.get(x, 0))
        )

        used_colors = {colors[nbr] for nbr in G.neighbors(next_node) if nbr in colors}
        color = 0
        while color in used_colors:
            color += 1
            
        colors[next_node] = color

    return colors

def get_colored_groups(df):
    G = nx.Graph()

    for student_id in df['StudentID']:
        G.add_node(student_id)

    conflicts_added = 0
    for i in range(len(df)):
        s1 = df.iloc[i]
        for j in range(i+1, len(df)):
            s2 = df.iloc[j]
            if (s1['ExamDate'] == s2['ExamDate']) and (s1['ExamTime'] == s2['ExamTime']):
                G.add_edge(s1['StudentID'], s2['StudentID'])
                conflicts_added += 1

    color_mapping = dsatur_coloring(G)
    groups = defaultdict(list)
    for student, color in color_mapping.items():
        groups[color].append(student)
    
    return groups

def extract_student_metadata(df):
    metadata = {}
    for _, row in df.iterrows():
        student_data = {
            'Name': row.get('Name', f"Student-{row['StudentID']}"),
            'Department': row['Department'],
            'Subject': row['Subject'],
            'ExamTime': row['ExamTime'],
            'ExamDate': row['ExamDate'],
            'Year': str(row['Year']),
            'Branch': row.get('Batch', 'Unknown'),
            'Semester': row.get('Semester', 'Unknown'),
            'Batch': row.get('Batch', 'Unknown'),
            'Photo': row.get('Photo', ''),
            'Location': row.get('Location', '')
        }
        metadata[row['StudentID']] = student_data
    
    return metadata