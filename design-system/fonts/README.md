# IRIS Design System — Typography

## Font family

**Poppins** is the sole typeface across all surfaces — UI, marketing, and monospace output.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

Weights used:

| Weight | Token | Usage |
|--------|-------|-------|
| 400 | regular | Body text, descriptions |
| 500 | medium | Labels, nav items, secondary UI |
| 600 | semibold | Panel titles, card names, table headers |
| 700 | bold | Stat values, headings |
| 800 | extrabold | Hero headlines, display text |

## Monospace

`--mono` is aliased to Poppins with `font-variant-numeric: tabular-nums`. There is **no JetBrains Mono, Fira Code, or any monospace font** in the IRIS design system.

```css
/* Correct */
.metric { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* Wrong */
.metric { font-family: 'JetBrains Mono', monospace; } /* never */
```

Apply `font-variant-numeric: tabular-nums` to any element displaying numbers, trace IDs, timestamps, scores, or rates — so digits align in columns without a monospace font.

## Type scale

| Class | Size | Weight | Use |
|-------|------|--------|-----|
| `.text-display` | clamp(2rem → 3rem) | 800 | Hero section only |
| `.text-h1` | clamp(1.625rem → 2.375rem) | 700 | Section headlines |
| `.text-h2` | clamp(1.25rem → 1.625rem) | 700 | Sub-section headlines |
| `.text-h3` | 1.125rem | 600 | Card/panel titles |
| `.text-body-lg` | 1.0625rem | 400 | Hero body copy |
| `.text-body` | 0.9375rem | 400 | Standard body |
| `.text-body-sm` | 0.875rem | 400 | Dense body, descriptions |
| `.text-caption` | 0.8125rem | 400 | Supplementary text |
| `.text-label` | 0.75rem | 600 | Form labels, tags |
| `.text-micro` | 0.625rem | 600 | Stat card labels, column headers (uppercase) |

## Rules

- No custom font loading outside of Poppins from Google Fonts.
- Do not set `font-family` to anything other than `var(--font)` or `var(--mono)`.
- `--mono` resolves to `'Poppins', system-ui, -apple-system, sans-serif` — identical to `--font`.
  The only difference is that consumers of `--mono` must also add `font-variant-numeric: tabular-nums`.
- System fallback: `system-ui, -apple-system, sans-serif` — never `monospace`.
