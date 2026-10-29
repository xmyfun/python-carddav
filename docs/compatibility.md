# Protocol coverage

**English** · [简体中文](compatibility.zh-CN.md)

What this library implements from RFC 6352 (CardDAV), RFC 4918 (WebDAV) and RFC 6578
(WebDAV Sync) — and what it intentionally leaves out.

## Methods and reports

| Capability | Spec | This library |
|---|---|---|
| Discovery: `PROPFIND` → `current-user-principal` → `addressbook-home-set` → collections | RFC 4918, RFC 5397, §7.1.1 | ✅ `get_principal()` / `get_addressbooks()` |
| `.well-known/carddav` (RFC 6764) | SHOULD | ✅ bare-host URL resolution |
| `addressbook-multiget` | §8.7 (**MUST** for servers; `Depth: 0`) | ✅ `multiget()` |
| `addressbook-query` | §8.6 (**MUST** for servers) | ✅ `search(xml, depth=…)` — the XML is sent verbatim |
| `sync-collection` | RFC 6578 | ✅ `get_changes(sync_token)` |
| `GET` one card, including `ETag` | §6.3.2.3 | ✅ `get_card()` |
| `PUT` create / update, `If-Match`, `If-None-Match: *` | §6.3.2, §9.2 | ✅ `put_card(..., if_match=, create_only=, href=)` |
| `DELETE` (optionally with `If-Match`) | RFC 4918, §9.2 | ✅ `delete_card()` |
| `POST` to a collection (server-assigned URL) | **not defined by RFC 6352** | ⚠️ `post_card()` exists as a compatibility path; untested against any server |
| `OPTIONS` / `DAV` capability probing | §6.1 | ❌ not implemented |
| Extended `MKCOL` (create an address book) | §6.3.1 (MAY) | ❌ not implemented — create books in the server UI or your own tooling |
| `PROPPATCH` (rename, description) | RFC 4918 Class 1 | ❌ not implemented |
| `COPY` / `MOVE` | RFC 4918 Class 1 | ❌ not implemented |
| `LOCK` / `UNLOCK` | RFC 4918 Class 2 | ❌ not implemented |
| Partial retrieval (`address-data` + `CARDDAV:prop`) | §8.4 | ❌ not implemented (and effectively unsupported by servers) |
| `CARDDAV:limit` / `nresults` handling | §8.6.1–8.6.2 | ⚠️ you may send it, but servers may ignore it; truncate client-side |

## The client-side "must"

RFC 6352 §3 requires servers to support all of §8; for clients, §9 only prescribes *how to
do it right*, not a checklist of every method. The set a client genuinely needs — and what
this library covers — is: **discovery + `multiget` + `query` + `PUT`/`GET`/`DELETE` +
conditional writes**. Everything above that line is convenience.

## Deliberate omissions

| Omitted | Why |
|---|---|
| vCard parsing | `Card.data` must stay byte-identical to the response; a parser would tempt callers into "helpful" rewrites |
| Field comparison / merge / dedup | Product decisions, not protocol concerns — they belong to the calling app ([sync.md](sync.md)) |
| Local database, index, cache | Would make the library stateful and hide what the server actually did |
| UID generation | The server or the calling app owns identity; the library only reads/writes bytes |
| OAuth 2.0 authorization-code flow | Out of scope: pass a bearer token you already obtained (`BearerAuth`) |
| Async API | Not needed for the documented workloads; the HTTP backend is pluggable, so an async variant can be added later without breaking the sync API |
| Scheduling / free-busy | That is CalDAV, not CardDAV |

## What "not implemented" means

It means *this library does not expose it*. In most cases you can still reach the server
with your own HTTP client — but then you own the protocol details, including the `Depth`
differences and status-code handling described in [servers.md](servers.md).

A broader comparison with `caldav`, including the gaps we chose not to close, is kept in
the maintainers' notes inside this repository.
