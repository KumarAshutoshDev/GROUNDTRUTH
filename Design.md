# GROUNDTRUTH: Design

*Companion to the PRD, `Architecture.md`, and `rules.md`. The PRD says what and why. Architecture says how it works. This document says how it looks and feels.*

**Status:** Draft for build. The three brand colors come from the reference image. Every other number (extra colors, sizes, timings) is a **proposal** to be tuned on the real dashboard, not a measured result. Contrast ratios in section 3.5 were measured with a script.

**Reference:** the palette-and-landing-page image shared with the project. We take its mood, colors, and layout habits. We do not copy its product, photo, or wording.

---

## 0. How to Read This File

This file uses the same words as `rules.md`: **MUST** is absolute, **SHOULD** is a default. Every design rule has an ID (`DES-1` and so on). Cite IDs in commits, reviews, and PRs.

Some design words are used a lot. Here they are in plain language:

| Word | Plain meaning |
|---|---|
| **Design token** | A named value, like `--gt-lime`, that holds one color or size. Everyone uses the name, so we can change it in one place. |
| **Hex code** | A short code for a color, like `#D4FF24`. |
| **Contrast ratio** | A number that says how easy it is to read one color on top of another. Bigger is easier. 1 means no difference. 21 is black on white. |
| **WCAG AA** | A common accessibility rule. Normal text needs a contrast of 4.5 or more. Large text and shapes (like bars and icons) need 3 or more. |
| **Pill** | A button or tag with fully round ends, like a medicine capsule. |
| **Radius** | How round a corner is. A bigger radius means a rounder corner. |
| **Serif / sans** | Serif fonts have little feet on the letters (like a book). Sans fonts do not (like a phone screen). |
| **Tabular numbers** | A font setting that makes every digit the same width, so numbers line up in columns and do not jiggle when they change. |
| **Glow** | A soft colored light around a shape, used to show "look here". |

---

## 1. Scope and Design Principles

| # | Principle | Consequence in the design |
|---|---|---|
| 1 | Dark and calm, with one bright voice | Most of the screen is Midnight Black. Cobalt adds depth. Lime is rare, so when it shows up, people look. |
| 2 | Color tells the truth about status | A color is never decoration if it also means a status. Lime, amber, and coral are reserved (DES-3). |
| 3 | Rejections are a feature | Quarantined and rejected facts are loud and easy to read, never hidden (DASH-2). |
| 4 | No hidden numbers | Trust, thresholds, and formulas are always visible next to what they affect (TRUST-5). |
| 5 | Never color alone | Every status has a color, a word, and an icon, so it works for color-blind users and on a bad projector. |
| 6 | Motion explains | Animation shows cause and effect (a taint spreading, a trust drop). It is never just for show. |
| 7 | Narrow and finished | The build covers the dashboard only. The pitch page is optional (section 10). |

**In scope for the build:** the audit dashboard (PRD FR-9, Architecture section 14).
**Out of scope for the build:** light theme, mobile-first layouts, marketing site, animated illustrations.

---

## 2. What We Take From the Reference Image

| What the image shows | What we take | Where it is used |
|---|---|---|
| Near-black page, one deep blue, one neon lime | The three-color palette | Whole product |
| Lime used only on the main button and the key product highlight | "Lime is rare and means go or look here" | Primary button, ADMIT, AUTO_FIX, focus ring |
| Big headline mixing a curly italic serif word with a thin sans word | The headline pattern | Dashboard title area, pitch page |
| Tiny uppercase labels with wide letter spacing | The label style | Panel titles, chip text, nav |
| Color cards with a name, a thin line, and a hex code | The "info card" layout | Formula panel, legend, thresholds |
| Rounded cards and pill buttons | The shape language | All components |
| Stat row: big number, tiny caption under it | The stat tile | Counters panel |
| Glowing blue shapes on black | The glow effect | Causality graph, selected fact |

**What we leave:** the earbuds, the photo, the person, and any product copy.

---

## 3. Color System

### 3.1 Brand palette (from the reference image)

| Token | Name | Hex | Role | Share of a typical screen (proposal) |
|---|---|---|---|---|
| `--gt-midnight` | Midnight Black | `#030407` | Page background | About 70% or more with surfaces |
| `--gt-cobalt` | Electric Cobalt Blue | `#1558C9` | Structure: panels, graph shapes, glow, secondary buttons | About 20% |
| `--gt-lime` | Acid Lime | `#D4FF24` | Go and focus: primary button, ADMIT, ACTIVE, AUTO_FIX, focus ring | 10% at most (DES-2) |

