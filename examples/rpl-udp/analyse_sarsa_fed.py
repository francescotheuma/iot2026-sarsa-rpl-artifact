#!/usr/bin/env python3
"""
analyse_sarsa.py — SARSA & Federated learning behaviour analysis

Set `COMPARISON_TARGET` at the top of the file to either 'MRHOF' or 'FEDERATED'.
"""

import re
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ─── Constants ───────────────────────────────────────────────────────────────
ALPHA       = 10
GAMMA       = 80
MAX_WEIGHT  = 1000
MIN_WEIGHT  = -1000
INIT_W_LQ   = 50
INIT_W_ENG  = 50
SARSA_HYSTERESIS = 8

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG   = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")
DEFAULT_MRHOF = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_mrhof.log")
DEFAULT_FED   = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_fed.log")

COMPARISON_TARGET = 'FEDERATED'

# ─── Parsers (Relaxed to catch SARSA-MATH, FED-MATH, or just MATH) ────────────
_MATH_RE = re.compile(r'^\s*(\d+)\s+ID:(\d+).*?MATH \| Par: (\d+) \| curQ: (-?\d+) \| rew: (-?\d+) \| futQ: (-?\d+) \| tgt: (-?\d+) \| err: (-?\d+)')
_WGHT_RE = re.compile(r'^\s*(\d+)\s+ID:(\d+).*?WGHT \| f_lq: (-?\d+) \| f_eng: (-?\d+) \| W_LQ: (-?\d+) \| W_ENG: (-?\d+)')
_EVAL_RE = re.compile(r'^\s*(?P<ts>\d+)\s+ID:(?P<node>\d+).*?EVALUATE: P1: (?P<p1>\d+) \(Q: (?P<q1>-?\d+)\) vs P2: (?P<p2>\d+) \(Q: (?P<q2>-?\d+)\) -> CHOSE: (?P<chose>\d+)')
_BATT_RE = re.compile(r'^\s*(\d+)\s+ID:(\d+).*?BATTERY_SAMPLE:\s*node=(\d+),\s*batt=(\d+),\s*TX=(\d+),\s*RX=\d+,\s*CPU=(\d+)')

COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#E91E63']

def parse_log(filepath):
    math_rows, wght_rows, eval_rows, batt_rows = [], [], [], []
    with open(filepath) as f:
        for line in f:
            m = _MATH_RE.search(line)
            if m:
                math_rows.append({'ts': int(m.group(1)), 'node': int(m.group(2)), 'par': int(m.group(3)), 'curQ': int(m.group(4)), 'rew': int(m.group(5)), 'futQ': int(m.group(6)), 'tgt': int(m.group(7)), 'err':  int(m.group(8))})
                continue
            w = _WGHT_RE.search(line)
            if w:
                wght_rows.append({'ts': int(w.group(1)), 'node': int(w.group(2)), 'f_lq': int(w.group(3)), 'f_eng': int(w.group(4)), 'W_LQ': int(w.group(5)), 'W_ENG': int(w.group(6))})
                continue
            e = _EVAL_RE.search(line)
            if e:
                eval_rows.append({'ts': int(e.group('ts')), 'node': int(e.group('node')), 'p1': int(e.group('p1')), 'q1': int(e.group('q1')), 'p2': int(e.group('p2')), 'q2': int(e.group('q2')), 'chose': int(e.group('chose'))})
                continue
            b = _BATT_RE.search(line)
            if b:
                batt_rows.append({'ts': int(b.group(1)), 'node': int(b.group(3)), 'batt': int(b.group(4)), 'tx': int(b.group(5)), 'cpu': int(b.group(6))})
    return pd.DataFrame(math_rows), pd.DataFrame(wght_rows), pd.DataFrame(eval_rows), pd.DataFrame(batt_rows)

# ─── Plots ───────────────────────────────────────────────────────────────────

def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"    -> Saved: {os.path.basename(path)}")

def plot_weights(df_wght, outdir, prefix='', label=''):
    if df_wght.empty: return
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for i, node in enumerate(sorted(df_wght['node'].unique())):
        nd = df_wght[df_wght['node'] == node]
        t = nd['ts'] / 60_000_000
        c = COLORS[i % len(COLORS)]
        ax1.plot(t, nd['W_LQ'], color=c, linestyle='-', linewidth=2, label=f'Node {node} W_LQ')
        ax1.plot(t, nd['W_ENG'], color=c, linestyle='--', linewidth=2, label=f'Node {node} W_ENG')
        ax2.plot(t, nd['f_lq'], color=c, linestyle='-', linewidth=1.5, alpha=0.8, label=f'Node {node} f_lq')
        ax2.plot(t, nd['f_eng'], color=c, linestyle='--', linewidth=1.5, alpha=0.8, label=f'Node {node} f_eng')
    ax1.axhline(INIT_W_LQ, color='black', linestyle=':', alpha=0.4)
    ax1.set_title(f'[{label}] Policy Weights Over Time', fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.4); ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    ax2.set_title(f'[{label}] Feature Signals Seen', fontweight='bold')
    ax2.set_xlabel('Simulation Time (mins)'); ax2.set_ylim(-5, 105)
    ax2.grid(True, linestyle='--', alpha=0.4); ax2.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    _save(fig, os.path.join(outdir, f'{prefix}analysis_weights.png'))

