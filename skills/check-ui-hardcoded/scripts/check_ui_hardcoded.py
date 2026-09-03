#!/usr/bin/env python3
"""
check_ui_hardcoded.py — Scan Swift files for hardcoded UI strings.

Three-pass pipeline:
  Pass A – Identify localization wrappers (.local, LL(), L(), etc.)
  Pass B – Detect hardcoded string literals in SwiftUI text APIs
  Pass C – Cross-check against .strings / .xcstrings resources

Key insight:
  SwiftUI Text("...") accepts LocalizedStringKey and auto-looks up .strings.
  So Text("Home") is safe IF "Home" exists in the localization table.
  We only flag it when the key is missing from .strings.

Usage:
  python3 l10n/check_ui_hardcoded.py [OPTIONS]

Options:
  --format text|json   Output format (default: text)
  --strict             Exit non-zero if any HIGH/MEDIUM issue found
  --include-tests      Scan test directories too (default: skip)
  --root PATH          Project root directory (default: cwd)
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Pass A: Localization wrapper identification
# ---------------------------------------------------------------------------


@dataclass
class WrapperInfo:
    name: str
    kind: str  # "extension_property" | "free_function"
    is_direct: bool  # body directly calls NSLocalizedString / String(localized:)

    @property
    def is_localizing(self) -> bool:
        return self.is_direct


def pass_a_identify_wrappers(swift_files: List[Path]) -> Dict[str, WrapperInfo]:
    wrappers: Dict[str, WrapperInfo] = {}

    for fpath in swift_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        _scan_extension_properties(content, wrappers)
        _scan_free_functions(content, wrappers)

    return wrappers


def _scan_extension_properties(content: str, wrappers: Dict[str, WrapperInfo]) -> None:
    ext_blocks = re.finditer(
        r"extension\s+String\s*\{",
        content,
    )
    for ext_m in ext_blocks:
        start = ext_m.end()
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        block = content[start : i - 1]

        for prop_m in re.finditer(
            r"var\s+(\w+)\s*:\s*String\s*(?:\{([^}]*)\}|get\s*\{([^}]*)\})",
            block,
            re.DOTALL,
        ):
            prop_name = prop_m.group(1)
            body = prop_m.group(2) or prop_m.group(3) or ""
            is_direct = _body_calls_localization(body)
            wrappers[prop_name] = WrapperInfo(
                name=prop_name,
                kind="extension_property",
                is_direct=is_direct,
            )


def _scan_free_functions(content: str, wrappers: Dict[str, WrapperInfo]) -> None:
    for m in re.finditer(
        r"(?:private\s+|static\s+|public\s+|internal\s+|fileprivate\s+)*"
        r"func\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*String\s*)?\{",
        content,
    ):
        func_name = m.group(1)
        params = m.group(2)
        if "String" not in params:
            continue

        start = m.end()
        depth = 1
        i = start
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        body = content[start : i - 1]

        is_direct = _body_calls_localization(body)
        if is_direct:
            wrappers[func_name] = WrapperInfo(
                name=func_name,
                kind="free_function",
                is_direct=True,
            )


def _body_calls_localization(body: str) -> bool:
    return bool(
        re.search(r"NSLocalizedString\s*\(", body)
        or re.search(r"String\s*\(\s*localized\s*:", body)
        or re.search(r"Bundle\.main\.localizedString", body)
        or re.search(r"NSBundle\.main\.localizedString", body)
    )


# ---------------------------------------------------------------------------
# Pass B: Hardcoded candidate detection
# ---------------------------------------------------------------------------


@dataclass
class HardcodedIssue:
    file: str
    line: int
    api: str
    literal: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    context: str  # "swiftui_auto" | "raw_string"
    key_exists: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "api": self.api,
            "literal": self.literal,
            "severity": self.severity,
            "context": self.context,
            "key_exists": self.key_exists,
        }


# APIs where SwiftUI auto-localizes (LocalizedStringKey)
_SWIFTUI_AUTO_APIS = [
    (r'\bText\s*\(\s*"', "Text"),
    (r'\bButton\s*\(\s*"', "Button"),
    (r'\bLabel\s*\(\s*"', "Label"),
    (r'\bSection\s*\(\s*header:\s*"', "Section"),
    (r'\bSection\s*\(\s*footer:\s*"', "Section"),
    (r'\bSection\s*\(\s*"', "Section"),
    (r'\.navigationTitle\s*\(\s*"', ".navigationTitle"),
    (r'\.navigationBarTitle\s*\(\s*"', ".navigationBarTitle"),
    (r'\.alert\s*\(\s*"', ".alert"),
    (r'\.confirmationDialog\s*\(\s*"', ".confirmationDialog"),
    (r'\.searchable\s*\(\s*text:\s*[^,]+,\s*prompt:\s*"', ".searchable"),
    (r'\bToggle\s*\(\s*"', "Toggle"),
    (r'\bPicker\s*\(\s*"', "Picker"),
    (r'\bDatePicker\s*\(\s*"', "DatePicker"),
]

# Non-SwiftUI string APIs — always raw String, never auto-localized
_RAW_STRING_APIS = [
    (r'\.tabItem\s*\{[^}]*Text\s*\(\s*"', ".tabItem > Text"),
]

# Non-content parameter names inside SwiftUI calls: string literals passed to
# these parameters are identifiers (SF Symbols, asset names, anchors), not
# user-visible text, so they must not be flagged as hardcoded UI copy.
_NON_CONTENT_PARAMS = [
    "systemImage",
    "systemImagePointer",
    "image",  # Label(_, image:) — asset catalog name
    "icon",
    "sfSymbol",
    "bundleImage",
    "imageResource",
]


def _literal_in_non_content_param(line: str, lit: str) -> bool:
    """True if the quoted literal is the argument of an identifier parameter
    (e.g. Label("Title", systemImage: "gear")). Positional first-argument
    content strings never match this."""
    prefix = re.escape(lit)
    for param in _NON_CONTENT_PARAMS:
        if re.search(rf'{param}\s*:\s*"{prefix}"', line):
            return True
    return False


def _swiftui_key_candidates(lit: str) -> List[str]:
    """Return the key variants Xcode may extract for an interpolated literal.
    The format specifier type (e.g. %lld vs %@) depends on the interpolated
    expression's Swift type, which cannot be inferred from the line alone —
    so enumerate both per interpolation (capped for sanity)."""
    interp = re.compile(r"\\\(([^()]*(?:\([^()]*\))*[^()]*)\)")
    matches = list(interp.finditer(lit))
    if not matches:
        return []

    def intish(expr: str) -> bool:
        if re.search(r"\bInt\b|NSInteger", expr):
            return True
        return bool(re.fullmatch(r"\d+", expr.strip()))

    variants: List[str] = []
    combos = min(2 ** len(matches), 16)
    for combo in range(combos):
        parts, pos, k = [], 0, 0
        for m in matches:
            parts.append(lit[pos:m.start()])
            # bit k of combo: 0 -> preferred specifier, 1 -> the other
            prefer_lld = intish(m.group(1))
            use_lld = prefer_lld if not (combo >> k) & 1 else not prefer_lld
            parts.append("%lld" if use_lld else "%@")
            pos = m.end()
            k += 1
        parts.append(lit[pos:])
        candidate = "".join(parts)
        if candidate not in variants:
            variants.append(candidate)
    return variants


def pass_b_detect_hardcoded(
    swift_files: List[Path],
    wrappers: Dict[str, WrapperInfo],
) -> List[HardcodedIssue]:
    issues: List[HardcodedIssue] = []
    known_props = {
        w.name
        for w in wrappers.values()
        if w.is_localizing and w.kind == "extension_property"
    }
    known_funcs = {
        w.name
        for w in wrappers.values()
        if w.is_localizing and w.kind == "free_function"
    }

    for fpath in swift_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        rel_path = str(fpath)

        for lineno, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue

            if _should_skip_line(line):
                continue

            # Check SwiftUI auto-localizing APIs
            for api_re_str, api_name in _SWIFTUI_AUTO_APIS:
                if re.search(api_re_str, line):
                    _check_api_line(
                        line,
                        lineno,
                        rel_path,
                        api_name,
                        "swiftui_auto",
                        known_props,
                        known_funcs,
                        issues,
                    )
                    break

            # Check raw string APIs
            for api_re_str, api_name in _RAW_STRING_APIS:
                if re.search(api_re_str, line):
                    _check_api_line(
                        line,
                        lineno,
                        rel_path,
                        api_name,
                        "raw_string",
                        known_props,
                        known_funcs,
                        issues,
                    )
                    break

    return issues


def _should_skip_line(line: str) -> bool:
    if re.search(r"\b(print|NSLog|os_log|Logger)\s*\(", line):
        return True
    if re.search(r"Text\s*\(\s*verbatim\s*:", line):
        return True
    if re.search(r"NSLocalizedString\s*\(", line):
        return True
    if re.search(r"String\s*\(\s*localized\s*:", line):
        return True
    if "TODO_L10N" in line:
        return True
    return False


def _check_api_line(
    line: str,
    lineno: int,
    rel_path: str,
    api_name: str,
    context: str,
    known_props: Set[str],
    known_funcs: Set[str],
    issues: List[HardcodedIssue],
) -> None:
    literals = _extract_string_literals(line)
    for lit in literals:
        if not lit.strip() or len(lit) <= 1:
            continue

        if _is_localized(line, lit, known_props, known_funcs):
            continue

        if _is_non_ui_literal(lit):
            continue

        if _literal_in_non_content_param(line, lit):
            continue

        issues.append(
            HardcodedIssue(
                file=rel_path,
                line=lineno,
                api=api_name,
                literal=lit,
                severity="HIGH",
                context=context,
            )
        )


def _extract_string_literals(line: str) -> List[str]:
    literals = []
    i = 0
    while i < len(line):
        if line[i] == '"':
            j = i + 1
            while j < len(line):
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == '"':
                    literals.append(line[i + 1 : j])
                    i = j + 1
                    break
                j += 1
            else:
                break
        else:
            i += 1
    return literals


def _is_localized(
    line: str, lit: str, known_props: Set[str], known_funcs: Set[str]
) -> bool:
    # "...".local  or  "...".<known_property>
    for prop in known_props:
        if re.search(rf'"{re.escape(lit)}"\s*\.\s*{re.escape(prop)}\b', line):
            return True

    # LL("...") or L("...")
    for func_name in known_funcs:
        if re.search(
            rf'{re.escape(func_name)}\s*\(\s*"{re.escape(lit)}"',
            line,
        ):
            return True

    # String(format: LL("..."), ...) or String(format: L("..."), ...)
    if re.search(r'String\s*\(\s*format\s*:\s*\w+\s*\(\s*"', line):
        return True

    return False


_SKIP_LITERAL_PATTERNS = [
    re.compile(r"^[a-z][a-zA-Z0-9_]*$"),  # camelCase identifiers
    re.compile(r"^[a-z-]+(\.[a-z-]+)+$"),  # dot.separated.ids
    re.compile(r"^\d+$"),  # pure numbers
    re.compile(r"^[#/\\]"),  # paths / format chars
    re.compile(r"^[a-fA-F0-9]{8,}$"),  # hex strings
    re.compile(r"^https?://"),  # URLs
    re.compile(r"^/"),  # file paths
    re.compile(r"^[a-z_]+$"),  # snake_case identifiers
]


def _is_non_ui_literal(lit: str) -> bool:
    for pat in _SKIP_LITERAL_PATTERNS:
        if pat.match(lit):
            return True
    return False


# ---------------------------------------------------------------------------
# Pass C: Resource cross-check
# ---------------------------------------------------------------------------


def pass_c_cross_check(
    issues: List[HardcodedIssue],
    root: Path,
) -> List[HardcodedIssue]:
    resource_keys = _load_localization_keys(root)

    for issue in issues:
        key_found = issue.literal in resource_keys
        if not key_found and "\\(" in issue.literal:
            # Interpolated literal: Xcode extracts it with printf specifiers
            # in place of interpolations; the specifier type is unknowable
            # from source alone, so accept any candidate variant.
            key_found = any(c in resource_keys for c in _swiftui_key_candidates(issue.literal))

        if issue.context == "swiftui_auto":
            if key_found:
                issue.key_exists = True
                issue.severity = "LOW"
            else:
                issue.key_exists = False
                issue.severity = "HIGH"
        else:
            if key_found:
                issue.key_exists = True
                issue.severity = "MEDIUM"
            else:
                issue.key_exists = False
                issue.severity = "HIGH"

    return [i for i in issues if i.severity != "LOW"]


def _load_localization_keys(root: Path) -> Set[str]:
    keys: Set[str] = set()

    for sp in root.rglob("*.lproj/Localizable.strings"):
        _parse_strings_file(sp, keys)

    for xp in root.rglob("*.xcstrings"):
        _parse_xcstrings_file(xp, keys)

    return keys


def _parse_strings_file(path: Path, keys: Set[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    for m in re.finditer(r'^\s*"((?:[^"\\]|\\.)*)"\s*=', content, re.MULTILINE):
        keys.add(m.group(1))


def _parse_xcstrings_file(path: Path, keys: Set[str]) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return
    for key in data.get("strings", {}):
        keys.add(key)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def find_swift_files(root: Path, include_tests: bool = False) -> List[Path]:
    skip_dirs = {".build", ".swiftpm", "Pods", "DerivedData", ".git", "build"}
    if not include_tests:
        skip_dirs.update({"Tests", "test"})
    files = []
    for p in root.rglob("*.swift"):
        if set(p.relative_to(root).parts) & skip_dirs:
            continue
        files.append(p)
    return sorted(files)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_text_output(
    wrappers: Dict[str, WrapperInfo],
    issues: List[HardcodedIssue],
) -> str:
    lines: List[str] = []

    lines.append("=" * 60)
    lines.append("LOCALIZATION WRAPPERS DETECTED")
    lines.append("=" * 60)
    if wrappers:
        for w in wrappers.values():
            status = "LOCALIZING" if w.is_localizing else "UNKNOWN"
            lines.append(f"  {w.name} ({w.kind}) -> {status}")
    else:
        lines.append("  (none)")
    lines.append("")

    high = sum(1 for i in issues if i.severity == "HIGH")
    medium = sum(1 for i in issues if i.severity == "MEDIUM")
    total = len(issues)

    lines.append("=" * 60)
    lines.append("HARDCODED STRING SCAN RESULTS")
    lines.append("=" * 60)
    lines.append(f"  Total candidates: {total}")
    lines.append(f"  HIGH   (key missing in .strings): {high}")
    lines.append(f"  MEDIUM (key exists, raw call):    {medium}")
    lines.append("")

    if not issues:
        lines.append("  No hardcoded UI strings found. All clear!")
        lines.append("")
        return "\n".join(lines)

    by_file: Dict[str, List[HardcodedIssue]] = {}
    for issue in issues:
        by_file.setdefault(issue.file, []).append(issue)

    for fpath, file_issues in sorted(by_file.items()):
        short = fpath
        lines.append(f"--- {short} ---")
        for issue in sorted(file_issues, key=lambda x: x.line):
            key_note = ""
            if issue.key_exists is True:
                key_note = " [key exists]"
            elif issue.key_exists is False:
                key_note = " [key NOT found]"
            ctx = "auto-l10n" if issue.context == "swiftui_auto" else "raw"
            lines.append(
                f"  L{issue.line:>4}  {issue.severity:<6}  {issue.api:<22}  "
                f'"{issue.literal}"{key_note}  ({ctx})'
            )
        lines.append("")

    return "\n".join(lines)


def format_json_output(
    wrappers: Dict[str, WrapperInfo],
    issues: List[HardcodedIssue],
) -> str:
    high = sum(1 for i in issues if i.severity == "HIGH")
    medium = sum(1 for i in issues if i.severity == "MEDIUM")

    return json.dumps(
        {
            "wrappers": [
                {
                    "name": w.name,
                    "kind": w.kind,
                    "is_localizing": w.is_localizing,
                }
                for w in wrappers.values()
            ],
            "summary": {
                "total": len(issues),
                "high": high,
                "medium": medium,
            },
            "issues": [i.to_dict() for i in issues],
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Swift files for hardcoded UI strings"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    swift_files = find_swift_files(root, include_tests=args.include_tests)
    if not swift_files:
        print("No Swift files found.", file=sys.stderr)
        sys.exit(0)

    wrappers = pass_a_identify_wrappers(swift_files)
    issues = pass_b_detect_hardcoded(swift_files, wrappers)
    issues = pass_c_cross_check(issues, root)

    if args.format == "json":
        print(format_json_output(wrappers, issues))
    else:
        print(format_text_output(wrappers, issues))

    if args.strict:
        if any(i.severity in ("HIGH", "MEDIUM") for i in issues):
            sys.exit(1)


if __name__ == "__main__":
    main()
