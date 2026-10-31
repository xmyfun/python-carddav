# Server quirks

**English** · [简体中文](quirks.zh-CN.md)

CardDAV is one protocol that behaves like several. This page is organised **by server**, because
that is the order you need when you point the library at a host: find your server, read what it
does differently.

## How to read the labels

Every claim below carries one of three labels. We do not publish a claim without one.

| Label | Meaning |
|---|---|
| **Verified** | Our own live test hit a real server and passed. Date, and where useful the test name, is given. |
| **Spec** | Taken from an RFC. Not something we observed — it is what the protocol requires. |
| **Reported** | Vendor documentation, or another project's compatibility notes. **We did not test it.** Treat it as a lead, not as a fact. |

## Status at a glance

| Server | Version tested | Engine | Auth | Evidence |
|---|---|---|---|---|
| **Radicale** (self-hosted) | **3.9.0** | Radicale | Basic (htpasswd) | **Verified** 2026-10-30, localhost |
| **Synology Contacts** (DSM) | DSM version **not determined** | — | Basic | **Verified** 2026-10-28/29, re-checked 2026-10-30, LAN |
| **Xandikos** | **0.4.10** | Xandikos | none built in | **Verified** 2026-10-30, localhost |
| Nextcloud / ownCloud, incl. Disroot | — | sabre/dav (PHP) | Basic | Reported, untested |
| Baikal | — | sabre/dav | Basic | Reported, untested |
| Google Contacts (**CardDAV endpoint**) | — | Google | OAuth 2.0 bearer only | Vendor docs, untested |
| iCloud | — | Apple | app-specific password | Reported, untested |
| Fastmail | — | Fastmail | app password | Reported, untested |

### Two observations about the Synology box, and what we do *not* claim

On 2026-10-30 we fetched the page the Synology box redirects to and read its body:

- `GET /carddav/.web` returns `200`, `Content-Type: text/plain`, body **`Radicale works!`**
  (15 bytes), served by `Server: nginx`.
- Its `sync-collection` tokens look like `http://radicale.org/ns/sync/27_4745`.

Those are the facts we saw. We did **not** determine which software version the box runs, nor how
it relates to upstream Radicale, so this page claims neither. The Synology box and stock Radicale
get **separate sections** below simply because their measured behaviour differs (§3.1).

## 1. The RFC baseline (spec, not a quirk)

These are what RFC 6352 and its neighbours require. A server that behaves differently is listed
as a quirk further down; a server that behaves this way is simply conforming. Every row cites
its clause.

| Behaviour | Clause | What the library does |
|---|---|---|
| New cards **MUST** be created with `PUT` to an unmapped URI | RFC 6352 §6.3.2 | `put_card(data)` |
| The resource name is "entirely arbitrary" — no required relationship to the UID | §6.3.2 | `put_card` derives `<uid>.vcf` **as a library convention** |
| Pure create **SHOULD** send `If-None-Match: *` | §6.3.2 | `put_card(create_only=True)` |
| Updates **SHOULD** send `If-Match` | §9.2 | `put_card(if_match=...)` |
| `addressbook-multiget` **MUST** use `Depth: 0` | §8.7 | sent for you |
| `addressbook-query` uses `Depth: 1` or `infinity` | §8.6 | `search(xml, depth="1")` |
| The server **MAY** ignore `CARDDAV:limit` | §10.6.1 | never treated as pagination |
| An invalid `sync-token` **SHOULD** give `403` + `DAV:valid-sync-token` | RFC 6578 | `SyncTokenInvalid` only on a real 403 |
| `/.well-known/carddav` redirects to the context path | RFC 6764 §4 | followed manually, see 3.6 |

**`POST` is not part of standard CardDAV.** A `POST` to a collection has no defined meaning in
WebDAV (RFC 4918 §9.5 leaves it to the server); the standardised "server assigns the URL" flow is
RFC 5995's `DAV:add-member`, an optional extension. So a server that rejects `POST` is
**compliant**, not broken.

