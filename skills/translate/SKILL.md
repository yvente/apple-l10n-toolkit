---
name: translate
description: Translate missing localization entries for one or more BCP-47 locales into the project's .xcstrings catalog through the l10n/ workflow (init, missing, translate, inject, status). Use when a completeness audit shows gaps or a new locale is being added; not for auditing (use the check skills first).
---

# Translate

Fill per-locale gaps in `.xcstrings` catalogs with reviewed translations,
keeping a cumulative translation memory.

## Inputs

One or more BCP-47 locale codes (e.g. `ko`, `pt-BR`, `ru ar tr`). Common
codes: `zh-Hans` 简中 · `zh-Hant` 繁中 · `en` English · `ja` Japanese ·
`ko` Korean · `de` German · `fr` French · `es` Spanish · `pt-BR`
Brazilian Portuguese · `it` Italian · `ru` Russian · `ar` Arabic · `tr`
Turkish.

## Procedure

Read [the shared system specification](references/l10n-audit-specification.md)
first.

### Step 1 — ensure the l10n/ workflow is in place

If the project has no `l10n/tool.py`: create `l10n/`, copy the bundled
`<skill-root>/scripts/tool.py` there, run `python3 l10n/tool.py init`, and
confirm the detected catalog list with the user before continuing.

### Step 2 — per locale

**2a. Fetch the gap:**

```bash
python3 l10n/tool.py missing <lang>
```

JSON `{key: base_text, ...}`; `{}` means complete — skip the locale.

**2b. Translate every key.** Rules:

- printf placeholders (`%@`, `%lld`, `%1$@`, `%%`, …) preserved verbatim;
- `\n` positions unchanged;
- brand and product names untranslated;
- length follows UI conventions — short buttons, fuller descriptions;
- tone matches the locale's existing translations in the catalog and
  `l10n/<lang>.json` memory.

**2c. Append** the new entries to `l10n/<lang>.json`. The file is the
cumulative record: when it exists, read it and append — never overwrite the
whole file.

**2d. Inject into the catalog:**

```bash
python3 l10n/tool.py inject <lang> l10n/<lang>.json
```

### Step 3 — coverage report

```bash
python3 l10n/tool.py status
```

Every locale must be complete; any `!` marker means remaining gaps.

## Finish

Report per-locale coverage before/after, the keys translated for each
locale, and any keys intentionally left (with reason). Remind the user the
`l10n/` directory is workflow state worth committing (translation memory +
cognate whitelist), while the app itself builds straight from the catalog.
