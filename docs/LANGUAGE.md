# VELA language design

Variance-aware Epoch Language for Adaptation.

This document is the complete design: philosophy, syntax, stdlib, flagship controller, projected impact, and honest limits. The implementation in this repo is a working subset of the same language, not a slide deck.

## A. Name, philosophy, paradigm

**Name:** VELA (Variance-aware Epoch Language for Adaptation). File extension `.vela`. The name is the constellation of the sails, and the thing a ship uses when the wind (capacity) changes.

**Philosophy:** A LEO path is not a continuous RTT process with occasional noise. It is a sequence of **epochs** punctuated by reconfigurations. Every measurement is born in an epoch, carries an interval and a sample count, and becomes uninhabited when that epoch ends. Loss is a closed taxonomy, not a boolean. A claim that "this beats BBR" is a **contract** the runtime evaluates across seeds, not a sentence in a README. The compiler exists to make scientific dishonesty a type error.

**Relation to LeoAware:** VELA is not a competing CCA. LeoAware is the engine. VELA is how that engine is named, checked, and safely extended for space internet. Observe-only compose matching LeoAware is success (no-regress). Beating BBR or raising house-gate goodput/p95 is a gift *to* LeoAware, not a replacement brand. See `docs/MISSION.md`.

**Paradigm:** hybrid of five things that already exist, locked to this domain.

1. **Epoch-typed reactive programming** - signals (`rtt`, `bw`, `delay_ratio`, `p_ho`) fire on ACK, loss, hint, and epoch edges.
2. **Affine provenance for samples** - a `Sample<T> @ e` cannot be read in epoch `e+1` unless it is explicitly named `prior` (soft, discounted, never a min-RTT).
3. **Algebraic loss** - `Loss = Mobility | Congestive | Unknown`. Recovery is type-directed.
4. **Monoidal mechanism composition** - `Detect + SoftReprobe + IntervalBw` is an operator sum with declared effects. Two cutters on the same event are a compile error unless the author writes `compose cuts = min`.
5. **Contract-oriented evaluation** - dual-gate, terrestrial, fairness, and confidence intervals are part of the program text.

This is not "Python with nicer names." Python will happily keep a 20 ms min-RTT across a 90 ms hop. VELA will not.

## B. Syntax and semantics

### Header and modules

```vela
lang vela 0.1
use std.epoch
use std.loss
use std.measure
use std.control
use std.path
use std.hint
use std.eval
```

`use` only imports **named** stdlib surfaces. There is no `import *` of measurement state. That is how stale samples sneak in.

### Types

| Type | Meaning |
|------|---------|
| `Epoch` | Opaque generation. Increments on reconfig (detected or hinted). |
| `Sample<T> @ e` | Point measurement valid only in epoch `e`. |
| `Interval<T> @ e` | `{lo, mid, hi, n, e}`. Default for bandwidth and RTT. |
| `Prob` | `[0, 1]` probability (handover calendar, loss class). |
| `Ratio` | Dimensionless (`delay_ratio = rtt / path_floor`). |
| `Loss` | `Mobility \| Congestive \| Unknown`. |
| `Hint<T>` | External signal (ASCENT-D, Orb, orbital). Fail-closed: corrupt => `None`. |
| `Contract` | Multi-seed assertion set. Not executable on the packet path. |

**Freshness law.** Reading `min_rtt` after `invalidate min_rtt` is a type error. The kernel stores the last epoch's scale as `prior.bw` / `prior.bdp` with a mandatory discount (`<= 0.75` in the first 2 s of a new epoch). You cannot write `min_rtt = prior.min_rtt`.

**Uncertainty law.** An `Interval` used as a point (`bw` in arithmetic) is implicitly `bw.mid` and **requires** `bw.n >= 2`. A single sample is not a bandwidth.

**Hint law.** `hint.ascent` is `Option<PathHint>`. Acting on a missing or erased hint is a type error. This is the ASCENT-D erase-on-fail policy at the type level.

### Events

