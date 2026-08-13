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
py -3 -m vela check examples/equinox.vela
py -3 -m vela digest examples/equinox.vela
py -3 -m vela mech
py -3 -m vela compile examples/equinox.vela -o emit/equinox_cca.py
py -3 -m unittest discover -s tests -v
```

Evaluate against the OrbitStack / LeoAware research sim (`~/Projects/leo-aware-transport`):

```bash
py -3 -m vela eval examples/horizon.vela --fast
py -3 -m vela eval examples/horizon.vela --seeds 13,7,42,99,123
```

## Language in one screen

```vela
lang vela 0.1

use std.epoch
use std.loss
use std.measure
use std.control
use std.eval

controller Horizon {
  compose Detect + SoftReprobe + IntervalBw + PredictiveFreeze + DualGateGuard

  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    p_ho: Prob

  on Reconfig(e) {
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }

  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > 1.35 then cut(0.72) else hold
  }

  when p_ho > 0.35 {
    freeze min_rtt, bw for 1.4 * rtt
    pace = bw.mid
  }

  every ack {
    chase delivery toward bw.quantile(0.35 + 0.40 * (1 - epoch.uncertainty)) / (1.26 * bdp)
      rollback if delay_ratio > 1.40
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

`examples/reach.vela`. Horizon stays as the first observe-only compose. See [docs/LANGUAGE.md](docs/LANGUAGE.md) and [docs/EVAL-NOTES.md](docs/EVAL-NOTES.md).

## Layout

```
vela/           compiler, type checker, composition kernel, Horizon CCA
examples/       equinox.vela, reach.vela, horizon.vela, luff.vela, leoaware_oce.vela
docs/           LANGUAGE.md (complete design)
tests/          parser, types, kernel
emit/           compiled Python (generated)
```

## Honesty

VELA does not violate causality or invent capacity. A Starlink-class path still has handovers, RTT jumps, and a real bottleneck. The language's job is to stop wasting the information the endpoint already has, and to refuse claims the numbers do not support.

**v0.3 Equinox:** the language grew. Integrators in `when` are type errors. WriteCap is linear. Reconfig is a closed kind. Eval writes a SHA-256 receipt bound to source + compose + merkle of rows. Views are first-class compose morphisms. House LeoAware remains 73.57 / 138.37 vs BBR 70.88 / 138.83. JSON + receipt under `results/` are the only win table. See `docs/EQUINOX.md` and `docs/EVAL-NOTES.md`.

## License

MIT. GitHub copy is **private** (`Pitchfork-and-Torch/vela`) until we decide to open it. Not affiliated with SpaceX, Cloudflare, or xAI. Issues on that repo only. No personal contact in-tree.
