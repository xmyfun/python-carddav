"""RFC 6352 discovery, listing and reading - identical for every server."""

from __future__ import annotations

import pytest


def test_discover_list_and_read(server) -> None:
    with server.client() as client:
        books = client.get_addressbooks()
        assert isinstance(books, list)
        if not books:
            pytest.skip(f"[{server.id}] no addressbooks discovered")
        book = books[0]
        cards = book.get_cards()
        assert isinstance(cards, list)
        if cards:
            first = book.get_card(cards[0].href)
            assert isinstance(first.data, bytes) and first.data
