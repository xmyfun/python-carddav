# 服务端怪癖

[English](quirks.md) · **简体中文**

CardDAV 看起来是一个协议，实际表现却像好几个。本页**按服务端**组织，因为当你把本库指向一台主机时，
需要的正是这个顺序：先找到你的服务端，再看它有什么不同。

## 证据标签怎么读

下面每一条都带三种标签之一。没有标签的说法我们不会写。

| 标签 | 含义 |
|---|---|
| **实测** | 我们自己的真机测试打过真实服务端并通过。给出日期，必要时给出测试名。 |
| **规范** | 出自 RFC。不是我们观察到的现象，而是协议的要求。 |
| **他方记录** | 厂商文档，或其他项目的兼容性笔记。**我们没有测过。**请当作线索，不要当作事实。 |

## 总览

| 服务端 | 实测版本 | 底层实现 | 鉴权 | 证据 |
|---|---|---|---|---|
| **Radicale**（自托管） | **3.9.0** | Radicale | Basic（htpasswd） | **实测** 2026-10-30，本机 localhost |
| **群晖 Contacts**（DSM） | DSM 版本**未确定** | — | Basic | **实测** 2026-10-28/29，2026-10-30 复核，局域网 |
| **Xandikos** | **0.4.10** | Xandikos | 自身不带鉴权 | **实测** 2026-10-30，本机 localhost |
| Nextcloud / ownCloud，含 Disroot | — | sabre/dav（PHP） | Basic | 他方记录，未实测 |
| Baikal | — | sabre/dav | Basic | 他方记录，未实测 |
| Google 通讯录（**CardDAV 端点**） | — | Google | 仅 OAuth 2.0 bearer | 厂商文档，未实测 |
| iCloud | — | Apple | 应用专用密码 | 他方记录，未实测 |
| Fastmail | — | Fastmail | 应用密码 | 他方记录，未实测 |

### 关于群晖那台机器：两条观测，以及我们**不**主张什么

2026-10-30 我们抓了群晖重定向到的那个页面并读了它的正文：

- `GET /carddav/.web` 返回 `200`，`Content-Type: text/plain`，正文是 **`Radicale works!`**
  （15 字节），`Server: nginx`。
- 它的 `sync-collection` token 形如 `http://radicale.org/ns/sync/27_4745`。

以上就是我们看到的事实。我们**没有**确定这台机器跑的是哪个软件版本，也没有确定它与上游 Radicale
是什么关系，因此本页两者都不主张。之所以把群晖与原版 Radicale 分成两节，仅仅因为**实测行为不同**
（§3.1）。

## 一、RFC 基线（是规范，不是怪癖）

以下是 RFC 6352 及其相关规范要求的行为。偏离这些的服务端，会在下面作为怪癖列出；符合这些的，
只是合规而已。每一行都标了条款。

| 行为 | 条款 | 本库对应 |
|---|---|---|
| 新建卡片 **MUST** 用 `PUT` 打到未映射 URI | RFC 6352 §6.3.2 | `put_card(data)` |
| 资源名「完全任意」，与 UID 无强制关系 | §6.3.2 | `put_card` 推导 `<uid>.vcf`，**这是本库约定** |
| 纯新建（不覆盖）**SHOULD** 带 `If-None-Match: *` | §6.3.2 | `put_card(create_only=True)` |
| 更新 **SHOULD** 带 `If-Match` | §9.2 | `put_card(if_match=...)` |
| `addressbook-multiget` **MUST** 用 `Depth: 0` | §8.7 | 本库自动发对 |
| `addressbook-query` 用 `Depth: 1` 或 `infinity` | §8.6 | `search(xml, depth="1")` |
| 服务端 **MAY** 忽略 `CARDDAV:limit` | §10.6.1 | 从不当作分页 |
| 无效 `sync-token` **SHOULD** 返回 `403` + `DAV:valid-sync-token` | RFC 6578 | 只在真的收到 403 时抛 `SyncTokenInvalid` |
| `/.well-known/carddav` 重定向到上下文路径 | RFC 6764 §4 | 本库手动跟随，见 3.6 |

**`POST` 不属于标准 CardDAV。** 对集合 `POST` 在 WebDAV 里没有定义语义（RFC 4918 §9.5 把语义
留给服务端）；「由服务端分配 URL」的标准化做法是 RFC 5995 的 `DAV:add-member`，属于可选扩展。
所以**拒绝 `POST` 的服务端是合规的**，不是坏了。

