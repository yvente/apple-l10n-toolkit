---
name: check-ui-hardcoded
description: Scan Swift sources for user-facing strings that never reach the localization catalog, covering SwiftUI auto-localizing APIs and raw String calls in .strings / .xcstrings projects. Use after adding new UI, when a locale audit is clean but users still see English, or before release hygiene; not for completeness or unused-key audits.
---

# Check UI Hardcoded

Audit the code → table direction: every user-facing string literal should
resolve to a catalog key.

## Inputs

The project root (default: current directory). Read-only; it scans `.swift`
sources and cross-checks against `.strings` / `.xcstrings` catalogs.

## Procedure

Read [the shared system specification](references/l10n-audit-specification.md)
first. Then run:

```bash
python3 <skill-root>/scripts/check_ui_hardcoded.py --root <project-root>
```

Options: `--format json`, `--strict` (exit 1 on HIGH/MEDIUM, for CI),
`--include-tests`.

## Interpreting results

- **HIGH (key NOT found)** — the literal never reaches a catalog; every
  locale, including the base, shows it verbatim. Fix by adding the key to
  the catalog (then translate via the `translate` skill) or by routing the
  call through a localization wrapper.
- **MEDIUM (key exists, raw call)** — a raw `String` API bypasses the
  project's localization wrappers even though a translation exists. Wrap it
  (`.local`, `String(localized:)`, or the project's convention).

Known-safe shapes the checker already skips: string literals in
identifier parameters (`systemImage:`, `image:`, …), debug output
(`print` / `NSLog` / `Logger`), `Text(verbatim:)`, and interpolated
literals whose extracted form (`%lld` / `%@` variants) exists in the
catalog. A `LOW` (key exists, auto-localized) is filtered out entirely.

## Finish

Report issue counts by severity, each finding with file:line and the
literal, the recommended fix per item (add key vs. wrap call), and confirm
which known-safe categories were skipped. Never edit source files in this
skill — audits stay read-only.
