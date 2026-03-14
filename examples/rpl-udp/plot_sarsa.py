import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import re
import os
from collections import defaultdict

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_SARSA = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
LOG_FILE_MRHOF = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")

# ==========================================
# 1. DATA EXTRACTION (PARSERS)
# ==========================================

def extract_sarsa_rl_data(filepath):
    """Parses SARSA specific Reinforcement Learning metrics (Weights, TD Error, Rewards)."""
    pattern = re.compile(
        r"ID:(?P<id>\d+).*?Parent:\s*(?P<parent>\d+).*?Rew:\s*(?P<rew>-?\d+).*?"
        r"TD_Err:\s*(?P<td_err>-?\d+).*?W_LQ:\s*(?P<w_lq>\d+).*?"
        r"W_Energy:\s*(?P<w_e>\d+).*?Parent_batt:\s*(?P<p_batt>\d+)"
    )
    records = []
    global_tx_counter = defaultdict(int)

    if not os.path.exists(filepath): 
        return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if "MAC REWARD" in line:
                match = pattern.search(line)
                if match:
                    src_id = int(match.group('id'))
                    global_tx_counter[src_id] += 1 

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

def extract_battery_samples(filepath):
    """Parses periodic hardware battery ticks and percentages."""
    pattern = re.compile(
        r"BATTERY_SAMPLE:\s*node=(?P<node>\d+),\s*batt=(?P<batt>\d+),\s*"
        r"TX=(?P<tx>\d+),\s*RX=(?P<rx>\d+),\s*CPU=(?P<cpu>\d+)"
    )
    records = []
    if not os.path.exists(filepath): 
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

def extract_throughput(filepath):
    """Counts the number of successfully transmitted Application-layer packets."""
    sends = defaultdict(int)
    if not os.path.exists(filepath): 
        return sends
    with open(filepath, 'r') as f:
        for line in f:
            if 'Sending request' in line:
                match = re.search(r'ID:(\d+)', line)
                if match:
                    sends[int(match.group(1))] += 1
    return sends

def extract_routing_overhead(filepath):
    """Counts RPL Control messages (DIO, DAO, DIS)."""
    overhead = {'DIO': 0, 'DAO': 0, 'DIS': 0}
    if not os.path.exists(filepath): 
        return overhead
    with open(filepath, 'r') as f:
        for line in f:
            if 'sending a multicast-DIO' in line:
                overhead['DIO'] += 1
            elif 'sending a DAO' in line:
                overhead['DAO'] += 1
            elif 'sending a DIS' in line:
                overhead['DIS'] += 1
    return overhead


# ==========================================
# 2. COMPARATIVE PLOTS (SARSA vs MRHOF)
# ==========================================

def plot_battery_comparison(df_sarsa, df_mrhof):
    """Draws a Side-by-Side comparison of battery drain to prove fairness."""
    if df_sarsa.empty or df_mrhof.empty: return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    
    # Left Subplot: SARSA
    for node in sorted(df_sarsa['node'].unique()):
        if node == 1: continue # Skip sink
        nd = df_sarsa[df_sarsa['node'] == node]
        axes[0].plot(nd['sample_idx'], nd['batt'], label=f'Node {node}', linewidth=2)
    axes[0].set_title("SARSA Battery Drain Profile")
    axes[0].set_xlabel("Sample Index")
    axes[0].set_ylabel("Battery %")
    axes[0].grid(True, linestyle='--', alpha=0.6)
    axes[0].legend()

    # Right Subplot: MRHOF
    for node in sorted(df_mrhof['node'].unique()):
        if node == 1: continue # Skip sink
        nd = df_mrhof[df_mrhof['node'] == node]
        axes[1].plot(nd['sample_idx'], nd['batt'], label=f'Node {node}', linewidth=2)
    axes[1].set_title("MRHOF Battery Drain Profile")
    axes[1].set_xlabel("Sample Index")
    axes[1].grid(True, linestyle='--', alpha=0.6)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_comp_battery.png"), dpi=300)
    print("Saved: plot_comp_battery.png")

