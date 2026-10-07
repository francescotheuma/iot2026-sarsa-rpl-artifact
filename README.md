# IoT 2026 SARSA/RPL research artifact

Source and selected results supporting **Energy-Aware RPL Parent Selection using Lightweight SARSA and Federated Weight Sharing**.

## Version and scope

Use **`main`** for the complete artifact: this README, the `research/` records and the implementation under `source/`. The `paper-source` branch preserves the original submission for reference; it does not need to be merged or checked out to run the artifact.

`source/` contains the Contiki-NG implementation used for the paper, identified by submission commit `ed98a7d8e9331802dc1fe50dee4884f8388e2e91`. The application, learning algorithm, battery model and saved experiment configurations are included in this repository.

The original submission commits are preserved in this repository on the [`paper-source`](https://github.com/francescotheuma/iot2026-sarsa-rpl-artifact/tree/paper-source) branch and in `main`'s ancestry. On `paper-source`, files retain their original paths (for example, `examples/rpl-udp/`). The artifact places the same implementation under `source/` alongside the reproduction instructions and result records.

The submission records Cooja commit `1869e6ee8d19812fc018350a633b661fecec947e`. The archived Cooja tree, including the project's logging support, is bundled under `source/tools/cooja/`. That commit is not available from the public upstream Cooja repository, so use the bundled tree for this artifact. Other optional Contiki-NG submodules are not bundled; their public URLs and exact commits are listed in `research/provenance.json`. Its dependency paths are relative to the original source root, which is `source/` on `main`. The artifact contains regular files rather than active Git submodules.

The implementation is preserved without algorithm changes. Artifact packaging changes are listed in `research/provenance.json`: the dense scenario uses a portable firmware path, and the application README describes this paper's experiments. The original files remain available on `paper-source`.

## Contents

- `source/examples/rpl-udp/`: application client/server, learning implementation (`rpl-sarsa.c`), battery proxy (`battery.c`), project configuration and the three saved experiment topologies.
- `source/os/net/link-stats.c`: passes MAC outcomes to the learning callback when SARSA is enabled.
- `source/os/net/routing/rpl-lite/rpl-icmp6.c`: continuation-score DIO option.
- `research/selected_results_and_tuning.csv`: 36 selected TTFND results and original workbook tuning notes.
- `research/complete_learning_configurations.csv`: complete parameter tuples for the 24 selected learning runs, reconstructed using the author's confirmed reset-to-default procedure.
- `research/table1_summary.csv`: Table 1 means and sample standard deviations, checked by `research/verify_results.py`.
- `research/provenance.json`: source and dependency versions, battery settings, unresolved values and their provenance.
- `SHA256SUMS.txt`: package-file integrity checks, covering every tracked file except the checksum list itself. `.gitattributes` preserves the expected file bytes across Windows and Linux checkouts.

The broader `source/os/`, `source/arch/`, `source/tools/` and other example/test folders are retained Contiki-NG and Cooja infrastructure. They provide the original build context; the paper's experiments are the three `Final Experiment ...` configurations listed below. Generic Sky/Cooja and Renode examples in the application folder are not additional paper experiments.

## How the implementation works

Each client scores eligible RPL parents using two features: the parent's advertised remaining battery percentage and a link-quality score derived from ETX. Both features range from 0 to 100. Raw ETX uses 128 units per transmission: the link score is 100 at ETX <= 128, falls linearly to 0 at ETX >= 512, and uses integer arithmetic between those limits. The score is `(w_energy * battery + w_lq * link_quality) / 100`. Both weights start at 50 and are clipped to 0--1000; they are not constrained to sum to 100.

For a successful MAC transmission, the reward is the parent's battery percentage, with `20 * numtx` subtracted when more than one transmission attempt was required. A failed transmission receives -100. Every Bth eligible MAC outcome updates both weights using the temporal-difference error. The target combines the immediate reward with the neighbour's advertised score for its own selected parent; this is the continuation score carried in DIOs. For a direct-root transmission, the target is just the immediate reward. Parent selection compares scores with a hysteresis margin favouring the current parent. There is no explicit random exploration policy. These calculations are in `source/examples/rpl-udp/rpl-sarsa.c`.

With federation enabled, clients periodically include their two weights in a UDP request. The root stores the latest pair from each registered client (up to 15), recomputes an equal-weight arithmetic average on receipt of a report, and unicasts that average back to the reporting client. It does not broadcast an update to all clients. Stored entries do not expire, so the average can include older reports. The receiving client blends the average with its current weights using F percent. See `udp-client.c` and `udp-server.c` in the application folder.

## Build and configuration

Clone the default `main` branch or download its ZIP. Use a Linux environment with GNU Make, the Z1/MSP430 toolchain (`msp430-gcc`, targeting the MSP430F2617), and Java 21. Python 3 is sufficient for checking the recorded results; that check does not require the simulator or compiler. Cooja includes its Gradle wrapper. Historical host/compiler versions have not been recovered, and this package has not been rebuilt or experimentally rerun as part of the manuscript revision.

From `source/tools/cooja/`, follow its README to build Cooja (for example `./gradlew distZip`). If extracting the ZIP loses executable permissions, restore them with `chmod +x gradlew`. Required Gradle dependencies are downloaded during the build; this is not an offline distribution.

Before compiling a chosen profile, edit `source/examples/rpl-udp/project-conf.h`:

| Profile | SARSA switch | FEDERATION switch |
| --- | --- | --- |
| MRHOF | Disabled | Disabled |
| Standalone SARSA | Enabled | Disabled |
| Federated SARSA | Enabled | Enabled |

Disable a switch by commenting out its `#define`. All profiles retain the supplied battery and application modules. The baseline is not a separately archived unmodified upstream firmware.

Each learning trial starts from these defaults, then applies its selected row in `complete_learning_configurations.csv`:

| Symbol | Configuration macro | Default |
| --- | --- | --- |
| A | SARSA_CONF_ALPHA | 20 |
| G | SARSA_CONF_GAMMA | 80 |
| B | SARSA_CONF_LEARNING_BATCH_SIZE | 7 |
| H | SARSA_CONF_HYSTERESIS | 8 |
| T | FED_CONF_THRESHOLD | 10 |
| F | FL_CONF_BLEND | 10 |

A, G and F are integer percentages. B is an update stride: only every Bth eligible MAC outcome updates weights, without averaging the preceding outcomes. T yields a weight report every T+1 reachable application requests. Federation settings are inactive in the standalone profile.

CPU/TX/RX costs are respectively 20/60/0 for all experiments. Only `CONF_DRAIN_MAGNITUDE` changed between battery conditions:

| Condition | Drain multiplier |
| --- | --- |
| Static diamond | 100 |
| Degraded diamond | 100 |
| Dense short | 100 |
| Dense longer | Unresolved: 10 or 50 are candidates |

The author reports that the other battery settings were unchanged and that all three profiles used the same battery settings within a condition. Static diamond, degraded diamond and dense short retain the reported multiplier of 100. The historical dense-longer multiplier is unresolved, with 10 and 50 as candidates. The six dense-longer learning rows leave `drain_multiplier` blank, and the provenance manifest uses `null`. These represent an unknown setting, not zero or a default value. The archived project configuration starts at 100 and does not establish the long-test setting.

The multiplier acts directly on the weighted Energest ticks. Commit history records 50 when the rings topology was added on 26 April and again on 3 May, followed by 100 on 4 May and at submission. Committed settings of 10 occur earlier in March. None of those commits is linked to the selected dense-longer runs. The fallback of 10 in `battery.c` applies only when `project-conf.h` does not define the multiplier. See `research/provenance.json` for the exact commits. Exact reproduction of the dense-longer condition requires recovering its historical setting; trying a candidate value is a new run, not a verified reconstruction.

After configuring the profile and parameters, rebuild both applications from `source/examples/rpl-udp/`:

```sh
make clean TARGET=z1
make udp-client.z1 udp-server.z1 TARGET=z1
```

Open the selected saved simulation in Cooja and confirm that both mote types use the newly built firmware:

| Condition | Saved configuration under source/examples/rpl-udp/ |
| --- | --- |
| Static diamond | Final Experiment 1 (Simple Diamond)/FinalExperiment1.csc |
| Degraded diamond | Final Experiment 2 (SARSA load balancing)/FinalExperiment2.csc |
| Dense short / dense longer | Final Experiment 3 (Rings)/FinalExperiment3.csc |

Set seed 123456, 123457 or 123458 as recorded in the results. Dense short and longer share the layout but use different depletion conditions and selected learning parameters. Source and firmware paths in the three experiment files resolve relative to the configuration directory. The dense simulation retains its historical window title, `Experiment 10`; the file `FinalExperiment3.csc` is the dense scenario used here.

TTFND is elapsed simulation time to the first battery-modelled client's depletion. Capacity is an artificial 10^9 weighted ticks, listening cost is zero, and the root is not depleted. This is a CPU/TX stress proxy, not a calibrated hardware battery model. Logger examples are included under `source/tools/cooja/`; the exact logger variant used for each reported run and the complete tuning-search history have not been established.

## Reproduce a selected run

1. Choose the condition, protocol and seed. The recorded seeds are 123456, 123457 and 123458. Match `Static`, `Degraded`, `Dense short` or `Dense longer` in the learning-configuration CSV to the condition tables above.
2. In `source/examples/rpl-udp/project-conf.h`, enable or disable `SARSA` and `FEDERATION` using the protocol table. For a learning variant, reset all six learning macros to the defaults above, then apply the matching CSV row. Empty federation fields mean not applicable to Standalone SARSA, not missing values. MRHOF has no learning-configuration row because it does not learn.
3. Set `CONF_DRAIN_MAGNITUDE` to 100 for static diamond, degraded diamond or dense short. The dense-longer value is unresolved: recover it before claiming an exact reproduction. If exploring 10 or 50, record the choice explicitly as a candidate configuration. Keep CPU/TX/RX coefficients at 20/60/0.
4. Clean and rebuild both Z1 applications using the commands above. Open the saved scenario and check that its client and root mote types use those rebuilt firmware files.
5. Set the chosen simulation seed in Cooja. Run until the first client reports `Battery depleted. Shutting down node.` and record its simulation timestamp in minutes. Do not include root depletion or average individual clients' lifetimes. Use the event timestamp, not the later display of a periodic sample.
6. Repeat for the other seeds. Summarise the three TTFND values using the arithmetic mean and sample standard deviation (`n-1` denominator). The published learning results were selected after tuning on each of these seeds; repeating the recorded settings is not an independent held-out evaluation.

## Saved simulator and radio settings

These settings are read from the archived source/configurations; they have not been verified by a new firmware build.

| Setting | Archived value / location |
| --- | --- |
| Motes and radio | Zolertia Z1, CC2420; saved `.csc` mote types and `source/arch/platform/z1/` |
| Static diamond medium | UDGM, transmit range 40, interference range 70, TX/RX success ratios 1.0 |
| Dense medium | UDGM, transmit range 50, interference range 100, TX/RX success ratios 1.0 |
| Degraded diamond medium | DirectedGraphMedium; bidirectional 3--4 links have success ratio 0.7, other listed links 1.0 |
| Directed-link attributes | Signal -10, LQI 105, delay 0, channel -1 in the saved degraded `.csc` |
| Application traffic | Nominal ten-second client requests, approximately +/- one-second jitter, random initial delay; replies from root (`udp-client.c`, `udp-server.c`) |
| UDP ports | Client 8765, root 5678 |

Range and signal fields above are simulator parameters, not measurements of physical deployment conditions. Exact positions, graph edges and mote settings are in the saved `.csc` files listed above.

The archived build defaults to CSMA (`MAKE_MAC_CSMA` in `source/Makefile.include`) and IEEE 802.15.4 channel 26 (`IEEE802154_CONF_DEFAULT_CHANNEL` in `source/os/contiki-default-conf.h`). The project configuration does not override these settings or add a MAC sleep schedule. Consult `source/examples/rpl-udp/Makefile`, `source/os/net/netstack.h` and `source/os/contiki-default-conf.h` for the archived build defaults. The `DUTY_CYCLE_PERCENT=5` constant in `battery.c` scales listening ticks in the accounting calculation only: it does not configure a MAC sleep schedule, and listening contributes zero depletion because its cost coefficient is zero.

## Result records and optional plots

`selected_results_and_tuning.csv` preserves the 36 selected lifetimes and the workbook's tuning notes. Its `scenario_sheet` labels map as follows: `Experiment 1` = Static, `Experiment 2` = Degraded, `Experiment 3` = Dense short, and `Experiment 3 LONG` = Dense longer. `selected_ttfnd_minutes` contains decimal minutes; `retained_raw_time` preserves the original timestamp text, including inconsistent separators. The summary calculations use the decimal-minute column.

`complete_learning_configurations.csv` expands the tuning notes into full configurations by applying them to the reset defaults above. `SARSA` in the CSVs means the standalone profile. These two CSVs serve different purposes: one preserves the recorded outcomes and notes, while the other provides the settings needed to configure each selected learning run. `table1_summary.csv` gives the aggregate results.

The archived logger examples under `source/tools/cooja/` write the timestamp/node format expected by the plotting helper. `logging_script.js` times out after 15 minutes; `logging_script_updated.js` times out after 30 minutes. `logging_script_pausable.js` also times out after 30 minutes and pauses once at 15 minutes for manual link changes. Those limits are too short for several reported runs, and the pausing example is not a recipe for the saved degraded configuration, whose degraded links are already set. For a new capture, set an adequate timeout and output filename for the chosen run; do not infer historical run settings from these examples. Relative log filenames are resolved from Cooja's working directory.

The archived `source/examples/rpl-udp/analyse_sarsa_simple.py` is an optional battery-curve plotting helper, separate from the summary checker. It requires pandas and Matplotlib, expects logs named `cooja_sarsa.log`, `cooja_mrhof.log` and/or `cooja_fed.log` in `source/tools/cooja/`, and selects them using `CHOICE` and `ENABLE_COMPARISON` near the top of the script. Its parser expects log lines beginning with a simulation timestamp in microseconds followed by `ID:<node>`. It writes images to the application's `plots/` folder. Those historical input logs are not bundled, so the script alone cannot regenerate the paper's plots.

## Check the reported summary

From the repository root, run:

```sh
python3 research/verify_results.py
```

This recomputes all 12 means and sample standard deviations from the 36 recorded TTFND values, checks the rounded values against Table 1, and checks the scenario/seed/profile mapping, known drain values, the explicit missing dense-longer value, and reconstruction from tuning notes for all 24 learning configurations. It does not rerun Cooja. `research/table1_summary.csv` contains the resulting summary. The calculations use the recorded decimal-minute values.

To verify the package file checksums on Linux, run `sha256sum -c SHA256SUMS.txt` from the repository root before editing any files. A configuration change will intentionally invalidate the corresponding checksum.

## Interpretation and limitations

Learning settings were manually tuned separately for each scenario/seed, selecting the longest TTFND. These are selected outcomes rather than held-out results from one fixed policy. Packet delivery and delay were not selection criteria. The unresolved dense-longer drain multiplier prevents exact reconstruction of that condition. Three seeds, no additional energy-aware baseline, unprofiled full implementation overhead, unavailable historical host/compiler versions and incomplete tuning-search history limit reproducibility and generalisation. Public availability of this package does not resolve those gaps.

## Licences

The artifact documentation, research result records and verification script are provided under the MIT licence in `LICENSE`.

The implementation and bundled third-party code retain their existing licences and copyright notices. See `source/LICENSE.md`, `source/tools/cooja/LICENSE.md` and individual file headers. The root MIT licence applies only to the artifact material described above.
