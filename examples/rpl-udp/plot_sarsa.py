import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import re
import os
from collections import defaultdict

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE_SARSA = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja_sarsa.log")
LOG_FILE_MRHOF = os.path.join(SCRIPT_DIR, "..", "..", "tools", "cooja", "cooja_mrhof.log")

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

def extract_battery_samples(filepath):
    """
    Parses periodic battery log samples from a Cooja log file.
    Expects lines with format: "BATTERY_SAMPLE: node=X, batt=XX, TX=X, RX=X, CPU=X"
    """
    # Updated regex to capture all the new hardware ticks
    pattern = re.compile(
        r"BATTERY_SAMPLE:\s*node=(?P<node>\d+),\s*batt=(?P<batt>\d+),\s*"
        r"TX=(?P<tx>\d+),\s*RX=(?P<rx>\d+),\s*CPU=(?P<cpu>\d+)"
    )
    
    records = []
    
    if not os.path.exists(filepath):
        print(f"Error: Could not find {filepath}")
        return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if "BATTERY_SAMPLE" in line:
                match = pattern.search(line)
                if match:
                    records.append({
                        'node': int(match.group('node')),
                        'batt': int(match.group('batt')),
                        'tx': int(match.group('tx')),
                        'rx': int(match.group('rx')),
                        'cpu': int(match.group('cpu'))
                    })
    
    df = pd.DataFrame(records)
    if not df.empty:
        df['sample_idx'] = df.groupby('node').cumcount() + 1
    
    return df

def plot_battery_comparison(df_sarsa, df_mrhof):
    """
    PLOT 3: Battery drain comparison between SARSA and MRHOF.
    Shows battery depletion per node for both objective functions.
    """
    plt.figure(figsize=(14, 7))
    
    # Plot SARSA nodes
    if not df_sarsa.empty:
        for node in sorted(df_sarsa['node'].unique()):
            node_data = df_sarsa[df_sarsa['node'] == node]
            plt.plot(node_data['sample_idx'], node_data['batt'], 
                    label=f'SARSA Node {node}', marker='o', markersize=3, linestyle='-', linewidth=2, alpha=0.8)
    
    # Plot MRHOF nodes
    if not df_mrhof.empty:
        for node in sorted(df_mrhof['node'].unique()):
            node_data = df_mrhof[df_mrhof['node'] == node]
            plt.plot(node_data['sample_idx'], node_data['batt'], 
                    label=f'MRHOF Node {node}', marker='s', markersize=3, linestyle='--', linewidth=2, alpha=0.8)
    
    plt.title("Battery Drain: SARSA vs MRHOF (Per Node)", fontsize=14)
    plt.xlabel("Sample Index", fontsize=12)
    plt.ylabel("Battery Level (%)", fontsize=12)
    plt.ylim(0, 105)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(fontsize=10, loc='best')
    
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_3_battery_comparison.png"), dpi=300)
    print("Saved: plot_3_battery_comparison.png")

def plot_hardware_ticks_comparison(df_sarsa, df_mrhof, target_node=3):
        """
        PLOT 4: Hardware Ticks comparison between SARSA and MRHOF.
        Creates a 3-pane plot (TX, RX, CPU) to diagnose exact battery drain causes.
        """
        s_data = df_sarsa[df_sarsa['node'] == target_node] if not df_sarsa.empty else pd.DataFrame()
        m_data = df_mrhof[df_mrhof['node'] == target_node] if not df_mrhof.empty else pd.DataFrame()
        
        if s_data.empty and m_data.empty: 
            return
            
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        
        # --- Pane 1: TX Ticks ---
        if not s_data.empty: ax1.plot(s_data['sample_idx'], s_data['tx'], label='SARSA TX', color='blue', linewidth=2)
        if not m_data.empty: ax1.plot(m_data['sample_idx'], m_data['tx'], label='MRHOF TX', color='red', linestyle='--', linewidth=2)
        ax1.set_title(f"Node {target_node}: Transmission (TX) Energest Ticks", fontsize=12)
        ax1.set_ylabel("Cumulative Ticks")
        ax1.grid(True, linestyle='--', alpha=0.6)
        ax1.legend(loc="upper left")
        
        # --- Pane 2: RX Ticks ---
        if not s_data.empty: ax2.plot(s_data['sample_idx'], s_data['rx'], label='SARSA RX', color='blue', linewidth=2)
        if not m_data.empty: ax2.plot(m_data['sample_idx'], m_data['rx'], label='MRHOF RX', color='red', linestyle='--', linewidth=2)
        ax2.set_title(f"Node {target_node}: Listening/Reception (RX) Energest Ticks", fontsize=12)
        ax2.set_ylabel("Cumulative Ticks")
        ax2.grid(True, linestyle='--', alpha=0.6)
        ax2.legend(loc="upper left")
        
        # --- Pane 3: CPU Ticks ---
        if not s_data.empty: ax3.plot(s_data['sample_idx'], s_data['cpu'], label='SARSA CPU', color='blue', linewidth=2)
        if not m_data.empty: ax3.plot(m_data['sample_idx'], m_data['cpu'], label='MRHOF CPU', color='red', linestyle='--', linewidth=2)
        ax3.set_title(f"Node {target_node}: Processing (CPU) Energest Ticks", fontsize=12)
        ax3.set_xlabel("Sample Index (Time - 10s intervals)", fontsize=12)
        ax3.set_ylabel("Cumulative Ticks")
        ax3.grid(True, linestyle='--', alpha=0.6)
        ax3.legend(loc="upper left")
        
        plt.tight_layout()
        filename = f"plot_4_hardware_ticks_node{target_node}.png"
        plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=300)
        print(f"Saved: {filename}")

if __name__ == "__main__":
    # 1. Extract MAC reward data (SARSA only)
    print("Extracting SARSA MAC reward data...")
    df_sarsa_mac = extract_log_data(LOG_FILE_SARSA)
    
    if not df_sarsa_mac.empty:
        print(f"Successfully extracted {len(df_sarsa_mac)} SARSA transmission records.")
        plot_weight_vs_battery(df_sarsa_mac, target_node=3)
        plot_td_error_convergence(df_sarsa_mac, target_node=3)
    else:
        print("Warning: No SARSA MAC reward data found.")
    
    # 2. Extract periodic battery samples
    print("\nExtracting periodic battery samples...")
    df_battery_sarsa = extract_battery_samples(LOG_FILE_SARSA)
    df_battery_mrhof = extract_battery_samples(LOG_FILE_MRHOF)
    
    if not df_battery_sarsa.empty or not df_battery_mrhof.empty:
        print(f"SARSA: {len(df_battery_sarsa)} battery samples")
        print(f"MRHOF: {len(df_battery_mrhof)} battery samples")
        
        # Generate the overall battery comparison plot
        plot_battery_comparison(df_battery_sarsa, df_battery_mrhof)
        
        # --- NEW: Generate hardware tick comparisons for each active node ---
        active_nodes = set()
        if not df_battery_sarsa.empty: 
            active_nodes.update(df_battery_sarsa['node'].unique())
        if not df_battery_mrhof.empty: 
            active_nodes.update(df_battery_mrhof['node'].unique())
        
        print("\nGenerating hardware tick analysis plots...")
        for node in active_nodes:
            # We skip Node 1 if it's the sink/root (it doesn't have parents or make routing decisions)
            if node != 1: 
                plot_hardware_ticks_comparison(df_battery_sarsa, df_battery_mrhof, target_node=node)
                
    else:
        print("Warning: No periodic battery samples found in logs.")
    
    print("\nAll plots generated successfully!")
