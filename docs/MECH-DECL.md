# std.mech ↔ LeoAware declaration wire

**Date:** 2026-09-22  
**Gift tip:** Pitchfork-and-Torch/leo-aware-transport @ `ed46126`  
**Schema:** `leoaware.vela_std_mech/v1` (`python3 -m leo_cc.mech_decl`)

VELA `std.mech` **cites** the LeoAware gift surface. It does not fork Detect /
SoftReprobe, does not retune SoftReprobe house cut **0.58**, and does not enable
closed-write on flagships.

## Why

LeoAware is the packet-path engine. VELA composers name `Detect`, `SoftReprobe`,
`OCE`, `DualGateGuard`, `SoftFlicker`, and `TypedLoss`. The sibling export is the
stable declaration so check / compose can cite those names without inventing a
second SoftReprobe.

## Commands

```bash
# Flagship check — no sibling required at runtime
python3 -m vela check examples/reach.vela
python3 -m vela check examples/ascent.vela

# Cite (loads sibling when present; never fails if absent)
python3 -m vela check examples/reach.vela --cite-leoaware
python3 -m vela mech --cite-leoaware

# Optional fail-closed validate against sibling gift
python3 -m vela mech --against-leoaware
python3 -m vela check examples/reach.vela --against-leoaware
```

`--against-leoaware` is fail-closed when the sibling is missing. Default
`vela check` on Reach / Ascent stays green without leo-aware-transport.

Override sibling path with `LEO_AWARE_TRANSPORT`.

## Shared gift names

| VELA / LeoAware name | Posture | Notes |
|----------------------|---------|-------|
| Detect | observe | Endpoint fusion; path HO fail-closed |
| SoftReprobe | observe | House cut **0.58** on RttHop and Flicker |
| OCE | review | Writes cwnd; not Current / not flagship |
| DualGateGuard | observe | Dual-gate bars; not a secret cutter |
| SoftFlicker | review | 0.85 dumped seed 7; observe `handover_flicker_hook` |
| TypedLoss | observe | Mobility hold / Congestive cut / Unknown+delay |
| IntervalBw | observe | Delivery interval; invalidated on SoftReprobe |

Local-only VELA names (Calendar, WriteBudget, QuietReach, …) stay VELA-side.

## Observe hooks (gift)

- `classify_detect_overfire` / `detect_overfire_hook`
- `classify_loss_taxonomy` / `loss_taxonomy_hook`
- `classify_handover_flicker` / `handover_flicker_hook`

`handover_flicker_hook` labels RttHop vs Flicker post-hoc. SoftFlicker stays
review-only. SoftReprobe 0.58 stays load-bearing on both arms.

## Laws

1. Do not retune SoftReprobe 0.58 / Detect 1.65 / 0.42 to make VELA look good.
2. Do not enable closed-write on observe flagships.
3. Do not require leo-aware-transport for `vela check` on Reach / Ascent.
4. Optional `--against-leoaware` is fail-closed if the sibling is absent.
5. Means only. No dish / PHY Mbps claims.

## Module

`vela/mech_decl.py` — `cite_leoaware_surface`, `validate_against_leoaware`,
`load_leoaware_decl`. Integration test: `tests/test_mech_decl_wire.py`
(skips when sibling absent).
