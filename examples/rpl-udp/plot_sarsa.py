import matplotlib.pyplot as plt
import pandas as pd
import re
import os
from collections import defaultdict

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_SARSA = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
LOG_FILE_MRHOF = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")

# ==========================================
# 1. PARSERS
# ==========================================

def extract_battery_samples(filepath):
    """Parses periodic hardware battery ticks and percentages."""
    pattern = re.compile(r"BATTERY_SAMPLE:\s*node=(?P<node>\d+),\s*batt=(?P<batt>\d+)")
    records = []
    if not os.path.exists(filepath): return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if "BATTERY_SAMPLE" in line:
                match = pattern.search(line)
                if match:
                    records.append({
                        'node': int(match.group('node')),
                        'batt': int(match.group('batt'))
                    })
    df = pd.DataFrame(records)
    if not df.empty:
        df['sample_idx'] = df.groupby('node').cumcount() + 1
    return df

def extract_throughput(filepath):
    """Counts application packets sent by nodes."""
    sends = defaultdict(int)
    if not os.path.exists(filepath): return sends
    with open(filepath, 'r') as f:
        for line in f:
            if 'Sending request' in line:
                match = re.search(r'ID:(\d+)', line)
                if match:
                    sends[int(match.group(1))] += 1
    return sends

def extract_sink_receives(filepath):
    """Counts packets successfully received at the Root (Node 1)."""
    receives = 0
    if not os.path.exists(filepath): return 0
    with open(filepath, 'r') as f:
        for line in f:
            # Adjust this to exactly match how your sink logs received data
            if 'ID: 1' in line or 'Received request' in line:
                receives += 1
    return receives

# ==========================================
# 2. PLOTTING
# ==========================================

def plot_battery_comparison(df_sarsa, df_mrhof):
    """Draws a side-by-side comparison of battery drain to prove load balancing."""
    if df_sarsa.empty or df_mrhof.empty: 
        print("Missing data for plots.")
        return
        
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    
    # Left: SARSA
    for node in sorted(df_sarsa['node'].unique()):
        if node == 1: continue # Skip sink
        nd = df_sarsa[df_sarsa['node'] == node]
        axes[0].plot(nd['sample_idx'], nd['batt'], label=f'Node {node}', linewidth=2)
    axes[0].set_title("SARSA (Balanced Drain)")
    axes[0].set_xlabel("Sample Index")
    axes[0].set_ylabel("Battery %")
    axes[0].grid(True, linestyle='--', alpha=0.6)
    axes[0].legend()

    # Right: MRHOF
    for node in sorted(df_mrhof['node'].unique()):
        if node == 1: continue # Skip sink
        nd = df_mrhof[df_mrhof['node'] == node]
        axes[1].plot(nd['sample_idx'], nd['batt'], label=f'Node {node}', linewidth=2)
    axes[1].set_title("MRHOF (Single Path Drain)")
    axes[1].set_xlabel("Sample Index")
    axes[1].grid(True, linestyle='--', alpha=0.6)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_A_B_battery_test.png"), dpi=300)
    print("Saved: plot_A_B_battery_test.png")

# ==========================================
# 3. EXECUTION & REPORTING
# ==========================================

if __name__ == "__main__":
    print("--- Parsing A/B Test Logs ---\n")
    
    sarsa_batt = extract_battery_samples(LOG_FILE_SARSA)
    mrhof_batt = extract_battery_samples(LOG_FILE_MRHOF)
    
    sarsa_sent = sum(extract_throughput(LOG_FILE_SARSA).values())
    mrhof_sent = sum(extract_throughput(LOG_FILE_MRHOF).values())
    
    sarsa_rec = extract_sink_receives(LOG_FILE_SARSA)
    mrhof_rec = extract_sink_receives(LOG_FILE_MRHOF)

    print("=== A/B TEST RESULTS ===")
    
    # Battery Variance
    if not sarsa_batt.empty and not mrhof_batt.empty:
        s_n2 = sarsa_batt[sarsa_batt['node'] == 2]['batt'].iloc[-1]
        s_n3 = sarsa_batt[sarsa_batt['node'] == 3]['batt'].iloc[-1]
        m_n2 = mrhof_batt[mrhof_batt['node'] == 2]['batt'].iloc[-1]
        m_n3 = mrhof_batt[mrhof_batt['node'] == 3]['batt'].iloc[-1]
        
        s_var = abs(s_n2 - s_n3)
        m_var = abs(m_n2 - m_n3)
        
        print("\n[ Final Battery Levels ]")
        print(f"SARSA -> Node 2: {s_n2}%, Node 3: {s_n3}% | Variance: {s_var}%")
        print(f"MRHOF -> Node 2: {m_n2}%, Node 3: {m_n3}% | Variance: {m_var}%")
        
        if s_var > 10:
            print("  ⚠️ SARSA Variance is high. Penalty might be too aggressive (Node 3 starved).")
        elif s_var < m_var:
            print("  ✅ SARSA improved load balancing over MRHOF!")
    
    # PDR
    print("\n[ Packet Delivery Ratio (PDR) ]")
    if sarsa_sent > 0:
        print(f"SARSA PDR: {(sarsa_rec / sarsa_sent) * 100:.2f}% ({sarsa_rec}/{sarsa_sent})")
    if mrhof_sent > 0:
        print(f"MRHOF PDR: {(mrhof_rec / mrhof_sent) * 100:.2f}% ({mrhof_rec}/{mrhof_sent})")
    
    print("========================\n")
    
    plot_battery_comparison(sarsa_batt, mrhof_batt)