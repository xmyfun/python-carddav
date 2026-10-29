#!/usr/bin/env python3
"""Export every address book to a directory — one file per card.

Uses the same library primitives as the ``carddav export`` command; this script exists to
show the API, not to replace the CLI.

    CARDDAV_URL=... CARDDAV_USER=... CARDDAV_PASSWORD=... \
        python examples/export_book.py --out ./export
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from carddav import get_davclient
from carddav.errors import DAVError


def _safe_name(display_name: str | None, url: str) -> str:
    """Good enough for an example: keep alphanumerics, replace the rest."""
    raw = display_name or url.rstrip("/").rsplit("/", 1)[-1]
    name = "".join(ch if ch.isalnum() or ch in " -_()" else "_" for ch in raw).strip(" .")
    return name or "book"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("CARDDAV_URL"))
    parser.add_argument("--user", default=os.environ.get("CARDDAV_USER"))
    parser.add_argument("--password", default=os.environ.get("CARDDAV_PASSWORD"))
    parser.add_argument("--out", default="export", help="output directory")
    args = parser.parse_args()

    if not args.url:
        print("error: set CARDDAV_URL or pass --url", file=sys.stderr)
        return 2

    out = Path(args.out).expanduser()
    if out.exists() and not out.is_dir():
        print(f"error: --out must be a directory: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    try:
        with get_davclient(args.url, username=args.user, password=args.password) as client:
            for book in client.get_addressbooks():
                target = out / _safe_name(book.display_name, book.url)
                book.export(target, per_card=True)
                count = len(list(target.glob("*.vcf")))
                written += count
                print(f"{target}  ({count} cards)")
    except DAVError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"total: {written} cards in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
