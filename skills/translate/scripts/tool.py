#!/usr/bin/env python3
"""
l10n/tool.py — Localization tool supporting both .strings and .xcstrings formats.

Auto-detects project format on first run.

Usage:
  python3 l10n/tool.py status                      # 各语言翻译覆盖率
  python3 l10n/tool.py missing <lang>              # 输出某语言缺失的 key（JSON）
  python3 l10n/tool.py inject <lang> <json_file>   # 将翻译注入资源文件
  python3 l10n/tool.py export <lang>               # 导出某语言已有翻译（JSON）
  python3 l10n/tool.py lint                        # 检查 key 是否为合法英文标识符
  python3 l10n/tool.py init                        # xcstrings 模式：生成 config.json
"""
import json
import re
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format():
    """Return 'xcstrings' or 'strings' based on what the project contains."""
    xcstrings = [
        p for p in PROJECT_ROOT.rglob("*.xcstrings")
        if ".build" not in p.parts and "DerivedData" not in p.parts
    ]
    if xcstrings:
        return "xcstrings"

    lproj_strings = list(PROJECT_ROOT.rglob("*.lproj/Localizable.strings"))
    if lproj_strings:
        return "strings"

    return None


# ---------------------------------------------------------------------------
# .strings backend
# ---------------------------------------------------------------------------

def _parse_strings_file(path):
    """Return {key: value} dict from a .strings file."""
    pairs = {}
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return pairs
    for m in re.finditer(
        r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;',
        content,
    ):
        pairs[m.group(1)] = m.group(2)
    return pairs


def _strings_find_lproj():
    """Return {lang: Path} for all *.lproj dirs that contain Localizable.strings."""
    result = {}
    for p in PROJECT_ROOT.rglob("*.lproj"):
        if not p.is_dir():
            continue
        if ".build" in p.parts or "DerivedData" in p.parts:
            continue
        strings_file = p / "Localizable.strings"
        if strings_file.exists():
            lang = p.name.replace(".lproj", "")
            result[lang] = strings_file
    return result


def strings_status():
    lproj = _strings_find_lproj()
    source_lang = "en"
    if source_lang not in lproj:
        print(f"Error: {source_lang}.lproj/Localizable.strings not found.")
        sys.exit(1)

    en_keys = set(_parse_strings_file(lproj[source_lang]).keys())
    total = len(en_keys)
    langs = sorted(k for k in lproj if k != source_lang)

    print(f"Source ({source_lang}): {total} keys\n")
    print(f"{'Lang':<14} {'Keys':>6} {'Missing':>8} {'Coverage':>10}")
    print("-" * 44)
    all_ok = True
    for lang in langs:
        lang_keys = set(_parse_strings_file(lproj[lang]).keys())
        missing = len(en_keys - lang_keys)
        coverage = len(lang_keys) / total * 100 if total else 0
        mark = " ✓" if missing == 0 else f" ({missing} missing)"
        if missing:
            all_ok = False
        print(f"{lang:<14} {len(lang_keys):>6} {missing:>8} {coverage:>9.1f}%{mark}")
    print()
    if all_ok:
        print("All languages fully covered.")


def strings_missing(lang):
    lproj = _strings_find_lproj()
    source_lang = "en"
    if source_lang not in lproj:
        print(f"Error: {source_lang}.lproj/Localizable.strings not found.")
        sys.exit(1)
    if lang not in lproj:
        print(f"Error: {lang}.lproj/Localizable.strings not found.")
        sys.exit(1)

    en_pairs = _parse_strings_file(lproj[source_lang])
    lang_keys = set(_parse_strings_file(lproj[lang]).keys())
    result = {k: v for k, v in en_pairs.items() if k not in lang_keys}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def strings_inject(lang, json_path):
    lproj = _strings_find_lproj()
    if lang not in lproj:
        print(f"Error: {lang}.lproj/Localizable.strings not found.")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        trans = json.load(f)

    strings_path = lproj[lang]
    existing = set(_parse_strings_file(strings_path).keys())

    new_entries = {k: v for k, v in trans.items() if k not in existing}
    if not new_entries:
        print(f"{lang}: nothing to inject (all keys already present).")
        return

    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines = [f'"{esc(k)}" = "{esc(v)}";' for k, v in new_entries.items()]
    block = "\n// Injected by l10n/tool.py\n" + "\n".join(lines) + "\n"
    with open(strings_path, "a", encoding="utf-8") as f:
        f.write(block)

    print(f"{lang}: injected {len(new_entries)} keys, skipped {len(existing & set(trans.keys()))}.")


def strings_export(lang):
    lproj = _strings_find_lproj()
    if lang not in lproj:
        print(f"Error: {lang}.lproj/Localizable.strings not found.")
        sys.exit(1)
    result = _parse_strings_file(lproj[lang])
    print(json.dumps(result, ensure_ascii=False, indent=2))


def strings_lint():
    lproj = _strings_find_lproj()
    source_lang = "en"
    if source_lang not in lproj:
        print(f"Error: {source_lang}.lproj/Localizable.strings not found.")
        sys.exit(1)

    pattern = re.compile(r'^[a-z][a-z0-9_.]*$')
    en_keys = _parse_strings_file(lproj[source_lang]).keys()
    bad = [k for k in en_keys if not pattern.match(k)]

    if not bad:
        print("PASS: 所有 key 均为合法英文标识符")
    else:
        print(f"FAIL: 发现 {len(bad)} 个不合规的 key\n")
        for k in bad:
            print(f'  "{k}"')
        sys.exit(1)