One library convention worth knowing, since it shows up in your writes: when you omit `href=`,
`put_card` derives `<uid>.vcf`. The UID is **percent-encoded** first (RFC 3986 §2), so `/`
becomes `%2F` and `:` becomes `%3A` — a server-supplied UID can neither escape the collection
nor be parsed as a URI scheme (`urn:uuid:…` would otherwise leave HTTP entirely). Ordinary UUIDs
are unchanged, and `unquote()` round-trips the value.

## 2. Radicale 3.9.0 — **Verified**

Measured 2026-10-30 on `127.0.0.1:5232` with htpasswd auth and a filesystem store. Collections
live under `/<user>/<collection>/`; we created one with `MKCOL` before probing.

### 2.1 Create is `PUT`; `POST` is advertised but not supported

`OPTIONS` on a collection returns an `Allow` header that **does** list `POST`, but `POST` to the
collection returns **`405`**.

→ Advertising a method is not the same as supporting it — probe by doing, not by asking.
Create with `put_card(data)`; add `create_only=True` when overwriting must fail.

### 2.2 The UID is authoritative, and a card without one is rejected

- `PUT` a card with **no** `UID:` → **`400`** (strictly RFC 6352 §5.1).
- `PUT` a card whose body UID disagrees with the file name → **the UID you sent is kept**; nothing
  is rewritten and no second resource appears.

→ Still read back after writing, but on this server what you sent is what is stored.

### 2.3 An unknown `sync-token` gives a real `403`

A token the server does not recognise produces **`403`**, so the library raises
`SyncTokenInvalid` and your fallback path actually fires — unlike the Synology box (§3.3).

Tokens look like `http://radicale.org/ns/sync/<64 hex chars>`. Treat them as opaque.

### 2.4 `CARDDAV:limit` is ignored

`addressbook-query` with `prop-filter name="FN"` + `text-match` works and inlines `address-data`;
adding `<c:limit><c:nresults>1</c:nresults></c:limit>` still returns every match — which RFC
6352 §10.6.1 explicitly permits. → Never use `limit` as pagination; truncate client-side.

### 2.5 Listing gives metadata, not bodies

`PROPFIND Depth: 1` returns href + etag only. → `get_cards()` returns metadata; use `get_card()`
or `multiget()` for bodies.

### 2.6 Paths: no `/carddav`, and the trailing slash does not matter

| Request | Result |
|---|---|
| `GET /.well-known/carddav` | `301` → `/` |
| `GET /carddav` and `GET /carddav/` | `403` — the path does not exist |
| `PROPFIND <collection>` with and without a trailing slash | `207` either way |

→ There is no `/carddav` prefix to hand-build here, and a missing trailing slash on a collection
URL is harmless. (The 405 in §3.6 belongs to the Synology front end, not to Radicale.)

### 2.7 Reported about Radicale, not tested by us

- **Collections cannot be created by the client.** Reported by vdirsyncer. → Create address books
  in the server UI; the library never writes collections.
- **Radicale deliberately does not implement the whole standard.** Reported by vdirsyncer. Basic
  read and write work fine; do not assume exotic features.

### 2.8 Other verified behaviour

`412` on a stale `If-Match`, `multiget`, `DELETE` and `sync-collection` deltas all behave as
documented in §1; discovery, listing, single fetch and `addressbook-query` all passed.

## 3. Synology Contacts (DSM) — **Verified**

Measured on a LAN DSM box, 2026-10-28/29 and re-checked 2026-10-30. Verified: discovery, listing,
single fetch, `multiget`, `PUT` create/update, `412` on a stale `If-Match`, `DELETE`,
`sync-collection` (create / update / delete / idle) and `addressbook-query` with `text-match`.

### 3.1 Where it differs from Radicale 3.9.0

Measured on both, 2026-10-30. These are observed differences, not a statement about lineage:

