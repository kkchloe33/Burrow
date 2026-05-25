# Burrow 兔子洞 🐇

> **你的私人记忆库** — 跑在手机上，通过 MCP 协议接入 AI 聊天客户端。

Burrow 是一个**个人记忆库系统**，运行在安卓手机的 Termux 环境中。它通过 **Streamable HTTP** 协议接入 Rikkahub 等 AI 聊天客户端，让 AI 拥有长期的跨对话记忆能力。

- **给 Rikkahub 用**：MCP Streamable HTTP 协议，手机后台运行，AI 对话时自动调用
- **给人类看**：自带的 Web 前端，手机浏览器就能访问
- **数据在你手里**：SQLite 单文件数据库，备份即复制

## ✨ 能力

| 工具 | 功能 | AI 什么时候用 |
|------|------|-------------|
| `remember` | 记住一条新记忆 | 用户讲了新事、新想法时自动调用 |
| `recall` | 回忆过去 | 聊到过去的话题时，搜关键词回忆 |
| `edit` | 修改记忆 | 用户发现记错了、想补充时 |
| `forget` | 归档/删除 | 用户说"这个不重要了" |
| `review` | 系统概览 | 想看看最近有啥、检查待办时 |
| `permanent` | 永久记忆管理 | 用户反复提同一件事，设成永久 |

## 🧩 记忆类型

| 类型 | 图标 | 用途 | 专属字段 |
|------|------|------|----------|
| `general` | 📄 | 普通记忆 | — |
| `journal` | 📝 | 日记/日志 | 心情 |
| `thought` | 💡 | 想法/灵感 | — |
| `todo` | 📋 | 待办事项 | — |
| `outfit` | 👗 | 穿搭记录 | 上装、下装、鞋子、配饰、天气、心情、场合 |
| `diet` | 🍽️ | 饮食记录 | 餐别、食物、饮品、地点、同行人、评分 |
| `period` | 🩸 | 经期记录 | 开始日期、结束日期、流量、症状、心情、备注 |

## 🏗️ 架构

```
手机 Termux 环境
┌──────────────────────────────────────────────┐
│  burrow/                                      │
│  ├── server.py      ← MCP 服务器 (Streamable HTTP)  ─┬─→ Rikkahub (AI 客户端)
│  ├── web_server.py  ← Web 服务器（可选）              └─→ 手机浏览器
│  ├── db.py          ← SQLite 数据库层
│  ├── tagger.py      ← LLM 自动打标（DeepSeek）
│  ├── embedder.py    ← 语义搜索（Gemini）
│  ├── config.yaml    ← 配置文件
│  ├── data/burrow.db ← 你的全部记忆数据
│  └── static/        ← Web 前端
└──────────────────────────────────────────────┘
```

## 🔧 技术栈

- **Python 3** — 全量后端
- **MCP (Model Context Protocol)** — Streamable HTTP 传输
- **SQLite + FTS5** — 本地数据库，trigram 分词器支持中文
- **DeepSeek API** — 自动打标（提取关键词标签 + 情感坐标）
- **Gemini Embedding API** — 语义向量搜索
- **httpx / uvicorn** — 异步 HTTP

## 📄 许可证

MIT