### 3.2 Neutrals (proposal)

The image only gives three colors, but a dashboard needs a few quiet shades for panels, lines, and text.

| Token | Hex | Use |
|---|---|---|
| `--gt-surface-1` | `#0A0F1A` | Panel background |
| `--gt-surface-2` | `#0F1626` | Raised card, hover |
| `--gt-line` | `#1B2438` | Thin borders and dividers (decoration only) |
| `--gt-text` | `#F2F5FA` | Main text |
| `--gt-text-muted` | `#8A94A8` | Secondary text, captions |
| `--gt-cobalt-soft` | `#5B8DEF` | Cobalt for **text, links, and thin outlines** (see 3.5) |

### 3.3 Functional colors (proposal, outside the reference)

Three brand colors are not enough to show five fact statuses. We add two warning colors. They are used **only** for status (DES-3).

| Token | Name | Hex | Means |
|---|---|---|---|
| `--gt-amber` | Signal Amber | `#FFB020` | Doubt: QUARANTINED, CONTESTED |
| `--gt-coral` | Alert Coral | `#FF4D5E` | Broken: REJECT, RETRACTED, TAINTED, ESCALATE |

This is the one place we go beyond your palette. See open decisions (section 15) if you want to change it.

### 3.4 Usage rules in short

- Lime on the page background is never allowed. Lime is a small highlight on top of dark.
- Cobalt carries large areas. Lime and coral carry small areas.
- Text on lime, amber, or coral is always Midnight Black.
- Text on cobalt is white.

### 3.5 Contrast check (measured)

| Pair | Ratio | Passes | Note |
|---|---|---|---|
| Lime on Midnight | 17.70 | Text and shapes | Safe for small text |
| Midnight on Lime | 17.70 | Text and shapes | Primary button text |
| Main text on Midnight | 18.76 | Text and shapes | |
| Main text on Surface 1 | 17.53 | Text and shapes | |
| Muted text on Midnight | 6.72 | Text and shapes | |
| Muted text on Surface 1 | 6.28 | Text and shapes | |
| White on Cobalt | 6.42 | Text and shapes | Secondary button text |
| Lime on Cobalt | 5.54 | Text and shapes | |
| Amber on Midnight | 11.21 | Text and shapes | |
| Coral on Midnight | 6.32 | Text and shapes | |
| Cobalt Soft on Midnight | 6.35 | Text and shapes | Use this for blue text and links |
| **Cobalt on Midnight** | **3.19** | **Shapes only, not small text** | Too dim for small text, fine for big shapes and bars |
| Line on Midnight | 1.32 | Decoration only | Never use a line color to carry meaning |

**Takeaway:** Electric Cobalt is great for big shapes and glow, but too dim for small text on black. Use `--gt-cobalt-soft` for any blue text (DES-9).

### 3.6 Tokens file

Lives at `dashboard/styles/tokens.css` (section 13). Components use these names, never raw hex codes (DES-1).

```css
:root {
  /* Brand (from the reference image) */
  --gt-midnight: #030407;
  --gt-cobalt:   #1558C9;
  --gt-lime:     #D4FF24;

  /* Neutrals (proposal) */
  --gt-surface-1:   #0A0F1A;
  --gt-surface-2:   #0F1626;
  --gt-line:        #1B2438;
  --gt-text:        #F2F5FA;
  --gt-text-muted:  #8A94A8;
  --gt-cobalt-soft: #5B8DEF;

  /* Functional, status only (proposal) */
  --gt-amber: #FFB020;
  --gt-coral: #FF4D5E;

  color-scheme: dark;
}
```

---

## 4. Typography

The reference image mixes a curly italic serif with a thin, clean sans. We keep that look.

| Role | Font (proposal) | Fallback stack | Used for |
|---|---|---|---|
| Display accent | Instrument Serif, italic | `Georgia, "Times New Roman", serif` | One emphasized word in a headline |
| Display and body | Inter | `system-ui, -apple-system, "Segoe UI", sans-serif` | Headlines, body, buttons |
| Mono | JetBrains Mono | `ui-monospace, "SF Mono", Menlo, monospace` | `fact_id`, hashes, `evidence_ref`, formulas |

