---
name: check-l10n-apple
description: Check Apple project localization completeness across locales for .strings and .xcstrings catalogs, reporting missing keys, extra keys, and likely-untranslated entries per locale. Use when auditing translation coverage, adding a locale, or verifying a translation batch; not for finding unused keys or hardcoded strings.
---

# Check L10n (Apple)

Audit locale completeness of an Apple project's localization tables.

## Inputs

The project root (default: current directory). The audit needs no
preparation and writes nothing; it reads `.strings` groups and `.xcstrings`
catalogs in place.

## Procedure

Read [the shared system specification](references/l10n-audit-specification.md)
first. Then run the bundled checker against the project root:

```bash
python3 <skill-root>/scripts/check_l10n.py <project-root>
```

If the project maintains `l10n/cognate_ok.txt`, the script loads it
automatically and exempts whitelisted keys from the value==key check.

## Interpreting results

- **Missing (<n>)** — the locale lacks keys the base locale has; users of
  that locale see base-language fallback. Fix via the `translate` skill.
- **Extra (<n>)** — classic `.strings` only; a locale file holds keys the
  base does not. Remove or reconcile.
- **Likely untranslated** — value equals the key and only this locale is
  unchanged; the entry is probably copied English. Fix via `translate`.
- **Possible cognate** — informational; if a human confirms the word is
  legitimately identical in that locale, add it to `l10n/cognate_ok.txt`
  with a rationale comment, otherwise translate it.

## Finish

Report per-locale status (complete ✅ / issues ⚠️), list every defective
key with its classification, and name the next action (usually `translate`
for the affected locales). Never edit catalog files in this skill — audits
stay read-only.
