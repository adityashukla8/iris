# IRIS Icon Set

31 Feather-style SVG icons. All icons use:
- `fill="none"`
- `stroke="currentColor"` — inherits color from parent CSS
- `stroke-width="1.75"` (2.0 for `check`)
- `stroke-linecap="round"`
- `stroke-linejoin="round"`
- `viewBox="0 0 24 24"`, default rendered at `20×20`

## Usage

```html
<!-- Inline (preferred — inherits color) -->
<span style="color: var(--sev-critical); display:inline-flex;">
  <img src="assets/icons/alert-triangle.svg" width="16" height="16">
</span>

<!-- As CSS mask (full color control) -->
.icon-shield {
  -webkit-mask: url(assets/icons/shield.svg) no-repeat center;
  mask: url(assets/icons/shield.svg) no-repeat center;
  background: currentColor;
  width: 20px; height: 20px;
}
```

## Icon index

| File | Usage |
|------|-------|
| activity.svg | Live-feed / vitals pulse |
| alert-triangle.svg | Warning severity |
| badge-check.svg | Verified / healed |
| bar-chart-2.svg | Analytics / heatmap |
| bell.svg | Alert feed |
| brain.svg | AI agent / LLM |
| check.svg | Pass / confirmed |
| check-circle.svg | Success state |
| chevron-down.svg | Collapse / dropdown |
| chevron-right.svg | Expand / navigate |
| clock.svg | Timestamp / latency |
| cpu.svg | Compute / pipeline |
| database.svg | Phoenix dataset |
| eye.svg | IRIS logo variant / inspect |
| file-text.svg | Trace / document |
| filter.svg | Filter dropdown |
| git-branch.svg | Prompt versioning |
| heart-pulse.svg | Clinical vitals |
| info.svg | Info severity |
| layers.svg | Multi-agent stack |
| link.svg | External link |
| list.svg | Trace list |
| loader.svg | Loading state |
| lock.svg | Safety lock |
| maximize-2.svg | Expand detail |
| message-square.svg | MCP chat |
| pill.svg | Drug / medication |
| refresh-cw.svg | Refresh / sync |
| search.svg | Search / filter |
| shield.svg | Safety supervisor |
| x-circle.svg | Critical / reject |
