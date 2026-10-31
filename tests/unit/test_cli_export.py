"""Tests for ``carddav export``: naming, layouts, info.json and CLI behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from carddav import _export
from carddav.card import Card
from carddav.cli import main
from carddav.errors import DAVError


def _vcard(uid: str, name: str) -> bytes:
    return (
        f"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:{uid}\r\nFN:{name}\r\nN:{name};;;;\r\nEND:VCARD\r\n"
    ).encode()


class FakeBook:
    """Duck-typed AddressBook: only what the exporter touches."""

    def __init__(
        self,
        url: str,
        cards: list[Card],
        *,
        display_name: str = "",
        ctag: str | None = None,
        error: DAVError | None = None,
    ) -> None:
        self.url = url
        self.display_name = display_name
        self.ctag = ctag
        self._cards = cards
        self._error = error

    def get_all_cards(self) -> list[Card]:
        if self._error is not None:
            raise self._error
        return self._cards


class FakeClient:
    def __init__(self, books: list[FakeBook]) -> None:
        self._books = books

    def get_addressbooks(self) -> list[FakeBook]:
        return self._books

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _factory(books: list[FakeBook]):
    def make(url: str, **kwargs: object) -> FakeClient:  # noqa: ANN202 - test local
        make.url = url  # type: ignore[attr-defined]
        make.kwargs = kwargs  # type: ignore[attr-defined]
        return FakeClient(books)

    return make


def _card(href: str, uid: str, name: str, etag: str = '"e1"') -> Card:
    return Card(href=href, etag=etag, data=_vcard(uid, name), uid=uid)


BOOK_A = FakeBook(
    "http://h:5000/carddav/bot/8984dcfb-0000/",
    [_card("http://h:5000/carddav/bot/8984dcfb-0000/a.vcf", "ua", "A")],
    ctag="ctag-1",
)
BOOK_B = FakeBook(
    "http://h:5000/carddav/bot/11112222-3333/",
    [
        _card("http://h:5000/carddav/bot/11112222-3333/b%20one.vcf", "ub", "B One"),
        _card("http://h:5000/carddav/bot/11112222-3333/c.vcf", "uc", "C"),
    ],
    display_name="Work",
)


def test_plan_names_folders_from_displayname_and_url_segment() -> None:
    plan = _export.build_plan([BOOK_A, BOOK_B])  # type: ignore[list-item]
    assert [item.name for item in plan] == ["8984dcfb-0000", "Work(11112222-3333)"]
    assert [item.slug for item in plan] == ["8984dcfb-0000", "11112222-3333"]


def test_folders_layout_writes_one_file_per_card_and_an_info_manifest(tmp_path: Path) -> None:
    plan = _export.build_plan([BOOK_A, BOOK_B])  # type: ignore[list-item]
    _export.fetch_cards(plan)
    _export.write(plan, tmp_path, single_file=False)
    info_path = _export.write_info(plan, tmp_path, single_file=False)

    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_bytes().startswith(b"BEGIN:VCARD")
    # percent-decoded, one level deep
    assert (tmp_path / "Work(11112222-3333)" / "b one.vcf").is_file()
    assert (tmp_path / "Work(11112222-3333)" / "c.vcf").is_file()

    info = json.loads(info_path.read_text(encoding="utf-8"))
    assert info["mode"] == "folders"
    first = info["books"][0]
    assert first["href"] == BOOK_A.url
    assert first["dir"] == "8984dcfb-0000"
    assert first["ctag"] == "ctag-1"
    assert first["count"] == 1
    assert first["cards"][0] == {
        "href": "http://h:5000/carddav/bot/8984dcfb-0000/a.vcf",
        "file": "a.vcf",
        "etag": '"e1"',
        "uid": "ua",
    }


def test_single_file_layout_merges_cards_per_address_book(tmp_path: Path) -> None:
    plan = _export.build_plan([BOOK_A, BOOK_B])  # type: ignore[list-item]
    _export.fetch_cards(plan)
    _export.write(plan, tmp_path, single_file=True)
    info = json.loads(_export.write_info(plan, tmp_path, single_file=True).read_text("utf-8"))

    bundle = (tmp_path / "Work(11112222-3333).vcf").read_text(encoding="utf-8")
    assert bundle.count("BEGIN:VCARD") == 2
    assert bundle.count("END:VCARD") == 2
    assert info["mode"] == "single-file"
    assert info["books"][1]["file"] == "Work(11112222-3333).vcf"
    assert info["books"][1]["count"] == 2
    assert "file" not in info["books"][1]["cards"][0]


def test_failed_address_book_is_recorded_but_does_not_block_the_rest(tmp_path: Path) -> None:
    broken = FakeBook("http://h/x/99999999/", [], error=DAVError("boom"))
    plan = _export.build_plan([broken, BOOK_A])  # type: ignore[list-item]
    _export.fetch_cards(plan)
    _export.write(plan, tmp_path, single_file=False)
    info = json.loads(_export.write_info(plan, tmp_path, single_file=False).read_text("utf-8"))

    assert not plan[0].ok
    assert "DAVError: boom" in (plan[0].error or "")
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").is_file()
    assert info["books"][0]["error"].startswith("DAVError")


def test_conflicts_lists_every_existing_target(tmp_path: Path) -> None:
    plan = _export.build_plan([BOOK_A])  # type: ignore[list-item]
    _export.fetch_cards(plan)
    assert _export.conflicts(plan, tmp_path, single_file=False) == []

    _export.write(plan, tmp_path, single_file=False)
    _export.write_info(plan, tmp_path, single_file=False)

    found = _export.conflicts(plan, tmp_path, single_file=False)
    assert (tmp_path / "8984dcfb-0000" / "a.vcf") in found
    assert (tmp_path / "info.json") in found


def test_write_skips_existing_files_but_writes_the_rest(tmp_path: Path) -> None:
    (tmp_path / "8984dcfb-0000").mkdir()
    (tmp_path / "8984dcfb-0000" / "a.vcf").write_text("OLD", encoding="utf-8")
    plan = _export.build_plan([BOOK_A, BOOK_B])  # type: ignore[list-item]
    _export.fetch_cards(plan)

    skipped = _export.write(plan, tmp_path, single_file=False)

    assert skipped == [tmp_path / "8984dcfb-0000" / "a.vcf"]
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_text(encoding="utf-8") == "OLD"
    # the other book was not blocked by the collision
    assert (tmp_path / "Work(11112222-3333)" / "b one.vcf").is_file()


def test_write_overwrite_replaces_existing_files(tmp_path: Path) -> None:
    (tmp_path / "8984dcfb-0000").mkdir()
    (tmp_path / "8984dcfb-0000" / "a.vcf").write_text("OLD", encoding="utf-8")
    plan = _export.build_plan([BOOK_A])  # type: ignore[list-item]
    _export.fetch_cards(plan)

    skipped = _export.write(plan, tmp_path, single_file=False, overwrite=True)

    assert skipped == []
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_bytes().startswith(b"BEGIN:VCARD")


def test_cli_export_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    code = main(
        ["export", "--url", "http://h:5000", "--out-dir", str(out)],
        client_factory=_factory([BOOK_A, BOOK_B]),
    )

    assert code == 0
    assert (out / "8984dcfb-0000" / "a.vcf").is_file()
    assert (out / "info.json").is_file()
    assert "2/2 address books, 3 cards" in capsys.readouterr().out


def test_cli_rejects_a_file_as_out_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    code = main(
        ["export", "--url", "http://h", "--out-dir", str(target)], client_factory=_factory([BOOK_A])
    )
    assert code == 2
    assert "must be a directory" in capsys.readouterr().err


def test_cli_skips_existing_files_and_reports_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "8984dcfb-0000").mkdir()
    (tmp_path / "8984dcfb-0000" / "a.vcf").write_text("OLD", encoding="utf-8")
    foreign = tmp_path / "notes.txt"
    foreign.write_text("mine", encoding="utf-8")

    code = main(
        ["export", "--url", "http://h", "--out-dir", str(tmp_path)],
        client_factory=_factory([BOOK_A, BOOK_B]),
    )

    assert code == 1
    err = capsys.readouterr().err
    assert "already existed and were skipped" in err
    assert "a.vcf" in err
    # untouched files stay untouched, new ones are still written
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_text(encoding="utf-8") == "OLD"
    assert foreign.read_text(encoding="utf-8") == "mine"
    assert (tmp_path / "Work(11112222-3333)" / "c.vcf").is_file()


def test_cli_overwrite_replaces_existing_files(tmp_path: Path) -> None:
    assert (
        main(
            ["export", "--url", "http://h", "--out-dir", str(tmp_path)],
            client_factory=_factory([BOOK_A, BOOK_B]),
        )
        == 0
    )
    (tmp_path / "8984dcfb-0000" / "a.vcf").write_text("OLD", encoding="utf-8")
    foreign = tmp_path / "notes.txt"
    foreign.write_text("mine", encoding="utf-8")

    code = main(
        ["export", "--url", "http://h", "--out-dir", str(tmp_path), "--overwrite"],
        client_factory=_factory([BOOK_A]),
    )

    assert code == 0
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_bytes().startswith(b"BEGIN:VCARD")
    # files of a book that no longer exists are left alone (no deletion any more)
    assert (tmp_path / "Work(11112222-3333)" / "c.vcf").is_file()
    assert foreign.read_text(encoding="utf-8") == "mine"


def test_cli_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    code = main(
        ["export", "--url", "http://h", "--out-dir", str(out), "--dry-run"],
        client_factory=_factory([BOOK_A]),
    )
    assert code == 0
    assert not out.exists()
    assert "dry-run" in capsys.readouterr().out


def test_cli_returns_one_when_an_address_book_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = FakeBook("http://h/x/99999999/", [], error=DAVError("boom"))
    code = main(
        ["export", "--url", "http://h", "--out-dir", str(tmp_path)],
        client_factory=_factory([broken, BOOK_A]),
    )
    assert code == 1
    assert "FAIL" in capsys.readouterr().out
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").is_file()


def test_cli_requires_a_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["export", "--out-dir", str(tmp_path / "out")],
        client_factory=_factory([]),
    )
    assert code == 2
    assert "--url is required" in capsys.readouterr().err


def test_single_file_mode_skips_an_empty_address_book(tmp_path: Path) -> None:
    empty = FakeBook("http://h/x/77777777/", [], display_name="Empty")
    plan = _export.build_plan([empty])  # type: ignore[list-item]
    _export.fetch_cards(plan)
    _export.write(plan, tmp_path, single_file=True)
    info = json.loads(_export.write_info(plan, tmp_path, single_file=True).read_text("utf-8"))

    assert [p.name for p in tmp_path.iterdir()] == ["info.json"]
    assert info["books"][0]["file"] is None
    assert info["books"][0]["count"] == 0


def test_cli_dry_run_reports_existing_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "8984dcfb-0000").mkdir()
    (tmp_path / "8984dcfb-0000" / "a.vcf").write_text("OLD", encoding="utf-8")

    code = main(
        ["export", "--url", "http://h", "--out-dir", str(tmp_path), "--dry-run"],
        client_factory=_factory([BOOK_A]),
    )

    err = capsys.readouterr().err
    assert code == 1
    assert "already exist" in err
    assert (tmp_path / "8984dcfb-0000" / "a.vcf").read_text(encoding="utf-8") == "OLD"
