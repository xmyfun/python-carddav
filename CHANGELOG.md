# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-03

First public release of `carddav`, a thin, dependency-light CardDAV client
library for Python.

### Added

- **Discovery** — walk `.well-known/carddav` → `current-user-principal` →
  `addressbook-home-set` → address books, starting from any entry-point URL
  (bare host, principal, home-set, or a single collection).
- **Read** — list resources (`href` / `etag`), batch-fetch with
  `addressbook-multiget`, and search with `addressbook-query`.
- **Incremental sync** — RFC 6578 `sync-collection` with `sync-token`, including
  correct handling of an expired token (re-fetch of the full listing).
- **Write** — `PUT` to create (`If-None-Match: *`) or update (`If-Match`),
  `DELETE`, and `POST` kept as a compatibility path for servers that assign URLs.
- **Raw access** — `Card.data` returns the exact bytes the server sent; nothing
  is parsed or rewritten by the library.
- **Pluggable HTTP** — `httpx` is the only runtime dependency and the default
  backend; `requests` is an optional backend and any object exposing
  `request()` / `close()` can be supplied (which also makes mocking trivial).
- **Authentication** — Basic, Digest (`DigestAuth`), Bearer (`BearerAuth`), and
  backend-native auth objects.
- **Thin CLI** — `carddav export` writes one directory per address book (or one
  merged `.vcf`) plus an `info.json` index; supports `--dry-run`,
  `--overwrite`, and `--single-file`.
- **Dependency policy** — `requires-python >= 3.10` (3.10 is supported on a
  best-effort basis only); `httpx>=0.28.1` is the sole runtime dependency.
- **Offline test suite** — exercises the full API against disposable local
  CardDAV servers (Radicale / Xandikos) with no network or credentials required.

### Notes

- The reference server today is Radicale (including Synology Contacts), verified
  2026-10-29. sabre/dav (Nextcloud / ownCloud / Baikal / Disroot), iCloud,
  Google Contacts (CardDAV endpoint), and Fastmail are implemented but not yet
  verified against live credentials.
- This release is **Alpha** (`Development Status :: 3 - Alpha`). The public API
  and protocol handling may still change; breaking changes bump the minor
  version and are documented here.