def plot_td_error(df_math, outdir, prefix='', label=''):
    if df_math.empty: return
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, node in enumerate(sorted(df_math['node'].unique())):
        nd = df_math[df_math['node'] == node].copy()
        t = nd['ts'] / 60_000_000
        c = COLORS[i % len(COLORS)]
        ax.scatter(t, nd['err'], color=c, s=25, alpha=0.5)
        ax.plot(t, nd['err'].rolling(min(5, len(nd)), min_periods=1).mean(), color=c, linewidth=2, label=f'Node {node}')
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5)
    ax.set_title(f'[{label}] TD Error (δ) Over Time', fontweight='bold')
    ax.set_xlabel('Simulation Time (mins)'); ax.set_ylabel('TD Error')
    ax.legend(); ax.grid(True, linestyle='--', alpha=0.4)
    _save(fig, os.path.join(outdir, f'{prefix}analysis_td_error.png'))

def plot_qvalues(df_eval, outdir, prefix='', label=''):
    if df_eval.empty: return
    records = []
    for _, r in df_eval.iterrows():
        records.append({'ts': r['ts'], 'node': r['node'], 'par': r['p1'], 'q': r['q1']})
        records.append({'ts': r['ts'], 'node': r['node'], 'par': r['p2'], 'q': r['q2']})
    df = pd.DataFrame(records)
    nodes = sorted(df['node'].unique())
    fig, axes = plt.subplots(len(nodes), 1, figsize=(14, 5 * len(nodes)), squeeze=False)
    for ax, node in zip(axes[:, 0], nodes):
        nd = df[df['node'] == node]
        for j, par in enumerate(sorted(nd['par'].unique())):
            grp = nd[nd['par'] == par]
            ax.plot(grp['ts'] / 60_000_000, grp['q'], color=COLORS[j % len(COLORS)], linewidth=1.5, alpha=0.8, label=f'→ parent {par}')
        ax.set_title(f'[{label}] Node {node}: Q-Values', fontweight='bold')
        ax.set_xlabel('Simulation Time (mins)'); ax.set_ylabel('Q-Value')
        ax.legend(); ax.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, f'{prefix}analysis_qvalues.png'))

def plot_reward_quality(df_math, outdir, prefix='', label=''):
    if df_math.empty: return
    nodes = sorted(df_math['node'].unique())
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=False)
    for i, node in enumerate(nodes):
        nd = df_math[df_math['node'] == node].copy()
        t = nd['ts'] / 60_000_000
        w = min(7, len(nd))
        ax1.plot(t, nd['rew'].rolling(w, min_periods=1).mean(), color=COLORS[i % len(COLORS)], linewidth=2, label=f'Node {node}')
        ax2.plot(t, (nd['rew'] < 0).rolling(w, min_periods=1).mean() * 100, color=COLORS[i % len(COLORS)], linewidth=2, label=f'Node {node}')
    ax1.set_title(f'[{label}] Rolling Mean Reward Over Time', fontweight='bold'); ax1.legend(); ax1.grid(True, linestyle='--', alpha=0.4)
    ax2.set_title(f'[{label}] Rolling % of Failed-TX Rewards', fontweight='bold'); ax2.set_xlabel('Simulation Time (mins)'); ax2.legend(); ax2.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, f'{prefix}analysis_reward_quality.png'))

