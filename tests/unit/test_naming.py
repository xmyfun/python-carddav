"""Unit tests for the filesystem naming rules used by ``carddav export``."""

from __future__ import annotations

from carddav._naming import (
    MAX_NAME_BYTES,
    book_dirname,
    collection_slug,
    href_filename,
    sanitize_component,
    unique_name,
)

SYNOLOGY = "http://192.168.31.9:5000/carddav/bot/8984dcfb-b498-43f4-9e47-286f2d2b5302/"


def test_sanitize_replaces_separators_after_decoding() -> None:
    # %2F must not survive as a literal and must not re-introduce a path level.
    assert sanitize_component("a%2Fb") == "a_b"
    assert sanitize_component("a%5Cb") == "a_b"
    assert sanitize_component("a/b") == "a_b"


def test_sanitize_decodes_utf8_and_strips_illegal_characters() -> None:
    assert sanitize_component("%E5%BC%A0%E4%B8%89") == "张三"
    assert sanitize_component('a<b>c:d"e|f?g*h') == "abcdefgh"
    assert sanitize_component("a\x00b\x1fc\x7fd") == "abcd"


def test_sanitize_strips_dots_and_spaces_and_falls_back() -> None:
    assert sanitize_component("  name.  ") == "name"
    assert sanitize_component("") == "book"
    assert sanitize_component("   ") == "book"
    assert sanitize_component("..") == "book"
    assert sanitize_component("", fallback="") == ""


def test_sanitize_prefixes_windows_reserved_names() -> None:
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("con.txt") == "_con.txt"
    assert sanitize_component("console") == "console"  # only whole names are reserved


def test_collection_slug_is_one_segment_from_the_url() -> None:
    assert collection_slug(SYNOLOGY) == "8984dcfb-b498-43f4-9e47-286f2d2b5302"
    assert collection_slug("https://h/carddav/home/work/") == "work"
    assert collection_slug("https://h/carddav/home/my%20book") == "my book"
    assert collection_slug("https://h/") == "book"  # no segment at all


def test_book_dirname_uses_displayname_only_as_a_readable_prefix() -> None:
    assert book_dirname("", SYNOLOGY) == "8984dcfb-b498-43f4-9e47-286f2d2b5302"
    assert book_dirname("  ", SYNOLOGY) == "8984dcfb-b498-43f4-9e47-286f2d2b5302"
    assert book_dirname("Work", "https://h/x/work/") == "Work(work)"
    # parentheses in the display name are kept; identity is the bracketed slug
    assert book_dirname("我的(旧)通讯录", "https://h/x/contacts/") == "我的(旧)通讯录(contacts)"


def test_book_dirname_stays_within_the_byte_budget() -> None:
    name = book_dirname("名" * 200, "https://h/x/" + "a" * 200 + "/")
    assert len(name.encode("utf-8")) <= MAX_NAME_BYTES
    assert name.endswith(")")
    # the slug (the identity) must survive truncation
    assert name.endswith("(" + "a" * 120 + ")")


def test_href_filename_uses_the_href_basename_and_adds_vcf() -> None:
    assert href_filename("https://h/b/07cd8491-d7e1.vcf") == "07cd8491-d7e1.vcf"
    assert href_filename("https://h/b/My%20Card.vcf") == "My Card.vcf"
    assert href_filename("https://h/b/no-suffix") == "no-suffix.vcf"
    # a trailing slash means "the collection itself", so its segment is used
    assert href_filename("https://h/b/") == "b.vcf"
    assert href_filename("https://h/") == "card.vcf"
    assert href_filename("https://h/b/a%2Fb.vcf") == "a_b.vcf"


def test_unique_name_appends_a_counter_case_insensitively() -> None:
    assert unique_name("a.vcf", set()) == "a.vcf"
    assert unique_name("A.vcf", {"a.vcf"}) == "A-2.vcf"
    assert unique_name("a.vcf", {"a.vcf", "a-2.vcf"}) == "a-3.vcf"
    assert unique_name("plain", {"plain"}) == "plain-2"
