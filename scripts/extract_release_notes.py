#!/usr/bin/env python3
"""从 CHANGELOG.md 提取当前版本的发布说明。

用法：
    python3 scripts/extract_release_notes.py <版本号，可带 v 前缀>

只提取 `## vX.Y.Z` 到下一个 `## ` 之间的内容（不含标题行），
供 GitHub Release 的 body 使用。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: extract_release_notes.py <版本号>", file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("v").strip()
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        print("⚠️  CHANGELOG.md 不存在", file=sys.stderr)
        return 1

    text = changelog.read_text(encoding="utf-8")
    # Match "## vX.Y.Z" headers (with optional leading 'v').
    pattern = re.compile(r"^##\s+v?([0-9]+\.[0-9]+\.[0-9]+)\b", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1) == version:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip("\n")
            print(body)
            return 0
    print(f"⚠️  未在 CHANGELOG.md 找到版本 v{version}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