有一条本库约定值得知道，因为它会出现在你的写入里：省略 `href=` 时，`put_card` 推导 `<uid>.vcf`，
推导前会先对 UID 做**百分号编码**（RFC 3986 §2）——`/` 变成 `%2F`、`:` 变成 `%3A`，因此服务端给的
UID 既不能越出集合，也不会被当成 URI scheme 解析（`urn:uuid:…` 否则会整体脱离 HTTP）。普通 UUID
一字不变，且 `unquote()` 可还原。

## 二、Radicale 3.9.0 —— **实测**

2026-10-30 在 `127.0.0.1:5232` 实测，htpasswd 鉴权 + 文件系统存储。集合路径形如
`/<user>/<collection>/`，探测前用 `MKCOL` 建了一个。

### 2.1 建卡用 `PUT`；`POST` 被通告但不支持

对集合 `OPTIONS` 返回的 `Allow` 头里**确实有** `POST`，但对集合 `POST` 返回 **`405`**。

→ 「通告某方法」≠「支持某方法」——要靠「做」来探测，不能靠「问」。建卡用 `put_card(data)`，
不允许覆盖时加 `create_only=True`。

### 2.2 UID 才是权威，且没有 UID 的卡会被拒

- `PUT` 一张**没有** `UID:` 的卡 → **`400`**（严格贴合 RFC 6352 §5.1）。
- `PUT` 一张 body 里 UID 与文件名不一致的卡 → **保留你发的 UID**，不会被改写，也不会多出第二个资源。

→ 写完仍然建议回读，但在这台服务端上，你发什么它就存什么。

### 2.3 未知 `sync-token` 会给真的 `403`

服务端不认识的 token 会返回 **`403`**，因此本库抛 `SyncTokenInvalid`，你的回退分支真的会触发 ——
这点与群晖不同（§3.3）。

token 形如 `http://radicale.org/ns/sync/<64 位十六进制>`。当作不透明串。

### 2.4 `CARDDAV:limit` 被忽略

`addressbook-query` 配 `prop-filter name="FN"` + `text-match` 正常工作并内联 `address-data`；
加上 `<c:limit><c:nresults>1</c:nresults></c:limit>` 仍然返回全部命中——RFC 6352 §10.6.1 明确允许
服务端这么做。→ 不要把 `limit` 当分页保证，需要就在客户端截断。

### 2.5 列举只给元数据，不给正文

`PROPFIND Depth: 1` 只返回 href + etag。→ `get_cards()` 返回元数据；正文用 `get_card()` 或
`multiget()`。

### 2.6 路径：没有 `/carddav`，结尾斜杠也不影响

| 请求 | 结果 |
|---|---|
| `GET /.well-known/carddav` | `301` → `/` |
| `GET /carddav` 与 `GET /carddav/` | `403` —— 该路径不存在 |
| `PROPFIND <集合>` 带/不带结尾斜杠 | 两种写法都是 `207` |

→ 这里没有 `/carddav` 前缀可拼，集合 URL 少了结尾斜杠也无所谓（§3.6 的 405 是群晖前置层的
行为，不是 Radicale 的）。

### 2.7 关于 Radicale 的他方记录（我们未实测）

- **客户端无法创建集合。** vdirsyncer 记录。→ 地址簿请在服务端 UI 预建，本库从不写集合。
- **Radicale 故意不实现完整标准。** vdirsyncer 记录。基础读写没问题，但不要假设那些偏门特性。

### 2.8 其他实测通过的行为

陈旧 `If-Match` 触发 `412`、`multiget`、`DELETE`、`sync-collection` 增量均符合 §一；
发现、列举、单张读取、`addressbook-query` 也都通过。

## 三、群晖 Contacts（DSM）—— **实测**

在局域网 DSM 上实测 2026-10-28/29，2026-10-30 复核。实测覆盖：发现、列举、单张读取、
`multiget`、`PUT` 新建/更新、陈旧 `If-Match` 触发 `412`、`DELETE`、`sync-collection`（建/改/删/空闲）、
`addressbook-query` 的 `text-match`。

### 3.1 它与 Radicale 3.9.0 的差异

两者都在 2026-10-30 实测。以下是**观测到的差异**，不是关于「血缘」的论断：

