# IRIS Design System

Design tokens, component patterns, icon set, and React UI kits for the IRIS Clinical AI Safety platform.

---

## Quickstart

```bash
# Preview any component card (34 available)
cd design-system/preview && python -m http.server 4202
open http://localhost:4202/stat-card.html

# Dashboard UI kit gallery
cd design-system/ui_kits/dashboard && python -m http.server 4200
open http://localhost:4200

# Marketing UI kit gallery
cd design-system/ui_kits/marketing && python -m http.server 4201
open http://localhost:4201
```

All galleries use **React 18 + Babel standalone** — no build step, no Node.js required.

---

## Structure

```
design-system/
  colors_and_type.css     ← design tokens + component CSS classes
  fonts/README.md         ← Poppins usage guide
  assets/
    logo/                 ← 3 SVG logo variants
    icons/                ← 31 Feather-style SVGs
  preview/
    _base.css
    *.html (×34)          ← one static HTML preview per component/token
  ui_kits/
    dashboard/            ← 8 React JSX components + index.html gallery
    marketing/            ← 3 React JSX components + index.html gallery
  README.md
  SKILL.md                ← Claude Code skill for design enforcement
```

---

## Design Principles

### 1. One typeface
**Poppins** everywhere — UI, marketing, and monospace output. `--mono` is aliased to Poppins with `font-variant-numeric: tabular-nums`. There is no JetBrains Mono or Fira Code anywhere.

### 2. Dark primary action, not blue
Primary buttons use `--action-bg: #0F172A` (dark fill). Blue (`#1D4ED8`) appears **only** as the active tab underline — nowhere else.

### 3. Severity as accent, not fill
Critical/warning/pass colors appear as:
- 7px status dots
- Inline chips with tinted background + matching border
- 3px left rails on stat cards (via `::before` pseudo-element — never `border-left`)

They never appear as large backgrounds, headers, or button fills.

### 4. Two surfaces only
- **Light (`#FFFFFF`)** — all cards, panels, topbar, table rows
- **Dark (`#0F172A`)** — activity-log panel and CTA/footer section **only**

No intermediate dark shades for decorative purposes.

### 5. No animation, no gradients
The only allowed transitions are `color .15s`, `background .15s`, `border-color .15s`. No bounce, no spin, no scale transforms, no CSS gradients.

---

## Token Reference

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--surface-base` | `#FFFFFF` | Cards, panels, topbar |
| `--surface-raised` | `#F8FAFC` | Panel backgrounds, table headers |
| `--surface-sunken` | `#F1F5F9` | Chips, tag backgrounds |
| `--surface-dark` | `#0F172A` | Activity log + CTA/footer ONLY |
| `--ink-primary` | `#0F172A` | Headings, bold labels |
| `--ink-secondary` | `#475569` | Body text, descriptions |
| `--ink-tertiary` | `#94A3B8` | Timestamps, metadata, placeholders |
| `--border-subtle` | `#E2E8F0` | Card/panel borders |
| `--border-default` | `#CBD5E1` | Focused inputs |
| `--action-bg` | `#0F172A` | Primary button fill |
| `--accent` | `#1D4ED8` | Active tab underline ONLY |
| `--sev-critical` | `#E05555` | Critical severity color |
| `--sev-warning` | `#C07818` | Warning severity color |
| `--sev-pass` | `#1A9652` | Pass/info severity color |

### Severity chip pattern
```html
<!-- Critical chip -->
<span class="sev-chip critical">CRITICAL</span>

<!-- In raw CSS -->
<span style="
  background: #FFF1F1; color: #C43434;
  border: 1px solid #FFD4D4; border-radius: 4px;
  font-size: .625rem; font-weight: 600; padding: 1px 7px;
">CRITICAL</span>
```

### Stat card left rail
```css
/* Always via ::before — never border-left */
.stat-card {
  position: relative;
  padding-left: 20px;
}
.stat-card::before {
  content: '';
  position: absolute;
  left: 0; top: 12px; bottom: 12px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--sev-critical); /* or warning/pass/neutral */
}
```

---

## Component Catalog

