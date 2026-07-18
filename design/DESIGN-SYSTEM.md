# Fleet Pulse — Design System & Report Guardrails

> Every report, EDA writeup, case study, presentation, and snippet produced in this
> repo MUST look like it came from the same team. This document is the contract.
> The identity is a **Siemens Healthineers-inspired clinical petrol/teal** system —
> the same one used by the product (`web/`) and the plan (`presentation/`).
>
> **The fastest way to comply:** start from `design/templates/report-template.html`
> and link `design/report.css`. Do not hand-roll new styles. For charts, use
> `design/fleetpulse.mplstyle`. When in doubt, copy an existing report.

---

## 1. Non-negotiables (read these five first)

1. **One palette.** Petrol/teal + clinical neutrals. Accent = teal. Severity colors
   (red/amber/green) are *semantic only* — never decorative. See §3.
2. **One type system.** A Swiss/grotesque sans for everything, a monospace for data,
   numbers, IDs, and code. Tabular figures wherever numbers align. See §4.
3. **Business framing on top, technical depth underneath.** Every report opens with the
   "so what" for a service manager, then goes deep. Never open with an algorithm.
4. **Honesty is part of the brand.** Synthetic data is always disclosed; limitations get
   their own section; no over-claiming. Every report carries the footer disclaimer (§9).
5. **Structure encodes meaning.** Numbered sections/steps only when order is real. No
   emoji as section markers. No decorative gradients. Restraint over flourish.

---

## 2. What each artifact type is for

| Artifact | Purpose | Template starting point |
|---|---|---|
| **EDA report** | Explore the data, prove it behaves, surface signal | `report-template.html` → keep §Data, §Findings, §Figures |
| **Case study** | The interview deliverable: problem → approach → results → limits | `report-template.html` (full) |
| **One-pager / snippet** | A single finding, chart, or metric for quick share | `report-template.html` → single section + one figure |
| **Presentation / storyboard** | Sequential narrative, section-per-beat | `report-template.html` with `.cover` + numbered sections |

All are **standalone HTML** (self-contained, shareable, no build step). Same CSS, same
skeleton — only the content changes.

---

## 3. Color

Use the CSS variables from `report.css`; never paste raw hex into content.

| Token | Hex | Use |
|---|---|---|
| `--ground` | `#08262B` | Cover/header background, dark chrome |
| `--teal` (accent) | `#0E8A92` | Primary accent: links, rules, eyebrows, key numbers |
| `--teal-bright` | `#17B9C0` | Highlights on dark, chart series 2 |
| `--ink` | `#0A2226` | Body text |
| `--ink-soft` | `#47656B` | Secondary text, captions |
| `--surface` | `#EDF3F3` | Page background (slight teal bias — chosen, not default grey) |
| `--paper` | `#FFFFFF` | Cards, tables |
| `--line` | `#D7E4E4` | Hairlines, borders |
| **Semantic (only for state)** | | |
| `--critical` | `#D64545` | Critical risk / failure / bad |
| `--watch` | `#C67F14` | Elevated / warning |
| `--healthy` | `#1F9E78` | Healthy / good / pass |

**Rules:** teal is the only accent — do not introduce a second brand color. Severity
colors mean *state*; never use red just because it "pops." Neutrals carry a faint teal
bias on purpose — do not swap in pure grey.

### Chart palette (order)
`#0E8A92` (teal) → `#17B9C0` (bright) → `#C67F14` (thermal amber) → `#5F8B92` (slate) →
`#0A4B52` (deep petrol). Encoded in `fleetpulse.mplstyle`. Failure/critical series use
`--critical`; healthy baselines use `--healthy`.

---

## 4. Typography

- **Sans (everything):** `"Helvetica Neue", Helvetica, Arial, system-ui, sans-serif`.
  Headings heavy with tight tracking (`-0.02em`); uppercase labels get `+0.12em`.