### 4.1 Scale (proposal)

| Style | Size / line height | Weight | Notes |
|---|---|---|---|
| Display | 56 / 60 px | Sans 300 plus serif italic accent | Hero only |
| H1 | 40 / 44 px | 400 | Page title |
| H2 | 28 / 34 px | 500 | Panel title |
| H3 | 20 / 26 px | 500 | Card title |
| Body | 16 / 24 px | 400 | Default text |
| Small | 14 / 20 px | 400 | Table cells, captions |
| Label | 11 / 16 px | 600 | UPPERCASE, letter spacing 0.12em, muted color |
| Mono | 13 / 20 px | 400 | IDs and code |

### 4.2 Headline pattern

One word gets the curly italic serif in lime. The rest is thin sans in white. Use it once per screen at most.

```
Every fact,                  <- thin sans, white
*traced.*                    <- italic serif, lime
```

### 4.3 Number rules

- All numbers use **tabular numbers**, so columns line up and live updates do not shift the layout.
- Trust values show two decimals (for example `0.60`).
- Hashes and IDs are cut in the middle with an ellipsis, and the full value shows on hover or copy.

---

## 5. Shape, Spacing, and Motion

### 5.1 Shape and spacing (proposal)

| Token | Value | Use |
|---|---|---|
| Spacing base | 4 px | All gaps are multiples: 4, 8, 12, 16, 24, 32, 48, 64 |
| `--gt-radius-card` | 16 px | Cards and info cards (the color cards in the image look like this) |
| `--gt-radius-panel` | 20 px | Big dashboard panels |
| `--gt-radius-pill` | 999 px | Buttons, chips, badges |
| Border | 1 px `--gt-line` | Panel and card edges |
| Glow | `0 0 24px` of cobalt at 40% | Selected fact, graph weakest link |

### 5.2 Motion (proposal)

| Moment | Motion | Time |
|---|---|---|
| Hover on a button or row | Slight brighten | 120 ms |
| New fact in the stream | Slides in from the top, then settles | 240 ms |
| Trust bar change | Bar slides to the new value, number counts to match | 400 ms |
| Taint cascade | Red spreads one hop at a time along the graph edges | 150 ms per hop |
| Replay scrubber drag | State updates immediately, no easing | 0 ms |

**Reduced motion (DES-10):** if the user's device asks for less motion, all of these become instant color changes. The taint cascade shows as a list of facts that changed instead.

---

## 6. Components

| Component | Look | Notes |
|---|---|---|
| **Primary button** | Lime fill, Midnight text, pill shape, small uppercase label | One per screen area. Matches the image's "Buy now" and "Explore now". |
| **Secondary button** | Transparent, 1 px `--gt-cobalt-soft` outline, white text, pill | Used for "Override", "Copy", and "Replay" |
| **Text button** | Cobalt Soft text with a small round icon, like "Watch the story" in the image | Low-priority actions |
| **Source chip** | Pill with an icon and the source type in tiny uppercase | Cobalt Soft outline only. Never lime, amber, or coral (DES-3). |
| **Status badge** | Pill with an icon, the status word, and a status color | See section 7 |
| **Trust bar** | Thin bar, the number beside it, and tick marks at `T_cite` and `T_auto` | Bar color comes from pack thresholds (DES-7) |
| **Fact card** | Surface 1 card, radius 16. Top row: type and status badge. Middle: value. Bottom: source chip, trust bar, `fact_id` in mono | Always shows all four of source type, trust, status, provenance (DES-6) |
| **Stat tile** | Big number, tiny uppercase caption under it, thin divider. Like "40H" and "ANC" in the image | Counters panel. Never a hard-coded number (DES-8). |
| **Info card** | Rounded card with a name, a thin line, and a value. Like the color cards in the image | Formula panel, thresholds, legend |
| **Top nav** | Tiny uppercase links on the left, search icon, lime pill on the right | Case switcher and Decision pill |
| **Empty state** | Muted text with one sentence on what will appear here | Never a blank panel |

---

## 7. Status Mapping

Every status has a color, an icon, and a word. All three always appear together (DES-4).

### 7.1 Fact status

| Status | Color | Icon | Extra treatment |
|---|---|---|---|
| ACTIVE | Lime | Check | Normal card |
| CONTESTED | Amber | Two opposing arrows | Card pairs with the fact it conflicts with |
| QUARANTINED | Amber | Box with lock | Dashed outline |
| RETRACTED | Coral | Cross | Value text is struck through |
| TAINTED | Coral | Warning triangle | Diagonal stripes in the card background |

