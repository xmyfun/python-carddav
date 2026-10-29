"""Thin CLI (bundled, not part of the import surface).

Subcommands are ``export`` / ``import`` (``internal/02`` section 1). Both are thin shells
over the library and do **no** field judgement. ``import`` is not implemented yet.

``export`` accepts any of the four entry URL shapes - bare host, principal,
addressbook-home-set, or a single address book (``internal/02`` section 12) - and writes
either one directory per address book or one ``.vcf`` bundle per address book.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import _export
from .client import DAVClient, get_davclient
from .errors import DAVError

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

ClientFactory = Callable[..., DAVClient]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carddav", description="CardDAV client (thin CLI)")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser(
        "export",
        help="export address books to a directory",
        description=(
            "Export every address book discoverable from --url. Without --single-file "
            "each address book becomes a directory holding one .vcf per card; with it, "
            "each address book becomes a single merged .vcf."
        ),
    )
    export.add_argument(
        "--url",
        default=os.environ.get("CARDDAV_URL"),
        help="bare host, principal URL, addressbook-home-set URL, or one address book URL",
    )
    export.add_argument(
        "--user",
        "--username",
        dest="username",
        default=os.environ.get("CARDDAV_USER"),
        help="account name (or set CARDDAV_USER)",
    )
    export.add_argument(
        "--password",
        "--passwd",
        dest="password",
        default=None,
        help="password (or set CARDDAV_PASSWORD; prompted on a TTY when omitted)",
    )
    export.add_argument(
        "--out-dir",
        "--outdir",
        "--out",
        dest="out_dir",
        required=True,
        help="existing or new directory; a file path is rejected",
    )
    export.add_argument(
        "--single-file",
        "--singlefile",
        "--single",
        dest="single_file",
        action="store_true",
        help="one merged .vcf per address book instead of one directory per address book",
    )
    export.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite files that already exist in --out-dir (default: skip them and report)",
    )
    export.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="discover and report what would be written, without writing anything",
    )
    export.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (self-signed NAS certificates; never for production)",
    )
    export.add_argument("--quiet", action="store_true", help="only print errors")

    imp = sub.add_parser("import", help="import a VCF directory into an address book")
    imp.add_argument("--url", default=os.environ.get("CARDDAV_URL"))
    imp.add_argument("--user", "--username", dest="username")
    imp.add_argument("--password", "--passwd", dest="password")

    return parser


def main(argv: Sequence[str] | None = None, *, client_factory: ClientFactory | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "export":
        return _cmd_export(args, client_factory or get_davclient)
    print("error: import is not implemented yet", file=sys.stderr)
    return EXIT_USAGE


def _cmd_export(args: argparse.Namespace, factory: ClientFactory) -> int:
    if not args.url:
        return _usage_error("--url is required (or set CARDDAV_URL)")

    out_dir = Path(args.out_dir).expanduser()
    if out_dir.exists() and not out_dir.is_dir():
        return _usage_error(f"--out-dir must be a directory, not a file: {out_dir}")

    password = _resolve_password(args)
    skipped: list[Path] = []
    try:
        with factory(
            args.url,
            username=args.username,
            password=password,
            verify=not args.insecure,
        ) as client:
            books = client.get_addressbooks()
            if not books:
                print("error: no address books found at that URL", file=sys.stderr)
                return EXIT_FAILURE
            plan = _export.build_plan(books)
            _export.fetch_cards(plan)
            _report(
                plan,
                out_dir,
                single_file=args.single_file,
                dry_run=args.dry_run,
                quiet=args.quiet,
                overwrite=args.overwrite,
            )
            if args.dry_run:
                pending = _export.conflicts(plan, out_dir, single_file=args.single_file)
                if pending:
                    _report_skipped(pending, dry_run=True)
                    return EXIT_FAILURE
                return EXIT_OK if all(item.ok for item in plan) else EXIT_FAILURE

            skipped = _export.write(
                plan, out_dir, single_file=args.single_file, overwrite=args.overwrite
            )
            info = _export.write_info(
                plan, out_dir, single_file=args.single_file, overwrite=args.overwrite
            )
            if info is None:
                skipped.append(out_dir / _export.INFO_FILENAME)
            if skipped:
                if not args.quiet:
                    print(f"skipped : {len(skipped)} existing file(s) left untouched")
                _report_skipped(skipped, dry_run=False)
    except DAVError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK if all(item.ok for item in plan) and not skipped else EXIT_FAILURE


def _report(
    plan: list[_export.BookExport],
    out_dir: Path,
    *,
    single_file: bool,
    dry_run: bool,
    quiet: bool,
    overwrite: bool,
) -> None:
    if quiet:
        return
    if single_file:
        mode = "single-file (one .vcf per address book)"
    else:
        mode = "folders (one directory per address book)"
    print(f"out-dir : {out_dir.resolve()}")
    print(f"mode    : {mode}{'  [dry-run: nothing written]' if dry_run else ''}")
    if overwrite:
        print("          overwriting files that already exist")
    total = 0
    for item in plan:
        total += len(item.cards)
        target = item.filename if single_file else f"{item.name}/"
        if item.ok:
            print(f"  ok    {target:<40} {len(item.cards):>4} cards")
        else:
            print(f"  FAIL  {target:<40} {item.error}")
    books_ok = sum(1 for item in plan if item.ok)
    print(f"total   : {books_ok}/{len(plan)} address books, {total} cards")


def _report_skipped(paths: list[Path], *, dry_run: bool) -> None:
    if dry_run:
        print(f"error: {len(paths)} target file(s) already exist:", file=sys.stderr)
    else:
        print(
            f"error: {len(paths)} file(s) already existed and were skipped "
            "(use --overwrite to replace them):",
            file=sys.stderr,
        )
    for path in paths:
        print(f"  {path}", file=sys.stderr)


def _resolve_password(args: argparse.Namespace) -> str | None:
    """``--password`` > ``CARDDAV_PASSWORD`` > TTY prompt > empty (anonymous-friendly)."""
    explicit = args.password
    if isinstance(explicit, str):
        return explicit
    env = os.environ.get("CARDDAV_PASSWORD")
    if env is not None:
        return env
    if args.username and sys.stdin.isatty():
        try:
            return str(getpass.getpass(f"password for {args.username}: "))
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - interactive
            return None
    return None


def _usage_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