| Behaviour | Radicale 3.9.0 | Synology Contacts |
|---|---|---|
| `POST` in `Allow` | present (but `POST` → `405`) | **absent** (`POST` → `500`) |
| `PUT` a card with no `UID` | **`400`** | succeeds — UID filled from the file name |
| UID disagreeing with the file name | kept as sent | **rewritten to the file name** |
| Unknown `sync-token` | **`403`** | full listing, no error |
| `sync-token` shape | `…/sync/<64 hex>` | `…/sync/27_4745` |
| `/.well-known/carddav` | `301` → `/` | `302` → `/carddav/` → `.web` |
| `/carddav` path | does not exist (`403`) | exists (`405` without the slash) |

→ Do not carry findings from one box over to the other.

### 3.2 The URL is the identity: the UID follows the file name

**Verified** 2026-10-29, three reproducible experiments; re-checked 2026-10-30.

| What we did | What came back |
|---|---|
| Read a contact created in the Synology UI | `href` last segment is `<uid>.vcf`; the UID is a bare UUID v4, no `urn:uuid:` prefix |
| `PUT` a card with **no** `UID:` to an explicit href | Server added `UID:<file name minus .vcf>` — **not** a UUID |
| `PUT` to an existing href whose body UID disagreed with the file name | Server rewrote the UID to the file name; still exactly one resource in the collection |

→ After any write, read the card back and use the returned `Card.uid` / `Card.href` as your new
baseline. When updating, pass the href you read — do not re-derive it.

### 3.3 An unknown or expired `sync-token` silently returns everything

**Verified** 2026-10-29, re-checked 2026-10-30. A token the server does not recognise produces
**no 403 and no `DAV:valid-sync-token` precondition** — instead a full listing plus a fresh token.
Harmless, but a full listing and a delta have **identical response shapes**, so you cannot tell
them apart from the shape. A usable signal: if any returned entry carries the same etag as your
stored base, this was a full resync.

### 3.4 `CARDDAV:limit` is ignored — as on Radicale (§2.4).

### 3.5 Listing gives metadata, not bodies — as on Radicale (§2.5).

### 3.6 `.well-known` redirects twice, and the trailing slash is mandatory

**Verified** 2026-10-29; re-checked 2026-10-30 with redirect following disabled.

| Request | Result |
|---|---|
| `GET /.well-known/carddav` | `302` → `http://<host>:5000/carddav/` (the normal RFC 6764 hop) |
| `GET /carddav/` | `302` again → `.web` |
| `GET /carddav/.web` | `200`, `text/plain`, body **`Radicale works!`** |
| `GET /carddav` (no slash) | `404` |
| `PROPFIND /carddav` (no slash) | **405** |
| `PROPFIND /carddav/` | `207` |

→ `DAVClient` follows redirects itself and stops at the first hop that looks like a DAV
collection, so bare hostnames work. Do not hand-build `/carddav` paths yourself — one missing
slash is a 405. If an entry URL rejects `PROPFIND`, the library raises `DiscoveryError` with the
status instead of retrying it; a missing trailing slash is the usual cause.

### 3.7 Discovery on a collection answers 401

**Verified** 2026-10-29. Asking an address book collection directly for
`current-user-principal` returns `401`; the library catches this and falls back to treating the
entry URL as the discovery root.

### 3.8 CardDAV only answers on the DSM ports

**Verified** + user report, 2026-10-28. The CardDAV URL is served on the DSM HTTP/HTTPS ports
(default `5000` / `5001`); move DSM to another port and the URL printed by the Contacts app
answers `405`. → Use the default ports.

## 4. Xandikos 0.4.10 — **Verified** (writes fine except through an HTTP proxy)

Measured 2026-10-30 on `127.0.0.1:8081`–`8085`, started with
`xandikos serve --defaults --autocreate -d <dir>`. Xandikos has **no authentication of its own**
(it expects a reverse proxy to do it) and `--defaults` pre-creates `/user/contacts/addressbook/`.

### 4.1 `POST` answers, and `post_card` reconstructs the href