| 行为 | Radicale 3.9.0 | 群晖 Contacts |
|---|---|---|
| `Allow` 里有 `POST` | 有（但 `POST` → `405`） | **没有**（`POST` → `500`） |
| `PUT` 一张没有 `UID` 的卡 | **`400`** | 成功 —— UID 由文件名补上 |
| UID 与文件名不一致 | 原样保留 | **改写为文件名** |
| 未知 `sync-token` | **`403`** | 返回全量，不报错 |
| `sync-token` 形态 | `…/sync/<64 位 hex>` | `…/sync/27_4745` |
| `/.well-known/carddav` | `301` → `/` | `302` → `/carddav/` → `.web` |
| `/carddav` 路径 | 不存在（`403`） | 存在（无斜杠则 `405`） |

→ 不要把一台的结论套到另一台上。

### 3.2 URL 才是身份：UID 服从文件名

**实测** 2026-10-29 三个可复现实验，2026-10-30 复核。

| 我们做了什么 | 回了什么 |
|---|---|
| 读取一张在群晖 UI 里新建的联系人 | `href` 末段是 `<uid>.vcf`；UID 是裸 UUID v4，没有 `urn:uuid:` 前缀 |
| 向显式 href `PUT` 一张**没有** `UID:` 的卡 | 服务端补上 `UID:<文件名去掉 .vcf>` —— **不是** UUID |
| 向已有 href `PUT`，但 body 里的 UID 与文件名不一致 | 服务端把 UID 改写成文件名；集合里始终只有一个资源 |

→ 任何写入之后都要回读，用返回的 `Card.uid` / `Card.href` 作为新基准。更新时传你读到的 href，
不要重新推导。

### 3.3 未知或过期的 `sync-token` 会静默返回全量

**实测** 2026-10-29，2026-10-30 复核。传入服务端不认识的 token，**既没有 403，也没有
`DAV:valid-sync-token` 前置条件**——而是返回全量加一个新 token。本身无害，但全量与增量的
**响应形状完全一样**，无法从形状区分。可用信号：若返回项中存在 etag 与你本地 base 相同的条目，
说明这是全量回退。

### 3.4 `CARDDAV:limit` 被忽略 —— 与 Radicale 一致（§2.4）。

### 3.5 列举只给元数据，不给正文 —— 与 Radicale 一致（§2.5）。

### 3.6 `.well-known` 会跳两次，且结尾斜杠不能省

**实测** 2026-10-29，2026-10-30 关闭重定向跟随后复核。

| 请求 | 结果 |
|---|---|
| `GET /.well-known/carddav` | `302` → `http://<host>:5000/carddav/`（RFC 6764 的正常一跳） |
| `GET /carddav/` | 又 `302` → `.web` |
| `GET /carddav/.web` | `200`、`text/plain`、正文 **`Radicale works!`** |
| `GET /carddav`（无斜杠） | `404` |
| `PROPFIND /carddav`（无斜杠） | **405** |
| `PROPFIND /carddav/` | `207` |

→ `DAVClient` 自己跟随重定向，并停在链上第一个「像 DAV 集合」的跳点，所以给裸域名也能工作。
不要自己拼 `/carddav` 路径——少一个斜杠就是 405。若入口 URL 拒绝 `PROPFIND`，本库抛
`DiscoveryError` 并带上状态码，不会重复发请求；缺少结尾斜杠是最常见的原因。

### 3.7 在集合上做发现会返回 401

**实测** 2026-10-29。直接向地址簿集合问 `current-user-principal` 会返回 `401`；本库捕获该错误
并降级为「把入口 URL 当发现根」。

### 3.8 CardDAV 只在 DSM 端口上应答

**实测** + 用户反馈，2026-10-28。CardDAV URL 只在 DSM 的 HTTP/HTTPS 端口上提供（默认
`5000` / `5001`）；把 DSM 改到别的端口后，Contacts 套件给出的 URL 会返回 `405`。→ 用默认端口。

## 四、Xandikos 0.4.10 —— **实测**（写入正常，仅经 HTTP 代理时例外）

2026-10-30 在 `127.0.0.1:8081`–`8085` 实测，启动方式
`xandikos serve --defaults --autocreate -d <dir>`。Xandikos **自身不带鉴权**（期望由反向代理负责），
`--defaults` 会预建 `/user/contacts/addressbook/`。

### 4.1 `POST` 会应答，且 `post_card` 会重建 href