```
on Reconfig(e) { ... }
on Loss(k) match k { Mobility => ...; Congestive => ...; Unknown => ... }
on Hint(h) { ... }          # fail-closed Option
every ack { ... }           # packet horizon
every epoch { ... }         # epoch horizon
when <pred> { ... }         # guarded continuous action
```

`when p_ho > 0.35` is not a thread. It is a predicate evaluated on each ACK against the path model. The body may `freeze`, scale `pace`, or suppress max-filters. It may not invent capacity.

### Mechanism composition

```vela
compose Detect + SoftReprobe + IntervalBw + PredictiveFreeze + HorizonChase + DualGateGuard
```

Each mechanism declares:

```
reads:  {rtt, bw, epoch, ...}
writes: {cwnd, pace, min_rtt, ...}
cuts:   none | soft | hard
phase:  ack | epoch | both
```

The checker rejects two `hard` cuts on the same event. Soft cuts compose as `min(cut_a, cut_b)` (the more conservative cut wins). This is the language-level answer to "OCE stacked on SER double-moved the window."

### Statistical contracts

```vela
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
  assert terrestrial.goodput >= 77 Mbps
  report ci(0.95), std, ablation
}
```

`vela eval` runs the contract. The compiler will **not** emit a `// beats BBR` comment. The JSON verdict is ACCEPT / FAIL / INCOMPLETE (missing terrestrial, too few seeds, etc.). The harness now emits that top-level `INCOMPLETE` when terrestrial is missing or `n_seeds` is below the contract minimum; a measured miss on a present assert is `FAIL`, and `INCOMPLETE` is never `ACCEPT`.

A one-sided t-test or bootstrap CI on 5 seeds is weak. VELA reports that weakness instead of hiding it: `power=low` is a first-class field. Claiming `p < 0.05` with n=5 and no paired path is a contract warning, not a badge.

### Path models (sim and constraint)

```vela
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform(20ms, 90ms)
  capacity ~ uniform(20Mbps, 120Mbps)
  mobility_loss ~ burst(p=0.08, window=400ms) on reconfig
}
```