def plot_throughput_comparison(sarsa_tp, mrhof_tp):
    """Bar chart comparing Application packets successfully sent."""
    nodes = sorted(list(set(list(sarsa_tp.keys()) + list(mrhof_tp.keys()))))
    nodes = [n for n in nodes if n in [2,3,4]] # Only plot relays and leaves
    
    s_vals = [sarsa_tp.get(n, 0) for n in nodes]
    m_vals = [mrhof_tp.get(n, 0) for n in nodes]

    x = np.arange(len(nodes))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width/2, s_vals, width, label='SARSA', color='royalblue')
    ax.bar(x + width/2, m_vals, width, label='MRHOF', color='firebrick')

    ax.set_ylabel('Application Packets Sent')
    ax.set_title('Application Throughput: SARSA vs MRHOF')
    ax.set_xticks(x)
    ax.set_xticklabels([f"Node {n}" for n in nodes])
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_comp_throughput.png"), dpi=300)
    print("Saved: plot_comp_throughput.png")

def plot_overhead_comparison(sarsa_oh, mrhof_oh):
    """Bar chart comparing RPL network routing overhead."""
    labels = ['DIO', 'DAO', 'DIS']
    s_vals = [sarsa_oh[l] for l in labels]
    m_vals = [mrhof_oh[l] for l in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width/2, s_vals, width, label='SARSA', color='royalblue')
    ax.bar(x + width/2, m_vals, width, label='MRHOF', color='firebrick')

    ax.set_ylabel('Number of Control Messages')
    ax.set_title('RPL Routing Overhead Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_comp_overhead.png"), dpi=300)
    print("Saved: plot_comp_overhead.png")

def plot_tx_ticks_comparison(df_sarsa, df_mrhof):
    """
    Bar chart comparing total TX (transmission) ticks of relay nodes.
    This is the definitive proof of Load Balancing.
    """
    if df_sarsa.empty or df_mrhof.empty: 
        return

    # Focus strictly on the Relay Nodes (the potential bottlenecks)
    target_nodes = [2, 3]

    sarsa_tx = []
    mrhof_tx = []

    for node in target_nodes:
        # Extract the final cumulative TX ticks for each node
        s_node_data = df_sarsa[df_sarsa['node'] == node]
        m_node_data = df_mrhof[df_mrhof['node'] == node]

        s_tx = s_node_data['tx'].max() if not s_node_data.empty else 0
        m_tx = m_node_data['tx'].max() if not m_node_data.empty else 0

        sarsa_tx.append(s_tx)
        mrhof_tx.append(m_tx)

    x = np.arange(len(target_nodes))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width/2, sarsa_tx, width, label='SARSA', color='royalblue')
    ax.bar(x + width/2, mrhof_tx, width, label='MRHOF', color='firebrick')

    ax.set_ylabel('Total Transmission (TX) Energest Ticks')
    ax.set_title('Relay Node Workload Distribution: SARSA vs MRHOF')
    ax.set_xticks(x)
    ax.set_xticklabels([f"Node {n}" for n in target_nodes])
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_comp_tx_ticks.png"), dpi=300)
    print("Saved: plot_comp_tx_ticks.png")

# ==========================================
# 3. INDIVIDUAL PROTOCOL PLOTS (DEEP DIVES)
# ==========================================

