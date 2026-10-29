"""Export address books to a directory tree - the engine behind ``carddav export``.

Two layouts, both driven purely by the library's primitives:

``folders``    ``<out>/<name>/<href basename>.vcf`` - one directory per address book
``single-file`` ``<out>/<name>.vcf`` - one bundle per address book

``info.json`` is written **last**, so a half-finished run never looks complete.
It records the ``href`` of every address book and every card, which is the only
reliable identity (``internal/02`` section 1, ``internal/03`` section 5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from ._naming import book_dirname, collection_slug, href_filename, unique_name
from .addressbook import AddressBook
from .card import Card
from .errors import DAVError

INFO_FILENAME = "info.json"
MODE_FOLDERS = "folders"
MODE_SINGLE_FILE = "single-file"


@dataclass
class BookExport:
    """One address book's slot in an export run."""

    book: AddressBook
    name: str
    slug: str
    cards: list[Card] = field(default_factory=list)
    #: File name per card, same order as ``cards`` (folders mode only).
    files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def filename(self) -> str:
        """The ``.vcf`` bundle name used in single-file mode."""
        stem = self.name[:-4] if self.name.casefold().endswith(".vcf") else self.name
        return f"{stem}.vcf"


def build_plan(books: list[AddressBook]) -> list[BookExport]:
    """Assign each address book its directory (or bundle) name."""
    taken: set[str] = set()
    plan: list[BookExport] = []
    for book in books:
        base = book_dirname(book.display_name, book.url)
        name = unique_name(base, taken)
        taken.add(name.casefold())
        plan.append(BookExport(book=book, name=name, slug=collection_slug(book.url)))
    return plan


def fetch_cards(plan: list[BookExport]) -> None:
    """Read every card of every address book; failures are recorded, not raised."""
    for item in plan:
        try:
            item.cards = item.book.get_all_cards()
        except DAVError as exc:
            item.error = f"{type(exc).__name__}: {exc}"


def card_filenames(cards: list[Card]) -> list[str]:
    """File name per card, same order as *cards* (unique case-insensitively)."""
    taken: set[str] = set()
    names: list[str] = []
    for card in cards:
        if not card.data:
            names.append("")
            continue
        name = unique_name(href_filename(card.href), taken)
        taken.add(name.casefold())
        names.append(name)
    return names


def targets(
    plan: list[BookExport], out_dir: Path, *, single_file: bool
) -> list[Path]:
    """Every file an export would write (used for conflict checks and dry runs)."""
    paths: list[Path] = []
    for item in plan:
        if not item.ok:
            continue
        if single_file:
            if item.cards:  # empty address books produce no bundle
                paths.append(out_dir / item.filename)
            continue
        paths.extend(
            out_dir / item.name / name
            for name in card_filenames(item.cards)
            if name
        )
    paths.append(out_dir / INFO_FILENAME)
    return paths


def conflicts(plan: list[BookExport], out_dir: Path, *, single_file: bool) -> list[Path]:
    """Targets that already exist on disk (would be skipped without ``overwrite``)."""
    return [path for path in targets(plan, out_dir, single_file=single_file) if path.exists()]


def write(
    plan: list[BookExport], out_dir: Path, *, single_file: bool, overwrite: bool = False
) -> list[Path]:
    """Write the cards; returns the paths skipped because they already existed."""
    _ensure_dir(out_dir)
    skipped: list[Path] = []
    for item in plan:
        if not item.ok:
            continue
        if single_file:
            # An empty address book gets no bundle: a 0-byte .vcf is not a
            # valid vCard and would confuse naive importers.
            if not item.cards:
                continue
            path = out_dir / item.filename
            if path.exists() and not overwrite:
                skipped.append(path)
                continue
            _write_bundle(path, item.cards)
            continue
        directory = out_dir / item.name
        _ensure_dir(directory)
        item.files = _write_cards(directory, item.cards, overwrite=overwrite, skipped=skipped)
    return skipped


def write_info(
    plan: list[BookExport], out_dir: Path, *, single_file: bool, overwrite: bool = False
) -> Path | None:
    """Write ``info.json``; ``None`` when it exists and *overwrite* is false."""
    path = out_dir / INFO_FILENAME
    if path.exists() and not overwrite:
        return None
    mode = MODE_SINGLE_FILE if single_file else MODE_FOLDERS
    books: list[dict[str, object]] = []
    for item in plan:
        entry: dict[str, object] = {
            "href": item.book.url,
            "slug": item.slug,
            "display_name": item.book.display_name,
            "ctag": item.book.ctag,
            "count": len(item.cards),
        }
        if single_file:
            entry["file"] = item.filename if item.cards else None
        else:
            entry["dir"] = item.name
        if item.error:
            entry["error"] = item.error
        records: list[dict[str, object]] = []
        for index, card in enumerate(item.cards):
            record: dict[str, object] = {
                "href": card.href,
                "etag": card.etag,
                "uid": card.uid,
            }
            if not single_file and index < len(item.files) and item.files[index]:
                record["file"] = item.files[index]
            records.append(record)
        entry["cards"] = records
        books.append(entry)

    payload = {
        "exported_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "client": {"name": "carddav", "version": __version__},
        "mode": mode,
        "books": books,
    }
    path = out_dir / INFO_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _ensure_dir(path: Path) -> None:
    """``mkdir -p`` that is a no-op for an existing directory."""
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)


def _write_cards(
    directory: Path, cards: list[Card], *, overwrite: bool, skipped: list[Path]
) -> list[str]:
    names = card_filenames(cards)
    for card, name in zip(cards, names, strict=True):
        if not name:
            continue
        target = directory / name
        if target.exists() and not overwrite:
            skipped.append(target)
            continue
        target.write_bytes(card.data or b"")
    return names


def _write_bundle(path: Path, cards: list[Card]) -> None:
    with path.open("wb") as handle:
        for card in cards:
            if not card.data:
                continue
            handle.write(card.data)
            if not card.data.endswith(b"\n"):
                handle.write(b"\r\n")
