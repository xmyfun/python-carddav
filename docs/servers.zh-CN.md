# 服务端支持与怪癖

[English](servers.md) · **简体中文**

CardDAV 看着是同一个协议，实际行为却有好几个流派。本页记录**我们真的验证过什么**、别人报告了什么，
以及由此得出的实用规则。

> **证据等级。** 「已实测」= 我们自己的真机测试连上真实服务端且通过。「社区记录」= 厂商文档或他人报告，
> **不是**我们的测试。表里没有任何一条是「猜测伪装成事实」。

## 状态

| 服务端 | 底层实现 | 鉴权 | 状态 |
|---|---|---|---|
| **Synology Contacts**（DSM） | Radicale 定制构建 | Basic | **已实测**（2026-10-29） |
| Radicale（自托管） | Radicale | Basic | 社区记录 —— 与群晖同族 |
| Nextcloud / ownCloud，含 Disroot | sabre/dav（PHP） | Basic | 社区记录，尚未实测 |
| Baikal | sabre/dav | Basic | 社区记录，尚未实测 |
| iCloud | 苹果自研 | App 专用密码 | 社区记录，尚未实测 |
| Google 通讯录（**CardDAV 端点**，不是 People API） | 谷歌自研 | 仅 OAuth 2.0 bearer | 社区记录，尚未实测 |
| Fastmail | Fastmail | App 专用密码 | 社区记录，尚未实测 |
| Xandikos | Xandikos | Basic | 社区记录，尚未实测 |

群晖上「已实测」覆盖的范围：发现、列举、单卡读取、`multiget`、`PUT` 新建/更新、
过期 `If-Match` 触发 `412`、`DELETE`、`sync-collection`（建/改/删/空闲），以及
`addressbook-query` 的 `text-match`。

## 会改变你写法的已知差异

### 1. 建卡用 `PUT`，不是 `POST`

RFC 6352 §6.3.2 写得很明确：新建 address object **必须**用 `PUT` 打到未映射的 URI。
「向集合 POST」是服务端自定的扩展（RFC 4918 把其语义留给服务端），而 RFC 5995 标准化的
「Add-Member」流程需要先发现 `DAV:add-member`，本库没有实现这一步。

- Radicale / 群晖：`Allow` 里根本没有 `POST`，发 `POST` 返回 **500**。这是**合规**的 —— 只是没实现该扩展。
- `post_card()` 只为「服务端自己分配 URL」的服务端保留，**目前尚未在任何服务端上验证成功**。

**实用规则**：用 `put_card(data)`（按 UID 推导 URL）或 `put_card(data, href=...)` 新建；
表达「绝不能覆盖」时加 `create_only=True`。

### 2. Radicale 上 URL 才是身份 —— `UID` 服从文件名

在群晖/Radicale 上，`PUT` 一张 `UID` 与 URL 末段不一致的 vCard，服务端会**把 `UID` 改写成文件名**；
`PUT` 一张没有 `UID` 的卡，它会用**文件名**补一个（不是 UUID）。

**实用规则**：任何写入之后都回读，用**服务端返回的** `Card.uid` 与 `Card.href` 当新基线。
绝不要假设「我发出去的字节原样存活」。

### 3. `href` 不是跨服务端的稳定标识

RFC 6352 §6.3.2 说资源名「完全任意」。同一张联系人，在一台服务端上叫 `07cd8491-….vcf`，
在另一台上可能叫 `card-1.vcf`。跨服务端时 `UID` 更接近身份 —— 但要先看第 4 条。

### 4. v4 UUID 不含任何信息

群晖 UI 生成的是 UUID **v4**（纯随机，无时间戳、无 MAC、无账号哈希）。所以不能按 UID 排序、
不能由它推断创建时间、也不能靠它判断「另一台服务端上的同一个人」。

### 5. 未知或过期的 `sync-token` 未必报错

Radicale 对不认识的 token **不返回** `403 valid-sync-token`，而是静默返回**全量**加一个新 token。
本库如实转述服务端行为，于是一次静默全量看起来就像「有一大堆变更」。

**实用规则**：如果返回项里出现 `etag` 与你本地 base 相同的条目，就当成「全量回退」信号，而不是普通增量。

### 6. `CARDDAV:limit` 可能被忽略

Radicale 接受 `<c:limit><c:nresults>N</c:nresults></c:limit>`，然后照样返回全部。规范允许这样做
（§10.6.1），所以**永远不要拿 `limit` 当分页保证** —— 自己截断。

### 7. 两个 REPORT 的 `Depth` 不一样

`addressbook-multiget` **必须**发 `Depth: 0`（§8.7）；`addressbook-query` 用 `1` 或 `infinity`（§8.6）。
写反了在宽容的服务端上能过，在严格的服务端上就失败。本库发的是正确值；你自己拼请求时要注意。

### 8. 群晖的端口与结尾斜杠

- CardDAV 只在 DSM 的 HTTP/HTTPS 端口上提供（默认 `5000` / `5001`）。把 DSM 改成别的端口后，
  Contacts 界面给出的 URL 会跟着变，但可能返回 `405`。
- `/carddav`（不带结尾斜杠）返回 **405**；`/carddav/` 正常。
- `/.well-known/carddav` 会先跳到 `/carddav/`，再**二次跳**到一个网页（`/carddav/.web`，正文
  `Radicale works!`）。本库只取第一个「像集合」的跳转，所以裸域名入口仍然可用。

### 9. `DELETE` 可能是软删除

Nextcloud（sabre/dav）在部分版本与配置下会把删除的资源**改名**而不是移除（社区记录，本库未实测）。
真如此的话，「已删除」的卡可能仍以另一个名字出现在列表里。

### 10. 服务端改写会造成「永远有待推送的改动」

任何服务端改写（第 2、4 条）都意味着你读回来的字节 ≠ 你发出去的字节。只记录「我上次发了什么」的
同步引擎会看到永久的 diff。**把服务端返回的内容当作 base。**

## 实用清单

1. 新建用 `PUT`；要求「已存在就失败」时加 `create_only=True`。
2. 更新用 `put_card(..., href=<你读到的 href>, if_match=<那个 etag>)` —— 不要重新推导 URL。
3. 写完回读；相信响应，不要相信请求。
4. 本地状态用 `UID` 做主键、`href` 做定位。
5. 把「全量列举」当成 token 过期的可能回退。
6. 不要依赖 `CARDDAV:limit` 做分页。
7. 不要解析 `href` 的含义；它是不透明字符串。

## 证据在哪

逐服务端的探测记录、版本与日期保存在仓库内的维护者笔记里。本页只留结论，
因此不依赖那些笔记也能读。
