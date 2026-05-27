---
name: iris-design-system
description: >
  Apply IRIS design tokens, component patterns, and anti-patterns when building
  or reviewing UI for the IRIS clinical AI safety dashboard or marketing site.
  Use this skill whenever creating new components, reviewing CSS, or auditing
  code for design consistency.
tags: [design, frontend, css, react, iris]
---

# IRIS Design System Skill

## When to invoke this skill

- Creating or editing any HTML/CSS/JSX in `dashboard/templates/`, `ui_kits/`, or marketing pages
- Reviewing code for design consistency violations
- Asked to "make it look like IRIS" or "follow the design system"
- Adding new UI components to the live dashboard

## Core rules (enforce without exception)

| Rule | What to do | What to never do |
|------|-----------|-----------------|
| **Typography** | `font-family: var(--font)` everywhere | Use JetBrains Mono, Fira Code, or any monospace font |
| **Monospace** | `var(--mono)` + `font-variant-numeric: tabular-nums` | Set `--mono` to a monospace font |
| **Primary button** | `background: var(--action-bg)` = `#0F172A` (dark fill) | Blue/cobalt fill (`#2563EB`, `#1D4ED8`) on buttons |
| **Blue accent** | `#1D4ED8` for active tab `border-bottom` ONLY | Blue backgrounds, blue text, blue borders anywhere else |
| **Severity colors** | Chips (`2px border, tinted bg`), 7px dots, 3px rails | Large colored fills, headers, backgrounds |
| **Stat card rails** | `::before` absolute div, `width:3px` | `border-left` |
| **Dark surface** | `#0F172A` on activity-log panel + CTA/footer ONLY | Dark surfaces on regular cards, panels, or headers |
| **Animations** | `transition: color .15s, background .15s` only | Bounce, spin, scale transforms, gradients |
| **Purple/violet** | Never | No `#7c3aed`, no Phoenix-violet anywhere |

## Token reference

```css
/* Surfaces */
--surface-base:   #FFFFFF
--surface-raised: #F8FAFC
--surface-sunken: #F1F5F9
--surface-dark:   #0F172A  /* activity log + CTA/footer ONLY */

/* Text */
--ink-primary:   #0F172A
--ink-secondary: #475569
--ink-tertiary:  #94A3B8

/* Borders */
--border-subtle:  #E2E8F0
--border-default: #CBD5E1

/* Action */
--action-bg:       #0F172A  /* primary button fill */
--action-bg-hover: #1E293B

/* Accent — tab underline ONLY */
--accent: #1D4ED8

/* Severity */
--sev-critical: #E05555  --sev-critical-bg: #FFF1F1  --sev-critical-border: #FFD4D4
--sev-warning:  #C07818  --sev-warning-bg:  #FFFBEB  --sev-warning-border:  #FEE9A0
--sev-pass:     #1A9652  --sev-pass-bg:     #EDFBF3  --sev-pass-border:     #D6F5E3
```

## File map

```
design-system/
  colors_and_type.css          ← all tokens, classes, component patterns
  assets/
    logo/                      ← iris-mark.svg, iris-mark-white.svg, iris-wordmark.svg
    icons/                     ← 31 Feather-style SVGs + README
  fonts/
    README.md                  ← Poppins usage rules
  preview/
    _base.css                  ← preview card base
    *.html (×34)               ← one HTML file per component / token group
  ui_kits/
    dashboard/
      index.html               ← self-contained React gallery (Babel standalone)
      styles.css
      TopBar.jsx  TabNav.jsx  StatRow.jsx  AlertFeed.jsx
      EvalCard.jsx  TraceInspector.jsx  HealingPanel.jsx  AnalyticsGrid.jsx
    marketing/
      index.html               ← self-contained React gallery (Babel standalone)
      styles.css
      Hero.jsx  HowItWorks.jsx  AgentGrid.jsx
  README.md                    ← full designer onboarding
  SKILL.md                     ← this file
```

## How to run the galleries

```bash
cd design-system

# Dashboard UI kit
cd ui_kits/dashboard && python -m http.server 4200
# open http://localhost:4200

# Marketing UI kit
cd ui_kits/marketing && python -m http.server 4201
# open http://localhost:4201

# Preview cards
cd preview && python -m http.server 4202
# open http://localhost:4202/color-palette.html
```
