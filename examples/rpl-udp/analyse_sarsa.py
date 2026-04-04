#!/usr/bin/env python3
"""
analyse_sarsa.py — SARSA learning behaviour analysis for Contiki-NG/Cooja logs.

Usage:
    python3 analyse_sarsa.py                        # uses tools/cooja/cooja_sarsa.log
    python3 analyse_sarsa.py path/to/cooja.log      # analyse a specific log

Answers three questions:
  A) Is the arithmetic correct?
       - err == tgt - curQ  (every update)
       - weight deltas match ALPHA * err * feature / 10000  (with clipping)

  B) Is the reward signal healthy?
       - What fraction of updates carry a positive reward?
       - Is reward quality improving over time (fewer failed TX)?
       - Are there suspiciously large negative rewards (-100) suggesting link problems?

  C) Is the learning behaviour as expected?
       - Do Q-values for a parent track that parent's energy? (energy-responsive routing)
       - Do weights drift in a direction that reflects what the environment is teaching?
         (if f_eng is more variable than f_lq, W_ENG should rise relative to W_LQ)
       - Does TD error shrink as the agent gets better at predicting rewards?
       - When a node has multiple parent candidates, does it consistently prefer the
         higher-Q one, and does that preference shift as energies change?
       - Are the feature signals (f_lq, f_eng) seen at learning time sensible — i.e.
         is f_eng decreasing over time as the battery drains?

Plots saved (alongside the script, or next to the log if a path is passed):
  analysis_weights.png        — weight evolution + feature signals seen
  analysis_td_error.png       — TD error over time with rolling mean
  analysis_qvalues.png        — Q-values during parent selection, per link
  analysis_reward_quality.png — rolling reward mean + fraction negative TX
  analysis_feature_signals.png— f_lq and f_eng seen at each learning step
  analysis_q_vs_energy.png    — chosen parent Q-value vs battery level (energy responsiveness)
  analysis_parent_switch.png  — which parent was chosen over time, with candidate battery levels
"""

import re
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ─── Constants — must match project-conf.h ───────────────────────────────────

ALPHA       = 10
GAMMA       = 80
MAX_WEIGHT  = 1000
MIN_WEIGHT  = -1000
INIT_W_LQ   = 50
INIT_W_ENG  = 50
SARSA_HYSTERESIS = 8   # from rpl-sarsa.c

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(SCRIPT_DIR, "../../tools/cooja/cooja_sarsa.log")

# ─── Parsers ─────────────────────────────────────────────────────────────────

_MATH_RE = re.compile(
    r'^\s*(\d+)\s+ID:(\d+).*?'
    r'SARSA-MATH \| Par: (\d+) \| curQ: (-?\d+) \| rew: (-?\d+) \| '
    r'futQ: (-?\d+) \| tgt: (-?\d+) \| err: (-?\d+)'
)
_WGHT_RE = re.compile(
    r'^\s*(\d+)\s+ID:(\d+).*?'
    r'SARSA-WGHT \| f_lq: (-?\d+) \| f_eng: (-?\d+) \| W_LQ: (-?\d+) \| W_ENG: (-?\d+)'
)
_EVAL_RE = re.compile(
    r'^\s*(?P<ts>\d+)\s+ID:(?P<node>\d+).*?'
    r'EVALUATE: P1: (?P<p1>\d+) \(Q: (?P<q1>-?\d+)\) vs P2: (?P<p2>\d+) \(Q: (?P<q2>-?\d+)\)'
    r' -> CHOSE: (?P<chose>\d+)'
)
_BATT_RE = re.compile(
    r'^\s*(\d+)\s+ID:(\d+).*?BATTERY_SAMPLE:\s*node=(\d+),\s*batt=(\d+)'
)


