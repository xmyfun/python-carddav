#!/usr/bin/env python3
"""List the address books discoverable from a CardDAV URL.

Configuration comes from the environment, so the script needs no arguments:

    export CARDDAV_URL=https://cloud.example.org
    export CARDDAV_USER=me
    export CARDDAV_PASSWORD='***'
    python examples/list_books.py
"""

from __future__ import annotations

import argparse
import os
import sys

from carddav import get_davclient
from carddav.errors import DAVError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("CARDDAV_URL"))
    parser.add_argument("--user", default=os.environ.get("CARDDAV_USER"))
    parser.add_argument("--password", default=os.environ.get("CARDDAV_PASSWORD"))
    args = parser.parse_args()

    if not args.url:
        print("error: set CARDDAV_URL or pass --url", file=sys.stderr)
        return 2

    try:
        with get_davclient(args.url, username=args.user, password=args.password) as client:
            books = client.get_addressbooks()
            if not books:
                print("no address books found")
                return 1
            for book in books:
                cards = book.get_cards()
                label = book.display_name or book.url
                print(f"{label}\n  href : {book.url}\n  cards: {len(cards)}")
    except DAVError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
