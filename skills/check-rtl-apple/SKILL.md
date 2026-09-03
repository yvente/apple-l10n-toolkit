---
name: check-rtl-apple
description: Audit SwiftUI projects for right-to-left (RTL) layout adaptation quality on Apple platforms, covering SF Symbol direction variants, layoutDirection scoping, transitions, and drag gestures per Apple HIG. Use when adding Arabic/Hebrew/Urdu locales, before releasing RTL support, or when RTL screenshots look wrong; not a string-completeness or hardcoded-text audit.
---

# Check RTL (Apple)

Audit how a SwiftUI codebase behaves when the layout direction flips to
right-to-left — the companion check to `translate` for Arabic, Hebrew, and
other RTL locales. Method-only skill: all rules are judgment rules from
Apple HIG applied to source reading; there is no deterministic script.

## Inputs

The project root (default: current directory) and its `.swift` sources.
Read-only.

## Core rules

### Must mirror under RTL (never force LTR)

- Navigation direction: back buttons, breadcrumbs, hierarchy arrows
- List / content layout: `HStack` child order, leading/trailing alignment
- Text alignment: titles, body copy, captions
- Page-turn direction and transition origins
- Non-directional action icons

### Must NOT mirror (force LTR)

- Playback controls — play/pause, next/previous represent the timeline, not
  the reading direction
- Playback progress bars — time flows left-to-right
- Physical metaphors — turntables, tonearms, tape reels
- Clocks and timers, map direction indicators

### SF Symbol direction variants

| Wrong | Right | Why |
|---|---|---|
| `chevron.right` | `chevron.forward` | forward/backward auto-flip with RTL |
| `chevron.left` | `chevron.backward` | same |
| `sidebar.left` | `sidebar.leading` | leading/trailing auto-flip |
| `arrow.left` (nav back) | `arrow.backward` | same |

`chevron.up/down` and `arrow.up/down` have no direction ambiguity — leave
them as-is.

## Procedure

**1a. Scan for directional SF Symbols** that should use adaptive variants:
`chevron.right`, `chevron.left`, `sidebar.left`, `sidebar.right`,
`arrow.left`, `arrow.right` inside `Image(systemName:)` / `Label` — excluding
playback contexts (`backward.end`, `forward.end`, `play`, `pause`), which
correctly stay LTR.

**1b. Scan `.environment(\.layoutDirection, .leftToRight)` scope:**

- Correct — on a single icon, or on an HStack that contains only playback
  controls
- Suspicious — on any container holding `Text` (breaks text alignment), or
  on a page-level stack (blocks the whole layout from mirroring)

**1c. Scan `.transition(.push(from: .leading/.trailing))`** — if sibling
playback controls are forced LTR, the transition must run inside that LTR
environment too, or the push origin contradicts the button position.

**1d. Scan `DragGesture` direction logic** reading `translation.width` —
if the gesture area is already forced LTR no change is needed; otherwise
the handler must read `layoutDirection` from the environment and invert.

**2. Verify force-LTR coverage** — playback progress (`Slider` or custom
bar), playback button group, physical-metaphor views, and circular trim
progress (`Circle().trim(...)`) all carry the LTR environment override.

**3. Report:**

```
## RTL adaptation report

### ❌ Must fix
- `path:line` — problem

### ⚠️ Confirm
- `path:line` — problem

### ✅ Handled correctly
- playback controls: forced LTR ✓
- progress bar: forced LTR ✓
- (other confirmed areas)

### Summary
X must fix, Y to confirm, Z handled correctly.
```

## Finish

Present the report and ask whether to fix; never edit source files in this
skill — audits stay read-only. When paired with `translate` adding an RTL
locale, recommend re-running after the locale ships to catch regressions in
screenshots or the wild.