对集合 `POST` 返回 **`200`** 并带 `Location` 头 —— 但这个 `Location` 是一个**畸形的协议相对 URL**：
`//user/contacts/addressbook/<uuid>.vcf`，把集合路径的第一段 `user` 当成了*主机*。若直接按
RFC 3986 解析，它变成 `http://user/...`（主机字面值 `user`），这个地址并不存在。

`post_card()` 检测到「Location 主机 ≠ 集合主机」后，改以「集合 URL + Location 末段
（`<uuid>.vcf`）」重建绝对 href —— 该末段正是真实资源名，重建后即可 `GET` 到刚建的卡。
**因此 2026-10-30 认定 Xandikos 0.4.10 上 `POST` 经重建后可用**。Radicale 仍返回 `405`、
群晖仍返回 `500`，所以 `PUT` 仍是唯一三端通吃的建卡方式。

### 4.2 有的地方更严，有的地方更松

| 探测 | Xandikos 0.4.10 | 对照：Radicale 3.9.0 |
|---|---|---|
| `PUT` 新 UID、无条件头 | `201` | `201` |
| `PUT` 带 `If-None-Match: *` | **`201`** —— `put_card(create_only=True)` 可用 | `201` |
| `PUT` 一张**没有** `UID` 的卡 | **`201`** —— 接受，回读没有 UID | **`400`** |
| 第二张卡复用已有 UID | **`201`** —— 不做 `no-uid-conflict` 检查 | `201` |
| UID 与文件名不一致 | 原样保留 | 原样保留 |
| 用当前 `If-Match` 更新 | `204` | `204` |
| 用陈旧 `If-Match` 更新 | `412` | `412` |
| **`CARDDAV:limit`** | **遵循** —— 3 条命中下发 `nresults=1` 就只返回 1 条 | 忽略 |

→ Xandikos 是**三台里唯一遵循 `CARDDAV:limit`** 的，也是唯一接受「没有 UID 的卡」的。
同样不要从 Radicale 套过来。

### 4.3 走 HTTP 代理时写入会失败

**实测** 2026-10-30。客户端经 HTTP 代理访问 Xandikos 时，发出的是**绝对形式请求目标**
（`PUT http://host/path`）而不是 origin-form（`PUT /path`）。Xandikos 的
`split_path_preserving_encoding()` 直接取 `request.raw_path`（`xandikos/webdav.py:421`），
不剥离 scheme 与 authority，于是容器路径被解析成
`http:/127.0.0.1:8081/user/contacts/addressbook` 这种东西，`backend.get_resource()` 返回 `None`，
`PUT` 因此得到 **409**（`webdav.py:2695`）；`DELETE` 则对确实存在的资源返回 **404**。

同一个客户端、同一台服务端、同一条连接上连续三次 `PUT`：

| 客户端 | 结果 |
|---|---|
| 走代理（httpx 默认读 `HTTP_PROXY`） | `201, 409, 409` |
| 绕过代理（`NO_PROXY=*`，或 httpx `trust_env=False`） | `201, 201, 201` |

RFC 7230 §5.3 要求服务端接受绝对形式，所以这是 Xandikos 的一处合规缺口；**直连时永远不会出现**。
Radicale 3.9.0 与群晖**不受影响** —— 同样的带代理请求它们都正常应答。

→ 若你的 Xandikos 主机要经过代理才能访问，请为该主机绕过代理（`NO_PROXY`），否则本库无法写入。

### 4.4 其他实测细节

- **`PROPFIND` 不带 `Content-Type` 会返回 `415`** —— Xandikos 拒绝 `application/octet-stream`
  的请求体。本库始终发 `application/xml`。
- **无效 `sync-token` 返回 `412` 而非 `403`** —— 因此不会抛 `SyncTokenInvalid`，而是以
  `PreconditionFailed` 的形式暴露出来。
- `sync-token` 是裸十六进制串（如 `0fc5d5a009e4b2ef1f0e6a5e1f1c6df4b1e63809`）。
- 列举只给元数据；`multiget` 与 `addressbook-query` 会内联 `address-data`；`DELETE` 返回 `204`。

## 五、sabre/dav 家族：Nextcloud / ownCloud / Baikal —— **他方记录，未实测**

我们目前没有这一族的凭据，所以**本节全部来自其他项目的笔记，不是我们自己的测试。**