def parse_log(filepath):
    math_rows, wght_rows, eval_rows, batt_rows = [], [], [], []
    with open(filepath) as f:
        for line in f:
            m = _MATH_RE.search(line)
            if m:
                math_rows.append({
                    'ts': int(m.group(1)), 'node': int(m.group(2)),
                    'par': int(m.group(3)), 'curQ': int(m.group(4)),
                    'rew': int(m.group(5)), 'futQ': int(m.group(6)),
                    'tgt': int(m.group(7)), 'err':  int(m.group(8)),
                })
                continue
            w = _WGHT_RE.search(line)
            if w:
                wght_rows.append({
                    'ts': int(w.group(1)), 'node': int(w.group(2)),
                    'f_lq': int(w.group(3)), 'f_eng': int(w.group(4)),
                    'W_LQ': int(w.group(5)), 'W_ENG': int(w.group(6)),
                })
                continue
            e = _EVAL_RE.search(line)
            if e:
                eval_rows.append({
                    'ts':    int(e.group('ts')),
                    'node':  int(e.group('node')),
                    'p1':    int(e.group('p1')),  'q1': int(e.group('q1')),
                    'p2':    int(e.group('p2')),  'q2': int(e.group('q2')),
                    'chose': int(e.group('chose')),
                })
                continue
            b = _BATT_RE.search(line)
            if b:
                batt_rows.append({
                    'ts': int(b.group(1)), 'node': int(b.group(3)),
                    'batt': int(b.group(4)),
                })
    return (pd.DataFrame(math_rows), pd.DataFrame(wght_rows),
            pd.DataFrame(eval_rows),  pd.DataFrame(batt_rows))


# ─── Verification ────────────────────────────────────────────────────────────

def verify_arithmetic(df_math, df_wght):
    """
    For every (MATH, WGHT) pair (always emitted consecutively per node):
      - Check err == tgt - curQ
      - Reconstruct weight delta from formula and compare to logged weights
    """
    ok_err = fail_err = ok_wgt = fail_wgt = 0
    wgt_mismatches = []

    for node, grp_m in df_math.groupby('node'):
        grp_w = df_wght[df_wght['node'] == node].reset_index(drop=True)
        grp_m = grp_m.reset_index(drop=True)

        n_pairs = min(len(grp_m), len(grp_w))
        if len(grp_m) != len(grp_w):
            print(f"  [WARN] Node {node}: {len(grp_m)} MATH rows vs {len(grp_w)} WGHT rows "
                  f"— using first {n_pairs} pairs")

        prev_lq  = INIT_W_LQ
        prev_eng = INIT_W_ENG

        for i in range(n_pairs):
            m = grp_m.iloc[i]
            w = grp_w.iloc[i]

            # Check 1: err == tgt - curQ
            expected_err = m['tgt'] - m['curQ']
            if m['err'] == expected_err:
                ok_err += 1
            else:
                fail_err += 1

            # Check 2: weight delta
            # C integer division truncates toward zero (unlike Python // which floors).
            # Use int() on float division to replicate C behaviour.
            delta_lq  = int((ALPHA * m['err'] * w['f_lq'])  / 10000)
            delta_eng = int((ALPHA * m['err'] * w['f_eng']) / 10000)

            exp_lq  = max(MIN_WEIGHT, min(MAX_WEIGHT, prev_lq  + delta_lq))
            exp_eng = max(MIN_WEIGHT, min(MAX_WEIGHT, prev_eng + delta_eng))

            if exp_lq == w['W_LQ'] and exp_eng == w['W_ENG']:
                ok_wgt += 1
            else:
                fail_wgt += 1
                wgt_mismatches.append({
                    'node': node, 'update': i + 1,
                    'ts_mins': m['ts'] / 60_000_000,
                    'exp_W_LQ':  exp_lq,  'got_W_LQ':  w['W_LQ'],
                    'exp_W_ENG': exp_eng, 'got_W_ENG': w['W_ENG'],
                })

            prev_lq  = w['W_LQ']
            prev_eng = w['W_ENG']

    total_err = ok_err + fail_err
    total_wgt = ok_wgt + fail_wgt
    tag_e = "✓" if fail_err == 0 else "✗"
    tag_w = "✓" if fail_wgt == 0 else "✗"
    print(f"  {tag_e} TD-error formula  (err == tgt - curQ)  : {ok_err}/{total_err} correct")
    print(f"  {tag_w} Weight-update formula                  : {ok_wgt}/{total_wgt} correct")

    if wgt_mismatches:
        print("\n  Weight mismatches detail:")
        for r in wgt_mismatches:
            print(f"    Node {r['node']} update #{r['update']} @ {r['ts_mins']:.2f} min: "
                  f"W_LQ expected={r['exp_W_LQ']} got={r['got_W_LQ']},  "
                  f"W_ENG expected={r['exp_W_ENG']} got={r['got_W_ENG']}")

    return fail_err, fail_wgt


