#!/usr/bin/env python3
"""Poll one address book for changes and remember the sync token between runs.

This is the smallest honest "sync" client: the library only reports what changed, and the
token is persisted here, in the application. Run it twice and watch the second run list
only what changed in between.

    CARDDAV_URL=... CARDDAV_USER=... CARDDAV_PASSWORD=... \
        python examples/watch_changes.py --state .carddav-token.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from carddav import get_davclient
from carddav.errors import DAVError, SyncTokenInvalid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("CARDDAV_URL"))
    parser.add_argument("--user", default=os.environ.get("CARDDAV_USER"))
    parser.add_argument("--password", default=os.environ.get("CARDDAV_PASSWORD"))
    parser.add_argument("--state", default=".carddav-token.json", help="where to keep the token")
    args = parser.parse_args()

    if not args.url:
        print("error: set CARDDAV_URL or pass --url", file=sys.stderr)
        return 2

    state_path = Path(args.state).expanduser()
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    token = state.get("token")

    try:
        with get_davclient(args.url, username=args.user, password=args.password) as client:
            book = client.get_addressbooks()[0]
            try:
                changes, new_token = book.get_changes(sync_token=token)
            except SyncTokenInvalid:
                print("token expired -> falling back to a full listing")
                changes, new_token = book.get_changes(sync_token=None)

            for change in changes:
                mark = "deleted" if change.deleted else "changed"
                print(f"{mark:>8}  {change.href}  etag={change.etag}")

            state["token"] = new_token
            state["href"] = book.url
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            print(f"{len(changes)} change(s); token saved to {state_path}")
    except DAVError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
