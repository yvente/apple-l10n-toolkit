# Contributing to apple-l10n-toolkit

Thanks for your interest in contributing!

## Prerequisites

- Codex CLI, ZCode, or Claude Code (or none — scripts run standalone)
- Python 3.10+
- Basic familiarity with Apple localization (`.strings` / `.xcstrings`)

## How to Contribute

### Reporting Issues

Open a GitHub issue with:
- A clear description of the problem
- Steps to reproduce (ideally a minimal fixture: a small `.xcstrings` + `.swift`)
- Expected vs actual behavior

False positives/negatives from the auditors are the most valuable reports —
please include the exact source line and catalog entry involved.

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Make your changes
4. Commit with a clear message (`git commit -m 'feat: add X'`)
5. Push and open a Pull Request

### Improving Skills

The `skills/` directory contains the canonical, self-contained skill
packages. To improve an existing skill or add a new one:

- Keep each `SKILL.md` focused and give it a discriminating description
- Put conditional detail in `references/` and deterministic behavior in tested scripts
- Keep every skill self-contained for `$skill-installer`
- Preserve the canonical classifications and state ownership in
  `references/l10n-audit-specification.md`, then synchronize the
  skill-local copies of that document
- Add or update golden fixtures in `tests/fixtures/` when behavior changes,
  and keep `python3 -m unittest discover -s tests` green

### Plugin and integrations

The plugin manifest lives at `.codex-plugin/plugin.json`. The repository
marketplace has two manifests: `.agents/plugins/marketplace.json`
(the Codex-standard location, with a git-URL source) and
`.claude-plugin/marketplace.json` (the Claude Code / ZCode-compatible
location, with a relative source). Keep both in sync when adding or
renaming plugins. All checks must remain deterministic pure-Python with no
third-party dependencies so the skills keep working in every environment.

## Code Style

- Markdown: use ATX headings (`#`), fenced code blocks
- Python: stdlib only, `pathlib`, type hints where they aid reading
- Commit messages: follow [Conventional Commits](https://www.conventionalcommits.org/)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
