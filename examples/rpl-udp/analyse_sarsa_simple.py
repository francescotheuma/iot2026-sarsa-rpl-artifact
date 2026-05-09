import pandas as pd
import matplotlib.pyplot as plt
import re
import os


SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SARSA_LOG   = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
MRHOF_LOG = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")
FED_LOG   = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_fed.log")

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "plots")

# ==============
# CONFIGURATION 
# ==============
CHOICE = 'FED'

if(CHOICE == 'MRHOF'):
    LOG_FILE_1 = MRHOF_LOG
    LABEL_1    = 'MRHOF'
elif(CHOICE == 'SARSA'):
    LOG_FILE_1 = SARSA_LOG
    LABEL_1    = 'SARSA'
elif(CHOICE == 'FED'):
    LOG_FILE_1 = FED_LOG
    LABEL_1    = 'Federated SARSA'

# Set ENABLE_COMPARISON to True to plot two logs side-by-side
ENABLE_COMPARISON = False
LOG_FILE_2 = FED_LOG
LABEL_2    = 'FEDERATED SARSA'

SHOW_DEATH_ANNOTATIONS = True

# ==========================================

def parse_battery_data(filename):
    data = []
    if not os.path.exists(filename):
        print(f"Error: File {filename} not found.")
        return pd.DataFrame()
    with open(filename, 'r') as f:
        for line in f:
            if 'BATTERY_SAMPLE' in line:
                # Format: BATTERY_SAMPLE: node=X, batt=Y, TX=A, RX=B, CPU=C
                m = re.search(r'^(\d+)\s+ID:(\d+).*node=(\d+), batt=(\d+), TX=(\d+), RX=(\d+), CPU=(\d+)', line)
                if m:
                    ts = int(m.group(1))
                    node = int(m.group(3))
                    batt = int(m.group(4))
                    tx = int(m.group(5))
                    cpu = int(m.group(7))
                    data.append({'ts': ts, 'node': node, 'batt': batt, 'tx': tx, 'cpu': cpu})
    return pd.DataFrame(data)

def add_custom_elements(ax, df):
    """Adds staggered death times, end-of-run battery, and the TX/CPU legend."""
    
    # 1. Colors & Nodes setup
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']
    all_nodes = sorted(df['node'].unique())
    node_to_color = {node_id: colors[i % len(colors)] for i, node_id in enumerate(all_nodes)}

    # 2. Death Time Labels (Staggered to prevent overlap)
    dead_nodes = df[df['batt'] == 0]
    if not dead_nodes.empty:
        # Get the first timestamp each node hit 0
        first_deaths = dead_nodes.sort_values('ts').groupby('node').first().reset_index()
        # Sort by timestamp so the boxes stack in order of death
        first_deaths = first_deaths.sort_values('ts')
        
        for i, row in first_deaths.iterrows():
            mins = row['ts'] / 60000000
            node_id = int(row['node'])
            color = node_to_color[node_id]
            
            # STAGGER LOGIC: 
            # The first node to die is at height -4, the second at -10, third at -16, etc.
            y_offset = -4 - (i * 6) 

            ax.annotate(
                f'Node {node_id}: {mins:.2f}m',
                xy=(mins, 0),             # Point the arrow to the exact death time (0% battery)
                xytext=(mins, y_offset),  # Place the text box at the unique staggered height
                color='white', 
                fontweight='bold',
                ha='center', 
                va='top', 
                fontsize=8,
                bbox=dict(
                    facecolor=color, 
                    alpha=0.9, 
                    edgecolor='none', 
                    boxstyle='round,pad=0.3'
                ),
                arrowprops=dict(
                    arrowstyle='->', 
                    color=color, 
                    lw=1, 
                    shrinkA=0, 
                    shrinkB=0
                )
            )

    # 3. End-of-Line Battery Labels (For all nodes)
    last_samples = df.sort_values('ts').groupby('node').last().reset_index()
    tx_cpu_handles = []
    
    for _, row in last_samples.iterrows():
        mins = row['ts'] / 60000000
        batt = int(row['batt'])
        node_id = int(row['node'])
        color = node_to_color[node_id]
        
        # Battery % label at the end of the depletion line
        ax.text(mins + 0.2, batt, f'{batt}%', color=color, fontweight='bold',
                va='center', ha='left', fontsize=9)
        
        # Create a legend proxy for TX/CPU stats
        info_label = f"N{node_id}: TX={row['tx']:,} | CPU={row['cpu']:,}"
        proxy = plt.Line2D([0], [0], color=color, lw=2, label=info_label)
        tx_cpu_handles.append(proxy)

    # 4. Handle Legends
    # Primary Legend (Node IDs) -> Bottom Left
    primary_legend = ax.legend(loc='lower left', fontsize='small', title="Nodes", ncol=2)
    ax.add_artist(primary_legend)
    
    # Secondary Legend (TX/CPU Stats) -> Top Right
    ax.legend(handles=tx_cpu_handles, loc='upper right', fontsize='x-small', 
              title="Cumulative Ticks", framealpha=0.8)

def plot_single(df, label):
    if df.empty: return
    fig, ax = plt.subplots(figsize=(10, 7))
    
    for node_id in sorted(df['node'].unique()):
        node_df = df[df['node'] == node_id].sort_values('ts')
        ax.plot(node_df['ts'] / 60000000, node_df['batt'], label=f'Node {int(node_id)}', lw=1.5)
    
    add_custom_elements(ax, df)
    
    ax.set_title(f'Battery Depletion & Load Analysis - {label}', pad=25)
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Battery %')
    ax.set_ylim(-15, 105)
    # Ensure there is enough space on the right for the % labels
    ax.set_xlim(left=0, right=ax.get_xlim()[1] * 1.1)
    ax.grid(True, alpha=0.3)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(os.path.join(OUTPUT_DIR, f"single_{label.lower().replace(' ', '_')}.png"), bbox_inches='tight')
    plt.close()

def plot_compare(df1, lbl1, df2, lbl2):
    if df1.empty or df2.empty: return
    fig, axes = plt.subplots(1, 2, figsize=(20, 8), sharey=True)
    
    for ax, df, lbl in zip(axes, [df1, df2], [lbl1, lbl2]):
        for node_id in sorted(df['node'].unique()):
            node_df = df[df['node'] == node_id].sort_values('ts')
            ax.plot(node_df['ts'] / 60000000, node_df['batt'], label=f'Node {int(node_id)}', lw=1.5)
        
        add_custom_elements(ax, df)
        ax.set_title(lbl, fontweight='bold', pad=20)
        ax.set_xlabel('Time (minutes)')
        ax.set_xlim(left=0, right=ax.get_xlim()[1] * 1.12)
        ax.grid(True, alpha=0.3)
    
    axes[0].set_ylabel('Battery Percentage (%)')
    plt.ylim(-15, 105)
    plt.tight_layout()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"compare_{lbl1.lower()}_vs_{lbl2.lower()}.png".replace(' ', '_')
    plt.savefig(os.path.join(OUTPUT_DIR, filename), bbox_inches='tight')
    plt.close()
    print(f"Comparison plot saved: {OUTPUT_DIR}/{filename}")


if __name__ == '__main__':
    df1 = parse_battery_data(LOG_FILE_1)
    if not df1.empty: plot_single(df1, LABEL_1)
    
    if ENABLE_COMPARISON:
        df2 = parse_battery_data(LOG_FILE_2)
        if not df2.empty:
            plot_single(df2, LABEL_2)
            plot_compare(df1, LABEL_1, df2, LABEL_2)