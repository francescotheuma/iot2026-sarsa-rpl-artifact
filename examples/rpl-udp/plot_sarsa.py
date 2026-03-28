import matplotlib.pyplot as plt
import pandas as pd
import re
import os
from collections import defaultdict

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE_SARSA = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
LOG_FILE_MRHOF = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")

SARSA_PLOT = False
BATTERY_PLOT = True

# ==========================================
# 1. PARSERS
# ==========================================

def extract_battery_samples(filepath):
    """Parses periodic hardware battery ticks, time, TX, and CPU."""
    pattern = re.compile(r"^\s*(?P<ts>\d+)\s+.*BATTERY_SAMPLE:\s*node=(?P<node>\d+),\s*batt=(?P<batt>\d+),\s*TX=(?P<tx>\d+),\s*RX=(?P<rx>\d+),\s*CPU=(?P<cpu>\d+)")
    records = []
    if not os.path.exists(filepath): return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if "BATTERY_SAMPLE" in line:
                match = pattern.search(line)
                if match:
                    records.append({
                        'time_mins': int(match.group('ts')) / 60_000_000,
                        'node': int(match.group('node')),
                        'batt': int(match.group('batt')),
                        'tx': int(match.group('tx')),
                        'cpu': int(match.group('cpu'))
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
            if 'ID:1 ' in line and 'Received request' in line:
                receives += 1
    return receives

def extract_sarsa_internals(filepath):
    """Extracts SARSA logs mapped perfectly to Simulation Time (Minutes)."""
    math_pattern = re.compile(r'^\s*(\d+)\s+ID:(\d+).*?SARSA-MATH \| Par: (\d+) \| curQ: (-?\d+) \| rew: (-?\d+) \| futQ: (-?\d+) \| tgt: (-?\d+) \| err: (-?\d+)')
    wght_pattern = re.compile(r'^\s*(\d+)\s+ID:(\d+).*?SARSA-WGHT \| f_lq: (-?\d+) \| f_eng: (-?\d+) \| W_LQ: (-?\d+) \| W_ENG: (-?\d+)')
    
    math_data = []
    wght_data = []
    
    if not os.path.exists(filepath): return pd.DataFrame(), pd.DataFrame()
        
    with open(filepath, 'r') as f:
        for line in f:
            if 'SARSA-MATH' in line:
                m = math_pattern.search(line)
                if m:
                    math_data.append({
                        'ts_mins': int(m.group(1)) / 60_000_000,
                        'node': int(m.group(2)),
                        'par': int(m.group(3)),
                        'curQ': int(m.group(4)),
                        'tgt': int(m.group(7)),
                        'err': int(m.group(8))
                    })
            elif 'SARSA-WGHT' in line:
                w = wght_pattern.search(line)
                if w:
                    wght_data.append({
                        'ts_mins': int(w.group(1)) / 60_000_000,
                        'node': int(w.group(2)),
                        'w_lq': int(w.group(5)),
                        'w_eng': int(w.group(6))
                    })
                    
    df_math = pd.DataFrame(math_data)
    df_wght = pd.DataFrame(wght_data)
    
    if not df_math.empty:
        df_math = df_math[(df_math['curQ'].between(-500, 500)) & 
                          (df_math['tgt'].between(-500, 500)) & 
                          (df_math['err'].between(-500, 500))]
        
    return df_math, df_wght

def extract_evaluate_qvalues(filepath):
    """Extracts dynamic Q-value evaluations from the best_parent log."""
    # Matches: EVALUATE: P1: X (Q: Y) vs P2: A (Q: B)
    eval_pattern = re.compile(r'^\s*(?P<ts>\d+)\s+ID:(?P<node>\d+).*?EVALUATE: P1: (?P<p1>\d+) \(Q: (?P<q1>-?\d+)\) vs P2: (?P<p2>\d+) \(Q: (?P<q2>-?\d+)\)')
    records = []
    
    if not os.path.exists(filepath): return pd.DataFrame()
    
    with open(filepath, 'r') as f:
        for line in f:
            if 'EVALUATE:' in line:
                match = eval_pattern.search(line)
                if match:
                    ts_mins = int(match.group('ts')) / 60_000_000
                    node = int(match.group('node'))
                    
                    # Store P1's Q-Value
                    records.append({
                        'ts_mins': ts_mins,
                        'node': node,
                        'par': int(match.group('p1')),
                        'q_val': int(match.group('q1'))
                    })
                    
                    # Store P2's Q-Value
                    records.append({
                        'ts_mins': ts_mins,
                        'node': node,
                        'par': int(match.group('p2')),
                        'q_val': int(match.group('q2'))
                    })
                    
    return pd.DataFrame(records)

# ==========================================
# 2. PLOTTING
# ==========================================

def plot_battery_comparison(df_sarsa, df_mrhof):
    if df_sarsa.empty or df_mrhof.empty: 
        print("Missing data for plots.")
        return
        
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    
    def plot_and_label(df, ax, title):
        ax.set_title(title, fontsize=14, fontweight='bold')
        summary_text = "Final Stats:\n"

        for node in sorted(df['node'].unique()):
            if node == 1: continue 
            nd = df[df['node'] == node]
            x_col = 'time_mins'

            line, = ax.plot(nd[x_col], nd['batt'], label=f'Node {node}', linewidth=2)

            final_x = nd[x_col].iloc[-1]
            final_y = nd['batt'].iloc[-1]
            final_cpu = nd['cpu'].iloc[-1] 
            final_tx = nd['tx'].iloc[-1] 
            
            summary_text += f"Node {node}: CPU {final_cpu:,} | TX {final_tx:,}\n"

            ax.text(
                final_x + (final_x * 0.05),
                final_y,
                f'{final_y}%',
                color=line.get_color(),
                fontweight='bold',
                va='center'
            )

        ax.set_xlabel("Time (Minutes)", fontweight='bold')
        ax.legend(loc="best", framealpha=0.8) 
        ax.grid(True, linestyle='--', alpha=0.6)
        
        props = dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray')
        ax.text(0.96, 0.96, summary_text.strip(), transform=ax.transAxes, 
                fontsize=10, verticalalignment='top', 
                horizontalalignment='right', bbox=props)
            
    plot_and_label(df_sarsa, axes[0], "SARSA")
    plot_and_label(df_mrhof, axes[1], "MRHOF")

    axes[0].set_ylabel("Battery %", fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_OF_battery_comparison.png"), dpi=300)
    print("Saved: plot_OF_battery_comparison.png")

def plot_evaluate_qvalues(df_eval):
    """Plots the continuously calculated Q-values during action selection."""
    if df_eval.empty:
        print("No EVALUATE logs found. Skipping Dynamic Q-Value plot.")
        return
        
    plt.figure(figsize=(12, 6))
    
    # Group by the specific parent link and draw lines
    for (node, par), group in df_eval.groupby(['node', 'par']):
        grp = group.copy()
        # Using a line plot here so you can see the continuous shifts based on global weights!
        plt.plot(grp['ts_mins'], grp['q_val'], label=f'Evaluated: Node {node} -> {par}', linewidth=2, alpha=0.8)
        
    plt.title('Dynamic Q-Value Evaluations Over Time (From best_parent)')
    plt.xlabel('Simulation Time (Minutes)')
    plt.ylabel('Calculated Q-Value')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_sarsa_evaluated_qvalues.png"), dpi=300)
    print("Saved: plot_sarsa_evaluated_qvalues.png")

def plot_sarsa_learning(df_math, df_wght):
    if df_math.empty or df_wght.empty:
        print("No SARSA internal logs found. Skipping ML plots.")
        return
        
    # Plot 1: Weights
    plt.figure(figsize=(12, 6))
    colors = ['blue', 'green', 'purple', 'orange']
    for i, node in enumerate(sorted(df_wght['node'].unique())):
        nd = df_wght[df_wght['node'] == node].copy()
        c = colors[i % len(colors)]
        plt.plot(nd['ts_mins'], nd['w_lq'], label=f'Node {node} W_LQ', color=c, linestyle='-', linewidth=2)
        plt.plot(nd['ts_mins'], nd['w_eng'], label=f'Node {node} W_ENG', color=c, linestyle='--', linewidth=2)
        
    plt.title('SARSA Policy Weights Over Time (Per Node)')
    plt.xlabel('Simulation Time (Minutes)')
    plt.ylabel('Weight Value')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_sarsa_weights.png"), dpi=300)
    print("Saved: plot_sarsa_weights.png")
    
    # Plot 2: TD Error
    plt.figure(figsize=(12, 6))
    for node in sorted(df_math['node'].unique()):
        nd = df_math[df_math['node'] == node].copy()
        plt.plot(nd['ts_mins'], nd['err'], label=f'Node {node} TD Error (δ)', alpha=0.7, marker='.', markersize=4)
        
    plt.axhline(0, color='black', linestyle='--', linewidth=2)
    plt.title('Temporal Difference (TD) Error Convergence (Per Node)')
    plt.xlabel('Simulation Time (Minutes)')
    plt.ylabel('TD Error Value')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_sarsa_tderror.png"), dpi=300)
    print("Saved: plot_sarsa_tderror.png")

    # Plot 3: Q-Values (Learning Updates ONLY)
    plt.figure(figsize=(12, 6))
    for (node, par), group in df_math.groupby(['node', 'par']):
        grp = group.copy()
        plt.plot(grp['ts_mins'], grp['curQ'], label=f'Update: Node {node} -> {par}', linewidth=2, marker='.', markersize=6)
        
    plt.title('SARSA Action-Values (Learning Updates ONLY)')
    plt.xlabel('Simulation Time (Minutes)')
    plt.ylabel('Q-Value (Reward Prediction)')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(SCRIPT_DIR, "plot_sarsa_qvalues.png"), dpi=300)
    print("Saved: plot_sarsa_qvalues.png")

# ==========================================
# 3. EXECUTION & REPORTING
# ==========================================

if __name__ == "__main__":
    print("--- Parsing A/B Test Logs ---\n")
    
    sarsa_batt = extract_battery_samples(LOG_FILE_SARSA)
    mrhof_batt = extract_battery_samples(LOG_FILE_MRHOF)
    
    sarsa_math, sarsa_wght = extract_sarsa_internals(LOG_FILE_SARSA)
    sarsa_eval = extract_evaluate_qvalues(LOG_FILE_SARSA) # <-- NEW EXTRACTOR

    sarsa_sent = sum(extract_throughput(LOG_FILE_SARSA).values())
    mrhof_sent = sum(extract_throughput(LOG_FILE_MRHOF).values())
    
    sarsa_rec = extract_sink_receives(LOG_FILE_SARSA)
    mrhof_rec = extract_sink_receives(LOG_FILE_MRHOF)

    print("=== A/B TEST RESULTS ===")
    
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
        
    print("\n[ Packet Delivery Ratio (PDR) ]")
    if sarsa_sent > 0:
        print(f"SARSA PDR: {(sarsa_rec / sarsa_sent) * 100:.2f}% ({sarsa_rec}/{sarsa_sent})")
    if mrhof_sent > 0:
        print(f"MRHOF PDR: {(mrhof_rec / mrhof_sent) * 100:.2f}% ({mrhof_rec}/{mrhof_sent})")
    
    print("========================\n")

    if SARSA_PLOT:
            plot_sarsa_learning(sarsa_math, sarsa_wght)
            plot_evaluate_qvalues(sarsa_eval) # <-- NEW PLOTTER
            
    if BATTERY_PLOT:
            plot_battery_comparison(sarsa_batt, mrhof_batt)

    print("Done!")