# Apple L10n Toolkit

Apple L10n Toolkit is an agent plugin for Codex, ZCode, and Claude Code
containing four focused skills for repeatable Apple app localization work:
three complementary audits plus a translate workflow.

It works with classic `.strings` files and string catalogs (`.xcstrings`),
SwiftUI or UIKit, in any Apple project shape.

## Skills

| Skill | Direction | Question answered | Primary output |
|---|---|---|---|
| `$check-l10n-apple` | locale ↔ locale | Is every locale complete and actually translated? | per-locale missing / extra / likely-untranslated report |
| `$check-ui-hardcoded` | code → table | Does every user-facing string reach a catalog? | HIGH/MEDIUM findings with file:line |
| `$check-l10n-unused-keys` | table → code | Is every catalog key still referenced by code? | unused / print-only / test-only / empty classification |
| `$translate` | — | Fills the gaps the audits find | updated `.xcstrings` + `l10n/` translation memory |

The canonical contract for classifications, the `l10n/` working directory,
and file formats is in [`references/l10n-audit-specification.md`](references/l10n-audit-specification.md).
Each installable skill carries the reference material and scripts it needs,
so standalone installation does not depend on files outside the skill
directory.

## Workflow

```text
        ┌────────────────────────────────────────────────┐
        │                l10n/ artifacts                 │
        │  (catalog + translation memory + whitelist)    │
        └───────────────▲────────────────────▲───────────┘
                        │ inject             │ maintain
     $check-l10n-apple │                $translate
     ──────────────────┴───────┐    ┌────────┴──────────
     $check-ui-hardcoded       │    │
     ──────────────────────────┤    │
     $check-l10n-unused-keys ──┘    │
     (delete dead keys directly)    │
                                    │
              gaps found by audits ─┘
```

- Run the three audits independently; they cover disjoint defect classes.
- `$translate` fills completeness gaps through `l10n/tool.py`
  (`missing → translate → inject → status`), appending to a cumulative
  per-locale translation memory.
- Unused-key deletions and source fixes (e.g. an unreachable `return ""`
  branch that re-extracts an empty key) are applied directly; no artifact
  beyond the catalog is produced.

## Installation

### Codex

```bash
codex plugin install https://github.com/yvente/apple-l10n-toolkit
```

or via the repository marketplace manifest at `.agents/plugins/marketplace.json`.

### Claude Code / ZCode

Add this repository as a plugin marketplace, then install the plugin:

```text
marketplace: yvente/apple-l10n-toolkit   (.claude-plugin/marketplace.json)
plugin:      apple-l10n-toolkit
```

### Standalone

Every skill under `skills/` is self-contained; copy a skill directory (or
just its `scripts/`) anywhere and run the Python directly. Python 3.10+,
no third-party dependencies.

```bash
python3 skills/check-l10n-apple/scripts/check_l10n.py <project-root>
python3 skills/check-ui-hardcoded/scripts/check_ui_hardcoded.py --root <project-root> [--strict]
python3 skills/check-l10n-unused-keys/scripts/check_unused_keys.py <project-root> [--json] [--strict]
```

## Tests

```bash
python3 -m unittest discover -s tests
```

Golden fixtures under `tests/fixtures/` pin each script's classification
contract, including known false-positive traps (SF Symbol parameters,
interpolated literals with `%lld` / `%@` variants, print-only and test-only
references, the cognate whitelist, and the translate round trip).

## Design notes

- Audits are read-only and deterministic — all logic lives in plain Python;
  the agent layer only interprets results and drafts fixes.
- `$translate` is the only skill that writes; it never touches keys the
  audits did not flag, and its memory files are append-only.
- Exit codes and `--json` outputs are stable for CI: `0` clean,
  `1` findings (with `--strict`), `2` no catalogs found.

## License

MIT — see [LICENSE](LICENSE).
