"""Repository invariants that are easy to break and cheap to check.

Covers the rules in ``AGENTS.md`` section 1: ``src/`` is plain ASCII English, every public
page under ``docs/`` has a Chinese mirror, public docs never link into ``internal/``, and
Markdown links actually resolve.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MD_LINK = re.compile(r"\]\(([^)#][^)]*)\)")
INTERNAL_LINK = re.compile(r"\]\(([^)]*internal[^)]*)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")
REPO_PREFIX = "https://github.com/xmyfun/python-carddav/blob/main/"


def _public_pages() -> list[Path]:
    pages = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
    return pages + sorted((ROOT / "docs").glob("*.md"))


def test_source_is_ascii_english() -> None:
    """``src/`` must be plain ASCII: no CJK, and no typographic symbols such as ``§``."""
    offenders: dict[str, list[str]] = {}
    for path in sorted((ROOT / "src" / "carddav").glob("*.py")):
        odd = sorted({ch for ch in path.read_text(encoding="utf-8") if ord(ch) > 127})
        if odd:
            offenders[path.name] = odd[:5]
    assert not offenders, f"non-ASCII characters in src/: {offenders}"


def test_every_public_doc_has_a_chinese_mirror() -> None:
    docs = ROOT / "docs"
    english = {p for p in docs.glob("*.md") if not p.name.endswith(".zh-CN.md")}
    chinese = set(docs.glob("*.zh-CN.md"))
    expected = {p.with_name(p.name[:-3] + ".zh-CN.md") for p in english}
    assert english, "docs/ has no English pages"
    assert expected == chinese, (
        f"missing mirrors: {sorted(p.name for p in expected - chinese)}; "
        f"orphans: {sorted(p.name for p in chinese - expected)}"
    )


def test_docs_has_no_index_page() -> None:
    """The index lives in the root README; a ``docs/README.md`` would duplicate it."""
    for name in ("README.md", "README.zh-CN.md"):
        assert not (ROOT / "docs" / name).exists(), f"docs/{name} duplicates the root README"


def test_public_docs_do_not_link_into_internal() -> None:
    """``internal/`` is not public; a link from public docs would be a dead end."""
    offenders = [
        f"{page.name} -> {match.group(1)}"
        for page in _public_pages()
        for match in INTERNAL_LINK.finditer(page.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"public docs link into internal/: {offenders}"


def test_relative_markdown_links_resolve() -> None:
    pages = _public_pages() + sorted((ROOT / "internal").glob("*.md"))
    broken: list[str] = []
    for page in pages:
        for match in MD_LINK.finditer(page.read_text(encoding="utf-8")):
            target = match.group(1).split("#")[0].strip()
            if not target or target.startswith(SKIP_PREFIXES):
                continue
            if not (page.parent / target).exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    assert not broken, f"broken relative links: {broken}"


def test_github_links_point_at_existing_files() -> None:
    """README links are absolute (PyPI cannot resolve relative ones) - keep them honest."""
    broken: list[str] = []
    for page in _public_pages():
        for match in MD_LINK.finditer(page.read_text(encoding="utf-8")):
            url = match.group(1)
            if not url.startswith(REPO_PREFIX):
                continue
            relative = unquote(url[len(REPO_PREFIX) :].split("#")[0])
            if not (ROOT / relative).exists():
                broken.append(f"{page.name} -> {relative}")
    assert not broken, f"GitHub links to missing files: {broken}"
