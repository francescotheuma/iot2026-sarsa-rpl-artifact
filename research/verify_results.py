"""Check recorded results against manuscript Table 1; no simulator rerun."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parent
SCENARIOS = {
    "Experiment 1": ("Static", "static_diamond", 100),
    "Experiment 2": ("Degraded", "degraded_diamond", 100),
    "Experiment 3": ("Dense short", "dense_short", 100),
    "Experiment 3 LONG": ("Dense longer", "dense_longer", 50),
}
PROFILES = ("MRHOF", "SARSA", "Federated SARSA")
SEEDS = {"123456", "123457", "123458"}
# Published mean and sample standard deviation, rounded to three decimals.
TABLE1 = {
    "Static": (("26.979", "0.093"), ("31.646", "0.602"), ("31.351", "0.416")),
    "Degraded": (("29.701", "3.723"), ("34.672", "0.359"), ("35.296", "0.231")),
    "Dense short": (("6.140", "0.099"), ("4.293", "0.552"), ("4.142", "0.882")),
    "Dense longer": (("60.528", "0.444"), ("64.062", "6.029"), ("64.019", "5.105")),
}


def read_csv(name):
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    rows = read_csv("selected_results_and_tuning.csv")
    configs = read_csv("complete_learning_configurations.csv")
    provenance = json.loads((ROOT / "provenance.json").read_text(encoding="utf-8"))
    check(len(rows) == 36, "Expected 36 selected results")
    check(len(configs) == 24, "Expected 24 learning configurations")
    groups = defaultdict(dict)
    for row in rows:
        scenario = SCENARIOS[row["scenario_sheet"]][0]
        profile, seed = row["profile"], row["seed"]
        check(profile in PROFILES and seed in SEEDS, "Unexpected profile or seed")
        group = groups[scenario, profile]
        check(seed not in group, f"Duplicate result: {scenario}, {profile}, {seed}")
        group[seed] = float(row["selected_ttfnd_minutes"])

    expected_keys = {
        (scenario, profile, seed)
        for scenario in TABLE1 for profile in PROFILES[1:] for seed in SEEDS
    }
    seen = set()
    for row in configs:
        key = row["scenario"], row["profile"], row["seed"]
        check(key in expected_keys and key not in seen, f"Unexpected/duplicate configuration: {key}")
        seen.add(key)
        _, provenance_key, drain = next(v for v in SCENARIOS.values() if v[0] == key[0])
        check(int(row["drain_multiplier"]) == drain, f"Wrong drain multiplier: {key}")
        check(provenance["historical_drain_multipliers"][provenance_key] == drain,
              f"Provenance disagrees: {key[0]}")
    check(seen == expected_keys, "Missing learning configurations")

    summary = []
    for scenario, expected in TABLE1.items():
        for profile, (expected_mean, expected_sd) in zip(PROFILES, expected):
            group = groups[scenario, profile]
            check(set(group) == SEEDS, f"Missing seeds: {scenario}, {profile}")
            values = list(group.values())
            calculated = f"{mean(values):.3f}", f"{stdev(values):.3f}"
            check(calculated == (expected_mean, expected_sd),
                  f"Table 1 mismatch: {scenario}, {profile}: {calculated}")
            summary.append({"scenario": scenario, "profile": profile, "n": 3,
                            "mean_ttfnd_minutes": calculated[0],
                            "sample_sd_minutes": calculated[1]})
    check(read_csv("table1_summary.csv") == [{k: str(v) for k, v in r.items()} for r in summary],
          "Summary CSV differs from recomputed results")
    print("PASS: all 12 Table 1 means and sample standard deviations match.")
    print("PASS: all 24 learning configurations match seeds and confirmed drain settings.")
    print("Recorded results checked only; Cooja was not rerun.")


if __name__ == "__main__":
    main()
