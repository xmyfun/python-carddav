# carddav

**简体中文** · [English](README.md)

一个轻量、行为可预期的 **Python CardDAV 客户端库** —— PyPI 包 [`carddav`](https://pypi.org/project/carddav/) 的源码仓库。

> **状态：0.2.0 —— 首个公开版本。** 下文描述的功能均已实现，并在真实服务端（Synology Contacts，底层为 Radicale 构建）上验证过。

## 为什么还要再造一个？

现有选择要么只管日历（`caldav` 处理 CalDAV，不处理通讯录），要么已经废弃（`pyCardDAV` 只支持 Python 2），要么被埋在某个命令行应用里（`vdirsyncer` 的 CardDAV 后端不是可安装的库）。核查时间 2026-10。

## 功能

- **发现** —— `.well-known/carddav` → `current-user-principal` → `addressbook-home-set` → 地址簿列表
- **读取** —— 列出资源（`href` / `etag`）、用 `addressbook-multiget` 批量取、用 `addressbook-query` 做服务端搜索
- **增量同步** —— RFC 6578 `sync-collection` + `sync-token`，含 token 过期后的回退路径
- **写入** —— `PUT` 新建（带 `If-None-Match: *`）或更新（带 `If-Match`）、`DELETE`；`POST` 仅作为「服务端分配 URL」这类怪癖服务端的兼容路径
- **原文访问** —— `Card.data` 返回服务端发来的**原始字节**，不做任何解析或重写
- **可插拔 HTTP** —— 运行时只依赖 `httpx`；可切到 `requests` 或任意自定义后端，顺带让 mock 变得很简单
- **薄 CLI** —— `carddav export` 按「一个通讯录一个目录」导出（或每本一个合并的 `.vcf`），并写 `info.json` 索引

## 不做什么

以下刻意留在调用方，不属本库职责：

- vCard 解析、字段映射、去重、合并、规范化
- 同步引擎：没有本地数据库、没有索引、没有冲突解决、没有缓存状态
- UID 的生成或改写
- **Google People API** —— Google 通讯录有两条通路：**CardDAV** 端点（本库实现的这条）与 **People REST API**（Google 官方 Python 客户端是 [`google-api-python-client`](https://pypi.org/project/google-api-python-client/)）。本库只实现 CardDAV 那条；若你要用 People API，请在自己的代码里用那个 SDK —— 本库既不封装也不依赖它
- OAuth2 授权码流程与 token 刷新 —— `BearerAuth(token)` 只接收你已经拿到的 token

这是刻意的取舍：一个「懂你通讯录」的客户端，就没法再如实告诉你服务端到底做了什么。

## 安装

```bash
pip install carddav              # 默认 httpx 后端
pip install "carddav[requests]"  # 可选：requests 后端
pip install "carddav[http2]"     # 可选：HTTP/2 支持
```

要求 Python 3.10+。注意 3.10 已上游 EOL，本库按「尽力支持」对待，下限会随依赖一起上移。

> **PyPI 发布在即。** 在 `carddav` 上架前，可先这样装：`pip install git+https://github.com/xmyfun/python-carddav.git`。

## 鉴权

| 方式 | 用法 | 说明 |
|---|---|---|
| Basic | `get_davclient(url, username=..., password=...)` | 只要给了 `username` 就自动使用 |
| Digest | `auth=DigestAuth(user, password)` | 必须显式传入 —— 本库不会先收 401 挑战再切换 |
| Bearer | `auth=BearerAuth(token)` | 给 OAuth2 保护的端点用；token 的获取与刷新由你负责 |
| 自带 | `auth=<所选后端原生的 auth 对象>` | 优先级高于 `username` / `password`，且必须与所选后端匹配（例如 `httpx.Auth`） |

不包含：OAuth2 授权码流程与 token 刷新、客户端证书（mTLS）、NTLM / Kerberos。

## HTTP 后端

HTTP 层被收在一个只有两个方法的接口后面（`Backend`：`request()` / `close()`），因此换栈或 mock 都不必碰库本身：

```python
get_davclient(url, backend="httpx")     # 默认
get_davclient(url, backend="requests")  # 需 pip install "carddav[requests]"
get_davclient(url, backend=my_fake)     # 任何带 request()/close() 的对象
```

离线测试正是靠这条缝实现的 —— 见 `tests/test_backend.py`。

## 服务端 URL

传给 `get_davclient` 的 `url` 可以指向 CardDAV 层级中的**任意一层** —— 库会从那里自行发现地址簿。URL 越粗，库需要走的发现步骤越多；直接给地址簿 URL 则完全跳过发现。四种形态返回的都是同样的 `AddressBook` / `Card` 对象。

| 粒度 | 含义 | 例子 |
|---|---|---|
| **裸域名** | 只给域名。库按 RFC 6764 查 `/.well-known/carddav` 找到入口。 | `https://cloud.example.org` |
| **Principal URL** | 当前登录用户自己的根，也就是 `current-user-principal`。 | `https://cloud.example.org/remote.php/dav/principals/users/me/` |
| **addressbook-home-set URL** | **承载**该用户全部地址簿的容器。服务端可能把它放在**另一台主机**上 —— iCloud 就会返回分片主机，这是正常现象，不是错误。 | `https://p48-contacts.icloud.com/1437425399/carddavhome/` |
| **某个具体地址簿 URL** | 精确指向一本地址簿 —— 跳过发现。 | `https://p48-contacts.icloud.com/1437425399/carddavhome/card/` |

发现过程（well-known → `current-user-principal` → `addressbook-home-set` → 地址簿）由库完成，你永远不需要自己写 `PROPFIND` 或解析 `href` 路径。实现了什么、刻意不做什么，见[服务端支持与怪癖](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.zh-CN.md)。

## 快速开始

API 形状对齐 [`caldav`](https://github.com/python-caldav/caldav)（`get_*` / `put_card` / `delete_card`），两个库用起来手感一致。

```python
from carddav import get_davclient

with get_davclient(
    url="https://cloud.example.org",
    username="me",
    password="app-password",  # iCloud 需要用 App 专用密码
) as client:  # 构造只建立连接；get_principal() 才触发发现
    book = client.get_principal().get_addressbooks()[0]

    cards_meta = book.get_cards()  # 只有元数据：href / etag（uid 需要读正文）
    for meta in cards_meta:
        print(meta.href, meta.etag)

    card = book.get_card(cards_meta[0].href)  # 原始字节 + etag
    print(len(card.data or b""))  # 服务端给什么就是什么
    etag = book.put_card(new_vcf, href=card.href, if_match=card.etag)  # 期间被人改过 → 412
    book.delete_card(card.href, if_match=etag)

    etag = book.put_card(vcf_bytes, create_only=True)  # PUT <uid>.vcf，已存在则拒绝
    href = book.post_card(vcf_bytes)  # 仅用于服务端分配 URL 的怪癖路径

    changes, token = book.get_changes()  # 首次：全量列举
    changes, token = book.get_changes(sync_token=token)  # 之后：只有变更
    for change in changes:
        print(change.href, change.deleted)

    cards = book.search(query_xml, depth="1")  # addressbook-query，报文原样发送
```

## 示例

可运行的脚本在 [`examples/`](https://github.com/xmyfun/python-carddav/tree/main/examples)，从环境变量读
`CARDDAV_URL` / `CARDDAV_USER` / `CARDDAV_PASSWORD`，不需要传参：

```bash
export CARDDAV_URL=https://cloud.example.org CARDDAV_USER=me CARDDAV_PASSWORD='***'

uv run python examples/list_books.py        # 通讯录与卡片数
uv run python examples/export_book.py --out ./export
uv run python examples/watch_changes.py    # 把 sync token 存在本地文件里
uv run python examples/search_cards.py --text Alice
```

## 命令行

包内自带一个薄薄的 `carddav` 命令。目前只实现了 `export` 子命令；它不做任何字段判断，只负责发现、取回、落盘。

```bash
# 默认：一个通讯录一个目录，每张卡一个 .vcf
carddav export --url https://cloud.example.org \
               --user me --password '***' --out-dir ./export

# 改成：每本通讯录一个合并的 .vcf
carddav export --url https://cloud.example.org --user me --out-dir ./export --single-file

# 先看再写
carddav export --url https://cloud.example.org --user me --out-dir ./export --dry-run
```

`--url` 接受前述四种入口形态（裸域名 / principal / home-set / 单个集合）。导出的名字是 `"<显示名>(<URL 末段>)"` —— 末段才是身份，显示名只是给人看的前缀。两种布局都会写 `info.json`，记录每本通讯录的 `href` 与每张卡的 `href`/`etag`/`uid`。已存在的文件会被**跳过并报告**（退出码 1），除非加 `--overwrite`；本命令从不删除任何文件。输出细节与 `info.json` 结构见 [`docs/cli.zh-CN.md`](https://github.com/xmyfun/python-carddav/blob/main/docs/cli.zh-CN.md)。

## 服务端支持

| 服务端 | 鉴权 | 状态 |
|---|---|---|
| Radicale —— 含 **Synology Contacts** | Basic | 已实测 2026-10-29 |
| Nextcloud / ownCloud（sabre/dav），含 Disroot | Basic | 尚未实测 |
| Baikal（sabre/dav） | Basic | 尚未实测 |
| iCloud | App 专用密码 | 尚未实测 |
| Google 通讯录（**CardDAV 端点**，不是 People API） | 由调用方提供 OAuth 2.0 access token | 尚未实测（本库不含 OAuth 流程） |
| Fastmail | App 专用密码 | 尚未实测 |

「状态」指**我们自己的真机测试验过**，不是「协议上应该能行」。目前基准服务端是 Radicale / Synology；sabre/dav、iCloud、Google 还需要凭据。各家服务端的坑与由此得出的实用规则见 [`docs/quirks.zh-CN.md`](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.zh-CN.md)。

## 文档

| 页面 | 内容 |
|---|---|
| [服务端支持与怪癖](https://github.com/xmyfun/python-carddav/blob/main/docs/quirks.zh-CN.md) | 哪些服务端实测过、各家差异、以及哪些能力刻意没做 |
| [同步模型](https://github.com/xmyfun/python-carddav/blob/main/docs/sync-model.zh-CN.md) | 为什么本库没有同步引擎，应用必须自己存什么 |
| [命令行参考](https://github.com/xmyfun/python-carddav/blob/main/docs/cli.zh-CN.md) | `carddav export`：输出布局、命名、`info.json`、退出码 |
| [变更日志](https://github.com/xmyfun/python-carddav/blob/main/CHANGELOG.md) | 版本历史 |

除变更日志外，每页都有中英两份（英文名对应 `*.md`）。

## 参与贡献

范围刻意收窄，所以规则很短 —— 但标着**不可妥协**的那几条会在评审时严格执行。

### 动手之前

- **报 bug / 提问** → [开 issue](https://github.com/xmyfun/python-carddav/issues)。请附上服务端软件与版本（`Nextcloud 30`、`iCloud`…），CardDAV 各家实现差异很大。
- **比改错别字更大的改动** → 先开 issue。API 形状与协议处理仍在演进，设计没对齐就写的 PR 通常要重写。
- **安全问题** → **不要**开 issue，走 [GitHub Security Advisories](https://github.com/xmyfun/python-carddav/security/advisories/new)。
- **改 README** → `README.md` 与 [`README.zh-CN.md`](README.zh-CN.md) 互为镜像，必须在**同一个 PR**里同时改。

### 开发环境

Python 3.10+，全部走 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync                    # 建 venv 并装开发依赖
uv run pytest              # 全量测试（离线，不需要凭据）
uv run ruff check .        # lint
uv run ruff format --check .
uv run mypy src
```

测试必须**完全离线**：不连真实 CardDAV 服务端、不需要凭据、不依赖环境变量。真实服务端只用于人工冒烟。

### 不可妥协的规则

这几条存在的原因：本库有两个「热心」客户端会破坏的职责 —— 如实汇报服务端做了什么，以及保持足够小。

1. **绝不出现真实联系人数据。** 姓名、电话、邮箱，以及含用户名的 `href` —— 测试、fixture、docstring、提交信息里都不许有。
2. **绝不出现凭据。** 密码、App 专用密码、token、`.env` 内容一律不许。
3. **不解析 vCard。** `Card.data` 必须是服务端返回的字节；`Card.uid` 只允许扫描 `UID` 行（处理折行）。
4. **不做字段逻辑。** 比较键、去重、合并、规范化都属于调用方。
5. **运行时依赖只有 `httpx`。** `requests`（可选后端）与 `h2`（HTTP/2）是 extra；新增依赖必须先书面说明理由。
6. **写入绝不自动重试**，UID 绝不隐式生成或改写。
7. **所有 HTTP 必须经 `Transport.request()`**；只有 `_backend_httpx.py` / `_backend_requests.py` 可以 import HTTP 库。
8. **解析前拒绝含 `<!DOCTYPE` 的 XML。**
9. **代码注释与 docstring 只用英文。** `docs/` 下的公开页面双语；`internal/` 下的开发者笔记用中文。

### 测试

- 每个协议行为都要有测试 —— 包括失败路径（`401`、`403`、`412`、`507`、过期的 `sync-token`）。
- 改了请求体，就要断言**发出的确切字节**。请求体用字符串模板正是为了这个。
- 修 bug 要带上「修之前会失败」的测试。

### 提交 PR

- 一个 PR 只做一件逻辑上说得清的事；重构与行为变更分开。
- 同步更新对应文档：面向使用者的事实 → `docs/`（中英各一份）；设计决策 → 仓库里的 `internal/` 笔记。
- 提交信息：祈使句短标题；不显然的话，正文写**为什么**。

提交即表示你同意你的贡献按本项目的 Apache-2.0 许可授权。

> ⚠️ **绝不要把真实联系人数据或凭据贴到 issue 里。** 姓名、电话、邮箱，以及任何含你用户名的 `href` 都要打码。

## 安全

漏洞请通过 [GitHub Security Advisories](https://github.com/xmyfun/python-carddav/security/advisories/new) **私下**报告，不要开公开 issue。凭据泄漏与 XML 解析问题都按安全缺陷处理。

## 版本策略

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。在 `0.x` 期间允许破坏性变更，但一律**升 MINOR**，并写进 [`CHANGELOG`](https://github.com/xmyfun/python-carddav/blob/main/CHANGELOG.md)；PATCH 版本不改公共 API、不抬高依赖下限。

抬高 `requires-python` 或运行时依赖下限等同于**破坏性变更** —— 那会让库在你机器上装不上。

## 许可

Apache License 2.0 —— 见 [`LICENSE`](https://github.com/xmyfun/python-carddav/blob/main/LICENSE) 与 [`NOTICE`](https://github.com/xmyfun/python-carddav/blob/main/NOTICE)。

## 相关项目

- 有一个做字段调研、身份匹配与地址簿合并的配套工具（私有仓库，同一作者）使用本库。它**不是必需的**：本库从不依赖它。