# ---------------------------------------------------------------------------
# .xcstrings backend (original logic, unchanged)
# ---------------------------------------------------------------------------

def load_config():
    if not CONFIG_PATH.exists():
        print("config.json not found. Run `python3 l10n/tool.py init` first.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_xcstrings(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_xcstrings(path, data):
    with open(path, "w", encoding="utf-8") as f:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        content = re.sub(r'^(\s*"[^"]+"):', r'\1 :', content, flags=re.MULTILINE)
        f.write(content)
        f.write("\n")


def get_all_languages(config):
    langs = set()
    for file_path in config["files"]:
        data = load_xcstrings(file_path)
        for val in data["strings"].values():
            langs.update(val.get("localizations", {}).keys())
    langs.discard(config.get("source_lang", "en"))
    return sorted(langs)


def xcstrings_status(config):
    files = config["files"]
    all_langs = get_all_languages(config)

    col = 10
    print(f"{'File':<45}", end="")
    for lang in all_langs:
        print(f"{lang:>{col}}", end="")
    print()
    print("-" * (45 + col * len(all_langs)))

    for file_path in files:
        data = load_xcstrings(file_path)
        total = len(data["strings"])
        print(f"{file_path:<45}", end="")
        for lang in all_langs:
            count = sum(
                1 for v in data["strings"].values()
                if lang in v.get("localizations", {})
            )
            cell = f"{count}/{total}"
            mark = "" if count == total else " !"
            print(f"{cell+mark:>{col}}", end="")
        print()


def xcstrings_inject(config, lang, json_path):
    with open(json_path, encoding="utf-8") as f:
        trans = json.load(f)

    for file_path in config["files"]:
        data = load_xcstrings(file_path)
        added = skipped = missing = 0
        for key, val in data["strings"].items():
            locs = val.setdefault("localizations", {})
            if lang in locs:
                skipped += 1
            elif key in trans:
                locs[lang] = {
                    "stringUnit": {"state": "translated", "value": trans[key]}
                }
                added += 1
            else:
                missing += 1
        save_xcstrings(file_path, data)
        print(f"{file_path}: added={added}, skipped={skipped}, missing={missing}")


def xcstrings_missing(config, lang):
    source = config.get("source_lang", "en")
    result = {}
    for file_path in config["files"]:
        data = load_xcstrings(file_path)
        for key, val in data["strings"].items():
            locs = val.get("localizations", {})
            if lang not in locs:
                en_val = locs.get(source, {}).get("stringUnit", {}).get("value", "")
                result[key] = en_val
    print(json.dumps(result, ensure_ascii=False, indent=2))


def xcstrings_export(config, lang):
    result = {}
    for file_path in config["files"]:
        data = load_xcstrings(file_path)
        for key, val in data["strings"].items():
            locs = val.get("localizations", {})
            if lang in locs:
                result[key] = locs[lang]["stringUnit"]["value"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


def xcstrings_lint(config):
    pattern = re.compile(r'^[a-z][a-z0-9_.]*$')
    bad_keys = []
    for file_path in config["files"]:
        data = load_xcstrings(file_path)
        for key in data["strings"]:
            if not pattern.match(key):
                bad_keys.append((file_path, key))

    if not bad_keys:
        print("PASS: 所有 key 均为合法英文标识符")
    else:
        print(f"FAIL: 发现 {len(bad_keys)} 个不合规的 key\n")
        for file_path, key in bad_keys:
            print(f'  {file_path}: "{key}"')
        sys.exit(1)


def cmd_init():
    found = sorted(
        str(p.relative_to(PROJECT_ROOT))
        for p in PROJECT_ROOT.rglob("*.xcstrings")
        if ".build" not in p.parts and "DerivedData" not in p.parts
    )
    if not found:
        print("未找到任何 .xcstrings 文件，请确认在正确的项目目录下运行。")
        sys.exit(1)

    if CONFIG_PATH.exists():
        print(f"config.json 已存在，跳过初始化。如需重新初始化请先删除 {CONFIG_PATH}")
        return

    config = {"source_lang": "en", "files": found}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("已生成 l10n/config.json：")
    for p in found:
        print(f"  {p}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
        return

    fmt = detect_format()

    if fmt is None:
        print("Error: no .xcstrings or .lproj/Localizable.strings files found.")
        sys.exit(1)

    if fmt == "strings":
        if cmd == "status":
            strings_status()
        elif cmd == "missing" and len(sys.argv) == 3:
            strings_missing(sys.argv[2])
        elif cmd == "inject" and len(sys.argv) == 4:
            strings_inject(sys.argv[2], sys.argv[3])
        elif cmd == "export" and len(sys.argv) == 3:
            strings_export(sys.argv[2])
        elif cmd == "lint":
            strings_lint()
        else:
            print(f"Unknown command or wrong arguments: {sys.argv[1:]}")
            print(__doc__)
            sys.exit(1)

    else:  # xcstrings
        config = load_config()
        if cmd == "status":
            xcstrings_status(config)
        elif cmd == "missing" and len(sys.argv) == 3:
            xcstrings_missing(config, sys.argv[2])
        elif cmd == "inject" and len(sys.argv) == 4:
            xcstrings_inject(config, sys.argv[2], sys.argv[3])
        elif cmd == "export" and len(sys.argv) == 3:
            xcstrings_export(config, sys.argv[2])
        elif cmd == "lint":
            xcstrings_lint(config)
        else:
            print(f"Unknown command or wrong arguments: {sys.argv[1:]}")
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()
