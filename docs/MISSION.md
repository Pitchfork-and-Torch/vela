# VELA mission (locked 2026-08-13)

VELA does **not** compete with LeoAware.

LeoAware is the packet-path congestion controller (OrbitStack). It is the engine that already works on Starlink-class paths.

VELA is the language that **builds onto** that engine: names Detect, SoftReprobe, delay yield, and typed loss; refuses stale samples and unnamed double-cuts; and lets the next improvement be composed and checked instead of stacked as another flag.

## Success

Space internet feels better: fewer dead seconds after a hop, no CUBIC collapse on beam flicker, honest dual-gate vs BBR and terrestrial, without making LeoAware worse.

A VELA program that matches LeoAware bit-for-bit is a **no-regress rail**, not a failed rival. A VELA program that improves goodput or p95 on the house gate is a **gift to LeoAware**, still composed from its mechanisms.

## Do not

- Frame eval as "VELA vs LeoAware, pick a winner and retire the engine."
- Fork Detect / SoftReprobe lightly. Compose them.
- Claim dish Mbps. Lab numbers live on OrbitStack receipts.

## Do

- Keep the 0.58 endpoint cut until a named ablation is green.
- Dual-gate vs BBR + terrestrial floor remains the user-facing test.
- Observe-only wrap must match LeoAware on the same seed.