`POST` to the collection returns **`200`** with a `Location` header — but that `Location` is a
**malformed protocol-relative URL**: `//user/contacts/addressbook/<uuid>.vcf`, where the
collection's first path segment (`user`) is treated as the *host*. Resolved naively per RFC 3986
it becomes `http://user/...` (host literally `user`), which does not exist.

`post_card()` detects the host mismatch (the `Location`'s host does not equal the collection's)
and reconstructs a usable absolute href from the collection plus the `Location`'s trailing segment
(`<uuid>.vcf`) — the real resource name. The created card is then retrievable, so **`POST` *is* a
working create path on Xandikos 0.4.10** (verified 2026-10-30). Radicale still answers `405` and
Synology `500`, so `PUT` remains the only create method that works on every server we tested.

### 4.2 Where it is stricter, and where it is looser

| Probe | Xandikos 0.4.10 | Radicale 3.9.0 for comparison |
|---|---|---|
| `PUT` with a fresh UID, no conditional header | `201` | `201` |
| `PUT` with `If-None-Match: *` | **`201`** — `put_card(create_only=True)` works | `201` |
| `PUT` a card with **no** `UID` | **`201`** — accepted, read back has no UID | **`400`** |
| `PUT` a second card re-using an existing UID | **`201`** — no `no-uid-conflict` check | `201` |
| A UID that disagrees with the file name | kept as sent | kept as sent |
| `PUT` update with the current `If-Match` | `204` | `204` |
| `PUT` update with a stale `If-Match` | `412` | `412` |
| **`CARDDAV:limit`** | **honoured** — 3 matches with `nresults=1` returns 1 | ignored |

→ Xandikos is the **only one of the three that honours `CARDDAV:limit`**, and the only one that
accepts a card without a UID. Do not generalise from Radicale here either.

### 4.3 Writes fail when the request goes through an HTTP proxy

**Verified** 2026-10-30. When a client talks to Xandikos through an HTTP proxy it sends an
**absolute-form request target** (`PUT http://host/path`) instead of origin-form (`PUT /path`).
Xandikos's `split_path_preserving_encoding()` takes `request.raw_path` verbatim
(`xandikos/webdav.py:421`) and never strips the scheme and authority, so the container path
resolves to something like `http:/127.0.0.1:8081/user/contacts/addressbook`;
`backend.get_resource()` then returns `None` and the `PUT` is answered with **409**
(`webdav.py:2695`). `DELETE` answers **404** for a resource that does exist.

Three consecutive `PUT`s on one connection, same client, same server:

| Client | Result |
|---|---|
| proxy in use (httpx reads `HTTP_PROXY` by default) | `201, 409, 409` |
| proxy bypassed (`NO_PROXY=*`, or httpx `trust_env=False`) | `201, 201, 201` |

RFC 7230 §5.3 requires a server to accept absolute-form, so this is a conformance gap in
Xandikos; it never appears on a direct connection. Radicale 3.9.0 and the Synology box are
**not** affected — they answered the same proxied requests normally.

→ If your Xandikos host is reached through a proxy, bypass the proxy for it (`NO_PROXY`), or
this library cannot write to it.

### 4.4 Other measured details

- **`PROPFIND` without a `Content-Type` header returns `415`** — Xandikos refuses
  `application/octet-stream` bodies. The library always sends `application/xml`.
- **An invalid `sync-token` returns `412`, not `403`** — so `SyncTokenInvalid` does *not* fire;
  the failure surfaces as `PreconditionFailed`.
- `sync-token` is a bare hex string (e.g. `0fc5d5a009e4b2ef1f0e6a5e1f1c6df4b1e63809`).
- Listing is metadata-only, `multiget` and `addressbook-query` inline `address-data`, and
  `DELETE` returns `204`.

## 5. sabre/dav family: Nextcloud, ownCloud, Baikal — **Reported, untested**

We have no credentials for this family yet, so **everything in this section comes from other
projects' notes, not from our own tests.**

