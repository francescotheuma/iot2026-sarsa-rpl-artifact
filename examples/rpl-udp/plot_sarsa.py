import matplotlib.pyplot as plt
import re
from collections import defaultdict
import os

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Build path to log file - Keeping your verified path
LOG_FILE = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja.log")

def parse_sarsa_logs():
    data = defaultdict(lambda: {'x': [], 'y': []})
    event_counters = defaultdict(int)

    # UPDATED REGEX: 
    # This looks for 'ID:' followed by numbers, and later 'W_LQ:' followed by numbers
    pattern = re.compile(r"ID:(?P<id>\d+).*W_LQ:\s*(?P<weight>\d+)")

    try:
        if not os.path.exists(LOG_FILE):
             print(f"Error: {LOG_FILE} not found. Check the path!")
             return None
             
        with open(LOG_FILE, 'r') as f:
            for line in f:
                # Only process lines with the SARSA info to save time and avoid errors
                if "MAC REWARD" in line:
                    match = pattern.search(line)
                    if match:
                        node_id = match.group('id')
                        weight = int(match.group('weight'))
                        
                        event_counters[node_id] += 1
                        data[node_id]['x'].append(event_counters[node_id])
                        data[node_id]['y'].append(weight)
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    return data

def plot_convergence(data):
    if not data or len(data) == 0:
        print("No data found in log. Check if 'W_LQ' entries exist in cooja.log.")
        return

    plt.figure(figsize=(10, 6))
    
    # Use step plot for RL weights - it shows exactly when changes happen
    for node_id in sorted(data.keys(), key=int):
        plt.step(data[node_id]['x'], data[node_id]['y'], where='post', label=f"Node {node_id}")

    plt.axhline(y=50, color='gray', linestyle='--', alpha=0.5, label="Initial Weight")
    
    plt.title("SARSA Convergence: W_LQ Weight per Node")
    plt.xlabel("Transmission Events (Learning Steps)")
    plt.ylabel("Weight Value (W_LQ)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Save a backup image in case the window doesn't pop up in WSL
    plt.savefig(os.path.join(SCRIPT_DIR, "sarsa_plot.png"))
    print("Plot saved as sarsa_plot.png")
    
    plt.show()

if __name__ == "__main__":
    sarsa_data = parse_sarsa_logs()
    plot_convergence(sarsa_data)