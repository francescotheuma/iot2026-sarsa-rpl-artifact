import matplotlib.pyplot as plt
import re
from collections import defaultdict
import os
import numpy as np

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja.log")

def parse_sarsa_logs():
    data = defaultdict(lambda: {'x': [], 'y': []})
    event_counters = defaultdict(int)
    pattern = re.compile(r"ID:(?P<id>\d+).*W_LQ:\s*(?P<weight>\d+)")

    try:
        if not os.path.exists(LOG_FILE):
             print(f"Error: {LOG_FILE} not found!")
             return None
             
        with open(LOG_FILE, 'r') as f:
            for line in f:
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
    if not data:
        print("No data found.")
        return

    plt.figure(figsize=(12, 7))
    
    # Increase window_size to make the plot smoother (e.g., 20-50)
    window_size = 25 

    for node_id in sorted(data.keys(), key=int):
        x = np.array(data[node_id]['x'])
        y = np.array(data[node_id]['y'])
        
        if len(y) > window_size:
            # Calculate Moving Average
            y_smoothed = np.convolve(y, np.ones(window_size)/window_size, mode='valid')
            x_smoothed = x[window_size-1:]
            
            # Plot the smooth trend line
            plt.plot(x_smoothed, y_smoothed, label=f"Node {node_id} Trend", linewidth=2)
            # Optional: Plot raw data faintly in the background
            plt.plot(x, y, alpha=0.1, color=plt.gca().get_lines()[-1].get_color())
        else:
            plt.plot(x, y, label=f"Node {node_id} (Insuff. Data)", alpha=0.5)

    plt.axhline(y=50, color='black', linestyle='--', alpha=0.3, label="Initial Weight")
    
    plt.title(f"SARSA Learning Progress (Moving Average n={window_size})", fontsize=14)
    plt.xlabel("Transmission Events (Learning Steps)", fontsize=12)
    plt.ylabel("Learned Weight (W_LQ)", fontsize=12)
    plt.legend(loc='upper left')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "sarsa_trend.png"))
    print("Trend plot saved as sarsa_trend.png")
    plt.show()

if __name__ == "__main__":
    sarsa_data = parse_sarsa_logs()
    plot_convergence(sarsa_data)