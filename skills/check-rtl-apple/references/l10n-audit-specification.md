# Apple L10n Toolkit — System Specification

Canonical contract for the toolkit's audit directions, classifications, the
`l10n/` working directory, and file formats. Each installable skill carries a
copy of this document; keep them synchronized when this file changes.

## Scope

Apple app projects localized with classic `.strings` (one file per
`<locale>.lproj/`) or string catalogs (`.xcstrings`). Source language is
assumed to be English (`en`) unless a project declares otherwise.

## Audit directions

Localization defects fall into disjoint audit directions. Each skill audits
exactly one; together with `translate` they close the loop.

| Direction | Skill | Question answered |
|---|---|---|
| locale ↔ locale | `check-l10n-apple` | Is every locale complete and actually translated? |
| code → table | `check-ui-hardcoded` | Does every user-facing string literal reach a catalog? |
| table → code | `check-l10n-unused-keys` | Is every catalog key still referenced by code? |
| locale → layout | `check-rtl-apple` | Does the layout survive a right-to-left locale? |

The `translate` skill is not an audit: it fills the gaps the audits find.

### Direction 1: locale completeness (`check_l10n.py`)

Compares every non-base locale against the base locale.

- **Missing** — key present in base, absent in the locale (user sees base-language fallback).
- **Extra** — key present in a locale's `.strings` but not in base (classic
  format only; `.xcstrings` shares one key set across locales so this cannot occur).
- **Likely untranslated** — value equals the key (suspicious copy-through),
  refined by a cross-locale heuristic:
  - `universal` — all-caps abbreviation, or unchanged in ≥3 other locales,
    or unchanged in any CJK locale → skipped silently;
  - `cognate` — unchanged in 1–2 other locales → informational;
  - `missing` — unchanged only in this locale → flagged.
- **Cognate whitelist** — `l10n/cognate_ok.txt` (one key per line, `#`
  comments) lists keys a human verified as legitimately identical in some
  locale (e.g. `Sticker` in German). Whitelisted keys are exempt from the
  value==key check in both `.strings` and `.xcstrings` paths. Record the
  verification rationale as a comment next to each entry.

### Direction 2: hardcoded UI strings (`check_ui_hardcoded.py`)

Scans Swift sources for string literals passed to user-facing APIs and
cross-checks them against the catalogs.

- **SwiftUI auto-localizing APIs** (`Text`, `Button`, `Label`, …) — flagged
  HIGH only when the key is absent from the catalog, because
  `Text("Home")` is localized automatically when the key exists.
- **Raw string APIs** — flagged MEDIUM when the key exists but the call site
  bypasses localization wrappers, HIGH when absent.
- **Interpolated literals** — Xcode extracts `Text("Face \(i + 1)")` into the
  catalog as `Face %lld`. The specifier type cannot be inferred from source
  alone, so both `%lld` and `%@` variants are enumerated per interpolation
  (capped at 16 combinations); any variant present in the catalog counts as
  localized.
- **Non-content parameters** — literals in identifier parameters
  (`systemImage:`, `image:`, `icon:`, …) are SF Symbols / asset names, never
  user-visible copy, and are skipped.
- Debug output (`print`, `NSLog`, `os_log`, `Logger`), `Text(verbatim:)`,
  `NSLocalizedString`, and `String(localized:)` lines are skipped.

### Direction 3: unused catalog keys (`check_unused_keys.py`)

For every `.xcstrings` key, searches all `.swift` sources (comments stripped)
for the verbatim quoted key and, when the key contains printf specifiers, the
Swift interpolated form. Classifications:

- **used** — referenced from app code (counts as healthy);
- **unused** — zero references anywhere; prime deletion candidates;
- **print-only** — every reference sits on a `print(...)` line; delete the key
  and the debug statements together;
- **test-only** — referenced only from test/preview/fixture sources (path
  segments `*Tests`, `Tests`, `Testing`, `Preview Content`, or `*Tests.swift`
  files); invisible to users — confirm intent before deleting;
- **empty** — the `""` key; table junk. Its usual source is an empty string
  literal in a `LocalizedStringKey` context (e.g. an unreachable
  `return ""` branch); removing the table entry alone lets Xcode re-extract
  it on the next build, so fix the source.

Exit codes: `0` clean, `1` findings (with `--strict`), `2` no catalogs found.
`--json` emits the full report for CI consumption.

Limits: keys assembled at runtime from variables cannot be proven used;
review before deleting. Classic `.strings` is not covered by direction 3.

### Companion direction: RTL layout adaptation (`check-rtl-apple`)

Judgment audit (no deterministic script) of how the layout behaves under
right-to-left locales, run when adding Arabic/Hebrew/Urdu or auditing RTL
regressions. Contract:

- **Must mirror** — navigation, list/content order, text alignment, page
  transitions, non-directional icons.
- **Must stay LTR** (forced via `.environment(\.layoutDirection,
  .leftToRight)`) — playback controls and progress, physical metaphors,
  clocks, map directions.
- **SF Symbols** — directional chevrons/arrows in navigation must use the
  adaptive variants (`chevron.forward`/`backward`, `sidebar.leading`);
  playback symbols correctly stay LTR.
- The LTR override must be scoped tightly: per icon or per playback-control
  container, never around `Text` or page-level stacks.
- Output is a fixed report shape (must-fix / confirm / handled) with
  `file:line` evidence; the skill never edits sources.

Paired with `translate`: adding an RTL locale should be followed by this
audit once the locale renders.

## The `l10n/` working directory

`translate` materializes a per-project working directory. It is workflow
state, not a build input — the app compiles from the Xcode catalog directly.

```
l10n/
├── tool.py            # copied from the skill; workflow entry point
├── config.json        # generated by `init`; catalog paths
├── cognate_ok.txt     # optional; cognate whitelist (direction 1)
├── <lang>.json        # cumulative translation memory, append-only
└── ...
```

### translate workflow

For each target BCP-47 locale:

1. `python3 l10n/tool.py missing <lang>` → JSON `{key: base_text, ...}`;
   `{}` means the locale is complete.
2. Translate every key. Rules:
   - printf placeholders (`%@`, `%lld`, `%1$@`, `%%`, …) are preserved verbatim;
   - `\n` positions are preserved;
   - brand and product names are not translated;
   - length follows UI conventions (short buttons, fuller descriptions);
   - tone matches the locale's existing translations.
3. **Append** entries to `l10n/<lang>.json` — never overwrite the file; it is
   the cumulative record and terminology reference.
4. `python3 l10n/tool.py inject <lang> l10n/<lang>.json`.
5. Finish with `python3 l10n/tool.py status`; every locale must be complete.

## Skill self-containment

Every skill directory carries its own `scripts/` and `references/` copies so
standalone installation never depends on files outside the skill directory.
Fixes land in the skill copies first; the root `references/` document is the
canonical text.
