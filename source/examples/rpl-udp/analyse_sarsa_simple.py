import pandas as pd
import matplotlib.pyplot as plt
import re
import os


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SARSA_LOG = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
MRHOF_LOG = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")
FED_LOG = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_fed.log")

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "plots")

# ==============
# CONFIGURATION
# ==============
CHOICE = 'SARSA'

if CHOICE == 'MRHOF':
    LOG_FILE_1 = MRHOF_LOG
    LABEL_1 = 'MRHOF'
elif CHOICE == 'SARSA':
    LOG_FILE_1 = SARSA_LOG
    LABEL_1 = 'SARSA'
elif CHOICE == 'FED':
    LOG_FILE_1 = FED_LOG
    LABEL_1 = 'Federated SARSA'
else:
    raise ValueError(f"Unknown CHOICE: {CHOICE}")

# Set ENABLE_COMPARISON to True to plot two logs side-by-side
ENABLE_COMPARISON = False
LOG_FILE_2 = FED_LOG
LABEL_2 = 'FEDERATED SARSA'

SHOW_DEATH_ANNOTATIONS = True

# ==========================================


def format_sim_time(ts):
    """
    Convert a Cooja timestamp in microseconds to:
    - true decimal miunutes for display
    - decimal minutes for plotting on x-axis
    """
    decimal_minutes = ts / 60_000_000
    return f"{decimal_minutes:.3f} min", decimal_minutes


def parse_battery_data(filename):
    """
    Parses:
    1. BATTERY_SAMPLE lines for the plotted battery curves.
    2. Battery depleted lines for exact death annotations.

    Returns:
    - df: battery sample dataframe
    - death_df: exact battery depletion dataframe
    """
    data = []
    deaths = []

    if not os.path.exists(filename):
        print(f"Error: File {filename} not found.")
        return pd.DataFrame(), pd.DataFrame()

    with open(filename, 'r') as f:
        for line in f:
            if 'BATTERY_SAMPLE' in line:
                # Format:
                # 123456 ID:4 [INFO: Battery] BATTERY_SAMPLE: node=4, batt=0, TX=..., RX=..., CPU=...
                m = re.search(
                    r'^(\d+)\s+ID:(\d+).*node=(\d+), batt=(\d+), TX=(\d+), RX=(\d+), CPU=(\d+)',
                    line
                )

                if m:
                    ts = int(m.group(1))
                    node = int(m.group(3))
                    batt = int(m.group(4))
                    tx = int(m.group(5))
                    rx = int(m.group(6))
                    cpu = int(m.group(7))

                    data.append({
                        'ts': ts,
                        'node': node,
                        'batt': batt,
                        'tx': tx,
                        'rx': rx,
                        'cpu': cpu
                    })

            elif 'Battery depleted. Shutting down node.' in line:
                # Format:
                # 1857047454 ID:3 [INFO: Battery] Battery depleted. Shutting down node.
                m = re.search(r'^(\d+)\s+ID:(\d+).*Battery depleted', line)

                if m:
                    ts = int(m.group(1))
                    node = int(m.group(2))

                    deaths.append({
                        'ts': ts,
                        'node': node
                    })

    return pd.DataFrame(data), pd.DataFrame(deaths)


def get_first_deaths(df, death_df=None):
    """
    Uses exact Battery depleted lines if available.
    Falls back to first BATTERY_SAMPLE with batt=0.
    """
    if death_df is not None and not death_df.empty:
        first_deaths = (
            death_df
            .sort_values('ts')
            .groupby('node')
            .first()
            .reset_index()
            .sort_values('ts')
        )
        first_deaths['source'] = 'depletion_log'
        return first_deaths

    dead_nodes = df[df['batt'] == 0]

    if dead_nodes.empty:
        return pd.DataFrame()

    first_deaths = (
        dead_nodes
        .sort_values('ts')
        .groupby('node')
        .first()
        .reset_index()
        .sort_values('ts')
    )
    first_deaths['source'] = 'battery_sample'
    return first_deaths


