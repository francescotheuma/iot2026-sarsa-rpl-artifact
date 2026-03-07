import matplotlib.pyplot as plt
import re
from collections import defaultdict
import os
import numpy as np

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Adjusted path based on your previous snippet
LOG_FILE = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja.log")

def parse_sarsa_logs():
    # We now store: w_lq, w_energy, and parent_batt for every (src, parent) pair
    data = defaultdict(lambda: {'x': [], 'w_lq': [], 'w_e': [], 'p_batt': []})
    event_counters = defaultdict(int)
    
    # NEW REGEX: Matches your new LOG_INFO format
    # ID:3 ... MAC REWARD: OK | Parent: 1 | Rew: 80 | TD_Err: 86 | W_LQ: 18 | W_Energy: 50 | My_batt: 100 | Parent_batt: 100
    pattern = re.compile(
        r"ID:(?P<id>\d+).*?Parent:\s*(?P<parent>\d+).*?W_LQ:\s*(?P<w_lq>\d+).*?W_Energy:\s*(?P<w_e>\d+).*?Parent_batt:\s*(?P<p_batt>\d+)"
    )

    try:
        if not os.path.exists(LOG_FILE):
             print(f"Error: {LOG_FILE} not found!")
             return None
             
        with open(LOG_FILE, 'r') as f:
            for line in f:
                if "MAC REWARD" in line:
                    match = pattern.search(line)
                    if match:
                        src_id = match.group('id')
                        parent_id = match.group('parent')
                        
                        # Create a unique key for each pair: e.g., "3->1"
                        pair_key = (src_id, parent_id)
                        
                        event_counters[pair_key] += 1
                        data[pair_key]['x'].append(event_counters[pair_key])
                        data[pair_key]['w_lq'].append(int(match.group('w_lq')))
                        data[pair_key]['w_e'].append(int(match.group('w_e')))
                        data[pair_key]['p_batt'].append(int(match.group('p_batt')))
                        
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    return data

def plot_convergence(data):
    if not data:
        print("No data found.")
        return

    plt.figure(figsize=(14, 8))
    window_size = 25 

    # Sort keys by source then parent for a clean legend
    for pair_key in sorted(data.keys()):
        src, parent = pair_key
        x = np.array(data[pair_key]['x'])
        
        # We will plot BOTH weights for each pair
        weights = {
            'W_LQ': (np.array(data[pair_key]['w_lq']), '-'),  # Solid line
            'W_Energy': (np.array(data[pair_key]['w_e']), '--') # Dashed line
        }
        
        for weight_name, (y, style) in weights.items():
            if len(y) > window_size:
                y_smoothed = np.convolve(y, np.ones(window_size)/window_size, mode='valid')
                x_smoothed = x[window_size-1:]
                
                label = f"Node {src}->P{parent} ({weight_name})"
                line = plt.plot(x_smoothed, y_smoothed, label=label, linestyle=style, linewidth=2)
                
                # Plot raw data faintly
                plt.plot(x, y, alpha=0.05, color=line[0].get_color())
            else:
                plt.plot(x, y, label=f"{src}->P{parent} {weight_name} (Insuff.)", alpha=0.3, linestyle=style)

    # Threshold lines
    plt.axhline(y=40, color='red', linestyle=':', alpha=0.5, label="Floor (40)")
    plt.axhline(y=200, color='green', linestyle=':', alpha=0.5, label="Ceiling (200)")
    
    plt.title(f"SARSA Dual-Feature Convergence (n={window_size})", fontsize=14)
    plt.xlabel("Transmission Events (per Parent Pair)", fontsize=12)
    plt.ylabel("Learned Weights", fontsize=12)
    
    # Place legend outside to avoid covering data
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    output_path = os.path.join(SCRIPT_DIR, "sarsa_dual_trend.png")
    plt.savefig(output_path)
    print(f"Trend plot saved as {output_path}")
    plt.show()

if __name__ == "__main__":
    sarsa_data = parse_sarsa_logs()
    plot_convergence(sarsa_data)