# ─── B) Reward signal health ──────────────────────────────────────────────────

def analyse_rewards(df_math):
    print("\n  [ Reward Signal ]")
    for node in sorted(df_math['node'].unique()):
        nd = df_math[df_math['node'] == node]
        rewards = nd['rew'].tolist()
        n = len(rewards)
        if n == 0:
            continue
        n_neg  = sum(1 for r in rewards if r < 0)
        pct_neg = 100 * n_neg / n
        mean_r  = sum(rewards) / n
        half = n // 2
        if half > 0:
            mean_early = sum(rewards[:half]) / half
            mean_late  = sum(rewards[half:]) / (n - half)
            trend = "improving ✓" if mean_late > mean_early else "degrading"
        else:
            mean_early = mean_late = mean_r
            trend = "insufficient data"
        tag = "✓" if pct_neg < 20 else ("!" if pct_neg < 50 else "✗")
        print(f"    Node {node}: {n} updates | mean reward={mean_r:.1f} | "
              f"negative={pct_neg:.0f}% ({n_neg} failed TX)  [{tag}]")
        if half > 0:
            print(f"             early mean={mean_early:.1f} → late mean={mean_late:.1f}  →  {trend}")


# ─── C) Behavioural analysis ──────────────────────────────────────────────────

def analyse_weight_direction(df_wght):
    """
    Expected: the weight that drifts most from 50 should correspond to the
    feature that varied most during learning (more variance = more signal).
    """
    print("\n  [ Weight Learning Direction ]")
    for node in sorted(df_wght['node'].unique()):
        nd = df_wght[df_wght['node'] == node]
        if nd.empty or len(nd) < 2:
            continue
        final_lq  = nd['W_LQ'].iloc[-1]
        final_eng = nd['W_ENG'].iloc[-1]
        drift_lq  = final_lq  - INIT_W_LQ
        drift_eng = final_eng - INIT_W_ENG
        var_lq  = nd['f_lq'].var()
        var_eng = nd['f_eng'].var()
        expected_dominant = "energy" if var_eng > var_lq else "link quality"
        actual_dominant   = "energy" if abs(drift_eng) > abs(drift_lq) else "link quality"
        consistent = "✓" if expected_dominant == actual_dominant else "unexpected !"
        print(f"    Node {node}: W_LQ drift={drift_lq:+d}  W_ENG drift={drift_eng:+d}")
        print(f"             f_lq variance={var_lq:.1f}  f_eng variance={var_eng:.1f}")
        print(f"             Dominant signal: {actual_dominant}  "
              f"(expected {expected_dominant} from variance)  [{consistent}]")


def analyse_feature_signals(df_wght):
    """
    f_eng seen at learning time should trend downward as battery drains.
    Flat f_eng means energy piggyback from DIOs is not delivering updates.
    """
    print("\n  [ Feature Signals seen at learning time ]")
    for node in sorted(df_wght['node'].unique()):
        nd = df_wght[df_wght['node'] == node]
        if nd.empty or len(nd) < 3:
            continue
        first_eng, last_eng = nd['f_eng'].iloc[0], nd['f_eng'].iloc[-1]
        first_lq,  last_lq  = nd['f_lq'].iloc[0],  nd['f_lq'].iloc[-1]
        eng_tag = ("decreasing ✓" if last_eng < first_eng
                   else "flat — energy signal not updating?" if last_eng == first_eng
                   else "increasing (unexpected for draining battery)")
        lq_tag  = "stable ✓" if abs(last_lq - first_lq) < 15 else "variable"
        print(f"    Node {node}: f_eng {first_eng}→{last_eng} ({eng_tag}) | "
              f"f_lq {first_lq}→{last_lq} ({lq_tag})")