| # | Observation | Source |
|---|---|---|
| 5.1 | `DELETE` may be a **soft delete**: the resource is renamed rather than removed, depending on version and configuration, and may reappear in listings under a different name | Reported (vdirsyncer). Unverified — filtering renamed objects is the caller's job. |
| 5.2 | ownCloud **below 7.0.0** shipped a SabreDAV version with collision and race-condition bugs; fixed upstream and in ownCloud 7.0.0 | Reported (vdirsyncer issue #16) |
| 5.3 | Baikal **up to 0.2.7** used the same old SabreDAV and has the same issue; fixed in later versions | Reported (vdirsyncer issue #160) |

## 6. Google Contacts (CardDAV endpoint) — **Vendor docs, untested**

From Google's own CardDAV documentation (read 2026-10-28/29) plus carddavclient's notes. **We
have never run this library against Google** — there are no credentials for it and no OAuth flow
in the library.

| # | What Google does | Nature |
|---|---|---|
| 6.1 | **Create is `POST`-only** — it does not accept `PUT` to a client-chosen URI | **Deviation from RFC 6352 §6.3.2.** `post_card()` is the compat path, untested against Google. |
| 6.2 | The server **rewrites the UID** when storing a new card | Reported (carddavclient). Read the UID back; it will not be the one you sent. |
| 6.3 | **OAuth 2.0 bearer only**, HTTPS required | Vendor docs. `BearerAuth(token)` takes a token you obtained yourself. |
| 6.4 | Supports GET / PUT / DELETE / OPTIONS / PROPFIND / REPORT; **no** LOCK / UNLOCK, COPY / MOVE, MKCOL, arbitrary WebDAV properties, or ACL (RFC 3744) | Vendor docs |
| 6.5 | vCard 3.0; `sync-token` expires after 29 days; an empty token is rejected with 400; `sync-collection` needs `Depth: 1` | Vendor docs |

Note how three servers differ: Google **replaces** your UID with an internal id, Synology
**aligns** it with the resource name (§3.2), Radicale 3.9.0 **keeps** what you sent (§2.2). All
lead to the same rule — upload is not final state, read it back.

## 7. iCloud — **Reported, untested**

- **App-specific passwords are required**, not the Apple ID password, because two-factor auth
  cannot be done over the DAV APIs. Reported by vdirsyncer.
- **Collection names have a minimum length.** Reported by vdirsyncer.
- We skip our live tests when an iCloud account has zero contacts.

## 8. Fastmail — **Reported, untested**

vdirsyncer reports no known issues with Fastmail.

## 9. Every server — **Reported**

**Partial retrieval is not supported anywhere.** No server implements "give me only some fields",
for either `multiget` or `query`; the author of carddavclient writes that he has not found a
single server that supports it.

→ The library does not implement partial retrieval. Fetch whole vCards.

## Practical checklist

1. Create with `PUT`; use `create_only=True` when overwriting must fail.
2. Update with `put_card(..., href=<the href you read>, if_match=<that etag>)` — not with a
   freshly derived URL.
3. Read back after writing; trust the response, not your request.
4. Key your local state on `UID`, position it on `href`, and treat `href` as opaque.
5. Handle both sync-token failure shapes: a real `403` on Radicale, a full listing on Synology,
   a `412` on Xandikos.
6. `CARDDAV:limit` is ignored by Radicale and Synology — truncate client-side. Xandikos is the
   one server that honours it (§4.2).
7. If a Xandikos host is reached through an HTTP proxy, bypass the proxy for that host — the
   server cannot parse absolute-form request targets and every write fails with `409` (§4.3).
8. Store what the server returned as your sync base, not what you sent.
9. Do not generalise between the three servers — they differ on `POST`, missing UIDs, UID
   rewriting, sync-token errors and `CARDDAV:limit` (§3.1, §4.2).

## Where the evidence lives

The per-server probe transcripts, versions and dates behind the *Verified* rows are kept in the
maintainers' notes inside this repository. This page publishes only the conclusions, so it can be
read without them.
