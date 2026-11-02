# 命令行：`carddav export`

[English](cli.md) · **简体中文**

包内自带一个薄命令。目前只实现了 `export` 子命令（`import` 仍是骨架）。它不做任何字段判断：
只负责发现、取回、落盘。

```bash
carddav export --url https://cloud.example.org \
               --user me --password '***' --out-dir ./export
```

## 入口 URL

`--url` 接受主 README 里说的四种形态：裸域名（走 `/.well-known/carddav` 发现）、principal URL、
`addressbook-home-set` URL，或某一本具体地址簿。URL 越粗，发现步骤越多；直接给集合 URL 则跳过发现。

## 参数

| 参数 | 含义 |
|---|---|
| `--url` | 入口 URL（或环境变量 `CARDDAV_URL`） |
| `--user`、`--username` | 账号（或 `CARDDAV_USER`） |
| `--password`、`--passwd` | 密码（或 `CARDDAV_PASSWORD`；在 TTY 下会提示输入） |
| `--out-dir`、`--outdir`、`--out` | 输出**目录**；给到文件会被拒绝 |
| `--single-file`、`--singlefile`、`--single` | 每本通讯录一个合并的 `.vcf`，而不是一个目录 |
| `--overwrite` | 覆盖已存在的文件 |
| `--dry-run` | 只发现与报告，不落盘 |
| `--insecure` | 跳过 TLS 校验（自签名证书的 NAS 用；生产环境禁用） |
| `--quiet` | 只打印错误 |

## 输出布局

默认 —— 一个通讯录一个目录，每张卡一个文件：

```
export/
├── info.json
├── test(8984dcfb-…)/          # "<显示名>(<URL 末段>)"
│   ├── 07cd8491-….vcf         # 文件名 = 卡片 href 的末段
│   └── carddav-write-proof-….vcf
└── My Contacts(137810dc-…)/
```

`--single-file` —— 每本通讯录一个合并的 `.vcf`：

```
export/
├── info.json
├── test(8984dcfb-…).vcf
└── My Contacts(137810dc-…).vcf
```

没有联系人的通讯录：目录模式下会建一个空目录；单文件模式下**不写文件**（0 字节的 `.vcf` 不是合法 vCard）。

## 命名规则

- **身份是集合 URL 的末段**，先百分号解码再清洗。同一 home-set 下这些末段天然唯一
  （WebDAV 不允许同级资源同名），因此**不加 hash 后缀**。
- **显示名只是可读前缀**：可以为空（群晖就返回 `""`）、可以重名，永远不参与唯一性。
- 清洗顺序：解码 → `/` 与 `\` 变 `_` → 去控制字符与 `< > : " | ? *` → 去首尾点与空格 →
  Windows 保留名（`CON`、`NUL`…）前加 `_` → 按 UTF-8 字节截到 200 且不切半个汉字。
- 卡片文件名取 `href` 末段，缺 `.vcf` 时补上。
- 清洗后若仍撞名（极少），按大小写不敏感追加 `-2`、`-3`…

## `info.json`

**最后写**，因此半途失败不会留下一个「看起来完整」的目录。它是唯一索引 —— 不要用文件名反推身份。

```json
{
  "exported_at": "2026-10-29T17:40:00+08:00",
  "client": {"name": "carddav", "version": "0.1.0"},
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

`--single-file` 模式下，每本通讯录用 `"file": "test(…).vcf"` 取代 `"dir"`，每张卡的记录里没有 `file`，
空通讯录的 `file` 为 `null`。导出失败的那本会带 `"error": "DAVError: …"`。

## 覆盖语义

**没有**「目录非空」检查，**也没有**任何清理动作。每个输出文件单独判断：

| 情况 | 行为 |
|---|---|
| 目标不存在 | 写入 |
| 目标已存在且没给 `--overwrite` | **跳过**，在 stderr 列出，退出码 **1**；其它文件照常写 |
| 目标已存在且给了 `--overwrite` | 原地覆盖 |
| `--dry-run` 且存在同名目标 | 只报告，不落盘，退出码 **1** |

本命令从不删除任何文件。后果：服务端删掉的卡，本地旧文件会留着。想要干净镜像就换一个空目录。

## 退出码

| 码 | 含义 |
|---|---|
| `0` | 全部导出成功（或 dry-run 且无冲突） |
| `1` | 至少一本通讯录失败，或至少一个文件被跳过 |
| `2` | 用法错误（缺 `--url`、`--out-dir` 指到文件…） |

## 安全提示

- 优先用 `CARDDAV_PASSWORD` 而不是 `--password`：命令行参数会出现在 shell 历史与 `ps` 里。
- `--insecure` 会关闭证书校验，只适用于家庭局域网里自签名证书的 NAS。

## 导入

`carddav import` 尚未实现。等它落地后，导入规则（新建还是更新、默认演练、绝不删除）
会补在本页。
