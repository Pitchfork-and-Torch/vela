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

### reach (v0.2 design, eval pending)

New flagship: `examples/reach.vela`. Compose Detect + SoftReprobe + Calendar + IntervalBw + WriteBudget + TrimHold + QuietReach + DualGateGuard.

Thesis: the leftover is the quiet middle of an epoch on easy paths (seeds 7, 123), not the hop.

**reach-ablate-1** (0.88 * bw.lo, uncertainty < 0.40): bit-identical to LeoAware on seed 7 45s (88.65/108.4), seed 123 90s (62.71/111.0), terrestrial (77.82/40). No-op. Lesson: `bw.lo` is below cruise; LEO intervals are wide so the tight-uncertainty gate never opens.

**reach-ablate-2** (`1.28 * bw.est * min_rtt`): seed 7 still identical (88.65 / 83.54). Seed 123 **52.89 / 141.6** vs Leo 62.71 / 111.0. Additive cwnd is the same death class.

**diag:** seed 7 90s 55 REPROBE / 8 HO. Seed 123 49/8. Seed 13 51/8. Seed 42 53/7. Counterfeit epochs.

**reach-ablate-3** (QuietShield refuse, 8-28s calendar): seed 7 45s 79.13/76.2. Missed real hops.

**reach-ablate-4** (QuietShield refuse, RTT-token only): seed 7 45s 87.81/114.6 (near). Seed 7 90s 74.92/175. Seed 123 66.92/193. Seed 13 58.29/187. Same class as v2.1. The 47 extra REPROBEs are flicker handling, not bugs.

**reach-ablate-5** (SoftFlicker cut 0.85, keep invalidate): seed 7 45s **55.24 / 123.8**. Seed 7 90s 62.43/123.8. Seed 123 80.98/156.5 (gp up, p95 death). Seed 13 62.87/102.5 (gp death). Same collapse class as Horizon chase.

**Decision:** Reach compose is observe-only. Typed reconfig stays in the stdlib. The 0.58 endpoint cut is load-bearing on hop *and* flicker. Do not claim a dual-gate win. VELA is not a rival to LeoAware; the engine remains v3.4-p95 (73.57 / 138.37 vs BBR 70.88 / 138.83). See `docs/MISSION.md`.

**reach-passthrough:** shipped `examples/reach.vela` seed 7 45s **88.65 / 108.4** = LeoAware. JSON log: `results/eval_reach-ablate.json`.
