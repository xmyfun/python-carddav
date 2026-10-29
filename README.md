# carddav

**English** · [简体中文](README.zh-CN.md)

A thin, predictable **CardDAV client library for Python** — the source code of the PyPI package [`carddav`](https://pypi.org/project/carddav/).

> **Status: 0.2.0 — first public release.** Everything below is implemented and exercised against a real server (Synology Contacts / Radicale).

## Why another one?

The existing options are either calendar-only (`caldav` handles CalDAV, not address books), abandoned (`pyCardDAV` is Python 2 only), or buried inside a command-line application (`vdirsyncer`'s CardDAV backend is not an installable library). Checked 2026-10.

## Features

- **Discovery** — `.well-known/carddav` → `current-user-principal` → `addressbook-home-set` → address books
- **Read** — list resources (`href` / `etag`), batch fetch with `addressbook-multiget`, search with `addressbook-query`
- **Incremental sync** — RFC 6578 `sync-collection` with `sync-token`, including the case where the token has expired
- **Write** — `PUT` to create (with `If-None-Match: *`) or update (with `If-Match`), `DELETE`; `POST` kept as a compatibility path for servers that assign URLs
- **Raw access** — `Card.data` returns the **exact bytes** the server sent; nothing is parsed or rewritten
- **Pluggable HTTP** — one runtime dependency (`httpx`); `requests` and custom backends selectable, which also makes mocking trivial
- **Thin CLI** — `carddav export` writes one directory per address book (or one merged `.vcf`), plus an `info.json` index

## What it is not

Deliberately out of scope, because they belong to the caller:

- vCard parsing, field mapping, deduplication, merging, normalization
- a sync engine: no local database, no index, no conflict resolution, no cached state
- UID generation or rewriting
- **the Google People API** — Google Contacts is reachable two ways: the **CardDAV** endpoint (what this library speaks) and the **People REST API** (Google's official Python client is [`google-api-python-client`](https://pypi.org/project/google-api-python-client/)). Only the CardDAV path is implemented here; if you need the People API, use that SDK in your own code — this library neither wraps nor depends on it
- OAuth2 authorization-code flow and token refresh — `BearerAuth(token)` takes a token you already obtained

This is on purpose: a client that "understands" your contacts can no longer tell you what the server actually did.

## Installation

```bash
pip install carddav              # httpx backend (default)
pip install "carddav[requests]"  # optional: requests backend
pip install "carddav[http2]"     # optional: HTTP/2 support
```

Requires Python 3.10+. Note that Python 3.10 is end-of-life upstream, so it is supported on a best-effort basis and the floor will move up together with our dependencies.

> **PyPI release pending.** Until `carddav` lands on PyPI: `pip install git+https://github.com/xmyfun/python-carddav.git`.


## Authentication

| Method | How | Notes |
|---|---|---|
| Basic | `get_davclient(url, username=..., password=...)` | used automatically when `username` is given |
| Digest | `auth=DigestAuth(user, password)` | must be passed explicitly — there is no automatic 401-challenge handling |
| Bearer | `auth=BearerAuth(token)` | for OAuth2-protected endpoints; you obtain and refresh the token |
| Your own | `auth=<backend-native auth object>` | wins over `username` / `password`; it must match the chosen backend (e.g. `httpx.Auth`) |

Not included: OAuth2 authorization-code flow and token refresh, client certificates (mTLS), NTLM / Kerberos.

## HTTP backends

The HTTP stack sits behind a two-method interface (`Backend`: `request()` / `close()`), so it can be swapped or mocked without touching the library:

```python
get_davclient(url, backend="httpx")     # default
get_davclient(url, backend="requests")  # pip install "carddav[requests]"
get_davclient(url, backend=my_fake)     # any object with request()/close()
```

The same seam is what makes offline tests possible — see `tests/test_backend.py`.

## Server URL

The `url` you pass to `get_davclient` can point at **any level** of the CardDAV
hierarchy — the library discovers the address book(s) from there. Coarser URLs
make the library walk more discovery steps; a direct address-book URL skips
discovery entirely. All of them return the same `AddressBook` / `Card` objects.

| Granularity | What it is | Example |
|---|---|---|
| **Bare host** | Just the domain. The library follows RFC 6764 and looks up `/.well-known/carddav` to find the entry point. | `https://cloud.example.org` |
| **Principal URL** | The authenticated user's own root, i.e. the `current-user-principal`. | `https://cloud.example.org/remote.php/dav/principals/users/me/` |
| **Addressbook-home-set URL** | The container that *holds* all of the user's address books. A server may place it on a **different host** — iCloud returns a shard host, which is normal, not an error. | `https://p48-contacts.icloud.com/1437425399/carddavhome/` |
| **A specific address book URL** | One exact address book — discovery is skipped. | `https://p48-contacts.icloud.com/1437425399/carddavhome/card/` |

Discovery itself (well-known → `current-user-principal` → `addressbook-home-set`
→ address books) is done by the library; you never write `PROPFIND` or parse
`href` paths yourself. What is implemented, and what is deliberately not, is listed in [Server support & quirks](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.md).

## Quick start

The API mirrors the shape of [`caldav`](https://github.com/python-caldav/caldav) (`get_*` / `put_card` / `delete_card`), so the two libraries feel the same.

```python
from carddav import get_davclient

with get_davclient(
    url="https://cloud.example.org",
    username="me",
    password="app-password",  # iCloud needs an app-specific password
) as client:  # construction only sets up the connection; get_principal() triggers discovery
    book = client.get_principal().get_addressbooks()[0]

    cards_meta = book.get_cards()  # metadata only: href / etag (uid needs the body)
    for meta in cards_meta:
        print(meta.href, meta.etag)

    card = book.get_card(cards_meta[0].href)  # raw bytes + etag
    print(len(card.data or b""))  # exactly what the server sent
    etag = book.put_card(new_vcf, href=card.href, if_match=card.etag)  # 412 if changed meanwhile
    book.delete_card(card.href, if_match=etag)

    etag = book.put_card(vcf_bytes, create_only=True)  # PUT <uid>.vcf, refuse if it exists
    href = book.post_card(vcf_bytes)  # only for servers that assign URLs (quirk path)

    changes, token = book.get_changes()  # first run: full listing
    changes, token = book.get_changes(sync_token=token)  # afterwards: only changes
    for change in changes:
        print(change.href, change.deleted)

    cards = book.search(query_xml, depth="1")  # addressbook-query, sent verbatim
```

## Examples

Runnable scripts live in [`examples/`](https://github.com/xmyfun/python-carddav/tree/main/examples). They read
`CARDDAV_URL` / `CARDDAV_USER` / `CARDDAV_PASSWORD` from the environment, so they need no
arguments:

```bash
export CARDDAV_URL=https://cloud.example.org CARDDAV_USER=me CARDDAV_PASSWORD='***'

uv run python examples/list_books.py        # address books and card counts
uv run python examples/export_book.py --out ./export
uv run python examples/watch_changes.py    # keeps a sync token in a local file
uv run python examples/search_cards.py --text Alice
```

## Command line

A thin `carddav` command ships with the package. Its only implemented subcommand today
is `export`; it does no field judgement, it just discovers, fetches and writes.

```bash
# one directory per address book, one .vcf per card (the default)
carddav export --url https://cloud.example.org \
               --user me --password '***' --out-dir ./export

# one merged .vcf per address book instead
carddav export --url https://cloud.example.org --user me --out-dir ./export --single-file

# look before you write
carddav export --url https://cloud.example.org --user me --out-dir ./export --dry-run
```

`--url` accepts any of the four entry shapes (bare host, principal, address-book
home-set, or a single collection). Each exported name is
`"<displayname>(<url segment>)"` — the segment is the identity, the display name is
only a readable prefix. Both layouts write an `info.json` recording every address
book's `href` and every card's `href`/`etag`/`uid`. Existing files are **skipped and
reported** (exit code 1) unless you pass `--overwrite`; nothing is ever deleted. Details and the exact
file layout and `info.json` schema: [`docs/cli.md`](https://github.com/xmyfun/python-carddav/blob/main/docs/cli.md).

## Server support

| Server | Auth | Status |
|---|---|---|
| Radicale — incl. **Synology Contacts** | Basic | tested 2026-10-29 |
| Nextcloud / ownCloud (sabre/dav), incl. Disroot | Basic | not yet tested |
| Baikal (sabre/dav) | Basic | not yet tested |
| iCloud | app-specific password | not yet tested |
| Google Contacts (**CardDAV endpoint**, not the People API) | OAuth 2.0 access token supplied by caller | not yet tested (no OAuth flow in the library) |
| Fastmail | app password | not yet tested |

"Status" means verified by our own live tests, not "the protocol should allow it". Radicale/Synology is the reference server today; sabre/dav, iCloud and Google still need credentials. Per-server quirks and the practical rules that follow are in [`docs/quirks.md`](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.md).

## Documentation

| Page | What it covers |
|---|---|
| [Server support & quirks](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.md) | Which servers are verified, what each one does differently, and what is deliberately not implemented |
| [Sync model](https://github.com/xmyfun/python-carddav/blob/main/docs/sync-model.md) | Why there is no sync engine, and what your application must store |
| [CLI reference](https://github.com/xmyfun/python-carddav/blob/main/docs/cli.md) | `carddav export`: output layout, naming, `info.json`, exit codes |
| [Changelog](https://github.com/xmyfun/python-carddav/blob/main/CHANGELOG.md) | Release history |

Every page except the changelog exists in both English and Chinese (`*.zh-CN.md`).

## Contributing

Thanks for taking a look. The scope is deliberately narrow, so the rules below are short —
but the ones marked **non-negotiable** are enforced in review.

### Before you start

- **Bug reports / questions** → [open an issue](https://github.com/xmyfun/python-carddav/issues). Please include the server software and version (`Nextcloud 30`, `iCloud`, …), since CardDAV behaviour differs a lot between implementations.
- **Anything bigger than a typo fix** → open an issue first. API shape and protocol handling are still being decided, and a PR that arrives before the design does usually has to be rewritten.
- **Security issues** → do **not** open an issue; use [GitHub Security Advisories](https://github.com/xmyfun/python-carddav/security/advisories/new).
- **README changes** → `README.md` and [`README.zh-CN.md`](README.zh-CN.md) are mirrors; update **both** in the same PR.

### Development setup

Python 3.10+. Everything runs through [uv](https://docs.astral.sh/uv/):

```bash
uv sync                    # create the venv and install dev dependencies
uv run pytest              # full test suite (offline, no credentials needed)
uv run ruff check .        # lint
uv run ruff format --check .
uv run mypy src
```

The test suite must stay **fully offline**: no real CardDAV server, no credentials, no
environment variables. Real servers are only used for manual smoke tests.

### Non-negotiable rules

These exist because the library has two jobs a "helpful" client would break: report what the
server actually did, and stay small.

1. **No real contact data, ever.** No names, phone numbers, e-mail addresses, or `href`s containing a username — not in tests, fixtures, docstrings or commit messages.
2. **No credentials, ever.** No passwords, app-specific passwords, tokens, or `.env` contents.
3. **Do not parse vCard.** `Card.data` must be the bytes the server returned. `Card.uid` may only scan for the `UID` line (handling folded lines).
4. **No field logic.** Comparison keys, deduplication, merging and normalization belong to the calling application.
5. **Runtime dependencies: `httpx` only.** `requests` (optional backend) and `h2` (HTTP/2) are extras. A new dependency needs a written justification first.
6. **Writes are never retried automatically**, and UIDs are never generated or rewritten implicitly.
7. **All HTTP goes through `Transport.request()`**; only `_backend_httpx.py` / `_backend_requests.py` may import an HTTP library.
8. **Reject XML containing `<!DOCTYPE`** before parsing.
9. **Code comments and docstrings are English only.** Public pages under `docs/` are bilingual; developer notes under `internal/` are Chinese.

### Tests

- Every protocol behaviour needs a test — including failure paths (`401`, `403`, `412`, `507`, expired `sync-token`).
- If you change a request body, assert the **exact bytes** sent. Request bodies are string templates for exactly this reason.
- A bug fix should come with a test that fails before the fix.

### Pull requests

- One logical change per PR; keep refactors separate from behaviour changes.
- Update the relevant page: user-visible facts → `docs/` (English + Chinese); design decisions → the repository's `internal/` notes.
- Commit messages: short imperative subject, then *why* in the body if it is not obvious.

By contributing you agree that your contribution is licensed under Apache-2.0, the license of this project.

> ⚠️ **Never paste real contact data or credentials into an issue.** Redact names, phone numbers, e-mail addresses and any `href` containing your username.

## Security

Please report vulnerabilities **privately** via [GitHub Security Advisories](https://github.com/xmyfun/python-carddav/security/advisories/new) instead of a public issue. Credential leakage and XML parsing issues are treated as security bugs.

## Versioning

This project follows [Semantic Versioning](https://semver.org/). While the version is `0.x`, breaking changes are allowed but always bump the **minor** version and are documented in the [`CHANGELOG`](https://github.com/xmyfun/python-carddav/blob/main/CHANGELOG.md); patch releases never change the public API or raise a dependency floor.

Raising `requires-python` or a runtime dependency floor is treated as a **breaking change** — it can make the library uninstallable for you.

## License

Apache License 2.0 — see [`LICENSE`](https://github.com/xmyfun/python-carddav/blob/main/LICENSE) and [`NOTICE`](https://github.com/xmyfun/python-carddav/blob/main/NOTICE).

## Related projects

- A companion tool for field research, identity matching and address-book merging (private, by the same author) consumes this library. It is **not required**: this library never depends on it.
