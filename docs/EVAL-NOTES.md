# VELA / Horizon eval notes

Only JSON under `results/` is a claim. This file is the lab log.

## Laws

- Do not mix OPE-fair v3.7 prompt numbers (58.78 / 152.09) with this machine's coupled-RNG LeoAware v3.4-p95 (73.57 / 138.37).
- `--fast` is 45s / 2 seeds. Not the house gate.
- House gate: seeds 13,7,42,99,123 · 90s · `leo_fast_ho` + terrestrial.

## Runs

### horizon-fast (v0.1.0)

`pace *= 0.94` every ACK while `p_ho > 0.35`.

| seed | Horizon gp/p95 | LeoAware gp/p95 |
|-----:|---------------:|----------------:|
| 13 | 73.52 / 123.2 | 68.21 / 165.4 |
| 7 | 65.25 / 181.3 | 88.65 / 108.4 |

Terrestrial OK (~77.8 @ 40). Verdict FAIL. Lesson: `when` bodies are levels, not integrators.

### horizon-fast2 (v0.1.1)

Set-pace + extra uncertainty yield.

| seed | Horizon gp/p95 | LeoAware gp/p95 |
|-----:|---------------:|----------------:|
| 13 | 66.27 / 96.1 | 68.21 / 165.4 |
| 7 | 67.83 / 128.5 | 88.65 / 108.4 |

p95 mean under BBR; goodput dumped. Extra post-hop yield stacked on v3.4 delay_yield.

### horizon-fast3 (v0.1.2)

PredictiveFreeze (set pace) + gated stable reclaim. No extra yield. No bw_est replace.

Seed 13: 83.34 / 120.4 vs Leo 68.21 / 165.4 (chase still on, helped this seed).
Seed 7: 65.89 / 118.4 vs Leo 88.65 / 108.4 (chase dump).

### seed-7 ablation (wrapper proof)

| variant | gp | p95 |
|---------|---:|----:|
| LeoAware | 88.65 | 108.4 |
| Horizon-pass (all flags off) | 88.65 | 108.4 |
| Horizon-freeze only | 88.65 | 108.4 |
| Horizon-chase only (uncapped) | 55.29 | 173.5 |
| Horizon-chase (180ms, then prior_bdp) | 65.9-76 | 120-150 |

**Decision:** ship Horizon compose **without** HorizonChase. Chase stays in the stdlib. Re-enable after `scripts/ablate_seed7.py` is green on seed 7 and seed 13.

### horizon-fast4 (v0.1.3, chase out of compose)

| seed | Horizon | LeoAware |
|-----:|--------:|---------:|
| 13 | 68.18 / 165.4 | 68.21 / 165.4 |
| 7 | 88.65 / 108.4 | 88.65 / 108.4 |
| terr | 77.76 / 40.0 | 77.76 / 40.0 |

PredictiveFreeze did not fire (needs 3 HO-scale gaps). Wrapper + compose = LeoAware within 0.02 Mbps. This is the no-regress rail.

### horizon-house (90s, partial, CPython 3.13 crash)

Interpreter died in LeoAware `_mad` on seed 42 (`Executing a cache`). Not a VELA bug.

| seed | BBR | LeoAware | Horizon |
|-----:|----:|---------:|--------:|
| 13 | 65.38 / 188.6 | 77.05 / 165.4 | 73.10 / 165.4 |
| 7 | 90.78 / 111.3 | 83.54 / 111.1 | 83.54 / 111.1 |

Seed 13 90s: freeze cwnd-cap cost ~4 Mbps, p95 unchanged. Kernel now pace-only at `p_ho > 0.80`. Re-run house gate next session.

### horizon-house (90s, isolated workers, 5 seeds) - COMPLETE

Isolated workers survived CPython 3.13. LeoAware matched the locked v3.4-p95 table (**73.57 / 138.37** vs BBR **70.88 / 138.83**).

| seed | BBR | LeoAware | Horizon (pace+reclaim) |
|-----:|----:|---------:|-----------------------:|
| 13 | 65.38 / 188.6 | 77.05 / 165.4 | 73.10 / 165.4 |
| 7 | 90.78 / 111.3 | 83.54 / 111.1 | 83.54 / 111.1 |
| 42 | 62.55 / 116.2 | 79.02 / 154.9 | 71.48 / 159.6 |
| 99 | 65.39 / 156.5 | 65.54 / 149.5 | 65.54 / 149.5 |
| 123 | 70.31 / 121.6 | 62.71 / 111.0 | **57.49 / 192.5** |

Means: Horizon 70.23 / 155.6 vs LeoAware 73.57 / 138.4 vs BBR 70.88 / 138.8. Terrestrial Horizon 78.18 @ 40 **PASS**. Dual-gate **FAIL**.

**Decision:** v0.1.4 kernel is observe-only. PredictiveFreeze / IntervalBw still *measure*. No pace or cwnd writes until a new ablation is green. JSON: `results/eval_horizon-house.json`.

Confirm after the patch: seed 123 90s LeoAware **62.71 / 111.0** = Horizon **62.71 / 111.0**.