| # | 现象 | 来源 |
|---|---|---|
| 5.1 | `DELETE` 可能是**软删除**：资源被改名而不是删除，取决于版本与配置，可能以另一个名字重新出现在列表里 | vdirsyncer 记录，未实测——过滤改名对象是调用方的事 |
| 5.2 | ownCloud **低于 7.0.0** 带的 SabreDAV 版本有冲突检测与竞态 bug；已在 SabreDAV 上游与 ownCloud 7.0.0 修复 | vdirsyncer issue #16 |
| 5.3 | Baikal **0.2.7 及更早**用的是同一版本的旧 SabreDAV，有同样问题；后续版本已修复 | vdirsyncer issue #160 |

## 六、Google 通讯录（CardDAV 端点）—— **厂商文档，未实测**

来自 Google 自己的 CardDAV 文档（2026-10-28/29 查阅）与 carddavclient 的笔记。**我们从未拿本库
跑过 Google**——没有凭据，本库也不做 OAuth 流程。

| # | Google 的做法 | 性质 |
|---|---|---|
| 6.1 | **建卡只接受 `POST`**，不接受 `PUT` 到客户端指定的 URI | **偏离 RFC 6352 §6.3.2。** `post_card()` 是兼容路径，未对 Google 实测过 |
| 6.2 | 存新卡时服务端会**改写 UID** | carddavclient 记录。UID 要回读，不会是你发的那个 |
| 6.3 | **仅 OAuth 2.0 bearer**，强制 HTTPS | 厂商文档。`BearerAuth(token)` 接收你自己拿到的 token |
| 6.4 | 支持 GET / PUT / DELETE / OPTIONS / PROPFIND / REPORT；**不**支持 LOCK / UNLOCK、COPY / MOVE、MKCOL、任意 WebDAV 属性、ACL（RFC 3744） | 厂商文档 |
| 6.5 | vCard 3.0；`sync-token` 29 天过期；空 token 被拒（400）；`sync-collection` 需要 `Depth: 1` | 厂商文档 |

三家做法的区别：Google 是**替换**你的 UID 为内部 id，群晖是把 UID **对齐**到资源名（§3.2），
Radicale 3.9.0 则**保留**你发的值（§2.2）。三者落到同一条规则上——上传不等于最终状态，必须回读。

## 七、iCloud —— **他方记录，未实测**

- **必须用应用专用密码**，不是 Apple ID 主密码，因为两步验证无法在 DAV 接口上完成。vdirsyncer 记录。
- **集合名有最小长度要求。** vdirsyncer 记录。
- 当 iCloud 账户联系人为 0 时，我们的真机测试会跳过。

## 八、Fastmail —— **他方记录，未实测**

vdirsyncer 称 Fastmail 无已知问题。

## 九、所有服务端 —— **他方记录**

**没有任何服务端支持部分取字段。** 无论 `multiget` 还是 `query`，都没有服务端实现「只给我部分
字段」；carddavclient 的作者明确写他从没找到过支持该特性的服务端。

→ 本库不实现部分读取，取卡就是取整张 vCard。

## 实操清单

1. 建卡用 `PUT`；不允许覆盖时用 `create_only=True`。
2. 更新用 `put_card(..., href=<你读到的 href>, if_match=<那个 etag>)`，而不是重新推导 URL。
3. 写完回读；相信响应，不要相信请求。
4. 本地状态以 `UID` 为键、以 `href` 定位，并把 `href` 当不透明串。
5. sync-token 失效的三种形态都要处理：Radicale 给真 `403`、群晖给全量、Xandikos 给 `412`。
6. Radicale 与群晖会忽略 `CARDDAV:limit` —— 需要就自己截断；Xandikos 是唯一遵循它的（§4.2）。
7. 若 Xandikos 主机要经过 HTTP 代理才能访问，请为该主机绕过代理 —— 它解析不了绝对形式请求目标，
   每次写入都会 `409`（§4.3）。
8. 同步基准存「服务端返回了什么」，而不是「我发了什么」。
9. 三台之间不要互相套用结论 —— 它们在 `POST`、缺失 UID、UID 改写、sync-token 报错、
   `CARDDAV:limit` 上都不一致（§3.1、§4.2）。

## 证据在哪

「实测」各条背后的逐服务端探测记录、版本与日期，保存在本仓库的维护者笔记中。本页只发布结论，
因此脱离那些笔记也能读懂。
