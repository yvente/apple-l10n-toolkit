"""Golden tests for apple-l10n-toolkit skill scripts.

Each test runs a skill's bundled script against a committed fixture project
and asserts the classification/finding contract from
references/l10n-audit-specification.md.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

CHECK_L10N = REPO / "skills/check-l10n-apple/scripts/check_l10n.py"
CHECK_UI = REPO / "skills/check-ui-hardcoded/scripts/check_ui_hardcoded.py"
CHECK_UNUSED = REPO / "skills/check-l10n-unused-keys/scripts/check_unused_keys.py"
TOOL = REPO / "skills/translate/scripts/tool.py"


def run(script: Path, *args, root: Path = None) -> subprocess.CompletedProcess:
    """Run a skill script. Audit scripts take the project root as an argument
    (check_ui_hardcoded via --root); translate's tool.py locates the project
    from its own path, so it runs with cwd=project instead."""
    cmd = [sys.executable, str(script)]
    cwd = None
    if root is not None:
        if script.name == "tool.py":      # project located from tool.py's own path
            cwd = root
        elif script == CHECK_UI:
            cmd += ["--root", str(root)]
        else:
            cmd += [str(root)]
    cmd += [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


class UnusedKeysTests(unittest.TestCase):
    """Direction: table -> code."""

    def test_golden_classifications(self):
        proc = run(CHECK_UNUSED, root=FIXTURES / "unused_project")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(
            "keys=7 used=3 unused=1 print-only=1 test-only=1 empty=1", proc.stdout
        )
        self.assertIn("'DeadKey'", proc.stdout)
        self.assertIn("'LogKey'", proc.stdout)
        self.assertIn("'OnlyInTests'", proc.stdout)
        # The three genuinely used keys must NOT appear as findings.
        for line in proc.stdout.splitlines():
            if line.startswith("  •"):
                self.assertNotIn("Plain", line)
                self.assertNotIn("faces", line)
                self.assertNotIn("Saved", line)

    def test_strict_exit_code(self):
        proc = run(CHECK_UNUSED, "--strict", root=FIXTURES / "unused_project")
        self.assertEqual(proc.returncode, 1)

    def test_json_report(self):
        proc = run(CHECK_UNUSED, "--json", root=FIXTURES / "unused_project")
        report = json.loads(proc.stdout)
        self.assertEqual(report["DeadKey"]["status"], "unused")
        self.assertEqual(report["LogKey"]["status"], "print-only")
        self.assertEqual(report["OnlyInTests"]["status"], "test-only")
        self.assertEqual(report[""]["status"], "empty")
        self.assertEqual(report["Plain"]["status"], "used")
        self.assertEqual(report["%lld faces"]["status"], "used")
        self.assertEqual(report["Saved %@"]["status"], "used")


class UiHardcodedTests(unittest.TestCase):
    """Direction: code -> table."""

    EXPECTED_HIGHS = {"Choose Sticker", "Totally Untranslated Title", "Click Me Now"}

    def test_golden_findings(self):
        proc = run(CHECK_UI, root=FIXTURES / "ui_hardcoded_project")
        self.assertIn("HIGH   (key missing in .strings): 3", proc.stdout)
        for literal in self.EXPECTED_HIGHS:
            self.assertIn(f'"{literal}"', proc.stdout)

    def test_no_false_positives(self):
        proc = run(CHECK_UI, root=FIXTURES / "ui_hardcoded_project")
        self.assertNotIn("square.grid.2x2", proc.stdout)      # SF Symbol param
        self.assertNotIn("Face \\(", proc.stdout)             # interpolated, key exists
        self.assertNotIn("items", proc.stdout)                # interpolated, key exists
        self.assertNotIn("Saved \\(", proc.stdout)            # interpolated, key exists

    def test_strict_exit_code(self):
        proc = run(CHECK_UI, "--strict", root=FIXTURES / "ui_hardcoded_project")
        self.assertEqual(proc.returncode, 1)

    def test_clean_project_exit_zero(self):
        proc = run(CHECK_UI, "--strict", root=FIXTURES / "unused_project")
        self.assertEqual(proc.returncode, 0, proc.stdout)


class CompletenessTests(unittest.TestCase):
    """Direction: locale <-> locale."""

    def test_golden_report(self):
        proc = run(CHECK_L10N, root=FIXTURES / "completeness_project")
        self.assertIn("[de] ⚠️", proc.stdout)
        self.assertIn("Missing (1)", proc.stdout)
        self.assertIn("'Later Key'", proc.stdout)
        self.assertIn("Likely untranslated (1)", proc.stdout)
        self.assertIn("'Forgot Me'", proc.stdout)
        # ja is complete; all-caps NASA is universal and never flagged.
        self.assertIn("[ja] ✅", proc.stdout)
        self.assertNotIn("'NASA'", proc.stdout)

    def test_cognate_whitelist_suppresses_untranslated(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            shutil.copytree(FIXTURES / "completeness_project", project)
            l10n = project / "l10n"
            l10n.mkdir()
            (l10n / "cognate_ok.txt").write_text(
                "# verified: same word in German\nForgot Me\n", encoding="utf-8"
            )
            proc = run(CHECK_L10N, root=project)
            self.assertIn("[de] ⚠️", proc.stdout)             # Later Key still missing
            self.assertNotIn("Likely untranslated", proc.stdout)  # Forgot Me whitelisted


class TranslateWorkflowTests(unittest.TestCase):
    """init → missing → inject → missing(empty) round trip."""

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "app"
            shutil.copytree(FIXTURES / "completeness_project", project)
            l10n = project / "l10n"
            l10n.mkdir()
            shutil.copy(TOOL, l10n / "tool.py")

            init = run(l10n / "tool.py", "init", root=project)
            self.assertIn("App.xcstrings", init.stdout)

            missing = run(l10n / "tool.py", "missing", "de", root=project)
            gap = json.loads(missing.stdout)
            self.assertEqual(set(gap), {"Later Key"})

            (l10n / "de.json").write_text(
                json.dumps({"Later Key": "Späterer Schlüssel"}, ensure_ascii=False),
                encoding="utf-8",
            )
            inject = run(l10n / "tool.py", "inject", "de", "l10n/de.json", root=project)
            self.assertIn("added=1", inject.stdout)

            missing = run(l10n / "tool.py", "missing", "de", root=project)
            self.assertEqual(json.loads(missing.stdout), {})


class SkillStructureTests(unittest.TestCase):
    """Every skill is self-contained and its spec copy stays in sync."""

    EXPECTED_SKILLS = {
        "check-l10n-apple",
        "check-ui-hardcoded",
        "check-l10n-unused-keys",
        "check-rtl-apple",
        "translate",
    }

    def test_expected_skill_set(self):
        names = {p.name for p in (REPO / "skills").iterdir() if p.is_dir()}
        self.assertEqual(names, self.EXPECTED_SKILLS)

    def test_each_skill_has_required_parts(self):
        for skill in self.EXPECTED_SKILLS:
            base = REPO / "skills" / skill
            self.assertTrue((base / "SKILL.md").is_file(), skill)
            self.assertTrue((base / "agents" / "openai.yaml").is_file(), skill)
            self.assertTrue(
                (base / "references" / "l10n-audit-specification.md").is_file(),
                skill,
            )

    def test_skill_frontmatter(self):
        for skill in self.EXPECTED_SKILLS:
            text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), skill)
            frontmatter = text.split("---\n")[1]
            self.assertIn(f"name: {skill}", frontmatter)
            self.assertIn("description:", frontmatter)

    def test_spec_copies_in_sync_with_canonical(self):
        canonical = (
            REPO / "references" / "l10n-audit-specification.md"
        ).read_text(encoding="utf-8")
        for skill in self.EXPECTED_SKILLS:
            copy = (
                REPO / "skills" / skill / "references" / "l10n-audit-specification.md"
            ).read_text(encoding="utf-8")
            self.assertEqual(copy, canonical, f"{skill}: spec copy out of sync")


if __name__ == "__main__":
    unittest.main()
