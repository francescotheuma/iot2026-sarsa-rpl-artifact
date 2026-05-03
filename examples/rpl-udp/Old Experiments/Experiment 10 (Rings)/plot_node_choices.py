import re
import pandas as pd
import matplotlib.pyplot as plt

def plot_node_parent_choices(filename, target_node, title, output_file):
    data = []
    with open(filename, 'r') as f:
        for line in f:
            # 1. Filter: Only look at lines belonging to our target node
            if f'ID:{target_node} ' not in line: 
                continue 
            
            # 2. Extract timestamp (convert from microseconds to minutes)
            time_match = re.search(r'^(\d+)', line)
            if not time_match: 
                continue
            minutes = int(time_match.group(1)) / 60000000

            # 3. Find the chosen parent
            parent = None
            sarsa_match = re.search(r'CHOSE: (\d+)', line)
            
            # RPL addresses are hex (e.g., fe80::c30c:0:0:a is Node 10)
            rpl_match = re.search(r'parent fe80::c30c:0:0:([0-9a-f]+)', line) 
            
            if sarsa_match: 
                parent = int(sarsa_match.group(1))
            elif rpl_match: 
                parent = int(rpl_match.group(1), 16) # Convert hex string to integer

            # 4. Save valid data points
            if parent is not None:
                data.append({'time': minutes, 'parent': parent})
    
    # 5. Check if we found anything
    if not data:
        print(f"No parent selections found for Node {target_node} in {filename}")
        return

    df = pd.DataFrame(data)
    
    # 6. Plotting
    plt.figure(figsize=(10, 5))
    
    # Scatter dots for exact moments, dashed line to show the jumps
    plt.plot(df['time'], df['parent'], c='dodgerblue', alpha=0.4, linestyle='--') 
    plt.scatter(df['time'], df['parent'], c='dodgerblue', s=40, alpha=0.8, edgecolors='black')

    plt.xlabel('Time (Minutes)', fontsize=12, fontweight='bold')
    plt.ylabel(f'Parent ID Chosen', fontsize=12, fontweight='bold')
    plt.title(title, fontsize=14)
    
    # Dynamically set Y-axis ticks based on the nodes actually chosen
    y_min, y_max = int(df['parent'].min()), int(df['parent'].max())
    plt.yticks(range(max(1, y_min - 1), y_max + 2))
    
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.tight_layout()
    
    # Save high-resolution image for thesis
    plt.savefig(output_file, dpi=300)
    print(f"Success! Saved plot for Node {target_node} to {output_file}")


# ==========================================
# HOW TO USE: Change the 'target_node_id' below
# ==========================================

target_node_id = 6  # <--- Change this number to test other nodes (e.g., 3, 5, 10)

# Run for MRHOF
plot_node_parent_choices(
    filename='cooja_mrhof_exp10_full.log', 
    target_node=target_node_id, 
    title=f"MRHOF: Node {target_node_id} Route Stability", 
    output_file=f"mrhof_node{target_node_id}_stability.png"
)

# Run for SARSA
plot_node_parent_choices(
    filename='cooja_sarsa_exp10_full.log', 
    target_node=target_node_id, 
    title=f"SARSA: Node {target_node_id} Route Stability", 
    output_file=f"sarsa_node{target_node_id}_stability.png"
)