### 7.2 Gate verdict

| Verdict | Look | Meaning (from rules.md) |
|---|---|---|
| ADMIT | Lime fill, Midnight text | Passed every check (GATE-3) |
| QUARANTINE | Amber outline and text | Well-formed but doubtful (GATE-2) |
| REJECT | Coral outline and text | Structurally invalid (GATE-1) |

The **reason** text (GATE-4) is always visible in the same row, not hidden in a tooltip.

### 7.3 Decision signal

| Signal | Look |
|---|---|
| AUTO_FIX | Lime fill pill |
| NEED_MORE | Cobalt Soft outline pill, with the missing checks listed under it |
| ESCALATE | Coral fill pill |

The flip from AUTO_FIX to ESCALATE (PRD beat 6) is the biggest color change in the whole product. It is meant to be seen from across a room.

### 7.4 Trust bar colors

| Band | Color |
|---|---|
| At or above `T_auto` | Lime |
| At or above `T_cite` but below `T_auto` | Cobalt Soft |
| Below `T_cite` but above 0 | Amber |
| Exactly 0 (TAINTED or RETRACTED) | Empty bar with a coral outline |

The thresholds are read from the domain pack. They are never typed into UI code (TRUST-2, DES-7).

### 7.5 Case state and negative knowledge

| Item | Look |
|---|---|
| OPEN, INVESTIGATING | Cobalt Soft dot |
| CONCLUDED | Lime dot |
| CLOSED | Muted dot |
| COVERED (negative check) | Lime text with a check |
| NOT_COVERED | Amber text, plus the failing condition (NEG-3) |

---

## 8. Screen Layout

### 8.1 Dashboard wireframe (desktop, 1440 px wide, proposal)

```
+----------------------------------------------------------------------------+
| GROUNDTRUTH    CASE <id>   [state]                       [ DECISION pill ] |
+------------------------+--------------------------------+------------------+
| FACT LIST              | CAUSALITY GRAPH                | VERDICT STREAM   |
| fact cards with        | cobalt glow on weakest link,   | newest on top,   |
| source chip + trust    | red spreading on taint         | reason shown     |
+------------------------+--------------------------------+------------------+
| REPLAY SCRUBBER   |<-------o---------------------->|   event N            |
+----------------------------------------------------------------------------+
| COUNTERS (baseline vs GT)  | FORMULA PANEL        | CONCLUSION VIEW        |
+----------------------------------------------------------------------------+
```

Below 900 px wide the panels stack in one column in this order: decision, verdict stream, fact list, graph, conclusion, counters, formula, replay. Full mobile polish is out of scope.

### 8.2 Panels (maps to Architecture section 14)

| Panel | Visual treatment | Data source |
|---|---|---|
| Fact list | Fact cards, newest first, filter by status | `/state` |
| Verdict stream | Rows with verdict badge, fact type, and reason. QUARANTINE and REJECT rows are taller and tinted (DES-5) | SSE on `GATE_VERDICT` |
| Causality graph | Nodes colored by status, edges in `--gt-line`, weakest link in a cobalt glow | `/graph` |
| Taint cascade | Coral spreads node by node along edges, 150 ms per hop | SSE on `FACT_TAINTED` |
| Replay scrubber | Slim bar with a lime handle, event number in mono, and small ticks at verdict events | `/state?at=N` |
| Counters | Two columns (baseline and GT) of stat tiles, with sample size and baseline definition printed under them (DES-8) | `/metrics` |
| Formula panel | Info cards showing `BASE`, `T_cite`, `T_auto`, half-lives, and the `min` formula in mono | Domain pack |
| Conclusion view | Provenance chain from conclusion back to evidence, then a clear "WHAT WE COULD NOT DETERMINE" block in amber | `/graph`, `/decision` |

---

## 9. Demo Moments (design view)

Maps to the PRD demo script (section 11). These are the moments the design must get right.

