#!/usr/bin/env python3
r"""check_unused_keys.py — report xcstrings keys with zero references in Swift code.

Direction: table -> code. Complements check_l10n.py (locale <-> locale) and
check_ui_hardcoded.py (code -> table).

For each key in every .xcstrings under ROOT, search all .swift sources
(comments stripped) for:
  1. the verbatim quoted key  ("Key %@", covers Text("...") / .localized(with:))
  2. if the key has printf specifiers, the interpolated form ("Key \(expr)")
     — covers Text("\(count) faces")

Classifications:
  UNUSED       zero references anywhere
  PRINT-ONLY   every reference sits on a print(...) line (debug leftovers)
  TEST-ONLY    referenced only from test / preview / fixture sources
               (paths matching *Tests, Tests, Testing, Preview Content)
  EMPTY KEY    the "" key — table junk
Everything else counts as used.

Usage:
  python3 check_unused_keys.py [ROOT] [--json] [--strict]

Exit codes: 0 = clean (used only), 1 = findings (with --strict),
2 = usage / no tables found.

Limits: xcstrings only (classic .strings not covered); keys assembled at
runtime from variables cannot be proven used — review before deleting.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SPEC = re.compile(r'%(?:\d+\$)?(?:ll|l|h)?[@dDiuxXoOfeEgGaAcCsS]|%%')

TEST_DIR_NAMES = {'Tests', 'Testing', 'Preview Content'}


def strip_comments(src: str) -> str:
    out, i, n, in_str = [], 0, len(src), False
    while i < n:
        c = src[i]
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i+1]); i += 2; continue
            if c == '"':
                in_str = False
            i += 1; continue
        if c == '"':
            if src.startswith('"""', i):
                j = src.find('"""', i + 3); i = n if j == -1 else j + 3
                out.append(' '); continue
            in_str = True; out.append(c); i += 1; continue
        if c == '/' and src[i+1:i+2] == '/':
            j = src.find('\n', i)
            if j == -1: break
            i = j; continue
        if c == '/' and src[i+1:i+2] == '*':
            j = src.find('*/', i + 2)
            if j == -1: break
            i = j + 2; continue
        out.append(c); i += 1
    return ''.join(out)


def is_test_source(rel: str) -> bool:
    """Generic test/preview/fixture detection: any path segment like
    'FooTests', 'Tests', 'Testing', 'Preview Content', or a *Tests.swift file."""
    parts = rel.split('/')
    if any(p in TEST_DIR_NAMES or p.endswith('Tests') for p in parts[:-1]):
        return True
    return parts[-1].endswith('Tests.swift')


def patterns_for(key: str):
    pats = [re.escape(f'"{key}"')]
    if key and SPEC.search(key):
        parts, pos = [], 0
        for m in SPEC.finditer(key):
            parts.append(re.escape(key[pos:m.start()]))
            parts.append('%' if m.group(0) == '%%' else r'\\\((?:[^()]|\([^()]*\))*\)')
            pos = m.end()
        parts.append(re.escape(key[pos:]))
        pats.append('"' + ''.join(parts) + '"')
    return [re.compile(p) for p in pats]


def main():
    ap = argparse.ArgumentParser(description='Find xcstrings keys unreferenced by Swift code.')
    ap.add_argument('root', nargs='?', default='.', help='project root (default: cwd)')
    ap.add_argument('--json', action='store_true', help='machine-readable report')
    ap.add_argument('--strict', action='store_true', help='exit 1 when any finding exists (CI)')
    args = ap.parse_args()
    root = Path(args.root).resolve()

    keys = {}
    for p in root.rglob('*.xcstrings'):
        for k in json.loads(p.read_text(encoding='utf-8')).get('strings', {}):
            keys.setdefault(k, p.relative_to(root).as_posix())
    if not keys:
        print('No .xcstrings found.', file=sys.stderr)
        sys.exit(2)

    sources = [(p.relative_to(root).as_posix(), is_test_source(p.relative_to(root).as_posix()),
                strip_comments(p.read_text(encoding='utf-8', errors='replace')))
               for p in sorted(root.rglob('*.swift'))]

    report = {}
    for key, table in sorted(keys.items()):
        if key == '':
            report[key] = {'status': 'empty', 'table': table, 'hits': []}
            continue
        hits = []
        for rx in patterns_for(key):
            for rel, test, text in sources:
                for m in rx.finditer(text):
                    line_start = text.rfind('\n', 0, m.start()) + 1
                    line_end = text.find('\n', m.end())
                    line = text[line_start:line_end if line_end != -1 else len(text)]
                    hits.append({'file': rel, 'test': test, 'line': text.count('\n', 0, m.start()) + 1,
                                 'text': line.strip()})
        if not hits:
            status = 'unused'
        elif all('print(' in h['text'] for h in hits):
            status = 'print-only'
        elif all(h['test'] for h in hits):
            status = 'test-only'
        else:
            status = 'used'
        report[key] = {'status': status, 'table': table,
                       'hits': [{'file': h['file'], 'line': h['line']} for h in hits[:8]]}

    findings = {k: v for k, v in report.items() if v['status'] != 'used'}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        counts = {}
        for v in report.values():
            counts[v['status']] = counts.get(v['status'], 0) + 1
        print(f"keys={len(report)} used={counts.get('used', 0)} "
              f"unused={counts.get('unused', 0)} print-only={counts.get('print-only', 0)} "
              f"test-only={counts.get('test-only', 0)} empty={counts.get('empty', 0)}")
        for status, title in (
            ('unused', 'UNUSED — zero references in any .swift'),
            ('print-only', 'PRINT-ONLY — every reference is inside print(...)'),
            ('test-only', 'TEST-ONLY — referenced only from test/preview/fixture code'),
            ('empty', 'EMPTY KEY — table junk'),
        ):
            items = [(k, v) for k, v in sorted(report.items()) if v['status'] == status]
            if not items:
                continue
            print(f'\n== {title} ({len(items)}) ==')
            for k, v in items:
                loc = f"   [{v['table']}]" if v['table'] else ''
                print(f'  • {k!r}{loc}')
                for h in v['hits'][:3]:
                    print(f'      {h["file"]}:{h["line"]}')
        if not findings:
            print('\nAll keys referenced ✅')

    sys.exit(1 if (args.strict and findings) else 0)


if __name__ == '__main__':
    main()
