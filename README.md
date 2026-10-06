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
- `research/provenance.json`: source and dependency versions and unresolved historical settings.
- `SHA256SUMS.txt`: package-file integrity checks.

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

CPU/TX/RX costs are respectively 20/60/0 for all experiments. Only `CONF_DRAIN_MAGNITUDE` varied to alter test duration. **Dense short uses 100, documented by thesis Figure 13 and Table 5. Diamond and dense longer multipliers still require author confirmation.** The archived value 100 must not be assumed to apply to every published run. Blank drain fields in the CSV explicitly represent missing information. The thesis also documents a separate dense half-drain condition at 50 (roughly 12 minutes MRHOF), which is not the conference dense longer condition (roughly 60 minutes). In the code D is a literal multiplier, so 50 is half the rate of 100; it is not independently divided by 100.

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

## Interpretation and limitations

Learning settings were manually tuned separately for each scenario/seed, selecting the longest TTFND. These are selected outcomes rather than held-out results from one fixed policy. Packet delivery and delay were not selection criteria. Three seeds, no additional energy-aware baseline, unprofiled full implementation overhead and missing historical drain settings limit reproducibility and generalisation. Public availability of this package does not resolve those gaps.

## Licences

Upstream licence files and per-file copyright notices are retained under `source/`. See `source/LICENSE.md` and `source/tools/cooja/LICENSE.md`; individual files and third-party components may carry their own terms. This archive does not replace their licences with a new blanket licence. Newly added documentation and result records have no separately assigned licence in this draft; the author should choose one before publication.

## Publication status

Intended public repository: https://github.com/francescotheuma/iot2026-sarsa-rpl-artifact . The source version is fixed by the provenance manifest. No tagged release or research-archive DOI has been assigned; do not cite an invented release or DOI.
