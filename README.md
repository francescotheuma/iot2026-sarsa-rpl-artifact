# IoT 2026 SARSA/RPL research artifact

Source and selected results supporting **Energy-Aware RPL Parent Selection using Lightweight SARSA and Federated Weight Sharing**.

## Version and scope

`source/` contains the tracked Contiki-NG submission tree at commit `ed98a7d8e9331802dc1fe50dee4884f8388e2e91` of `francescotheuma/contiki-ng-sarsa`, inspected on branch `fyp-submission`. This is a snapshot without the private repository's Git history. It is deliberately not a snapshot of the different `main` branch. Uncommitted changes and generated logs/builds are excluded.

Cooja is included under `source/tools/cooja/` at the parent's pinned commit `1869e6ee8d19812fc018350a633b661fecec947e`. Other optional platform submodules are not bundled; their public URLs and exact commits are listed in `research/provenance.json`. The included source is preserved without algorithm changes.

## Contents

- `source/examples/rpl-udp/`: application client/server, learning implementation, battery proxy, project configuration and saved topologies.
- `source/os/net/routing/rpl-lite/rpl-icmp6.c`: continuation-score DIO option.
- `research/selected_results_and_tuning.csv`: 36 selected TTFND results and original workbook tuning notes.
- `research/complete_learning_configurations.csv`: complete parameter tuples for the 24 selected learning runs, reconstructed using the author's confirmed reset-to-default procedure.
- `research/table1_summary.csv`: Table 1 means and sample standard deviations, checked by `research/verify_results.py`.
- `research/provenance.json`: source and dependency versions, confirmed battery settings and their provenance.
- `SHA256SUMS.txt`: package-file integrity checks. Hashes refer to repository file bytes; use `git -c core.autocrlf=false clone` when checking on Windows to avoid checkout newline conversion. The checksum list excludes itself.

## Build and configuration

Use a Linux environment with the Z1/MSP430 toolchain required by this Contiki-NG tree, GNU Make and a compatible Java/Gradle environment. The bundled Cooja build specifies Java 21 and includes its Gradle wrapper. Historical host/compiler versions have not been recovered, and this package has not been rebuilt or experimentally rerun as part of the manuscript revision.

From `source/tools/cooja/`, follow its README to build Cooja (for example `./gradlew distZip`). If extracting the ZIP loses executable permissions, restore them for `gradlew`. Required Gradle dependencies are downloaded during the build; this is not an offline distribution.

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
| Dense longer | 50 |

These values were confirmed by the author on 7 October 2026. All other battery settings were unchanged, and each condition used the same battery settings for MRHOF, Standalone SARSA and Federated SARSA. The learning-configuration CSV and provenance manifest record the same multipliers. The archived project configuration starts at 100: explicitly set it to 50 before building dense longer.

The multiplier acts directly on the weighted Energest ticks; 50 is half the rate of 100 for the same recorded activity. The thesis also records a half-drain dense experiment with a different reported lifetime. Keep that result set distinct from the conference dense-longer results. The historical settings above rely on the author's confirmation; they have not been independently rerun.

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

Set seed 123456, 123457 or 123458 as recorded in the results. Dense short and longer share the layout but use different depletion conditions and selected learning parameters. Saved files resolve application paths relative to the configuration directory.

TTFND is elapsed simulation time to the first battery-modelled client's depletion. Capacity is an artificial 10^9 weighted ticks, listening cost is zero, and the root is not depleted. This is a CPU/TX stress proxy, not a calibrated hardware battery model. Exact historical custom logger scripts and the full tuning-search history have not been established; the committed Cooja tree is included, not the current uncommitted logger variants.

## Reproduce a selected run

1. Choose the condition, protocol and seed. The recorded seeds are 123456, 123457 and 123458. Match `Static`, `Degraded`, `Dense short` or `Dense longer` in the learning-configuration CSV to the condition tables above.
2. In `source/examples/rpl-udp/project-conf.h`, enable or disable `SARSA` and `FEDERATION` using the protocol table. For a learning variant, reset all six learning macros to the defaults above, then apply the matching CSV row. Empty federation fields mean not applicable to Standalone SARSA, not missing values. MRHOF has no learning-configuration row because it does not learn.
3. Set `CONF_DRAIN_MAGNITUDE` for the chosen condition. Keep CPU/TX/RX coefficients at 20/60/0.
4. Clean and rebuild both Z1 applications using the commands above. Open the saved scenario and check that its client and root mote types use those rebuilt firmware files.
5. Set the chosen simulation seed in Cooja. Run until the first client reports `Battery depleted. Shutting down node.` and record its simulation timestamp in minutes. Do not include root depletion or average individual clients' lifetimes. Use the event timestamp, not the later display of a periodic sample.
6. Repeat for the other seeds. Summarise the three TTFND values using the arithmetic mean and sample standard deviation (`n-1` denominator). The published learning results were selected after tuning on each of these seeds; repeating the recorded settings is not an independent held-out evaluation.

The archived logger and full tuning search are not completely recovered. These instructions describe how to configure and measure a run, not a claim that the historical results have been rerun successfully.

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

## Check the reported summary

From the repository root, run:

```sh
python3 research/verify_results.py
```

This recomputes all 12 means and sample standard deviations from the 36 recorded TTFND values, checks the rounded values against Table 1, and checks the scenario/seed/profile mapping and drain values for all 24 learning configurations. It does not rerun Cooja. `research/table1_summary.csv` contains the resulting summary. The calculations use the recorded decimal-minute values; the retained raw timestamp column is preserved as historical evidence and is not silently reinterpreted.

## Interpretation and limitations

Learning settings were manually tuned separately for each scenario/seed, selecting the longest TTFND. These are selected outcomes rather than held-out results from one fixed policy. Packet delivery and delay were not selection criteria. Three seeds, no additional energy-aware baseline, unprofiled full implementation overhead, unavailable historical host/compiler versions and incomplete tuning-search history limit reproducibility and generalisation. Public availability of this package does not resolve those gaps.

## Licences

Upstream licence files and per-file copyright notices are retained under `source/`. See `source/LICENSE.md` and `source/tools/cooja/LICENSE.md`; individual files and third-party components may carry their own terms. This archive does not replace their licences with a new blanket licence. Newly added documentation and result records have no separately assigned licence in this draft; the author should choose one before publication.

## Publication status

Public repository: https://github.com/francescotheuma/iot2026-sarsa-rpl-artifact . The source version is fixed by the provenance manifest. No tagged release or research-archive DOI has been assigned; do not cite an invented release or DOI.
