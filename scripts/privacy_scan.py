from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NAME_MARKER = "总档案"
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "private absolute path": re.compile(
        r"[A-Za-z]:\\Users\\[^\\\s]+\\(?:Documents|Desktop)\\"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Chinese identity number": re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    "mainland mobile number": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT
    )
    paths = []
    for raw in output.decode("utf-8").split("\0"):
        if not raw:
            continue
        path = ROOT / raw
        if PRIVATE_NAME_MARKER in path.name or "work" in path.relative_to(ROOT).parts:
            continue
        if path.is_file():
            paths.append(path)
    return paths


def main() -> int:
    failures: list[str] = []
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode(
        "utf-8"
    )
    for name in tracked.split("\0"):
        if PRIVATE_NAME_MARKER in Path(name).name:
            failures.append("a private archive path is tracked by Git")
    for path in tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                failures.append(f"{path.relative_to(ROOT)}: {label}")
    if failures:
        print("Privacy scan failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Privacy scan passed for {len(tracked_files())} eligible files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
