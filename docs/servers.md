# Server support & quirks

**English** · [简体中文](servers.zh-CN.md)

CardDAV looks like one protocol but behaves like several. This page records what we have
actually verified, what other people report, and the practical rules that follow.

> **Evidence levels.** "Verified" means our own live tests hit a real server and passed.
> "Reported" means vendor documentation or community reports, **not** our test. Nothing in
> this table is a guess dressed up as a fact.

## Status

| Server | Underlying implementation | Auth | Status |
|---|---|---|---|
| **Synology Contacts** (DSM) | Radicale build | Basic | **Verified** (2026-10-29) |
| Radicale (self-hosted) | Radicale | Basic | Reported — same family as Synology |
| Nextcloud / ownCloud, incl. Disroot | sabre/dav (PHP) | Basic | Reported, not yet tested |
| Baikal | sabre/dav | Basic | Reported, not yet tested |
| iCloud | Apple | App-specific password | Reported, not yet tested |
| Google Contacts (**CardDAV endpoint**, not the People API) | Google | OAuth 2.0 bearer only | Reported, not yet tested |
| Fastmail | Fastmail | App password | Reported, not yet tested |
| Xandikos | Xandikos | Basic | Reported, not yet tested |

What "verified" covers on the Synology box: discovery, listing, single fetch, `multiget`,
`PUT` create/update, `412` on stale `If-Match`, `DELETE`, `sync-collection` (create /
update / delete / idle), and `addressbook-query` with `text-match`.

## Known differences that change how you write code

### 1. Creating a card is `PUT`, not `POST`

RFC 6352 §6.3.2 is explicit: new address objects **MUST** be created with `PUT` against an
unmapped URI. `POST`-to-collection is a server-specific extension (RFC 4918 leaves its
meaning to the server), and RFC 5995's standardised "add member" flow needs a
`DAV:add-member` discovery step that this library does not implement.

- Radicale / Synology: `Allow` does not list `POST` at all; a `POST` returns **500**. That
  is compliant — the extension simply is not implemented.
- `post_card()` exists only for servers that assign URLs themselves. **We have not
  verified it against any server yet.**

**Practical rule:** create with `put_card(data)` (URL derived from the UID) or
`put_card(data, href=...)`, and use `create_only=True` when you mean "must not overwrite".

### 2. The resource URL is the identity on Radicale — the `UID` follows the file name

On Synology/Radicale, `PUT` a vCard whose `UID` disagrees with the last URL segment and
the server **rewrites the `UID` to match the file name**. `PUT` a card without a `UID` and
it fills one in from the file name (not a UUID).

**Practical rule:** after any write, read the card back and use the **returned** `Card.uid`
and `Card.href` as your new baseline. Never assume the bytes you sent survived verbatim.

### 3. `href` is not a stable cross-server key

RFC 6352 §6.3.2 says the resource name is "entirely arbitrary". Two servers may store the
same contact under `07cd8491-….vcf` and `card-1.vcf`. Across servers, `UID` is the closest
thing to an identity — but see point 4.

### 4. A v4 UUID carries no information

Synology's UI generates UUID **v4** (random, no timestamp, no MAC, no account hash). So you
cannot sort by UID, infer creation time from it, or use it to recognise "the same person"
on another server.

### 5. Unknown or expired `sync-token` may not raise an error

Radicale answers an unknown token with a **full listing** and a fresh token instead of
`403 valid-sync-token`. The library surfaces whatever the server sent, so a silent full
resync looks like "many changes".

**Practical rule:** treat a response containing entries whose `etag` equals your stored
base etag as a full-resync signal, not as a normal delta.

### 6. `CARDDAV:limit` may be ignored

Radicale accepts `<c:limit><c:nresults>N</c:nresults></c:limit>` and returns everything
anyway. The spec allows this (§10.6.1), so **never use `limit` as a pagination guarantee** —
truncate client-side.

### 7. `Depth` differs between REPORTs

`addressbook-multiget` **MUST** send `Depth: 0` (§8.7); `addressbook-query` uses `1` or
`infinity` (§8.6). Getting this backwards works on lenient servers and fails on strict
ones. The library sends the right value; if you write raw requests yourself, mind the
difference.

### 8. Synology ports and trailing slashes

- The CardDAV URL is only served on the DSM HTTP/HTTPS ports (default `5000` / `5001`). If
  you move DSM to another port, the URL printed by the Contacts app follows it but may
  answer `405`.
- `/carddav` (no trailing slash) returns **405**; `/carddav/` works.
- `/.well-known/carddav` redirects to `/carddav/`, which then redirects **again** to a web
  page (`/carddav/.web`, body `Radicale works!`). The library stops at the first
  collection-looking hop, so bare-host URLs still work.

### 9. `DELETE` may be a soft delete

Nextcloud (sabre/dav) can rename deleted resources instead of removing them, depending on
version and configuration (reported, not verified here). If that happens, "deleted" cards
may still appear in listings under a different name.

### 10. Server-side rewriting causes phantom "pending changes"

Any server-side rewrite (points 2 and 4) means the bytes you get back differ from the bytes
you sent. A sync engine that stores only "what I last sent" will see a permanent diff.
Store **what the server returned** as your base.

## Practical checklist

1. Create with `PUT`; use `create_only=True` when overwriting must fail.
2. Update with `put_card(..., href=<the href you read>, if_match=<that etag>)` — not with a
   freshly derived URL.
3. Read back after writing; trust the response, not your request.
4. Key your local state on `UID`, position it on `href`.
5. Treat a full listing as a possible token-expiry fallback.
6. Never rely on `CARDDAV:limit` for pagination.
7. Don't parse `href` to extract meaning; it is an opaque string.

## Where the evidence lives

Per-server probe transcripts, versions and dates are kept in the maintainers' notes inside
this repository. This page records only the conclusions, so it can be read without them.