def plot_q_vs_energy(df_eval, df_batt, outdir, prefix='', label=''):
    if df_eval.empty or df_batt.empty: return
    records = []
    for node in sorted(df_eval['node'].unique()):
        ev = df_eval[df_eval['node'] == node].copy()
        ev = ev[ev['p1'] != ev['p2']].sort_values('ts')
        for _, r in ev.iterrows():
            def batt_at(par_node, ts):
                pb = df_batt[df_batt['node'] == par_node]
                return pb.loc[(pb['ts'] - ts).abs().idxmin(), 'batt'] if not pb.empty else None
            b1, b2 = batt_at(r['p1'], r['ts']), batt_at(r['p2'], r['ts'])
            if b1 is not None and b2 is not None:
                records.append({'node': node, 'dQ': r['q1'] - r['q2'], 'dBatt': b1 - b2})
    if not records: return
    df = pd.DataFrame(records)
    fig, ax = plt.subplots(figsize=(9, 7))
    for i, node in enumerate(sorted(df['node'].unique())):
        nd = df[df['node'] == node]
        ax.scatter(nd['dBatt'], nd['dQ'], c=COLORS[i % len(COLORS)], s=25, alpha=0.6, label=f'Node {node}')
    ax.axhline(0, color='black'); ax.axvline(0, color='black')
    ax.set_title(f'[{label}] Energy Responsiveness', fontweight='bold'); ax.legend(); ax.grid(True, linestyle='--', alpha=0.4)
    _save(fig, os.path.join(outdir, f'{prefix}analysis_q_vs_energy.png'))

def plot_parent_switches(df_eval, df_batt, outdir, prefix='', label=''):
    if df_eval.empty: return
    nodes = sorted(df_eval['node'].unique())
    fig, axes = plt.subplots(len(nodes), 1, figsize=(14, 5 * len(nodes)), squeeze=False)
    for ax_row, node in zip(axes[:, 0], nodes):
        ev = df_eval[(df_eval['node'] == node) & (df_eval['p1'] != df_eval['p2'])].sort_values('ts')
        if ev.empty: continue
        all_pars = sorted(set(ev['p1'].tolist() + ev['p2'].tolist()))
        par_pos = {p: i for i, p in enumerate(all_pars)}
        ax_row.step(ev['ts'] / 60_000_000, [par_pos[c] for c in ev['chose']], where='post', color='black', linewidth=2, label='Chosen parent')
        ax_row.set_yticks(list(par_pos.values())); ax_row.set_yticklabels([f'Node {p}' for p in par_pos])
        ax_row.set_title(f'[{label}] Node {node}: Parent Choice Over Time', fontweight='bold')
        ax_row.grid(True, linestyle='--', alpha=0.3); ax_row.legend(loc='upper left')
        if not df_batt.empty:
            ax2 = ax_row.twinx()
            for j, par in enumerate(all_pars):
                pb = df_batt[df_batt['node'] == par].sort_values('ts')
                if not pb.empty: ax2.plot(pb['ts'] / 60_000_000, pb['batt'], color=COLORS[j % len(COLORS)], linestyle='--', alpha=0.7)
            ax2.set_ylabel('Battery %'); ax2.set_ylim(0, 110)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, f'{prefix}analysis_parent_switch.png'))

def plot_ticks_over_time(df_batt, outdir, prefix='', label=''):
    if df_batt.empty or 'tx' not in df_batt.columns: return
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for i, node in enumerate(sorted(df_batt['node'].unique())):
        nd = df_batt[df_batt['node'] == node].sort_values('ts')
        t = nd['ts'] / 60_000_000
        ax1.plot(t, nd['tx'], color=COLORS[i % len(COLORS)], linewidth=2, label=f'Node {node}')
        ax2.plot(t, nd['cpu'], color=COLORS[i % len(COLORS)], linewidth=2, label=f'Node {node}')
    ax1.set_title(f'[{label}] Cumulative TX Ticks', fontweight='bold'); ax1.grid(True, linestyle='--', alpha=0.4); ax1.legend()
    ax2.set_title(f'[{label}] Cumulative CPU Ticks', fontweight='bold'); ax2.grid(True, linestyle='--', alpha=0.4); ax2.legend()
    plt.tight_layout()
    _save(fig, os.path.join(outdir, f'{prefix}analysis_ticks.png'))

# --- SIDE-BY-SIDE COMPARISON PLOTS ---

def plot_battery_comparison(df_sarsa, df_compare, compare_label, outdir):
    if df_sarsa.empty or df_compare.empty: return
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    
    def _panel(df, ax, title):
        ax.set_title(title, fontsize=13, fontweight='bold')
        for i, node in enumerate(sorted(df['node'].unique())):
            if node == 1: continue # Usually the sink doesn't drain battery
            nd = df[df['node'] == node].sort_values('ts')
            t = nd['ts'] / 60_000_000
            line, = ax.plot(t, nd['batt'], color=COLORS[i % len(COLORS)], linewidth=2, label=f'Node {node}')
            
            # Annotate final battery values directly on the line
            if not nd.empty:
                final_t = t.iloc[-1]
                final_batt = nd['batt'].iloc[-1]
                ax.annotate(f'{final_batt}%', xy=(final_t, final_batt), 
                            xytext=(4, 0), textcoords='offset points',
                            color=line.get_color(), fontweight='bold', va='center')
                            
        ax.set_xlabel('Time (mins)', fontweight='bold')
        ax.legend(loc='lower left', framealpha=0.8)
        ax.grid(True, linestyle='--', alpha=0.4)
        
    _panel(df_sarsa, axes[0], 'SARSA Battery Depletion')
    _panel(df_compare, axes[1], f'{compare_label} Battery Depletion')
    axes[0].set_ylabel('Battery %', fontweight='bold')
    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_battery_comparison.png'))

