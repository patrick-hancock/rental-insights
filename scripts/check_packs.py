"""C4.T1: check that every runnable markdown pack has every template section.

    python scripts/check_packs.py [path ...]     default: packs/

A path can be a pack file (.md) or a folder; a folder is checked through its PACK.md, or
through every .md in it when there is no PACK.md. packs/TEMPLATE.md is checked like a pack.
Exit 0 when every pack passes, 1 otherwise, 2 when a path does not exist or holds no pack.

Each pack must have the six sections below as '## ' headings, each with some text.
A pack other than TEMPLATE.md must not keep '<...>' placeholders, and no pack may contain
a personal Windows path or an email address (packs are meant to be published).
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SECTIONS = ["Purpose", "Setup", "Prompt", "Sample inputs", "Expected outputs", "How to check"]
PERSONAL = [
    (re.compile(r"[A-Za-z]:\\Users\\", re.I), "a personal Windows path"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "an email address"),
]
PLACEHOLDER = re.compile(r"<[A-Z][^<>\n]{3,}>")


def pack_files(path: Path) -> list[Path]:
    """A file is one pack; a pack folder is its PACK.md (other .md files there are samples).
    The packs/ root holds TEMPLATE.md plus one pack folder per subfolder."""
    if path.is_file():
        return [path]
    if (path / "PACK.md").exists():
        return [path / "PACK.md"]
    files = sorted(path.glob("*.md"))
    for sub in sorted(d for d in path.iterdir() if d.is_dir()):
        files.append(sub / "PACK.md")  # a missing PACK.md is reported as a failure below
    return files


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    problems = []
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    found = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    for name in SECTIONS:
        if name not in found:
            problems.append(f"missing section '## {name}'")
        elif not found[name]:
            problems.append(f"section '## {name}' is empty")
    if path.name != "TEMPLATE.md" and PLACEHOLDER.search(body):
        problems.append(f"template placeholder left in: {PLACEHOLDER.search(body).group(0)[:40]}")
    for pattern, label in PERSONAL:
        if pattern.search(text):
            problems.append(f"contains {label}")
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or [REPO / "packs"]
    files = []
    for t in targets:
        if not t.exists():
            print(f"ERROR {t}: does not exist")
            return 2
        files += pack_files(t)
    if not files:
        print("ERROR: no pack files found")
        return 2
    failed = 0
    for f in files:
        problems = check(f) if f.exists() else ["pack folder has no PACK.md"]
        failed += bool(problems)
        print(f"{'FAIL' if problems else 'OK  '} {f.relative_to(REPO) if f.is_relative_to(REPO) else f}")
        for p in problems:
            print(f"     - {p}")
    print(f"{len(files) - failed} of {len(files)} packs pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