def analyse_td_convergence(df_math):
    print("\n  [ TD Error Convergence ]")
    for node in sorted(df_math['node'].unique()):
        nd = df_math[df_math['node'] == node]['err'].tolist()
        if len(nd) < 4:
            print(f"    Node {node}: only {len(nd)} samples — too few to assess")
            continue
        half = len(nd) // 2
        mean_a = sum(abs(x) for x in nd[:half])  / half
        mean_b = sum(abs(x) for x in nd[half:])  / (len(nd) - half)
        # Non-stationary caveat: battery drains continuously, so perfect
        # convergence is not expected. Growing error = environment changing
        # faster than the agent can track.
        if mean_b < mean_a:
            tag = "converging ✓"
        elif mean_b < mean_a * 1.5:
            tag = "roughly stable (non-stationary environment — expected)"
        else:
            tag = "diverging — agent not keeping up with environment ✗"
        print(f"    Node {node}: |err| early={mean_a:.1f}  late={mean_b:.1f}  →  {tag}")


def analyse_parent_selection(df_eval):
    if df_eval.empty:
        return
    wrong = total = 0
    for _, r in df_eval.iterrows():
        if r['p1'] == r['p2']:
            continue
        total += 1
        chose_q = r['q1'] if r['chose'] == r['p1'] else r['q2']
        other_q = r['q2'] if r['chose'] == r['p1'] else r['q1']
        if other_q > chose_q + SARSA_HYSTERESIS:
            wrong += 1
    tag = "✓" if wrong == 0 else "✗"
    print(f"\n  {tag} Parent always chose higher-Q candidate (hysteresis={SARSA_HYSTERESIS}): "
          f"{total - wrong}/{total}")


def analyse_energy_responsiveness(df_eval, df_batt):
    """
    At each EVALUATE event where node has two distinct parent candidates,
    check whether the parent with more battery was also assigned the higher Q.
    This is the correct test: it's a per-decision relative comparison, not an
    absolute time-series correlation (which is confounded by both Q and battery
    drifting down together over time regardless of agent behaviour).
    """
    if df_eval.empty or df_batt.empty:
        return

    print("\n  [ Energy Responsiveness — does higher-battery parent get higher Q? ]")

    for node in sorted(df_eval['node'].unique()):
        ev = df_eval[df_eval['node'] == node].copy()
        # Only events where the two candidates are different nodes
        ev = ev[ev['p1'] != ev['p2']].sort_values('ts')
        if ev.empty:
            continue

        agree = total = 0
        for _, r in ev.iterrows():
            # Get battery for each candidate at this moment
            def batt_at(par_node, ts):
                pb = df_batt[df_batt['node'] == par_node]
                if pb.empty:
                    return None
                idx = (pb['ts'] - ts).abs().idxmin()
                return pb.loc[idx, 'batt']

            b1 = batt_at(r['p1'], r['ts'])
            b2 = batt_at(r['p2'], r['ts'])
            if b1 is None or b2 is None or b1 == b2:
                continue

            total += 1
            higher_batt_par = r['p1'] if b1 > b2 else r['p2']
            higher_q_par    = r['p1'] if r['q1'] > r['q2'] else r['p2']
            if higher_batt_par == higher_q_par:
                agree += 1

        if total == 0:
            print(f"    Node {node}: no events with differing-battery candidates")
            continue

        pct = 100 * agree / total
        tag = "✓" if pct >= 60 else ("~" if pct >= 40 else "✗ (energy not influencing Q!)")
        print(f"    Node {node}: higher-battery parent got higher Q in "
              f"{agree}/{total} decisions ({pct:.0f}%)  [{tag}]")


# ─── Plots ───────────────────────────────────────────────────────────────────

COLORS = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336']


def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {os.path.basename(path)}")