def plot_weights_comparison(df_wght_a, df_wght_b, label_a, label_b, outdir):
    if df_wght_a.empty or df_wght_b.empty: return
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    
    def _panel(df, ax, title):
        for i, node in enumerate(sorted(df['node'].unique())):
            nd = df[df['node'] == node]
            t = nd['ts'] / 60_000_000
            c = COLORS[i % len(COLORS)]
            ax.plot(t, nd['W_LQ'], color=c, linestyle='-', linewidth=2, label=f'Node {node} W_LQ')
            ax.plot(t, nd['W_ENG'], color=c, linestyle='--', linewidth=2, label=f'Node {node} W_ENG')
        ax.axhline(INIT_W_LQ, color='black', linestyle=':', alpha=0.4)
        ax.set_title(title, fontweight='bold')
        ax.set_xlabel('Time (mins)')
        ax.grid(True, linestyle='--', alpha=0.4)
        
    _panel(df_wght_a, axes[0], f'{label_a} Weights')
    _panel(df_wght_b, axes[1], f'{label_b} Weights')
    axes[0].set_ylabel('Weight Value')
    axes[0].legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_weights_comparison.png'))


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log_path      = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    compare_path  = sys.argv[2] if len(sys.argv) > 2 else (DEFAULT_MRHOF if COMPARISON_TARGET == 'MRHOF' else DEFAULT_FED)
    compare_label = 'MRHOF' if COMPARISON_TARGET == 'MRHOF' else 'FEDERATED'
    out_dir       = os.path.join(os.path.dirname(os.path.abspath(log_path)) if len(sys.argv) > 1 else SCRIPT_DIR, "plots")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Loading Base SARSA log : {log_path}")
    print(f"Loading Comparison log : {compare_path}\n")

    df_math, df_wght, df_eval, df_batt = parse_log(log_path)
    
    if df_math.empty and df_batt.empty:
        print("ERROR: Base SARSA log is empty or could not be parsed.")
        sys.exit(1)

    df_compare_math, df_compare_wght, df_compare_eval, df_compare_batt = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if os.path.exists(compare_path):
        df_compare_math, df_compare_wght, df_compare_eval, df_compare_batt = parse_log(compare_path)

    def generate_standard_plots(m_df, w_df, e_df, b_df, prefix, label):
        print(f"\n--- Generating {label} plots (saving as {prefix}*.png) ---")
        if m_df.empty: print(f"  [WARN] No MATH data found for {label}. Skipping Math plots.")
        if e_df.empty: print(f"  [WARN] No EVALUATE data found for {label}. Skipping Parent/Q plots.")
        
        plot_weights(w_df, out_dir, prefix, label)
        plot_td_error(m_df, out_dir, prefix, label)
        plot_qvalues(e_df, out_dir, prefix, label)
        plot_reward_quality(m_df, out_dir, prefix, label)
        plot_q_vs_energy(e_df, b_df, out_dir, prefix, label)
        plot_parent_switches(e_df, b_df, out_dir, prefix, label)
        plot_ticks_over_time(b_df, out_dir, prefix, label)

    # 1. Base SARSA Plots
    generate_standard_plots(df_math, df_wght, df_eval, df_batt, prefix='sarsa_', label='SARSA')

    # 2. Federated/MRHOF Plots
    if COMPARISON_TARGET == 'FEDERATED':
        generate_standard_plots(df_compare_math, df_compare_wght, df_compare_eval, df_compare_batt, prefix='federated_', label='FEDERATED')
        
        # Add back the Side-by-Side Weight Comparison if both exist
        print("\n--- Generating Side-by-Side Comparisons ---")
        plot_weights_comparison(df_wght, df_compare_wght, 'SARSA', 'FEDERATED', out_dir)
    else:
        print(f"\n--- Generating {compare_label} plots (saving as mrhof_*.png) ---")
        plot_ticks_over_time(df_compare_batt, out_dir, prefix='mrhof_', label='MRHOF')

    # 3. Add back the Side-by-Side Battery Comparison!
    plot_battery_comparison(df_batt, df_compare_batt, compare_label, out_dir)

    print("\n✅ All plot generations completed.")