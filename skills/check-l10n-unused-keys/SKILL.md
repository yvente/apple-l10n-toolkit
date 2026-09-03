---
name: check-l10n-unused-keys
description: Find .xcstrings keys with zero references in Swift code, classifying unused, print-only, test-only, and empty keys with CI-friendly exit codes. Use before pruning string catalogs, after removing UI, or when a catalog accumulated legacy entries; requires .xcstrings (not classic .strings).
---

# Check L10n Unused Keys

Audit the table → code direction: catalog entries no live code references
anymore.

## Inputs

The project root (default: current directory). Read-only; needs `.xcstrings`
catalogs (classic `.strings` is not covered). Supports `--json` and
`--strict` (exit 1 on findings) for CI.

## Procedure

Read [the shared system specification](references/l10n-audit-specification.md)
first. Then run:

```bash
python3 <skill-root>/scripts/check_unused_keys.py <project-root> [--json] [--strict]
```

## Interpreting results

- **UNUSED** — zero references in any `.swift` file. Deletion candidates:
  remove the whole entry (all locales) from the catalog.
- **PRINT-ONLY** — every reference sits on a `print(...)` line; delete the
  key and the debug statements together.
- **TEST-ONLY** — referenced only from test/preview/fixture code; invisible
  to users. Confirm intent before deleting.
- **EMPTY KEY** — the `""` key. Trace its source: an empty string literal
  in a `LocalizedStringKey` context re-extracts into the catalog on every
  build, so fix the source (e.g. remove an unreachable `return ""`
  branch), not just the table.

## Finish

Report the classification counts, every non-used key with its class and
reference locations, and recommend deletions. Caveat every recommendation:
runtime-assembled keys cannot be proven used — batch deletions should go in
a dedicated commit for easy revert. Never edit catalog or source files in
this skill — audits stay read-only.