def plot_sarsa_weights_vs_battery(df, target_node):
    """Plots RL weight adaptation in response to environmental changes."""
    node_data = df[df['src'] == target_node]
    if node_data.empty: return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    parents = node_data['parent'].unique()
    colors = {1: 'blue', 2: 'red', 3: 'green'} 
    
    for p in parents:
        p_data = node_data[node_data['parent'] == p]
        c = colors.get(p, 'black')
        ax1.plot(p_data['tx_num'], p_data['p_batt'], label=f'Parent {p} Battery', color=c, marker='o', markersize=3, linestyle='-')
        ax2.plot(p_data['tx_num'], p_data['w_lq'], label=f'Parent {p} W_LQ', color=c, linestyle='-', alpha=0.8)
        ax2.plot(p_data['tx_num'], p_data['w_e'], label=f'Parent {p} W_Energy', color=c, linestyle='--', alpha=0.8)

    ax1.set_title(f"Node {target_node}: Environmental Change (Battery Drain)", fontsize=14)
    ax1.set_ylabel("Battery %")
    ax1.set_ylim(0, 105)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc="lower left")

    ax2.set_title(f"Node {target_node}: RL Agent Weight Adaptation", fontsize=14)
    ax2.set_ylabel("Weight Value")
    ax2.set_xlabel("Global Transmission Event")
    ax2.axhline(y=200, color='red', linestyle=':', label='Ceiling Bound')
    ax2.axhline(y=50, color='gray', linestyle=':', label='Initial Value')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc="upper left")

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, f"plot_indiv_sarsa_weights_node{target_node}.png"), dpi=300)
    print(f"Saved: plot_indiv_sarsa_weights_node{target_node}.png")

def plot_single_of_hardware_ticks(df, algo_name, target_node=3):
    """Plots TX, RX, and CPU hardware usage over time for a single protocol."""
    node_data = df[df['node'] == target_node]
    if node_data.empty: return
        
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    ax1.plot(node_data['sample_idx'], node_data['tx'], label=f'{algo_name} TX', color='blue', linewidth=2)
    ax1.set_title(f"Node {target_node} ({algo_name}): Transmission (TX)", fontsize=12)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend()
    
    ax2.plot(node_data['sample_idx'], node_data['rx'], label=f'{algo_name} RX', color='green', linewidth=2)
    ax2.set_title(f"Node {target_node} ({algo_name}): Listening (RX)", fontsize=12)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend()
    
    ax3.plot(node_data['sample_idx'], node_data['cpu'], label=f'{algo_name} CPU', color='darkorange', linewidth=2)
    ax3.set_title(f"Node {target_node} ({algo_name}): Processing (CPU)", fontsize=12)
    ax3.set_xlabel("Sample Index")
    ax3.grid(True, linestyle='--', alpha=0.6)
    ax3.legend()
    
    plt.tight_layout()
    filename = f"plot_indiv_ticks_node{target_node}_{algo_name.lower()}.png"
    plt.savefig(os.path.join(SCRIPT_DIR, filename), dpi=300)
    print(f"Saved: {filename}")


# ==========================================
# 4. MAIN CONTROLLER
# ==========================================

if __name__ == "__main__":
    print("--- Parsing Logs ---")
    
    # Extract Dataframes & Dictionary metrics
    sarsa_rl = extract_sarsa_rl_data(LOG_FILE_SARSA)
    sarsa_batt = extract_battery_samples(LOG_FILE_SARSA)
    mrhof_batt = extract_battery_samples(LOG_FILE_MRHOF)
    
    sarsa_tp = extract_throughput(LOG_FILE_SARSA)
    mrhof_tp = extract_throughput(LOG_FILE_MRHOF)
    
    sarsa_oh = extract_routing_overhead(LOG_FILE_SARSA)
    mrhof_oh = extract_routing_overhead(LOG_FILE_MRHOF)

    print("--- Generating Comparative Plots ---")
    plot_battery_comparison(sarsa_batt, mrhof_batt)
    plot_throughput_comparison(sarsa_tp, mrhof_tp)
    plot_overhead_comparison(sarsa_oh, mrhof_oh)
    plot_tx_ticks_comparison(sarsa_batt, mrhof_batt)

    print("--- Generating Individual Profiles ---")
    if not sarsa_rl.empty:
        plot_sarsa_weights_vs_battery(sarsa_rl, target_node=3)
    
    if not sarsa_batt.empty:
        plot_single_of_hardware_ticks(sarsa_batt, "SARSA", target_node=3)
        
    if not mrhof_batt.empty:
        plot_single_of_hardware_ticks(mrhof_batt, "MRHOF", target_node=3)

    print("Done! Check your script directory for the .png files.")