- **Mono (data/code/IDs):** `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.
  Machine IDs (`FP-CT-0183`), metrics, code, error codes — all mono.
- **Numbers align:** add `.tnum` (tabular-nums) to any column/stat of digits.
- **Measure:** body text ~65–70 characters wide. Don't run full-bleed paragraphs.
- **Do NOT** link a webfont CDN (breaks offline/shared). System stack only.

Type scale (from `report.css`): cover title `clamp(2rem, 5vw, 3rem)` · section h2
`~1.6rem` · h3 `~1.15rem` · body `16px` · caption `0.85rem` · eyebrow `0.72rem` upper.

---

## 5. Layout & components (all provided by `report.css`)

- **Cover** (`.cover`) — dark petrol band: eyebrow, title, one-line objective, meta strip.
- **Section** (`.section`) — numbered eyebrow (`.eyebrow`) + `h2`; generous vertical rhythm.
- **Stat band** (`.stats` / `.stat`) — 2–4 big tabular KPI figures. Lead findings with these.
- **Table** (`.tbl`) — hairline rules, uppercase header, mono for IDs/numbers, `overflow-x:auto`.
- **Callout** (`.callout`) — dark petrol block for the key takeaway / honesty note.
- **Note** (`.note`) — amber left-border box for caveats and assumptions.
- **Figure** (`figure.fig` + `figcaption`) — chart/image with a mandatory caption stating
  what it shows AND its synthetic-data caveat where relevant.
- **Severity pill** (`.pill.crit` / `.watch` / `.ok`) — inline state chips.
- **Code** (`pre`, `code`) — mono, petrol-tinted surface.
- **Footer** (`.footer`) — the disclaimer (§9), on every artifact.

Layout: single readable column, max-width ~940px. Use flow + spacing from the CSS;
don't add ad-hoc margins. Wide content scrolls inside its own `overflow-x:auto` box.

---

## 6. Voice & copy

- Active voice. Name things as a service manager would ("weekly worklist", "wasted
  visits", "lead time"), not as the system is built.
- Lead with the decision/outcome; put the method after.
- Numbers get context: "PR-AUC 0.48 — vs a random baseline of 0.013" beats a bare figure.
- No hype words ("revolutionary", "cutting-edge"). Confidence comes from specifics.
- Every claim about the data or model is falsifiable and, where synthetic, disclosed.

---

## 7. Charts & EDA figures

- Apply `design/fleetpulse.mplstyle` at the top of any notebook/script:
  ```python
  import matplotlib.pyplot as plt
  plt.style.use("design/fleetpulse.mplstyle")   # path relative to repo root
  ```
- Save figures into the report's `img/` folder at ≥120 dpi, PNG.
- Every figure needs a caption: what it shows + the takeaway + any caveat.
- Mark events (failures, maintenance) with a dashed vertical rule in `--critical`.
- Faint grid, no chartjunk, emphasize the endpoint/signal, label axes with units.

---

## 8. How to make a new report (checklist)

1. Copy `design/templates/report-template.html` → `reports/<name>/index.html`
   (keep reports under a `reports/` folder; put figures in `reports/<name>/img/`).
2. Keep the `<link rel="stylesheet" href="…/report.css">` OR inline `report.css` if the
   file must be shared standalone (see comment at top of the template).
3. Fill: cover (title + one-line objective + meta), then sections. Lead with a stat band.
4. Charts: `fleetpulse.mplstyle`, captions, synthetic-data caveat.
5. Keep the footer disclaimer. Do not add new colors or fonts.
6. Sanity check against §1. If anything looks off-brand, copy an existing report instead.

---

## 9. Required footer disclaimer (verbatim)

> Independent portfolio project for interview preparation. Not affiliated with, endorsed
> by, or using data from Siemens Healthineers. All data is synthetic; machine names,
> figures, and brand styling are illustrative.

---

## 10. Files in this design system

- `design/DESIGN-SYSTEM.md` — this contract.
- `design/report.css` — the single stylesheet every HTML report links/inlines.
- `design/templates/report-template.html` — copy-to-start skeleton showing every component.
- `design/fleetpulse.mplstyle` — matplotlib style so EDA charts match the palette.
- `.claude/skills/fleetpulse-report/SKILL.md` — Claude skill: "make a report" auto-follows this system.
