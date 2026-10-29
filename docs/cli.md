# CLI: `carddav export`

**English** · [简体中文](cli.zh-CN.md)

A thin command ships with the package. Its only implemented subcommand today is `export`
(`import` is still a stub). It performs no field judgement: it discovers, fetches and
writes.

```bash
carddav export --url https://cloud.example.org \
               --user me --password '***' --out-dir ./export
```

## Entry URL

`--url` accepts any of the four shapes described in the main README: a bare host
(`/.well-known/carddav` discovery), a principal URL, an `addressbook-home-set` URL, or one
specific address book. Coarser URLs mean more discovery steps; a direct collection URL
skips discovery.

## Options

| Option | Meaning |
|---|---|
| `--url` | Entry URL (or `CARDDAV_URL`) |
| `--user`, `--username` | Account name (or `CARDDAV_USER`) |
| `--password`, `--passwd` | Password (or `CARDDAV_PASSWORD`; prompted on a TTY) |
| `--out-dir`, `--outdir`, `--out` | Output **directory**; a path to a file is rejected |
| `--single-file`, `--singlefile`, `--single` | One merged `.vcf` per address book instead of one directory per address book |
| `--overwrite` | Replace files that already exist |
| `--dry-run` | Discover and report, write nothing |
| `--insecure` | Skip TLS verification (self-signed NAS certificates; never in production) |
| `--quiet` | Only print errors |

## Output layouts

Default — one directory per address book, one file per card:

```
export/
├── info.json
├── test(8984dcfb-…)/          # "<display name>(<url segment>)"
│   ├── 07cd8491-….vcf         # file name = last segment of the card's href
│   └── carddav-write-proof-….vcf
└── My Contacts(137810dc-…)/
```

`--single-file` — one merged `.vcf` per address book:

```
export/
├── info.json
├── test(8984dcfb-…).vcf
└── My Contacts(137810dc-…).vcf
```

An address book with no cards produces an empty directory in folder mode, and **no file**
in single-file mode (a 0-byte `.vcf` is not a valid vCard).

## Naming rules

- **Identity is the last segment of the collection URL**, percent-decoded and sanitized.
  Under one home-set those segments are unique by definition (WebDAV forbids two sibling
  resources with the same name), so no hash suffix is added.
- **The display name is only a readable prefix.** It may be empty (Synology returns `""`)
  or duplicated; it never affects uniqueness.
- Sanitizing order: percent-decode → `/` and `\` become `_` → strip control characters and
  `< > : " | ? *` → strip trailing dots/spaces → prefix Windows reserved names (`CON`,
  `NUL`, …) with `_` → truncate to 200 UTF-8 bytes without splitting a character.
- Card file names come from the card's `href` last segment, with `.vcf` appended if missing.
- If two names collide after sanitizing (rare), `-2`, `-3`… is appended case-insensitively.

## `info.json`

Written **last**, so a half-finished run never looks complete. It is the only index — do not
infer identity from file names.

```json
{
  "exported_at": "2026-10-29T17:40:00+08:00",
  "client": {"name": "carddav", "version": "0.2.0"},
  "mode": "folders",
  "books": [
    {
      "href": "http://host/carddav/bot/8984dcfb-…/",
      "slug": "8984dcfb-…",
      "display_name": "test",
      "ctag": null,
      "count": 2,
      "dir": "test(8984dcfb-…)",
      "cards": [
        {"href": "http://host/carddav/bot/8984dcfb-…/07cd8491-….vcf",
         "file": "07cd8491-….vcf", "etag": "\"6ed1…\"", "uid": "07cd8491-…"}
      ]
    }
  ]
}
```

In `--single-file` mode the book entry carries `"file": "test(…).vcf"` instead of `"dir"`,
the per-card records have no `file`, and an empty book has `"file": null`. A book that failed
to export carries `"error": "DAVError: …"`.

## Overwrite semantics

There is **no directory-emptiness check** and **no cleanup**. Each output file is judged on
its own:

| Situation | Behaviour |
|---|---|
| Target does not exist | Written |
| Target exists, no `--overwrite` | **Skipped**, listed on stderr, exit code **1**; other files still written |
| Target exists, `--overwrite` | Overwritten in place |
| `--dry-run` with existing targets | Reports them, writes nothing, exit code **1** |

Nothing is ever deleted. Consequence: if a card was removed on the server, its old file
stays on disk. Use a fresh directory when you want a clean mirror.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Everything exported (or dry-run with no conflicts) |
| `1` | At least one address book failed, or at least one file was skipped |
| `2` | Usage error (missing `--url`, `--out-dir` points at a file, …) |

## Security notes

- Prefer `CARDDAV_PASSWORD` over `--password`: command-line arguments are visible in shell
  history and `ps`.
- `--insecure` disables certificate verification; it is meant for a NAS with a self-signed
  certificate on your own LAN.

## Import

`carddav import` is not implemented yet. When it lands, its rules (create vs update,
dry-run by default, never delete) will be documented on this page.
