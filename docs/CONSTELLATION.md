# Space internet blend

Mission: `docs/MISSION.md`.

Public engine: `Pitchfork-and-Torch/leo-aware-transport`
Language: `Pitchfork-and-Torch/vela` (MIT, public). This tree.
Sites: orbitstack.jonbailey.xyz (numbers) and vela.jonbailey.xyz (language).
Public numbers go through the progress sanitizer (never a naive lab copy).
Do not merge this compiler into the public engine repo.

## Flagship surface (Starlink usefulness)

VELA builds onto LeoAware for Starlink-class paths. The public surface is
observe-only. SoftReprobe house cut stays **0.58** on RTT hop and flicker.
Do not claim dish Mbps. Lab Mbps live on OrbitStack receipts.

| Program | Path | Role |
|---------|------|------|
| Reach | `examples/reach.vela` | Packet-path flagship. LeoAware wrap at check time (`passthrough`, typed reconfig/loss, house 0.58). |
| Equinox | `examples/equinox.vela` | 0.3 discipline demo on the same compose class. Authority 0 refuses writes. Not a closed-write intro. |
| Ascent | `examples/ascent.vela` | Fail-closed Starlink hint assist. Missing ASCENT-D / Orb hint is None, not a hop oracle. |

`vela check` on Reach and Equinox must print `observe-only`,
`reconfig=RttHop|Flicker  (house cut 0.58)`, typed loss, and
`passthrough`. SoftFlicker / HorizonChase stay `posture review`. Do not merge a review closed-write compose as the flagship.

Blend docs: `docs/EQUINOX.md`, `docs/LANGUAGE.md`, `docs/EVAL-NOTES.md`.
