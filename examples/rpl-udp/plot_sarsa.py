import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import re
import os
from collections import defaultdict

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja.log")

def extract_log_data(filepath):
    """
    Parses the Cooja log and builds a Pandas DataFrame
    """

    pattern = re.compile(
        r"ID:(?P<id>\d+).*?Parent:\s*(?P<parent>\d+).*?Rew:\s*(?P<rew>-?\d+).*?"
        r"TD_Err:\s*(?P<td_err>-?\d+).*?W_LQ:\s*(?P<w_lq>\d+).*?"
        r"W_Energy:\s*(?P<w_e>\d+).*?Parent_batt:\s*(?P<p_batt>\d+)"
    )

    records = []
    global_tx_counter = defaultdict(int)

    if not os.path.exists(filepath):
        print("Error: Could not find {filepath}")
        return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if "MAC REWARD" in line:
                match = pattern.search(line)
                if match:
                    src_id = int(match.group('id'))
                    global_tx_counter[src_id] += 1 # Increment global timeline

                    records.append({
                        'src': src_id,
                        'parent': int(match.group('parent')),
                        'tx_num': global_tx_counter[src_id],
                        'w_lq': int(match.group('w_lq')),
                        'w_e': int(match.group('w_e')),
                        'td_err': int(match.group('td_err')),
                        'p_batt': int(match.group('p_batt')),
                        'rew': int(match.group('rew'))
                    })
    return pd.DataFrame(records)

def plot_weight_vs_battery(df, target_node):
    """
    PLOT 1: The 'Hero Plot'. Dual-pane graph showing causality.
    Top pane: Parent Battery Depletion.
    Bottom pane: The RL Agent adapting the weights in response.
    """
    node_data = df[df['src'] == target_node]
    if node_data.empty: return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # We will plot lines for each parent it interacted with
    parents = node_data['parent'].unique()
    colors = {1: 'blue', 2: 'red', 3: 'green'} # Assign stable colors
    
    for p in parents:
        p_data = node_data[node_data['parent'] == p]
        c = colors.get(p, 'black')
        
        # Top Pane: Battery
        ax1.plot(p_data['tx_num'], p_data['p_batt'], label=f'Parent {p} Battery', color=c, marker='o', markersize=3, linestyle='-')
        
        # Bottom Pane: Weights
        ax2.plot(p_data['tx_num'], p_data['w_lq'], label=f'Parent {p} W_LQ', color=c, linestyle='-', alpha=0.8)
        ax2.plot(p_data['tx_num'], p_data['w_e'], label=f'Parent {p} W_Energy', color=c, linestyle='--', alpha=0.8)

    # Styling Top Pane (Battery)
    ax1.set_title(f"Node {target_node}: Environmental Change (Battery Drain)", fontsize=14)
    ax1.set_ylabel("Battery %")
    ax1.set_ylim(0, 105)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc="lower left")

    # Styling Bottom Pane (Weights)
    ax2.set_title(f"Node {target_node}: RL Agent Weight Adaptation (Parameter Saturation)", fontsize=14)
    ax2.set_ylabel("Weight Value")
    ax2.set_xlabel("Global Transmission Event (Timeline)")
    ax2.axhline(y=200, color='red', linestyle=':', label='Ceiling Bound (200)')
    ax2.axhline(y=50, color='gray', linestyle=':', label='Initial Value (50)')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc="upper left")

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, f"plot_1_weights_vs_battery{target_node}.png"), dpi=300)
    print("Saved: plot_1_weights_vs_battery.png")

def plot_td_error_convergence(df, target_node):
    """
    PLOT 2: The Mathematical Proof of Convergence.
    Shows the TD Error stabilizing at 0 for the optimal route.
    """
    node_data = df[df['src'] == target_node]
    if node_data.empty: return

    plt.figure(figsize=(10, 5))
    parents = node_data['parent'].unique()
    colors = {1: 'blue', 2: 'red'}

    for p in parents:
        p_data = node_data[node_data['parent'] == p]
        plt.scatter(p_data['tx_num'], p_data['td_err'], label=f'Parent {p} TD Error', color=colors.get(p, 'black'), alpha=0.6, s=15)

    plt.axhline(y=0, color='green', linestyle='-', linewidth=2, label='Perfect Convergence (0)')
    
    plt.title(f"Node {target_node}: Temporal Difference (TD) Error over Time", fontsize=14)
    plt.xlabel("Global Transmission Event (Timeline)")
    plt.ylabel("TD Error")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, f"plot_2_td_error{target_node}.png"), dpi=300)
    print("Saved: plot_2_td_error.png")


if __name__ == "__main__":
    # 1. Extract data
    print("Extracting data from logs...")
    df_sarsa = extract_log_data(LOG_FILE)
    
    if not df_sarsa.empty:
        print(f"Successfully extracted {len(df_sarsa)} transmission records.")
        
        # 2. Generate thesis plots
        plot_weight_vs_battery(df_sarsa, target_node=3)
        plot_td_error_convergence(df_sarsa, target_node=3)
        
        print("All plots generated successfully!")
    else:
        print("Failed to generate plots.")
