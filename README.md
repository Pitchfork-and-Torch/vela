# VELA

**Variance-aware Epoch Language for Adaptation**

A domain language for designing, checking, and deploying LEO-aware congestion control.

Tagline: *Samples die with their epoch. Claims without variance do not compile.*

VELA does not compete with LeoAware. LeoAware is the packet-path engine (OrbitStack). VELA is the language that names its mechanisms, refuses stale samples, and lets the next space-internet improvement be composed instead of stacked as another unnamed flag (Soft-QIR, Keel, 2PC TBPR, SER, OCE). A VELA wrap that matches LeoAware is the no-regress rail. A wrap that improves the house gate is a gift to that engine.

It is a language where:

- path epochs and reconfiguration are types, not comments
- mobility loss and congestion have different recovery types
- bandwidth and min-RTT are intervals with provenance
- dual-gate contracts (goodput, p95, terrestrial, fairness) are part of the program
- mechanisms compose with declared effects, so a new chase cannot silently double-cut `cwnd`

## Why not Python / C++ / Rust alone?

Those languages can *express* a controller. They cannot *refuse* a stale min-RTT, a point estimate treated as truth, or a "win" claimed on one seed. VELA makes those scientific errors type errors or contract failures.

The compiler still emits ordinary sender code (Python now, Rust-shaped IR next) that plugs into a QUIC-class `on_ack` / `on_loss` / `can_send` loop.

## Quick start

```bash
git clone https://github.com/Pitchfork-and-Torch/vela.git
cd vela
py -3 -m vela check examples/reach.vela
py -3 -m vela check examples/equinox.vela
py -3 -m vela check examples/fair.vela
py -3 -m vela digest examples/equinox.vela
py -3 -m vela mech
py -3 -m vela compile examples/equinox.vela -o emit/equinox_cca.py
py -3 -m unittest discover -s tests -v
```

`vela check examples/reach.vela` must print `observe-only`, `passthrough`, and `no-oracle`. That is the no-regress rail, not a rival CCA.

Evaluate against the OrbitStack / LeoAware research sim (clone `Pitchfork-and-Torch/leo-aware-transport`, or set `LEO_AWARE_TRANSPORT`):

```bash
py -3 -m vela eval examples/reach.vela --fast
py -3 -m vela eval examples/reach.vela --seeds 13,7,42,99,123
```

## Language in one screen

Flagship Reach. Observe-only. A cruise `pace` or `chase` write is a type error
(passthrough; that leftover dumped seed 7). Not a rival CCA.

```vela
lang vela 0.1

use std.epoch
use std.loss
use std.measure
use std.control
use std.path
use std.eval

controller Reach {
  posture observe
  compose Detect + SoftReprobe + Calendar + IntervalBw
        + WriteBudget + DualGateGuard

  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    delay_ratio: Ratio
    p_ho: Prob

  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }

  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > 1.35 then cut(0.72) else hold
  }
}

contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
  assert terrestrial.goodput >= 77 Mbps
  report ci(0.95), ablation
}
```

## Flagship controller

**Reach** is the current VELA program on top of LeoAware. It names typed reconfig (RTT hop vs flicker) and keeps the load-bearing 0.58 cut. Every additive write we tried failed a house seed. Those operators live in the stdlib so the next gift to LeoAware cannot be an unnamed flag.

`examples/reach.vela`. `vela check` proves it is observe-only, names typed reconfig (`RttHop | Flicker`, house cut 0.58), names typed loss (`Mobility | Congestive | Unknown`), and stamps `passthrough` (no cruise write). Closed-write operators are a type error unless the author writes `posture review`. A `when` / `every` pace or cwnd write is also a type error on observe. A Mobility cut or an unguarded Unknown cut is a type error on observe. Horizon stays as the first observe-only compose. `examples/ascent.vela` is the fail-closed Starlink assist path: a missing hint is None, not a hop oracle. See [docs/LANGUAGE.md](docs/LANGUAGE.md) and [docs/EVAL-NOTES.md](docs/EVAL-NOTES.md).

## Layout

```
vela/           compiler, type checker, composition kernel, Horizon CCA
examples/       equinox.vela, reach.vela, fair.vela, ascent.vela, horizon.vela, luff.vela, leoaware_oce.vela
docs/           LANGUAGE.md (complete design), EQUINOX.md, INGRESS.md
tests/          parser, types, kernel, eval verdicts
emit/           compiled Python (generated)
```

## Honesty

VELA does not violate causality or invent capacity. A Starlink-class path still has handovers, RTT jumps, and a real bottleneck. The language's job is to stop wasting the information the endpoint already has, and to refuse claims the numbers do not support.

**v0.4 Ingress:** the endpoint cannot see the next hop (`next_capacity` is a type error and a kernel drop). Optional `scenario leo_multi` plus `assert mean(jain) >= 0.85` is a contract, not a README. Soft cuts compose as min at runtime (SoftFlicker cannot undo the 0.58 house cut). Flagship Reach stays observe-only.

**v0.3 Equinox:** integrators in `when` are type errors. WriteCap is linear. Reconfig is a closed kind. Eval writes a SHA-256 receipt bound to source + compose + merkle of rows. Views are first-class compose morphisms. House LeoAware remains 73.57 / 138.37 vs BBR 70.88 / 138.83. JSON + receipt under `results/` are the only win table. See `docs/INGRESS.md`, `docs/EQUINOX.md`, and `docs/EVAL-NOTES.md`.

## License

MIT. Source: [github.com/Pitchfork-and-Torch/vela](https://github.com/Pitchfork-and-Torch/vela). Site: [vela.jonbailey.xyz](https://vela.jonbailey.xyz/). Not affiliated with SpaceX, Cloudflare, or xAI. Issues on that repo only. No personal contact in-tree.
