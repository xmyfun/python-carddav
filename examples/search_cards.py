#!/usr/bin/env python3
"""Server-side search with ``addressbook-query`` (RFC 6352 section 8.6).

The query XML is sent verbatim: the library has no filter model, so what you write here is
what the server sees. This example looks for a text fragment in the formatted name (``FN``).

    CARDDAV_URL=... CARDDAV_USER=... CARDDAV_PASSWORD=... \
        python examples/search_cards.py --text Alice
"""

from __future__ import annotations

import argparse
import os
import sys
from xml.sax.saxutils import escape

from carddav import get_davclient
from carddav.errors import DAVError

QUERY = """<?xml version="1.0" encoding="utf-8"?>
<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">
  <d:prop><d:getetag/><c:address-data/></d:prop>
  <c:filter test="anyof">
    <c:prop-filter name="FN">
      <c:text-match collation="i;unicode-casemap" match-type="contains">{text}</c:text-match>
    </c:prop-filter>
  </c:filter>
  <c:limit><c:nresults>{limit}</c:nresults></c:limit>
</c:addressbook-query>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("CARDDAV_URL"))
    parser.add_argument("--user", default=os.environ.get("CARDDAV_USER"))
    parser.add_argument("--password", default=os.environ.get("CARDDAV_PASSWORD"))
    parser.add_argument("--text", required=True, help="substring to look for in FN")
    parser.add_argument("--limit", type=int, default=50, help="hint only: servers may ignore it")
    args = parser.parse_args()

    if not args.url:
        print("error: set CARDDAV_URL or pass --url", file=sys.stderr)
        return 2

    query = QUERY.format(text=escape(args.text), limit=args.limit)
    try:
        with get_davclient(args.url, username=args.user, password=args.password) as client:
            book = client.get_addressbooks()[0]
            cards = book.search(query, depth="1")
            for card in cards:
                print(f"{card.uid or '?':<40} {card.href}")
            print(f"{len(cards)} match(es)")
    except DAVError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
