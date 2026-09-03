#!/usr/bin/env python3
"""
check_l10n.py — Apple .strings / .xcstrings localization completeness checker.
Compares all non-base locales against the base locale (en) and reports
missing keys, extra keys, and untranslated values (value == key).
"""

import os
import re
import sys
import json
from collections import defaultdict
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────

def parse_strings_file(path: Path) -> dict[str, str]:
    """Parse a classic .strings file → {key: value}."""
    result = {}
    try:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        print(f"  ⚠️  Cannot read {path}: {e}")
        return result

    # Remove block comments
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    # Remove line comments
    raw = re.sub(r"//[^\n]*", "", raw)

    pattern = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;')
    for m in pattern.finditer(raw):
        key = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        val = m.group(2).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        result[key] = val
    return result


def parse_xcstrings_file(path: Path) -> dict[str, dict[str, str]]:
    """
    Parse a .xcstrings file → {key: {locale: translated_value}}.
    Returns a nested dict so callers can query per-locale.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Cannot parse {path}: {e}")
        return {}

    result: dict[str, dict[str, str]] = {}
    strings = data.get("strings", {})
    for key, entry in strings.items():
        localizations = entry.get("localizations", {})
        result[key] = {}
        for locale, loc_data in localizations.items():
            # stringUnit → simple value
            if "stringUnit" in loc_data:
                result[key][locale] = loc_data["stringUnit"].get("value", "")
            # variations (plural etc.) — just mark as present
            elif "variations" in loc_data:
                result[key][locale] = "__plural__"
    return result


# ── discovery ─────────────────────────────────────────────────────────────────

def find_strings_groups(root: Path):
    """
    Yield (bundle_name, base_locale, {locale: Path}) for every group of
    Localizable.strings files found under root.
    """
    # Map: bundle_dir → {locale: path}
    bundles: dict[Path, dict[str, Path]] = defaultdict(dict)

    for p in root.rglob("*.strings"):
        # Expect structure: <bundle>/<locale>.lproj/<name>.strings
        lproj = p.parent
        if not lproj.name.endswith(".lproj"):
            continue
        locale = lproj.name[: -len(".lproj")]
        bundle = lproj.parent
        # Use filename as sub-key so InfoPlist.strings and Localizable.strings
        # are treated as separate groups.
        group_key = bundle / p.name
        bundles[group_key][locale] = p

    for group_key, locale_map in sorted(bundles.items()):
        bundle_label = f"{group_key.parent.name}/{group_key.name}"
        yield bundle_label, locale_map


def find_xcstrings_files(root: Path):
    """Yield (label, path) for every .xcstrings file found under root."""
    for p in root.rglob("*.xcstrings"):
        yield p.relative_to(root).as_posix(), p


# ── cognate / universal-term detection ───────────────────────────────────────

CJK_LOCALES = {"ja", "ko", "zh-Hans", "zh-HK", "zh-Hant", "zh-TW"}

# Keys listed in l10n/cognate_ok.txt are silently skipped in the value==key check.
# Format: one key per line; lines starting with # are comments.
def load_cognate_ok(root: Path) -> set[str]:
    ok_file = root / "l10n" / "cognate_ok.txt"
    if not ok_file.exists():
        return set()
    lines = ok_file.read_text(encoding="utf-8").splitlines()
    return {line for line in lines if line and not line.startswith("#")}


def classify_unchanged(
    key: str,
    target_locale: str,
    all_locale_data: dict[str, dict[str, str]],
    base_locale: str = "en",
) -> str:
    """
    For a key where value == key in target_locale, return one of:
      'universal'  — skip entirely (abbreviation, brand, or cross-locale consensus)
      'cognate'    — low-confidence warning (same in 1-2 other locales, likely same-root word)
      'missing'    — high-confidence warning (only this locale is unchanged)
    """
    stripped = key.strip()

    # All-caps (or digits+separators only) → abbreviation / label / file-format name
    if stripped and stripped == stripped.upper():
        return "universal"

    other_locales = {
        loc: data
        for loc, data in all_locale_data.items()
        if loc not in (base_locale, target_locale)
    }

    # CJK languages never borrow words verbatim → if CJK also has value==key it's truly universal
    if any(
        data.get(key) == key
        for loc, data in other_locales.items()
        if loc in CJK_LOCALES
    ):
        return "universal"

    # Count other non-base locales where value==key
    same_count = sum(1 for data in other_locales.values() if data.get(key) == key)

    if same_count >= 3:
        return "universal"   # shared across many locales → cognate or brand name
    if same_count >= 1:
        return "cognate"     # 1-2 other locales also unchanged → likely cognate
    return "missing"         # only this locale is unchanged → likely forgotten


# ── report ────────────────────────────────────────────────────────────────────

def check_strings_group(label: str, locale_map: dict[str, Path], base_locale: str = "en", cognate_ok: set[str] | None = None):
    print(f"\n{'═'*60}")
    print(f"  {label}")
    print(f"{'═'*60}")

    if base_locale not in locale_map:
        available = sorted(locale_map)
        print(f"  ⚠️  Base locale '{base_locale}' not found. Available: {available}")
        if not available:
            return
        base_locale = available[0]
        print(f"  → Falling back to '{base_locale}' as base.")

    base_keys = parse_strings_file(locale_map[base_locale])
    base_set = set(base_keys)
    locales = sorted(k for k in locale_map if k != base_locale)

    # Parse all locales upfront so classify_unchanged can do cross-locale checks
    all_locale_data: dict[str, dict[str, str]] = {
        locale: parse_strings_file(locale_map[locale]) for locale in locales
    }
    all_locale_data[base_locale] = base_keys

    print(f"  Base ({base_locale}): {len(base_set)} keys")
    print(f"  Checking: {', '.join(locales)}\n")

    all_ok = True
    for locale in locales:
        loc_keys = all_locale_data[locale]
        loc_set = set(loc_keys)

        missing_keys = base_set - loc_set
        extra_keys = loc_set - base_set

        # Classify each value==key entry
        likely_missing: list[str] = []
        cognates: list[str] = []
        for k in base_set & loc_set:
            if loc_keys[k] == k and k != "":
                if cognate_ok and k in cognate_ok:
                    continue  # explicitly verified as correct
                cls = classify_unchanged(k, locale, all_locale_data, base_locale)
                if cls == "missing":
                    likely_missing.append(k)
                elif cls == "cognate":
                    cognates.append(k)
                # 'universal' → silently skip

        issues = []
        if missing_keys:
            issues.append(f"    ❌ Missing ({len(missing_keys)}) — key absent from file:")
            for k in sorted(missing_keys):
                issues.append(f"       • {k!r}")
        if extra_keys:
            issues.append(f"    ➕ Extra ({len(extra_keys)}) — not in base locale:")
            for k in sorted(extra_keys):
                issues.append(f"       • {k!r}")
        if likely_missing:
            issues.append(f"    ❌ Likely untranslated ({len(likely_missing)}) — value == key, unique to this locale:")
            for k in sorted(likely_missing):
                issues.append(f"       • {k!r}")
        if cognates:
            issues.append(f"    ℹ️  Possible cognate ({len(cognates)}) — also unchanged in 1-2 other locales, verify:")
            for k in sorted(cognates):
                issues.append(f"       • {k!r}")

        if missing_keys or extra_keys or likely_missing:
            all_ok = False
            print(f"  [{locale}] ⚠️")
            print("\n".join(issues))
        elif cognates:
            # cognates-only is informational, not a failure
            print(f"  [{locale}] ✅  {len(loc_set)} keys present")
            print("\n".join(issues))
        else:
            print(f"  [{locale}] ✅  {len(loc_set)} keys, all present")

    if all_ok:
        print("\n  All locales complete ✅")


def check_xcstrings_file(label: str, path: Path, base_locale: str = "en", cognate_ok: set[str] | None = None):
    print(f"\n{'═'*60}")
    print(f"  {label}  (.xcstrings)")
    print(f"{'═'*60}")

    data = parse_xcstrings_file(path)
    if not data:
        return

    # Collect all locales present anywhere
    all_locales: set[str] = set()
    for translations in data.values():
        all_locales.update(translations.keys())

    base_keys = set(data.keys())
    other_locales = sorted(all_locales - {base_locale})

    print(f"  Total keys: {len(base_keys)}")
    print(f"  Locales found: {sorted(all_locales)}\n")

    # Build all_locale_data in the same shape as the .strings checker expects
    xcstrings_locale_data: dict[str, dict[str, str]] = {
        locale: {k: data[k].get(locale, k) for k in base_keys}
        for locale in all_locales
    }

    all_ok = True
    for locale in other_locales:
        missing = [k for k in base_keys if locale not in data[k]]

        likely_missing: list[str] = []
        cognates: list[str] = []
        for k in base_keys:
            if data[k].get(locale) == k:
                if cognate_ok and k in cognate_ok:
                    continue  # explicitly verified as correct
                cls = classify_unchanged(k, locale, xcstrings_locale_data)
                if cls == "missing":
                    likely_missing.append(k)
                elif cls == "cognate":
                    cognates.append(k)

        issues = []
        if missing:
            issues.append(f"    ❌ Missing ({len(missing)}):")
            for k in sorted(missing):
                issues.append(f"       • {k!r}")
        if likely_missing:
            issues.append(f"    ❌ Likely untranslated ({len(likely_missing)}):")
            for k in sorted(likely_missing):
                issues.append(f"       • {k!r}")
        if cognates:
            issues.append(f"    ℹ️  Possible cognate ({len(cognates)}) — verify:")
            for k in sorted(cognates):
                issues.append(f"       • {k!r}")

        if missing or likely_missing:
            all_ok = False
            print(f"  [{locale}] ⚠️")
            print("\n".join(issues))
        elif cognates:
            translated = sum(1 for k in base_keys if locale in data[k])
            print(f"  [{locale}] ✅  {translated}/{len(base_keys)} keys translated")
            print("\n".join(issues))
        else:
            translated = sum(1 for k in base_keys if locale in data[k])
            print(f"  [{locale}] ✅  {translated}/{len(base_keys)} keys translated")

    if all_ok:
        print("\n  All locales complete ✅")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    root = root.resolve()
    print(f"🔍 Scanning: {root}\n")

    found_something = False
    cognate_ok = load_cognate_ok(root)
    if cognate_ok:
        print(f"ℹ️  Loaded {len(cognate_ok)} cognate-ok entries from l10n/cognate_ok.txt\n")

    # .strings files
    for label, locale_map in find_strings_groups(root):
        found_something = True
        check_strings_group(label, locale_map, cognate_ok=cognate_ok)

    # .xcstrings files
    for label, path in find_xcstrings_files(root):
        found_something = True
        check_xcstrings_file(label, path, cognate_ok=cognate_ok)

    if not found_something:
        print("No .strings or .xcstrings files found.")
        sys.exit(1)

    print(f"\n{'─'*60}")
    print("Done.")


if __name__ == "__main__":
    main()
