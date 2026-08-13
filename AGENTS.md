# VELA (folder rules)

Canonical language tree for **VELA** (Variance-aware Epoch Language for Adaptation).

- Invented to design, check, and deploy the next generation of LEO-aware congestion control after LeoAware v3.7 OCE.
- Sibling science stack: `~/Projects/leo-aware-transport` (MIT, Pitchfork-and-Torch).
- This tree is the language + compiler + kernel. Do not fork LeoAware detect/reprobe lightly; compose them as stdlib mechanisms.
- ASCII punctuation in public docs (no em/en dashes).
- Secret scan before any commit/push.
- License: MIT. GitHub visibility is **private** (`Pitchfork-and-Torch/vela`) until the operator opens it.
- Do not relicense the sibling leo-aware-transport tree.

## Commands

```
py -3 -m vela check examples/reach.vela
py -3 -m vela compile examples/reach.vela
py -3 -m vela eval examples/reach.vela --fast --tag reach-fast
py -3 -m vela eval examples/reach.vela --seeds 13,7,42,99,123 --tag reach-house
py -3 -m unittest discover -s tests -v
```

## Honesty

Never claim a dual-gate win without the eval harness JSON. Coupled-RNG historical numbers (v3.4-p95 73.57 / 138.37) are not comparable to OPE-fair figures.
