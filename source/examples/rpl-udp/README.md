# Paper implementation: RPL UDP with SARSA and federated weight sharing

This folder contains the paper's UDP application and parent-selection implementation:

- `udp-client.c` and `udp-server.c`: application traffic and federated weight reports/replies.
- `rpl-sarsa.c`: parent scoring, learning updates and federated blending.
- `battery.c` and `battery.h`: the Energest-based battery proxy and depletion logging.
- `project-conf.h`: protocol switches, learning parameters and battery coefficients.
- `Final Experiment 1 (Simple Diamond)/FinalExperiment1.csc`: static diamond.
- `Final Experiment 2 (SARSA load balancing)/FinalExperiment2.csc`: degraded diamond.
- `Final Experiment 3 (Rings)/FinalExperiment3.csc`: dense short/longer topology.

Use the [artifact README](../../../README.md) for build instructions, configuration tables, seed selection and measurement steps. The matching per-run settings and result records are under [`research/`](../../../research/).

The saved experiments use Z1 motes, with node 1 as the UDP server/RPL root and the other nodes as clients. Enable `SARSA` for learning parent selection, and enable `FEDERATION` alongside it for weight sharing. Disable both for the MRHOF comparison. Clean and rebuild both applications whenever these settings change.

`analyse_sarsa_simple.py` is the archived plotting helper. It needs pandas, Matplotlib and separately captured logs in the format described in the artifact README. Historical logs are not included.

The generic `rpl-udp-sky.csc`, `rpl-udp-cooja.csc`, `rpl-udp.resc` and `rpl-udp.robot` files are retained upstream examples for Sky/Cooja motes and Renode. They are not the saved configurations used for the paper.
