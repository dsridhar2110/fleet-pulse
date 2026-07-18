---
name: fleetpulse-report
description: Create any report, EDA writeup, case study, presentation, storyboard, one-pager, or snippet for the Fleet Pulse repo so it follows the shared Fleet Pulse design system. Use whenever the user asks to make/write/generate a report, EDA, analysis writeup, case study, findings summary, chart, or any shareable document in this repository.
---

# Fleet Pulse — Report Builder

Produce a report that is visually indistinguishable from every other Fleet Pulse
artifact. The design system is the contract in `design/DESIGN-SYSTEM.md`; this skill is
how you apply it. **Never invent a new look — reuse the system.**

## Steps

1. **Read the guardrails first.** Open `design/DESIGN-SYSTEM.md`. Follow §1 non-negotiables
   (one palette, one type system, business-first framing, honesty, meaningful structure).

2. **Start from the template, don't hand-roll.** Copy `design/templates/report-template.html`
   to `reports/<kebab-name>/index.html`. Put any images in `reports/<kebab-name>/img/`.
   Fix the stylesheet path to `../../design/report.css`.
   - If the report must be shared as a single standalone file, inline `design/report.css`
     into a `<style>` block instead of linking it.

3. **Pick the shape by artifact type** (see DESIGN-SYSTEM §2):
   - **EDA report** → cover + Data section + Findings + Figures + Limits note.
   - **Case study** → full arc: Problem → Approach → Results (stat band) → Honest limits → Questions.
   - **One-pager / snippet** → cover + one section + one figure + takeaway callout.
   - **Presentation / storyboard** → `.cover` + numbered sections, one beat each.

4. **Compose only with the provided components** (all defined in `report.css`):
   `.cover` + `.meta`, `.section` with numbered eyebrow, `.stats`/`.stat` (lead findings),
   `table.tbl`, `.card`, `.callout` (key takeaway), `.note` (caveats), `figure.fig` +
   `figcaption`, `.pill` (severity), `pre`/`code`. Do not add ad-hoc CSS, colors, or fonts.

5. **Charts** → apply the shared matplotlib style so figures match:
   ```python
   import matplotlib.pyplot as plt
   plt.style.use("design/fleetpulse.mplstyle")
   ```
   Save PNG ≥120 dpi into the report's `img/`. Every figure gets a caption (what it shows
   + takeaway + synthetic-data caveat). Mark failures/events with a dashed `--critical` rule.

6. **Write to the voice** (DESIGN-SYSTEM §6): business/outcome first, method second; numbers
   with context ("PR-AUC 0.48 — vs random 0.013"); no hype; disclose every synthetic/simplified
   choice. Use the real project numbers from the root `CLAUDE.md` §6 when relevant.

7. **Always keep the footer disclaimer** (DESIGN-SYSTEM §9), verbatim.

8. **Self-check before finishing** against DESIGN-SYSTEM §1. If anything looks off-brand,
   open an existing report under `reports/` (or `presentation/fleet-pulse-brief.html`) and match it.

## Guardrails (hard rules)

- Petrol/teal is the only accent. Red/amber/green mean *state* only — never decoration.
- System fonts only — never link a webfont CDN (breaks offline/shared files).
- Tabular figures (`.tnum` / mono) for all aligned numbers and IDs.
- No emoji as section markers; number sections only when order is real.
- Every report is self-contained, standalone HTML, and carries the disclaimer.
- When unsure, copy an existing artifact rather than improvising.
