# VELA (folder rules)

Canonical language tree for **VELA** (Variance-aware Epoch Language for Adaptation).

- Language that **builds onto** LeoAware for space internet. Not a rival CCA. Mission: `docs/MISSION.md`. Blend: `docs/CONSTELLATION.md`. Workday loop: `lab/WORKDAY.md`.
- Sibling science stack: `~/Projects/leo-aware-transport` (MIT, Pitchfork-and-Torch).
- This tree is the language + compiler + kernel. Do not fork LeoAware detect/reprobe lightly; compose them as stdlib mechanisms.
- ASCII punctuation in public docs (no em/en dashes).
- Secret scan before any commit/push.
- License: MIT. GitHub visibility is **private** (`Pitchfork-and-Torch/vela`) until the operator opens it.
- Do not relicense the sibling leo-aware-transport tree.

## Commands

```
py -3 -m vela check examples/equinox.vela
py -3 -m vela digest examples/equinox.vela
py -3 -m vela mech
py -3 -m vela compile examples/equinox.vela
py -3 -m vela eval examples/reach.vela --fast --tag reach-fast
py -3 -m unittest discover -s tests -v
```

## Honesty

Never claim a dual-gate win without the eval harness JSON. Coupled-RNG historical numbers (v3.4-p95 73.57 / 138.37) are not comparable to OPE-fair figures.
`--publish` must call `~/orbitstack/scripts/publish_progress.py` (desk-check `--dry-run` first). Never copy `lab/PUBLIC_PROGRESS.json` onto the public site.