| Beat | What the audience sees | Design requirement |
|---|---|---|
| 2. Facts stream in | Cards slide in with source chip and trust bar | Source chip and trust bar visible on first paint |
| 3. Gate quarantines a fact | An amber row appears in the stream with the reason | Row stands out from ADMIT rows. Reason in plain words. |
| 4. Negative fact | A COVERED result shows, and the tool-call counter stays at zero | Counter tile does not move. Show a small lime check. |
| 5. Counter comparison | Baseline and GT stat tiles side by side | Sample size and baseline definition printed under them |
| 6. Verifier downgrades a fact | Trust bars drop, two conclusions go red, decision pill flips from lime to coral | Bars animate down in order of the chain. Pill flip is the loudest moment. |
| 7. Replay to event 14 | Scrubber moves and every panel rewinds | Instant update, no easing. Event number is large. |
| 8. Conclusion | Provenance chain plus the "what we could not determine" block | Amber block is always shown, even when empty ("Nothing open") |

---

## 10. Pitch Surface (optional, stretch)

The reference image is a landing page. A pitch page is **not in the PRD**, so it needs one-line approval from the team lead before work starts (SCOPE-2). It is the first thing to cut.

If approved, it reuses the image's layout with our own content:

| Image element | GROUNDTRUTH version |
|---|---|
| Tiny top nav and lime "Buy now" pill | Nav: PRODUCT, HOW IT WORKS, DASHBOARD. Lime pill: "See the demo" |
| Headline "Feel Every Moment" | Headline in the pattern from 4.2, for example: "Agents that share *the truth.*" |
| Small caption on the left | One plain sentence on the problem (the three failure modes in the PRD) |
| Hero product image | The causality graph, glowing in cobalt with one lime conclusion node. No stock photo. |
| Stat row (40H, ANC) | Three stat tiles filled **only** from a recorded run (DES-8, CLAIM-2) |
| "Watch the story" link | "Watch the replay" text button |

**Copy rules:** no "novel", "first", "unique" (CLAIM-1). Do not call the Verifier ground truth or a guarantee (CLAIM-4). Do not say we replace LangGraph or a vector DB (CLAIM-5).

---

## 11. Accessibility

| Area | Rule |
|---|---|
| Contrast | Text 4.5 or more. Shapes and icons 3 or more. See 3.5. |
| Color alone | Never. Color plus icon plus word (DES-4). |
| Focus | Every clickable thing shows a 2 px lime outline with a 2 px gap when reached by keyboard |
| Keyboard | Panels, the scrubber, and Override can be used without a mouse. Scrubber: left and right arrows move one event. |
| Motion | Honors the device's reduced-motion setting (DES-10) |
| Screen readers | New verdicts in the stream are announced politely, with verdict, fact type, and reason |
| Text size | Nothing below 11 px. Only labels are that small, and they are uppercase with extra spacing. |

---

## 12. Design Rules

| ID | Rule |
|---|---|
| **DES-1** | **Tokens only.** Components MUST NOT contain raw hex codes or one-off pixel sizes. Use the tokens in `tokens.css`. |
| **DES-2** | **Lime is rare.** Lime means go or look here: primary button, ADMIT, ACTIVE, AUTO_FIX, focus ring, one headline accent. It SHOULD NOT cover more than about a tenth of any screen. |
| **DES-3** | **Reserved colors.** Lime, amber, and coral carry status meaning. Nothing purely decorative may use amber or coral. Source chips use Cobalt Soft only. |
| **DES-4** | **Never color alone.** Every status shows a color, an icon, and a word. |
| **DES-5** | **Loud rejections.** QUARANTINE and REJECT rows are visually stronger than ADMIT rows and show the reason inline (DASH-2, GATE-4). |
| **DES-6** | **Four things on every fact.** Every displayed fact shows source type, trust, status, and provenance (DASH-3). |
| **DES-7** | **Trust colors come from the pack.** Band colors use `T_cite` and `T_auto` read from the domain pack. The formula panel is always reachable (TRUST-2, TRUST-5). |
| **DES-8** | **Measured numbers only.** Any number on screen is a measured value from a recorded run, or is clearly marked as a placeholder. Sample size and baseline definition sit next to any improvement figure (CLAIM-2, CLAIM-3, DASH-4). |
| **DES-9** | **Readable blue.** Small blue text uses `--gt-cobalt-soft`, never `--gt-cobalt` (measured contrast 3.19, below 4.5). |
| **DES-10** | **Motion explains.** Motion shows cause and effect only. Reduced-motion users get instant changes. The replay view reads recorded events and never re-invokes agents (DASH-5). |
| **DES-11** | **Read-only dashboard.** The only control that changes anything is Override. It uses the secondary button style and asks for confirmation (DASH-1). |
| **DES-12** | **Dark only.** The build ships one dark theme. A light theme needs approval (SCOPE-2). |
| **DES-13** | **No extra weight.** A new UI library, icon pack, or font package needs a one-line reason in the PR (rules.md section 4). Design work MUST NOT add a datastore (INV-11). |
| **DES-14** | **Honest words.** UI copy follows the claims rules: no "novel" or "first" (CLAIM-1), and the Verifier is never shown as proof (CLAIM-4). |

