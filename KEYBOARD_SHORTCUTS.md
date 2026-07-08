# Cortical Browser — Keyboard Shortcuts

> **Temporary reference.** Draft notes to fold into the full user manual later.

Shortcuts are handled by a global key listener and are **ignored while typing in a
text field or dropdown** (Vertex, Rings, colour-limit inputs, selectors), so those
controls keep working normally.

## Views & display

| Key | Action |
| --- | --- |
| `r` | Reset everything: orthoslice zoom/pan, orthoslice grayscale contrast, and the 3-D surface framing (camera angles, zoom, rotation pivot). |
| `x` | Toggle the orthoslice crosshair on/off (mirrors the **X-hair** checkbox). |
| `p` | Toggle **Pivot@vertex** — orbit the 3-D surfaces around the selected vertex vs. the whole-brain centre. |

## Orthoslice navigation (moves the crosshair one voxel)

| Key | Plane | Direction |
| --- | --- | --- |
| `↑` / `↓` | Axial | superior / inferior |
| `→` / `←` | Sagittal | right / left |
| `PgUp` / `PgDn` | Coronal | anterior / posterior |

Left/right follow the **anatomical** L–R axis, independent of the radiological display flip.

## Cortical depth

| Key | Action |
| --- | --- |
| `+` (or `=`) / `Home` | Step depth deeper |
| `-` / `End` | Step depth shallower |

`=` works as an unshifted `+`. Depth is clamped to the current metric's range and the depth slider stays in sync.

## Neighbor rings

| Key | Action |
| --- | --- |
| Numpad `+` / `-` | Increase / decrease the neighbor-ring count |

The numpad keys are distinct from the main-keyboard `+`/`-` (which control depth); they require a real numeric keypad with NumLock on.

---

### Notes / open questions for the manual
- Direction conventions chosen so far: up/right/PgUp increase the coordinate (superior/right/anterior); `+`/`Home` go deeper.
- Numpad-only rings control has no laptop fallback yet (candidate: `[` / `]`).
- Consider documenting the mouse interactions too (Ctrl+scroll = orthoslice zoom, scroll = 3-D surface zoom, click = select vertex).
