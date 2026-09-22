# VELA (folder rules)

Canonical language tree for **VELA** (Variance-aware Epoch Language for Adaptation).

- Language that **builds onto** LeoAware for space internet. Not a rival CCA. Mission: `docs/MISSION.md`. Blend: `docs/CONSTELLATION.md`. Eval loop: `lab/WORKDAY.md`.
- Sibling science stack: `~/Projects/leo-aware-transport` (MIT, Pitchfork-and-Torch).
- This tree is the language + compiler + kernel. Do not fork LeoAware detect/reprobe lightly; compose them as stdlib mechanisms.
- ASCII punctuation in public docs (no em/en dashes).
- Secret scan before any commit/push.
- License: MIT. GitHub: public `Pitchfork-and-Torch/vela` (open source). Site: https://vela.jonbailey.xyz/
- Do not relicense the sibling leo-aware-transport tree.

## Flagship surface

- Packet-path flagship: observe-only `examples/reach.vela` (passthrough, typed reconfig/loss, house cut 0.58).
- Equinox: `examples/equinox.vela` is the 0.3 discipline demo on that compose class. Not a closed-write intro.
- Ascent: fail-closed Starlink hint assist. SoftFlicker / HorizonChase stay review.
- Blend: `docs/CONSTELLATION.md`, `docs/EQUINOX.md`. No dish Mbps.

## Commands

```
py -3 -m vela check examples/reach.vela
py -3 -m vela check examples/equinox.vela
py -3 -m vela check examples/ascent.vela
py -3 -m vela digest examples/equinox.vela
py -3 -m vela mech
py -3 -m vela compile examples/equinox.vela
py -3 -m vela eval examples/reach.vela --fast --tag reach-fast
py -3 -m vela receipt results/receipt_reach-fast.json --source examples/reach.vela --eval results/eval_reach-fast.json
py -3 -m unittest discover -s tests -v
```

## Honesty

Never claim a dual-gate win without the eval harness JSON. Coupled-RNG historical numbers (v3.4-p95 73.57 / 138.37) are not comparable to OPE-fair figures.
`--publish` must run the progress sanitizer. Never copy `lab/PUBLIC_PROGRESS.json` onto a public site.
Do not market Equinox WriteCap / review posture as the Starlink intro.
