# Burrow 记忆库使用指南

## 核心能力

| 工具 | 何时使用 | 关键参数说明 |
|------|---------|-------------|
| `remember` | 用户讲新事、新想法、新记录时 | `content`(必填), `type`(可选,默认general), `event_time`(可选,事件真实时间), `fields`(类型专属字段,只传知道的即可), `importance`(1-10) |
| `recall` | 用户提及过去的事、需要信息时 | `query`(搜索关键词), `type`(限定类型), `domain`(限定领域), `max_results`, `date_from/date_to`(按event_time过滤) |
| `edit` | 用户发现记忆有误、需补充时 | `id`(必填), 只传需要修改的字段(空/默认值=不修改) |
| `forget` | 用户说"删掉/归档/不重要了"时 | `id`, `hard`(false=软归档/default, true=真删除) |
| `review` | 查看概览、检查类型统计、看近期记录 | `type`(空=概览), `period`(today/week/month/year) |
| `permanent` | 用户反复提到同一件事、需要长期保存时 | `action`(list/promote/demote/suggest), `id` |

## 使用原则

### 记录新信息
- **用户讲了一件事** → 立即 `remember(content=完整细节)`
- **用户只言片语** → 直接 `remember(content=原文)`，type 和 fields 不传也行
- **用户表达想法/感受** → `remember(type="thought", content=...)`
- **用户安排了待办** → `remember(type="todo", content=...)`
- **用户记录穿搭/饮食/经期** → 使用对应 type，fields 只填你知道的字段，不知道的留空
- **用户提到某个具体时间** → 将时间填入 `event_time` 参数

### 回忆信息
- **用户提到过去的话题** → 立刻 `recall(query="关键词")`
- **用户问"我上次..."** → `recall(query="上次的话题")`
- **需要检查待办** → `recall(type="todo")`
- **想了解某领域过往** → `recall(domain="编程/生活/健康")`

### 修改与管理
- **用户发现记忆有错误** → `edit(id=..., 只传要改的字段)`
- **用户说"这个不重要了"** → `forget(id=...)`(软归档)
- **用户说"彻底删掉"** → `forget(id=..., hard=True)`
- **重要的事被反复提及** → `permanent(action="promote", id=...)`

### 对话结束
- 检查待办：`recall(type="todo")`
- 检查今天记录：`recall(date_from="今天日期T00:00:00")`
- 系统概览：`review()`

## 记忆类型参考

| type | 用途 | 字段模板（全部可选，只填知道的）|
|------|------|------------------------------|
| general | 普通记忆，无特定结构 | 无固定字段 |
| journal | 日记/日志 | `{"mood":"心情"}` |
| thought | 想法/灵感 | 无固定字段 |
| todo | 待办事项 | 无固定字段 |
| outfit | 穿搭记录 | `{"top":"","bottom":"","shoes":"","weather":"","occasion":""}` |
| diet | 饮食记录 | `{"meal":"","foods":[],"location":"","rating":0}` |
| period | 经期记录 | `{"start_date":"","end_date":"","flow":0,"symptoms":[],"mood":""}` |

## 记忆格式说明

`recall()` 返回的每条记忆格式：
```
[event_time] [type] [domain] 标题 | 结构化信息 | ID:id
```

其中 `event_time` 是事件发生的真实时间（而非记录创建时间），`结构化信息` 会根据 type 自动展开为可读格式。

