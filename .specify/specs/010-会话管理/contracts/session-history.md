# Contract: 历史会话

工作台继续使用现有会话接口。本契约只规定历史列表和打开一段聊天时读到的内容。

## 列出历史会话

`GET /api/v1/sessions`

每一项对应 [data-model.md](../data-model.md) 的一条历史会话条目：

| 字段 | 规则 |
| --- | --- |
| `session_id` | 会话标识 |
| `last_message` | 最近一次用户提问 |
| `last_activity_at` | 该次提问的时刻 |

顺序为 `last_activity_at` 从新到旧。没有用户提问的会话不返回。响应不包含其他会话的聊天记录。

## 打开一段会话

`GET /api/v1/sessions/{sid}`

- 返回该段全部用户提问，按发生顺序排列，字段沿用现有 `messages`（含 `turn_id`、`run_id`、`text`）。
- 不返回其他会话的 `messages`。
- 回答不在 `messages` 里重复存放。页面用这些提问的 `run_id` 读取现有运行事件，只把事件放进对应提问。
- 会话不存在时返回 404。页面说明暂时打不开，并保持当前已经显示的内容不被另一段替换。

## 继续与新开

- 继续聊天仍使用 `POST /api/v1/sessions/{sid}/turns`，消息写入该 `sid`。
- 新开一段仍使用 `POST /api/v1/sessions`。在第一条用户提问写入之前，它不出现在 `GET /api/v1/sessions`。
- 写入新提问后，再次列出时该条的 `last_message` 和 `last_activity_at` 改为这一次。

## 上次打开

浏览器只在本机保存上次打开的 `session_id`。它不是接口字段。重新打开页面时先拉列表，标识仍在列表中才请求 `GET /api/v1/sessions/{sid}`。

## 禁止

- 不得在列表响应中附带每一段的全部回答。
- 不得因为打开失败而返回另一段的 `messages`。
- 不得为历史列表新增删除、重命名或搜索接口。
