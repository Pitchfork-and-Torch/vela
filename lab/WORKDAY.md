# Eval loop

**Objective:** Improve VELA on top of LeoAware without regressing the engine.

**State:** `lab/STATE.md`, `lab/journal.jsonl`, `lab/PUBLIC_PROGRESS.json`

**Act:** `scripts/space_internet_loop.py --once` from the backlog. Isolated evals only.
Safe pending `language` / `eval` items only. `--once --dry-run` previews the next job and
writes `results/loop_last.json` without mutating backlog, STATE, journal, or PUBLIC_PROGRESS.

**Validate:** seed 7 45s must stay within 0.05 Mbps / 0.2 ms of LeoAware 88.65 / 108.4. Then seed 123 90s. Then terrestrial >= 77 @ 40.

**Stop:** `lab/STOP` exists, or the backlog is empty of safe pending items.

**Anti-hack:** do not edit LeoAware to make a VELA wrap look good. Do not enable closed-write operators without a green ablation. Do not claim dish Mbps. Never naive-copy `lab/PUBLIC_PROGRESS.json` onto a public site.

## Start

```
powershell -ExecutionPolicy Bypass -File .\scripts\Start-SpaceInternetLoop.ps1
```

Optional: `-DryRun` previews ticks. `-Publish` runs `space_internet_loop.py --publish`
(progress sanitizer) and deploys the public progress site only if the sanitizer exits 0.
Never naive-copy the lab JSON.

## Parallel roles

See `lab/ROLES.md` for Measurer, Language, and Publisher.