### For AI coding assistants

Follow rules.md section 12, plus:

1. Read this file and `tokens.css` before touching any UI.
2. Never invent a color, font, or size. If it is not here, propose it and wait.
3. Never hard-code a metric, trust value, or threshold in the UI (DES-7, DES-8).
4. When you build a status element, show the color, icon, and word together.
5. Report the real result of lint and a visual check. If you could not look at the screen, say so.

---

## 13. Suggested Files

Adds to the repository layout in Architecture section 17.

```
groundtruth/
  dashboard/
    styles/
      tokens.css        colors, radii, spacing, fonts (section 3.6)
      base.css          reset, body, typography
    components/         buttons, chips, badges, trust bar, fact card, stat tile, info card
    panels/             fact_list, verdict_stream, graph, replay, counters, formula, conclusion
  docs/
    design/             exported mockups and screenshots, named by panel
```

The dashboard stack (React or server-rendered) is still open (Architecture section 19). The tokens are plain CSS variables, so both options work.

**Design review checklist** (add to the review checklist in rules.md section 13):

- No raw hex codes in components (DES-1)
- Every status shows color, icon, and word (DES-4)
- QUARANTINE and REJECT rows are loud and show the reason (DES-5)
- No number on screen that is not measured or marked as a placeholder (DES-8)
- Small blue text uses Cobalt Soft (DES-9)
- Reduced-motion works (DES-10)

---

## 14. Build Order (maps to PRD phases)

| PRD phase | Design work, in this order |
|---|---|
| P1 Spine | Nothing visual. Create `tokens.css` so later work has it. |
| P6 Dashboard | 1. Verdict stream. 2. Fact card and fact list. 3. Decision pill and top bar. 4. Graph. 5. Replay scrubber. |
| P4 Trust (UI part) | Trust bar and formula panel, built with P6 once `/graph` and `/decision` exist |
| P8 Contamination | Taint cascade motion and TAINTED card style, only after the graph is solid |
| P9 Demo hardening | Screenshot check of every demo beat in section 9, projector contrast check, reduced-motion check |
| P10 and later | Pitch surface (section 10), light theme |

The order inside P6 follows Architecture section 18: verdict stream first, fact list second, graph third, replay last. If time runs short, the scrubber becomes a step list (PRD cut rule), which this design already supports.

---

## 15. Open Decisions

| Decision | Options | Needed by |
|---|---|---|
| Amber and coral as extra status colors | Keep as proposed, or choose other shades, or stay with only brand colors and rely on icons | P6 |
| Fonts | Instrument Serif, Inter, JetBrains Mono as proposed, or system fonts only to avoid a download | P6 |
| Dashboard stack | React or server-rendered (same open item as Architecture section 19) | P6 |
| Graph drawing method | Plain SVG, or a small graph library (needs a one-line reason, DES-13) | P6 |
| Pitch surface | Build it (needs approval), or skip | P9 |
| Light theme | Skip for the hackathon, or add after | Post-hackathon |
| Projector check | Test on the real demo screen early, since dark themes can wash out | P9 |

---

## 16. Quick Reference

| Question | Answer |
|---|---|
| What are the three brand colors? | Midnight Black `#030407`, Electric Cobalt `#1558C9`, Acid Lime `#D4FF24` |
| What does lime mean? | Go, positive, or look here (DES-2) |
| Which colors are only for status? | Lime, amber, and coral (DES-3) |
| Can I use Electric Cobalt for small text? | No. Use Cobalt Soft (DES-9). |
| Can I show a color without a word and icon? | No (DES-4) |
| Where do trust band colors come from? | The domain pack thresholds (DES-7) |
| Can I type a number into the UI? | Only if it is measured or marked as a placeholder (DES-8) |
| Can I add a light theme? | Not without approval (DES-12) |
| Can I add an icon pack or font package? | With a one-line reason in the PR (DES-13) |
