"""Optional text comparison and actionlint checks. Does not transform either file."""
import argparse
import difflib
import hashlib
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEFAULT_BEFORE = ROOT.parents[1] / "output/baseline/lijazsalim/simple-maven-app/.github/workflows/simple-maven-app.yml"


def lint(path, binary=None):
    local = ROOT / "tools" / ("actionlint.exe" if os.name == "nt" else "actionlint")
    binary = binary or (str(local) if local.is_file() else shutil.which("actionlint"))
    if not binary:
        return "not-run", "actionlint missing. Install it with setup.ps1 -WithActionlint, or supply --actionlint."
    try:
        result = subprocess.run([str(binary), "-no-color", "-shellcheck=", "-pyflakes=", str(path.resolve())],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        return ("pass" if result.returncode == 0 else "fail"), (result.stdout + result.stderr).strip() or "No errors."
    except (OSError, subprocess.SubprocessError) as exc:
        return "not-run", str(exc)


def make_report(before, after, binary=None):
    before_bytes, after_bytes = before.read_bytes(), after.read_bytes()
    before_text, after_text = before_bytes.decode("utf-8-sig"), after_bytes.decode("utf-8-sig")
    left, right = lint(before, binary), lint(after, binary)
    diff = "".join(difflib.unified_diff(before_text.splitlines(True), after_text.splitlines(True),
                                        fromfile="baseline", tofile="enhanced"))
    # A long enough fence keeps arbitrary workflow/log content inside its code block.
    def block(text, language="text"):
        longest = max((len(part) for part in re.findall(r"`+", text)), default=0)
        fence = "`" * max(3, longest + 1)
        return f"{fence}{language}\n{text.rstrip()}\n{fence}"
    report = "\n\n".join([
        "# Baseline versus enhanced workflow",
        "This script only compares files and runs actionlint. It does not repair workflows or execute builds.",
        f"| Check | Baseline | Enhanced |\n| --- | --- | --- |\n| actionlint | {left[0]} | {right[0]} |",
        "A lint pass checks syntax and expressions, not runtime or source-to-target behavior. ShellCheck/Pyflakes are disabled. GitHub-hosted execution: not run.",
        "## Workflow diff", block(diff or "No differences.", "diff"),
        "## Baseline lint", block(left[1]), "## Enhanced lint", block(right[1]),
        "## Inputs", block(f"Before: {before.resolve()}\nSHA256: {hashlib.sha256(before_bytes).hexdigest()}\nAfter: {after.resolve()}\nSHA256: {hashlib.sha256(after_bytes).hexdigest()}"),
    ]) + "\n"
    return report, left[0], right[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, default=DEFAULT_BEFORE)
    parser.add_argument("--after", type=Path, default=ROOT / "output/enhanced.yml")
    parser.add_argument("--report", type=Path, default=ROOT / "output/comparison.md")
    parser.add_argument("--actionlint", type=Path)
    args = parser.parse_args(argv)
    try:
        output = args.report.resolve()
        if output in {args.before.resolve(), args.after.resolve()}:
            raise ValueError("Report cannot overwrite either workflow.")
        if not output.is_relative_to((ROOT / "output").resolve()):
            raise ValueError("Keep reports under this tool's output/ directory.")
        report, before_status, after_status = make_report(args.before, args.after, args.actionlint)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Baseline lint: {before_status}\nEnhanced lint: {after_status}\nReport: {output}")
        return 2 if "not-run" in (before_status, after_status) else (0 if after_status == "pass" else 1)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