def add_custom_elements(ax, df, death_df=None):
    """
    Adds:
    - exact death time annotations
    - end-of-line battery labels
    - TX/CPU legend
    """
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']

    all_nodes = sorted(df['node'].unique())
    node_to_color = {
        node_id: colors[i % len(colors)]
        for i, node_id in enumerate(all_nodes)
    }

    # 1. Death Time Labels
    if SHOW_DEATH_ANNOTATIONS:
        first_deaths = get_first_deaths(df, death_df)

        if not first_deaths.empty:
            for label_index, row in enumerate(first_deaths.itertuples(index=False)):
                node_id = int(row.node)

                if node_id not in node_to_color:
                    continue

                color = node_to_color[node_id]
                label_time, x_mins = format_sim_time(int(row.ts))

                # Stagger labels vertically to prevent overlap
                y_offset = -4 - (label_index * 6)

                ax.annotate(
                    f'Node {node_id}: {label_time}',
                    xy=(x_mins, 0),
                    xytext=(x_mins, y_offset),
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

    # 2. End-of-Line Battery Labels
    last_samples = (
        df
        .sort_values('ts')
        .groupby('node')
        .last()
        .reset_index()
    )

    tx_cpu_handles = []

    for _, row in last_samples.iterrows():
        mins = row['ts'] / 60_000_000
        batt = int(row['batt'])
        node_id = int(row['node'])
        color = node_to_color[node_id]

        ax.text(
            mins + 0.2,
            batt,
            f'{batt}%',
            color=color,
            fontweight='bold',
            va='center',
            ha='left',
            fontsize=9
        )

        info_label = f"N{node_id}: TX={int(row['tx']):,} | CPU={int(row['cpu']):,}"
        proxy = plt.Line2D([0], [0], color=color, lw=2, label=info_label)
        tx_cpu_handles.append(proxy)

    # 3. Legends
    primary_legend = ax.legend(
        loc='lower left',
        fontsize='small',
        title="Nodes",
        ncol=2
    )
    ax.add_artist(primary_legend)

    ax.legend(
        handles=tx_cpu_handles,
        loc='upper right',
        fontsize='x-small',
        title="Cumulative Ticks",
        framealpha=0.8
    )


def plot_single(df, label, death_df=None):
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 7))

    for node_id in sorted(df['node'].unique()):
        node_df = df[df['node'] == node_id].sort_values('ts')
        ax.plot(
            node_df['ts'] / 60_000_000,
            node_df['batt'],
            label=f'Node {int(node_id)}',
            lw=1.5
        )

    add_custom_elements(ax, df, death_df)

    ax.set_title(f'Battery Depletion & Load Analysis - {label}', pad=25)
    ax.set_xlabel('Time (minutes)')
    ax.set_ylabel('Battery %')
    ax.set_ylim(-15, 105)

    # Ensure there is enough space on the right for the % labels
    ax.set_xlim(left=0, right=ax.get_xlim()[1] * 1.1)

    ax.grid(True, alpha=0.3)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_path = os.path.join(
        OUTPUT_DIR,
        f"single_{label.lower().replace(' ', '_')}.png"
    )

    plt.savefig(output_path, bbox_inches='tight')
    plt.close()

    print(f"Single plot saved: {output_path}")


def plot_compare(df1, lbl1, deaths1, df2, lbl2, deaths2):
    if df1.empty or df2.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(20, 8), sharey=True)

    for ax, df, lbl, death_df in zip(
        axes,
        [df1, df2],
        [lbl1, lbl2],
        [deaths1, deaths2]
    ):
        for node_id in sorted(df['node'].unique()):
            node_df = df[df['node'] == node_id].sort_values('ts')
            ax.plot(
                node_df['ts'] / 60_000_000,
                node_df['batt'],
                label=f'Node {int(node_id)}',
                lw=1.5
            )

        add_custom_elements(ax, df, death_df)

        ax.set_title(lbl, fontweight='bold', pad=20)
        ax.set_xlabel('Time (minutes)')
        ax.set_xlim(left=0, right=ax.get_xlim()[1] * 1.12)
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel('Battery Percentage (%)')

    plt.ylim(-15, 105)
    plt.tight_layout()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filename = f"compare_{lbl1.lower()}_vs_{lbl2.lower()}.png".replace(' ', '_')
    output_path = os.path.join(OUTPUT_DIR, filename)

    plt.savefig(output_path, bbox_inches='tight')
    plt.close()

    print(f"Comparison plot saved: {output_path}")


if __name__ == '__main__':
    df1, deaths1 = parse_battery_data(LOG_FILE_1)

    if not df1.empty:
        plot_single(df1, LABEL_1, deaths1)
    else:
        print(f"No battery data parsed from {LOG_FILE_1}")

    if ENABLE_COMPARISON:
        df2, deaths2 = parse_battery_data(LOG_FILE_2)

        if not df2.empty:
            plot_single(df2, LABEL_2, deaths2)
            plot_compare(df1, LABEL_1, deaths1, df2, LABEL_2, deaths2)
        else:
            print(f"No battery data parsed from {LOG_FILE_2}")