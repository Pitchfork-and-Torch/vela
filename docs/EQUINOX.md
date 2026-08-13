# VELA 0.3 Equinox

The language, not another cwnd guess.

Equation Group code is famous for modular operators, least privilege,
fail-closed paths, and a ledger. We steal the *discipline* and invert
the ethics: no ambient write to the window, no claim without a hash,
no silent compose. We do not ship implants, polymorphic malware, or
packet-path crypto that hides a controller.

Modern cryptography here means **commitment**, not ciphertext on the
wire. Polymorphism here means **typed views**, not self-modifying
binaries.

## Laws added in 0.3

1. **Level vs integrator.** `when { pace *= k }` is a type error.
   Horizon seed 7 (55 / 173) is now unrepresentable unless the author
   writes `integrate when` and accepts the warning.
2. **No ambient authority.** A `WriteCap<cwnd> @ epoch` plus
   `authority { cwnd: 0 }` refuses cruise writes. Reconfig still
   invalidates samples. Observe is the default power.
3. **Kinded reconfig.** `on Reconfig match` is a closed taxonomy
   (`RttHop | Flicker`), same shape as `Loss`. SoftFlicker 0.85
   dumped seed 7. The kinds exist so the next cut is named, not guessed.
4. **Content-addressed stdlib.** Each mechanism has a domain-separated
   SHA-256 of its effect row (`VELA1|mech|...`). Compose order is part
   of the digest. `vela mech` prints the catalog.
5. **Eval receipt.** `vela eval` writes `receipt_<tag>.json`: source
   digest, compose digest, merkle of seed rows, verdict. `vela receipt
   --source` verifies. A swapped number fails the hash.
6. **Views.** `view Observe of Equinox { compose ... }` is a morphism
   of the same controller. `vela eval --view Observe` cannot pretend
   it ran the other compose.

## Commands

```
py -3 -m vela check examples/equinox.vela
py -3 -m vela digest examples/equinox.vela
py -3 -m vela mech
py -3 -m vela receipt results/receipt_reach.json --source examples/reach.vela
```

## What 0.3 does not do

It does not replace LeoAware. The engine remains v3.4-p95 at
73.57 / 138.37 vs BBR 70.88 / 138.83. Equinox makes the next illegal
write a compile error instead of a 90s seed dump, so gifts to that
engine can be composed without stacking unnamed flags.