The same model object is used by the discrete-event simulator **and** by `PredictiveFreeze` (`p_ho` is the model's predictive CDF, not a magic oracle of the next hop time). In endpoint-only mode the model is estimated from detected gaps, never from future RNG.

## C. Standard library

| Module | What it provides |
|--------|------------------|
| `std.epoch` | `Epoch`, `invalidate`, `prior` (discounted), freshness checks |
| `std.loss` | `Mobility`, `Congestive`, `Unknown`, evidence accumulation |
| `std.measure` | `Sample`, `Interval`, `quantile`, `delay_ratio`, delivery-rate window |
| `std.control` | `cwnd`, `pace`, `Reprobe`, `Freeze`, `cut`, `hold`, `chase` |
| `std.path` | handover calendar, flicker, RTT-jump priors, `p_ho` |
| `std.hint` | ASCENT-D / Orb ingest, `fail_closed`, role checks |
| `std.eval` | `contract`, dual-gate, CI, ablation, seed lists |
| `std.mech` | `Detect`, `SoftReprobe`, `IntervalBw`, `PredictiveFreeze`, `HorizonChase`, `DualGateGuard`, `OCE` (legacy), `Calendar`, `WriteBudget`, `TrimHold`, `TrimFill`, `TrimReclaim`, `QuietReach`, `QuietShield`, `SoftFlicker` |

**Detect** is the LeoAware multi-signal fusion (RTT MAD, ACK inter-arrival, rate drop, mobility burst) with a dual-signal gate. VELA does not "invent a better detector" in v0.1. It *names* the detector so it can be composed without being rewritten.

**SoftReprobe** is two-phase explore/fill with a declared cut (default 0.58 endpoint) and automatic sample invalidation.

**IntervalBw** replaces a point `bw_est` with `{lo, mid, hi}` and an `uncertainty = (hi-lo)/mid`.

**PredictiveFreeze** consumes `std.path`'s calendar. It does not receive the simulator's next hop time in endpoint-only mode.

**HorizonChase** is the OCE successor: post-reprobe delivery chase into an *interval* target, with delay-ratio rollback.

**DualGateGuard** is not a packet-path cutter by default. It records live goodput/p95 trajectory for the eval harness and may ease chase gain if the running p95 would break the contract. It must not secretly sacrifice terrestrial.

**OCE** is provided as a legacy mechanism so v3.7-class controllers can be *expressed* in VELA and compared by ablation (`compose ... + OCE` vs `+ HorizonChase`).

## D. Flagship program: Horizon (named compose on LeoAware, after OCE)

LeoAware v3.7 OCE (prompt SoT, OPE-fair `leo_fast_ho`) sits at **58.78 Mbps / 152.09 ms p95** vs BBRv3approx **58.21 / 152.89** - a dual-gate clearance of +0.57 Mbps and -0.80 ms. That is a real win and also a warning: the next hand-stacked module will not buy 10%.

Horizon is not module N+1. It changes the *quantity being controlled*.

### What OCE does

OCE is a ~3 RTT post-SER echo that chases delivery into `bw_est / 1.42 x BDP` and rolls back on `delay_ratio`. It is a point-estimate chase *after* the hop has already hurt the window. It cannot refuse a stale sample (that is a different module). It cannot be less aggressive in a wide interval and more aggressive in a tight one without another pile of flags.

### What Horizon does

1. **Epoch horizon (predictive freeze).** From the detected inter-hop gaps, estimate `p_ho` over the next 1.4 RTT. When `p_ho` is high, freeze optimistic updates (max-filter off, pace gain 1.00, no chase). This spends the last good milliseconds of an epoch *not* stuffing a queue into a freeze window. OCE cannot do this because OCE has no first-class path model.

2. **Packet horizon (interval chase) - stdlib, not in the v0.1 compose.** `HorizonChase` is a named mechanism. Uncapped chase failed seed-7 ablation (55 Mbps / 173 ms vs LeoAware 89 / 108). The language did its job: compose-list ablation found the bad operator. The shipped Horizon program does **not** include it until `scripts/ablate_seed7.py` is green. IntervalBw still *observes* `{lo, mid, hi}` for `p_ho` and future chase.

3. **Uncertainty-scaled yield.** v3.4-p95 yielded early on every ACK (that is how p95 fell under BBR and goodput fell from the v3.3-A peak). Horizon yields early only when uncertainty is high or `p_ho` is high. In a tight epoch it is allowed to sit closer to 1.15 x BDP. The language makes this one `when` clause, not a sixth copy of the delay ladder.

4. **Typed Unknown loss.** Mobility holds. Congestive cuts 0.72. Unknown requires `delay_ratio > 1.35` before a cut. This is already LeoAware policy; VELA makes the fall-through visible.

5. **Dual-gate as a live object.** The same contract that `vela eval` runs can ease chase gain if the in-run p95 trajectory is breaking. It cannot mint capacity.

### Why VELA makes this leap possible

In Python/C++/Rust the Horizon ideas are "just more state." They collide with REPROBE, freeze, delay_yield, OCE, and Orb suppress. Every session that stacked a module onto LeoAware paid that tax (false REPROBE storms, hybrid double-cut, DTCE rejected, p95 reclaim trading away the 75 Mbps floor).

In VELA:

- `PredictiveFreeze` *declares* it writes `pace` and `freeze`, not `cwnd` hard-cut. The checker will not let it also call `cut(0.58)`.
- `HorizonChase` *declares* it runs only in `phase: ack` after `SoftReprobe` has exited. It cannot start during explore.
- `IntervalBw` is the only writer of `bw`. OCE cannot sneak a second `bw_est = max_filter`.
- The contract is in the file. A researcher cannot "forget terrestrial" without `INCOMPLETE`.

The algorithmic leap is the same physics. The language leap is that the physics is *composable and checkable*.

Concrete Horizon source: [`examples/horizon.vela`](../examples/horizon.vela). Shipped Horizon is observe-only after the house gate (see `docs/EVAL-NOTES.md`).

### D2. Flagship program: Reach (after Horizon and Luff)

Horizon pointed into the wind. Luff trimmed every gust. QuietReach lifted `cwnd` in a quiet epoch. QuietShield refused Detect. SoftFlicker softened the 0.58 cut. Every write failed a house seed.

The leftover vs BBR on seeds 7 and 123 is **not a missing fill**. Seed 7 90s runs 55 REPROBE against 8 real handovers. Those extra detects are flicker handling (capacity wobble, ACK-IA freeze), not bugs. BBR skips them and wins 7/123. LeoAware pays the 0.58 cut and wins 13/42 plus the dual-gate *means*. Mean p95 slack vs BBR is 0.46 ms.

**Reach** is the beam reach: name the typed reconfig, keep the house-winning cut, and make every failed successor a stdlib operator you have to *choose*.

Shipped compose: `Detect + SoftReprobe + Calendar + IntervalBw + WriteBudget + DualGateGuard`. Observe-only. Bit-identical to LeoAware when the write flags are off.

Typed reconfig (in the stdlib, not in this compose):

| Kind | Evidence | Cut | Ablation |
|------|----------|-----|----------|
| RttHop | `rtt_mad` / `rtt_jump` / `rtt_classic` | 0.58 | load-bearing |
| Flicker | `ack_ia` / `rate_drop` alone | 0.58 (0.85 dumped seed 7 to 55 Mbps) | SoftFlicker FAIL |

Closed write class (stdlib only): `HorizonChase`, `TrimFill`, `TrimReclaim`, `QuietReach`, `QuietShield`, `SoftFlicker`, `TrimHold`.

Source: [`examples/reach.vela`](../examples/reach.vela). The language result is the failure class. The packet policy that still clears the house dual-gate is LeoAware v3.4-p95.

A reconstructed OCE-class controller lives in [`examples/leoaware_oce.vela`](../examples/leoaware_oce.vela) so ablation is a compose-list change, not a fork.

### Projected / measured gain

The *design target* is a statistically honest dual-gate: mean goodput clearly above the OCE/LeoAware baseline and mean p95 at or under the BBR/LeoAware p95, with terrestrial `>= 77 Mbps @ 40 ms`, on the same seeds and the same path law.

On this machine the locked sibling sim is LeoAware **v3.4-p95** (coupled-RNG era: 73.57 Mbps / 138.37 ms vs BBR 70.88 / 138.8). OPE-fair v3.7 numbers in the invention prompt (58.78 / 152.09) are a different eval law and must not be mixed into one table.

`vela eval` writes `results/eval_*.json`. That file is the only allowed source for "Horizon beats X" sentences. If an eval misses the stretch 5-10% goodput target, the language is still the product; the controller is a program you can change without rewriting the kernel.

Lab note (first `--fast` eval, 45s, seeds 13+7): a literal `pace *= 0.94` on every ACK while `p_ho > 0.35` destroyed seed 7 (65 / 181 vs LeoAware 89 / 108). That is exactly the class of accident VELA is meant to make visible: a `when` body is a *level*, not a per-ACK multiply, unless the author writes an integrator. Kernel 0.1.1 sets pace from `bw.mid` and requires `p_ho > 0.55` plus three real HO-scale gaps before the calendar is trusted.

## E. Real-world impact (Starlink-class)

If Horizon (or a later VELA program) clears a dual-gate with a material margin, users see:

- **Higher sustained goodput** on the same dish and the same orbit, because the sender stops under-running stable epochs and stops over-running the last 200 ms before a hop.
- **Lower interactive latency variance** because predictive freeze and uncertainty-scaled yield cut the queue spike that currently sits in the p95.
- **Fewer "dead" seconds after handover** because REPROBE + interval chase refill from a discounted prior instead of CUBIC collapse or a stale BBR min-RTT.
- **Fairness / multi-flow:** `fair_mode` remains a declared mechanism (AIMD around 1.0 x BDP). VELA does not pretend one flow's Horizon chase is multi-flow optimal.
- **Energy / radio:** fewer useless retransmits during mobility bursts (typed Mobility => hold). The satellite still burns the same RF; the user device wastes fewer watts on recovery.
- **Assist path:** when ASCENT-D hints are present they are `Option` and fail-closed. When they are absent, Horizon is still defined. That is the only deployment story that matches today's Starlink (no official path-hint API).

Secondary: a VELA program is a reviewable artifact. A reviewer can see `compose` and the contract without spelunking 900 lines of `on_ack`.

## F. Limitations (language and algorithm)

**Physics.** VELA cannot see the next satellite before the path changes unless a real hint exists. `p_ho` is a calendar estimate from past gaps. Irregular hops (ISL reroute, weather, beam reshape) will fool the calendar. Predictive freeze then becomes a mild pace ease at the wrong time. The kernel caps that ease (default 6%) so a wrong calendar cannot stall the flow.

**Information.** IntervalBw needs samples. The first 1-2 RTT of an epoch are supposed to be uncertain. Forcing a tight interval early is the same bug as a stale min-RTT, with extra ceremony.

**Statistics.** Five seeds do not make a journal result. VELA will mark `power=low` and still allow ACCEPT on the dual-gate *means* (the OrbitStack house rule) while refusing a `p < 0.05` badge unless the contract asks for more seeds or a paired bootstrap and gets them.

**Deployment.** The working backend is Python on the LeoAware discrete-event sim, which is a research path, not quiche. Rust emit is a typed IR sketch (`vela emit-rust`), not a congestion controller you can ship in production QUIC tomorrow. Porting still requires a real ACK clock, pacing, and loss signal.

**Composition is not magic.** If two mechanisms both want to raise `cwnd`, the checker asks you to pick `compose growth = min | max | sum`. Wrong picks still compile if they are explicit. VELA prevents *accidents*, not *bad taste*.

**Fairness and AQMs.** Horizon is a single-sender policy. A fleet of Horizons plus Cubic plus BBR at a shared gateway is a different paper. The language can *state* a Jain bound; it cannot enforce other people's stacks.

**Hints can lie.** Fail-closed integrity (ASCENT-D) stops bit flips. It does not stop a malicious or stale honest hint with a valid MAC. Role + age checks are the remaining rail; they are not a PKI.

**Sim != orbit.** `LeoPath` is a Starlink-*class* model (handover, jump, flicker, mobility burst). It is not a replay of a particular cell or a particular software release. Real CSV traces are a `path` object. Until they are wired, numbers are lab numbers.

**OCE-era complexity.** VELA does not delete LeoAware. It wraps the parts that worked (Detect, SoftReprobe, delay yield) and refuses the parts that exploded (unnamed flags, double cuts, README-only wins). Researchers can still write a bad controller in VELA. They cannot write an *invisible* one.

---

## Implementation map (this repo)

| Piece | Role |
|-------|------|
| `vela/lexer.py` `parser.py` `ast.py` | Concrete syntax (0.3: view, integrate, authority) |
| `vela/types.py` `checker.py` | Freshness, loss, reconfig kinds, WriteCap, integrators |
| `vela/digest.py` `receipt.py` | Domain-separated SHA-256, merkle receipts |
| `vela/ir.py` `compile.py` | Mechanism IR + Python lowering + views |
| `vela/kernel.py` | Composition runtime + HorizonCCA |
| `vela/eval_harness.py` | Dual-gate runner on leo-aware-transport |
| `examples/*.vela` | Equinox (0.3), Reach, Horizon, Luff, OCE-class |

## G. Equinox (VELA 0.3)

The 0.2 packet search closed: every additive write failed a house seed.
0.3 evolves the *language* so those accidents are type errors, hashed
operators, and receipts.

See [EQUINOX.md](EQUINOX.md). Summary:

| Law | What it refuses |
|-----|-----------------|
| Level vs integrator | `when { pace *= k }` without `integrate when` |
| WriteCap | cruise writes with `authority` budget 0 |
| Kinded reconfig | `on Reconfig match` missing `RttHop` or `Flicker` |
| Cut refinement | `cut(1.2)` |
| Compose digest | silent operator swap |
| Eval receipt | a verdict detached from its source |
| Views | eval of compose A claimed as compose B |

Existing `lang vela 0.1` programs still parse. WriteCap and reconfig
match are opt-in. Flagship sources: `examples/equinox.vela` (language)
and `examples/reach.vela` (house policy).

Version: VELA 0.3.0 (Equinox: authority, receipts, views).