| Preview file | Component | Notes |
|-------------|-----------|-------|
| `color-palette.html` | Color tokens | Slate scale + severity triad |
| `typography-scale.html` | Type scale | Display → micro |
| `type-body.html` | Body + mono | Tabular-nums demo |
| `spacing-scale.html` | Spacing | 4px grid |
| `elevation-shadows.html` | Shadow levels | xs → lg |
| `border-radius.html` | Radius scale | 4px → full |
| `logo-mark.html` | Logo mark | 3 sizes |
| `logo-wordmark.html` | Logo + name | Light + dark |
| `logo-responsive.html` | Responsive mark | 72 → 24px |
| `icon-grid.html` | All 31 icons | Grid view |
| `icon-usage.html` | Icon in context | With severity colors |
| `btn-primary.html` | Primary button | Dark fill, 3 sizes |
| `btn-ghost.html` | Ghost button | Outlined |
| `btn-danger.html` | Approve + Reject | Healing pipeline |
| `btn-icon.html` | Icon-only buttons | Compact |
| `badge-severity.html` | Severity chips | Sizes + variants |
| `badge-status.html` | Status pills | Live / Pending / Idle |
| `stat-card.html` | Stat card | Rail variants |
| `panel.html` | Panel shell | With dot + meta |
| `alert-item.html` | Alert feed item | 3 severity variants |
| `input-text.html` | Text input | Default + focused |
| `input-select.html` | Select dropdown | Custom arrow |
| `chip-tag.html` | Context chips | Gray + flagged |
| `eval-card-pass.html` | Eval card (pass) | Confidence bar |
| `eval-card-fail.html` | Eval card (critical) | Reasoning chain |
| `trace-list-item.html` | Trace list row | Selected state |
| `timeline-chart.html` | SVG line chart | 3 series |
| `heatmap-table.html` | Evaluator heatmap | Row tinting |
| `healing-candidate.html` | Healing candidate | Approve/Reject |
| `diff-viewer.html` | Prompt diff | Before/After |
| `mcp-tool-card.html` | MCP tool card | Dark terminal |
| `topbar.html` | Topbar | Logo + actions |
| `tab-nav.html` | Tab strip | Active state |
| `pipeline-node.html` | Pipeline nodes | 4 type variants |

---

## Icons

31 Feather-style SVG icons in `assets/icons/`. All use:
- `fill="none"`, `stroke="currentColor"`, `stroke-width="1.75"`
- `stroke-linecap="round"`, `stroke-linejoin="round"`
- `viewBox="0 0 24 24"`, default rendered at `20×20`

Color via parent CSS — no hardcoded stroke colors.

See `assets/icons/README.md` for full index.

---

## React UI Kits

### Dashboard (`ui_kits/dashboard/`)

8 components that mirror the live IRIS Shift Commander dashboard:

| File | Component | Props |
|------|-----------|-------|
| `TopBar.jsx` | Top navigation bar | `onRefresh`, `onScan`, `lastRefreshed`, `scanLoading` |
| `TabNav.jsx` | Tab strip | `tabs`, `activeTab`, `onChange` |
| `StatRow.jsx` | 6 KPI cards | `stats` object |
| `AlertFeed.jsx` | Live alert list | `alerts`, `maxHeight` |
| `EvalCard.jsx` | Single evaluator result | `evaluation` object |
| `TraceInspector.jsx` | Two-panel trace view | `traces`, `selectedId`, `onSelect` |
| `HealingPanel.jsx` | Candidates + history | `candidates`, `history`, `onApprove`, `onReject` |
| `AnalyticsGrid.jsx` | Heatmap / timeline / breakdown | `analytics` (from `GET /analytics`) |

### Marketing (`ui_kits/marketing/`)

3 components for the IRIS homepage:

| File | Component | Props |
|------|-----------|-------|
| `Hero.jsx` | Hero section with stats | `onDashboardClick`, `onGithubClick` |
| `HowItWorks.jsx` | 6-step pipeline walkthrough | — |
| `AgentGrid.jsx` | 6 agent cards | — |

---

## Anti-patterns

These patterns are explicitly prohibited:

```css
/* WRONG — blue button */
.btn { background: #2563EB; }

/* WRONG — border-left for stat card */
.stat-card { border-left: 3px solid #E05555; }

/* WRONG — monospace font */
.metric { font-family: 'JetBrains Mono', monospace; }

/* WRONG — severity as large fill */
.card-header.critical { background: #FFF1F1; }

/* WRONG — purple decoration */
.node.phoenix { background: #f5f0ff; color: #6b21a8; }

/* WRONG — gradient */
.hero { background: linear-gradient(135deg, #1E293B, #0F172A); }

/* WRONG — bounce animation */
.alert { animation: bounce .4s cubic-bezier(.6,-0.28,.74,.05); }
```

---

## Contributing

1. Add new design tokens to `colors_and_type.css` first.
2. Add a preview card in `preview/` to verify the rendering.
3. Update the component catalog table in this README.
4. If creating a new React component, add it to the appropriate `ui_kits/` gallery.
5. Run `SKILL.md` rules against your changes before committing.
