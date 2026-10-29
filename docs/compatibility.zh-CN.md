# 协议覆盖

[English](compatibility.md) · **简体中文**

本库从 RFC 6352（CardDAV）、RFC 4918（WebDAV）、RFC 6578（WebDAV Sync）里实现了什么，
以及刻意不做什么。

## 方法与 REPORT

| 能力 | 规范 | 本库 |
|---|---|---|
| 发现：`PROPFIND` → `current-user-principal` → `addressbook-home-set` → 集合枚举 | RFC 4918、RFC 5397、§7.1.1 | ✅ `get_principal()` / `get_addressbooks()` |
| `.well-known/carddav`（RFC 6764） | SHOULD | ✅ 裸域名入口解析 |
| `addressbook-multiget` | §8.7（服务端 **MUST**；`Depth: 0`） | ✅ `multiget()` |
| `addressbook-query` | §8.6（服务端 **MUST**） | ✅ `search(xml, depth=…)` —— XML 原样发送 |
| `sync-collection` | RFC 6578 | ✅ `get_changes(sync_token)` |
| `GET` 单卡（含 `ETag`） | §6.3.2.3 | ✅ `get_card()` |
| `PUT` 新建 / 更新、`If-Match`、`If-None-Match: *` | §6.3.2、§9.2 | ✅ `put_card(..., if_match=, create_only=, href=)` |
| `DELETE`（可带 `If-Match`） | RFC 4918、§9.2 | ✅ `delete_card()` |
| 向集合 `POST`（服务端分配 URL） | **RFC 6352 未定义** | ⚠️ `post_card()` 作为兼容路径存在，尚未在任何服务端验证成功 |
| `OPTIONS` / `DAV` 头能力探测 | §6.1 | ❌ 未实现 |
| 扩展 `MKCOL`（建地址簿） | §6.3.1（MAY） | ❌ 未实现 —— 请在服务端 UI 或你自己的工具里建 |
| `PROPPATCH`（改名、描述） | RFC 4918 Class 1 | ❌ 未实现 |
| `COPY` / `MOVE` | RFC 4918 Class 1 | ❌ 未实现 |
| `LOCK` / `UNLOCK` | RFC 4918 Class 2 | ❌ 未实现 |
| 部分检索（`address-data` + `CARDDAV:prop`） | §8.4 | ❌ 未实现（服务端基本也不支持） |
| `CARDDAV:limit` / `nresults` | §8.6.1–8.6.2 | ⚠️ 可以发，但服务端可能忽略；请自己截断 |

## 客户端的「必须」

RFC 6352 §3 要求**服务端**支持 §8 的全部 REPORT；对**客户端**，§9 只规定「怎么做才对」，
并不要求实现每一个方法。客户端真正需要的集合是：**发现 + `multiget` + `query` +
`PUT`/`GET`/`DELETE` + 条件写** —— 这正是本库覆盖的范围。再往上都属于便利功能。

## 刻意不做

| 不做 | 理由 |
|---|---|
| vCard 解析 | `Card.data` 必须与响应字节完全一致；一旦有解析器，调用方就会开始「顺手」改写 |
| 字段比较 / 合并 / 去重 | 这是产品决策而非协议问题，属于调用方（见 [sync.zh-CN.md](sync.zh-CN.md)） |
| 本地数据库、索引、缓存 | 会让库变成有状态，并掩盖服务端真实做了什么 |
| UID 生成 | 身份归服务端或调用方；本库只读写字节 |
| OAuth 2.0 授权码流程 | 不在范围内：传入你已拿到的 bearer token（`BearerAuth`） |
| 异步 API | 文档中的工作量用不上；HTTP 后端可插拔，将来加异步变体不会破坏同步 API |
| 调度 / free-busy | 那是 CalDAV，不是 CardDAV |

## 「未实现」是什么意思

意思是**本库没有暴露这个能力**。多数情况下你仍可用自己的 HTTP 客户端直接请求服务端 ——
但那时协议细节就归你负责，包括 [servers.zh-CN.md](servers.zh-CN.md) 里说的 `Depth` 差异与状态码处理。

与 `caldav` 的更完整对照（含我们选择不补的缺口）保存在仓库内的维护者笔记里。