def plot_weights(df_wght, outdir):
    """Weights (top) + the feature signals the agent was actually seeing (bottom)."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for i, node in enumerate(sorted(df_wght['node'].unique())):
        nd = df_wght[df_wght['node'] == node]
        t  = nd['ts'] / 60_000_000
        c  = COLORS[i % len(COLORS)]
        ax1.plot(t, nd['W_LQ'],  color=c, linestyle='-',  linewidth=2,
                 label=f'Node {node} W_LQ')
        ax1.plot(t, nd['W_ENG'], color=c, linestyle='--', linewidth=2,
                 label=f'Node {node} W_ENG')
        ax2.plot(t, nd['f_lq'],  color=c, linestyle='-',  linewidth=1.5,
                 alpha=0.8, label=f'Node {node} f_lq')
        ax2.plot(t, nd['f_eng'], color=c, linestyle='--', linewidth=1.5,
                 alpha=0.8, label=f'Node {node} f_eng')
    ax1.axhline(INIT_W_LQ, color='black', linestyle=':', linewidth=1,
                alpha=0.4, label=f'Initial ({INIT_W_LQ})')
    ax1.set_title('Policy Weights Over Time  (W_LQ solid, W_ENG dashed)', fontweight='bold')
    ax1.set_ylabel('Weight Value')
    ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax2.set_title('Feature Signals Seen at Each Learning Step', fontweight='bold')
    ax2.set_xlabel('Simulation Time (mins)')
    ax2.set_ylabel('Feature Value (0–100)')
    ax2.set_ylim(-5, 105)
    ax2.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8)
    ax2.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_weights.png'))


def plot_td_error(df_math, outdir):
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, node in enumerate(sorted(df_math['node'].unique())):
        nd = df_math[df_math['node'] == node].copy()
        t  = nd['ts'] / 60_000_000
        c  = COLORS[i % len(COLORS)]
        ax.scatter(t, nd['err'], color=c, s=25, alpha=0.5)
        w = min(5, len(nd))
        ax.plot(t, nd['err'].rolling(w, min_periods=1).mean(),
                color=c, linewidth=2, label=f'Node {node}')
    ax.axhline(0, color='black', linestyle='--', linewidth=1.5, label='Ideal (0)')
    ax.set_title('TD Error (δ) Over Time  — scatter + rolling mean', fontweight='bold')
    ax.set_xlabel('Simulation Time (mins)')
    ax.set_ylabel('TD Error')
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.4)
    _save(fig, os.path.join(outdir, 'analysis_td_error.png'))


def plot_qvalues(df_eval, outdir):
    if df_eval.empty:
        return
    records = []
    for _, r in df_eval.iterrows():
        records.append({'ts': r['ts'], 'node': r['node'],
                        'par': r['p1'], 'q': r['q1']})
        records.append({'ts': r['ts'], 'node': r['node'],
                        'par': r['p2'], 'q': r['q2']})
    df = pd.DataFrame(records)
    nodes = sorted(df['node'].unique())
    fig, axes = plt.subplots(len(nodes), 1, figsize=(14, 5 * len(nodes)), squeeze=False)
    for ax, node in zip(axes[:, 0], nodes):
        nd = df[df['node'] == node]
        for j, par in enumerate(sorted(nd['par'].unique())):
            grp = nd[nd['par'] == par]
            ax.plot(grp['ts'] / 60_000_000, grp['q'],
                    color=COLORS[j % len(COLORS)], linewidth=1.5,
                    alpha=0.8, label=f'→ parent {par}')
        ax.set_title(f'Node {node}: Q-Values Per Parent Candidate', fontweight='bold')
        ax.set_xlabel('Simulation Time (mins)')
        ax.set_ylabel('Q-Value')
        ax.legend()
        ax.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_qvalues.png'))


def plot_reward_quality(df_math, outdir):
    """Rolling mean reward and rolling fraction of negative rewards."""
    nodes = sorted(df_math['node'].unique())
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=False)
    for i, node in enumerate(nodes):
        nd = df_math[df_math['node'] == node].copy()
        t  = nd['ts'] / 60_000_000
        c  = COLORS[i % len(COLORS)]
        w  = min(7, len(nd))
        ax1.plot(t, nd['rew'].rolling(w, min_periods=1).mean(),
                 color=c, linewidth=2, label=f'Node {node}')
        ax2.plot(t, (nd['rew'] < 0).rolling(w, min_periods=1).mean() * 100,
                 color=c, linewidth=2, label=f'Node {node}')
    ax1.axhline(0, color='black', linestyle='--', linewidth=1, alpha=0.5)
    ax1.set_title('Rolling Mean Reward Over Time  (higher = better)', fontweight='bold')
    ax1.set_ylabel('Mean Reward')
    ax1.legend(); ax1.grid(True, linestyle='--', alpha=0.4)
    ax2.axhline(20, color='orange', linestyle='--', linewidth=1,
                alpha=0.7, label='Concern threshold (20%)')
    ax2.set_title('Rolling % of Failed-TX Rewards  (lower = better)', fontweight='bold')
    ax2.set_xlabel('Simulation Time (mins)')
    ax2.set_ylabel('% Negative Rewards')
    ax2.set_ylim(-5, 105)
    ax2.legend(); ax2.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_reward_quality.png'))


def plot_q_vs_energy(df_eval, df_batt, outdir):
    """
    For each EVALUATE event with two different candidates, plot the Q-difference
    (Q_p1 - Q_p2) vs the battery-difference (batt_p1 - batt_p2).
    If energy is influencing Q, points should cluster in quadrants I and III
    (same sign = higher battery → higher Q).
    """
    if df_eval.empty or df_batt.empty:
        return

    records = []
    for node in sorted(df_eval['node'].unique()):
        ev = df_eval[df_eval['node'] == node].copy()
        ev = ev[ev['p1'] != ev['p2']].sort_values('ts')
        for _, r in ev.iterrows():
            def batt_at(par_node, ts):
                pb = df_batt[df_batt['node'] == par_node]
                if pb.empty:
                    return None
                idx = (pb['ts'] - ts).abs().idxmin()
                return pb.loc[idx, 'batt']
            b1 = batt_at(r['p1'], r['ts'])
            b2 = batt_at(r['p2'], r['ts'])
            if b1 is None or b2 is None:
                continue
            records.append({
                'node': node,
                'ts_mins': r['ts'] / 60_000_000,
                'dQ':    r['q1'] - r['q2'],
                'dBatt': b1 - b2,
            })

    if not records:
        return

    df = pd.DataFrame(records)
    fig, ax = plt.subplots(figsize=(9, 7))

    for i, node in enumerate(sorted(df['node'].unique())):
        nd = df[df['node'] == node]
        ax.scatter(nd['dBatt'], nd['dQ'], c=COLORS[i % len(COLORS)],
                   s=25, alpha=0.6, label=f'Node {node}')

    # Shade the "correct" quadrants (I and III)
    xlim = max(abs(df['dBatt'].min()), abs(df['dBatt'].max())) * 1.1
    ylim = max(abs(df['dQ'].min()),    abs(df['dQ'].max()))    * 1.1
    ax.axhline(0, color='black', linewidth=1)
    ax.axvline(0, color='black', linewidth=1)
    ax.fill_between([ 0,  xlim], [ 0,  0], [ ylim,  ylim], alpha=0.06, color='green', label='Energy-aligned (Q↑ when batt↑)')
    ax.fill_between([-xlim, 0], [-ylim, -ylim], [0, 0],    alpha=0.06, color='green')

    ax.set_xlim(-xlim, xlim)
    ax.set_ylim(-ylim, ylim)
    ax.set_title(
        'Energy Responsiveness: ΔQ vs ΔBattery at each parent comparison\n'
        'Green quadrants = higher-battery parent correctly got higher Q',
        fontweight='bold')
    ax.set_xlabel('Battery(P1) − Battery(P2)  [%]')
    ax.set_ylabel('Q(P1) − Q(P2)')
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.4)
    _save(fig, os.path.join(outdir, 'analysis_q_vs_energy.png'))


def plot_parent_switches(df_eval, df_batt, outdir):
    """
    For each node with EVALUATE events, show which parent was chosen at each
    decision point over time. Battery levels of each candidate are overlaid on
    a secondary y-axis so you can see whether parent switches correlate with
    energy divergence.
    """
    if df_eval.empty:
        return

    nodes = sorted(df_eval['node'].unique())
    fig, axes = plt.subplots(len(nodes), 1,
                             figsize=(14, 5 * len(nodes)), squeeze=False)

    for ax_row, node in zip(axes[:, 0], nodes):
        ev = df_eval[df_eval['node'] == node].sort_values('ts').copy()
        ev = ev[ev['p1'] != ev['p2']]   # only contested decisions
        if ev.empty:
            ax_row.set_title(f'Node {node}: no contested EVALUATE events')
            continue

        t_mins    = ev['ts'] / 60_000_000
        chose_ids = ev['chose'].values
        all_pars  = sorted(set(ev['p1'].tolist() + ev['p2'].tolist()))

        # Map parent IDs to integer positions for a clean step plot
        par_pos = {p: i for i, p in enumerate(all_pars)}
        chose_pos = [par_pos[c] for c in chose_ids]

        ax_row.step(t_mins, chose_pos, where='post',
                    color='black', linewidth=2, zorder=5, label='Chosen parent')
        ax_row.set_yticks(list(par_pos.values()))
        ax_row.set_yticklabels([f'Node {p}' for p in par_pos])
        ax_row.set_ylabel('Chosen Parent')
        ax_row.set_title(f'Node {node}: Parent Choice Over Time', fontweight='bold')
        ax_row.grid(True, linestyle='--', alpha=0.3)

        # Overlay battery of each candidate on secondary y-axis
        if not df_batt.empty:
            ax2 = ax_row.twinx()
            for j, par in enumerate(all_pars):
                pb = df_batt[df_batt['node'] == par].sort_values('ts')
                if pb.empty:
                    continue
                ax2.plot(pb['ts'] / 60_000_000, pb['batt'],
                         color=COLORS[j % len(COLORS)], linewidth=1.5,
                         linestyle='--', alpha=0.7, label=f'Node {par} battery')
            ax2.set_ylabel('Battery %')
            ax2.set_ylim(0, 110)
            ax2.legend(loc='lower right', fontsize=8)

        ax_row.set_xlabel('Simulation Time (mins)')
        ax_row.legend(loc='upper left', fontsize=8)

    plt.tight_layout()
    _save(fig, os.path.join(outdir, 'analysis_parent_switch.png'))


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    out_dir  = os.path.dirname(os.path.abspath(log_path)) if len(sys.argv) > 1 else SCRIPT_DIR

    if not os.path.exists(log_path):
        print(f"Error: log file not found: {log_path}")
        sys.exit(1)

    print(f"Log : {log_path}")
    print(f"Out : {out_dir}\n")

    df_math, df_wght, df_eval, df_batt = parse_log(log_path)

    print("=== DATA SUMMARY ===")
    print(f"  SARSA-MATH  updates : {len(df_math)}")
    print(f"  SARSA-WGHT  updates : {len(df_wght)}")
    print(f"  EVALUATE    events  : {len(df_eval)}")
    print(f"  BATTERY_SAMPLE rows : {len(df_batt)}")
    if not df_math.empty:
        ts_min, ts_max = df_math['ts'].min(), df_math['ts'].max()
        print(f"  Span of learning    : {ts_min/60_000_000:.1f} – {ts_max/60_000_000:.1f} min")
    if df_math.empty or df_wght.empty:
        print("\nNo SARSA learning logs found — was SARSA_LOGGING defined?")
        sys.exit(0)

    print(f"\n=== CONSTANTS ===")
    print(f"  ALPHA={ALPHA}  GAMMA={GAMMA}  "
          f"WEIGHT_CLIP=[{MIN_WEIGHT},{MAX_WEIGHT}]  "
          f"HYSTERESIS={SARSA_HYSTERESIS}")

    print("\n=== A) ARITHMETIC CORRECTNESS ===")
    fail_err, fail_wgt = verify_arithmetic(df_math, df_wght)

    print("\n=== B) REWARD SIGNAL HEALTH ===")
    analyse_rewards(df_math)

    print("\n=== C) LEARNING BEHAVIOUR ===")
    analyse_feature_signals(df_wght)
    analyse_weight_direction(df_wght)
    analyse_td_convergence(df_math)
    analyse_parent_selection(df_eval)
    analyse_energy_responsiveness(df_eval, df_batt)

    print("\n=== VERDICT ===")
    if fail_err == 0 and fail_wgt == 0:
        print("  Arithmetic : PASS")
    else:
        print(f"  Arithmetic : FAIL  ({fail_err} err mismatch, {fail_wgt} weight mismatch)")

    print("\n=== PLOTS ===")
    plot_weights(df_wght, out_dir)
    plot_td_error(df_math, out_dir)
    plot_qvalues(df_eval, out_dir)
    plot_reward_quality(df_math, out_dir)
    plot_q_vs_energy(df_eval, df_batt, out_dir)
    plot_parent_switches(df_eval, df_batt, out_dir)

    print("\nDone.")
