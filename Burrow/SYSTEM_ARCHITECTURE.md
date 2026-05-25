# Burrow 系统架构与运转流程

## 一、系统概览

Burrow（兔子洞）是一个**个人记忆库系统**，以 MCP（Model Context Protocol）服务器的形式接入 AI 聊天客户端（如 Rikkahub），同时提供独立的 Web 前端界面。

### 核心理念

- **AI 自动记录**：对话中用户提及的任何信息，AI 通过 `remember` 工具自动存入
- **智能浮现**：AI 在相关话题时自动 `recall` 相关记忆，无参数时按时间+重要度浮现代办和近期重要记忆
- **类型化存储**：7 种预设类型（general/journal/thought/todo/outfit/diet/period），每种有专属结构化字段模板
- **多维搜索**：FTS5 全文搜索 + 语义搜索（向量）+ 类型/领域/时间过滤

---

## 二、系统模块依赖关系

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Rikkahub (AI客户端)                          │
│              通过 MCP 协议 (Streamable HTTP) 调用工具                 │
└────────────────────────────┬────────────────────────────────────────┘
                             │ MCP 工具调用
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│   server.py (MCP 服务器)                    │  web_server.py (Web)  │
│   FastMCP 框架                              │  HTTP REST API        │
│   ┌──────────────────────────────────┐     │  ┌──────────────────┐  │
│   │ remember / recall / edit         │     │  │ GET /api/entries │  │
│   │ forget / review / permanent      │     │  │ POST /api/entries│  │
│   └──────────┬───────────┬───────────┘     │  │ PUT/DELETE ...   │  │
│              │           │                  │  └────────┬─────────┘  │
└──────────────┼───────────┼──────────────────┼───────────┼────────────┘
               │           │                  │           │
     ┌─────────▼──┐  ┌────▼──────┐    ┌──────▼──────┐   │
     │ tagger.py  │  │ embedder  │    │  db.py      │   │
     │ (LLM打标)   │  │ .py       │    │  (数据库层)  │   │
     │            │  │ (向量生成) │    │             │   │
     │ DeepSeek   │  │ Gemini    │    │  SQLite     │   │
     │ Chat API   │  │ Embedding │    │  .db        │   │
     └────────────┘  └───────────┘    └─────────────┘   │
                                        │               │
                                        ▼               ▼
                               ┌──────────────────────────────┐
                               │      SQLite Database          │
                               │  burrow/data/burrow.db        │
                               │  ┌────────────┐               │
                               │  │ entries    │ ← 记忆主表     │
                               │  │ type_config│ ← 类型配置     │
                               │  │ entries_fts│ ← FTS5全文索引 │
                               │  └────────────┘               │
                               └──────────────────────────────┘

                                 （外部 API 调用）
    ┌─────────────────┐         ┌─────────────────────┐
    │ DeepSeek Chat   │ ←────── │ tagger.py 调用      │
    │ 关键词/情感提取  │         │ (LLM打标)            │
    └─────────────────┘         └─────────────────────┘

    ┌─────────────────┐         ┌─────────────────────┐
    │ Gemini          │ ←────── │ embedder.py 调用     │
    │ Embedding API   │         │ (语义向量生成)        │
    └─────────────────┘         └─────────────────────┘

    ┌─────────────────┐
    │ 浏览器前端       │ ←────── web_server.py
    │ index.html      │         (静态文件+ REST API)
    │ app.js / style  │
    └─────────────────┘
```

---

## 三、核心模块详解

### 3.1 db.py —— 数据库层

**职责**：SQLite 操作封装，建表、CRUD、FTS5 全文搜索、类型配置管理

**核心表结构**：

```sql
entries (
    id TEXT PK,           -- 12位hex UUID
    type TEXT,            -- general/journal/thought/todo/outfit/diet/period
    title TEXT,
    content TEXT NOT NULL,
    fields TEXT,          -- JSON字符串，类型专属结构化字段
    tags TEXT,            -- 逗号分隔的关键词标签
    domain TEXT,          -- 主题领域：编程/生活/健康...
    valence REAL,         -- 情感效价 0~1
    arousal REAL,         -- 唤醒度 0~1
    event_time TEXT,      -- 事件真实发生时间（ISO格式）
    embedding BLOB,       -- 向量嵌入（二进制packed）
    importance INTEGER,   -- 重要度 1~10
    is_permanent INTEGER, -- 是否永久记忆
    is_archived INTEGER,  -- 是否已归档
    created_at TEXT,
    updated_at TEXT
)

type_config (type, label, icon, floats_in_default, fields_schema, sort_order)
-- 类型配置：类型名/展示标签/图标/是否浮现在无参recall/字段JSON Schema/排序

entries_fts -- FTS5 虚拟表（trigram分词器，支持中文）
  -- 索引字段：title, content, tags（外部内容表，关联 entries.rowid）
```

**关键技术决策**：
- FTS5 使用 `trigram` 分词器 + 预处理函数 `_tokenize_for_fts` 在中文字符间插入空格，实现中文分词
- FTS5 是"外部内容表"模式（`content=entries`），不复制数据，通过 rowid 关联
- FTS5 未命中时回退到 LIKE 模糊匹配作为兜底
- `is_archived` 在搜索中默认排除，`include_archived=True` 可包含

### 3.2 tagger.py —— 打标模块

**职责**：调用外部 LLM（默认 DeepSeek Chat）自动提取：
- **关键词标签**（10~15 个，含原文提取 + 语义扩展）
- **主题领域**（domain，如"编程/生活/健康"）
- **情感坐标**（valence + arousal）

**调用流程**：

```
remember(content)
  → tagger.extract_tags(content)
    → POST DeepSeek Chat API (system prompt + user prompt)
    → 解析返回格式: 标签... | domain:X | valence:Y | arousal:Z
    → 返回 {tags, domain, valence, arousal}
```

**策略**：
- 内容 < 20 字符不调用（节省 token）
- 无 API key 则禁用，返回默认值
- temperature=0.3，max_tokens=200

### 3.3 embedder.py —— 向量嵌入模块

**职责**：调用 Gemini Embedding API 生成语义向量 + 余弦相似度搜索

**调用流程**：

```
remember(content)
  → embedder.generate_embedding(content)
    → POST Gemini Embedding API
    → pack_embedding(vec) → bytes → 存入 embedding 字段

recall(query)
  → query 非空 + embedding 启用
    → embedder.generate_embedding(query)
    → embedder.search_similar(query_vec, entries, top_k=10)
      → 对每条有 embedding 的记忆计算余弦相似度
      → 返回相似度 >= 0.3 的结果，按相似度排序
```

**技术实现**：
- 向量以二进制 `struct.pack("<Nf", ...)` 紧凑存储
- 搜索时先 FTS5，再对结果做语义重排序
- 语义结果优先，其余 FTS5 结果补充

### 3.4 server.py —— MCP 服务器

**职责**：提供 6 个 MCP 工具，供 AI 客户端调用

| 工具 | 触发场景 |
|------|----------|
| `remember` | 用户讲新事、新想法、新记录 |
| `recall` | 用户提及过去的事、需要信息时自动搜索 |
| `edit` | 用户发现记忆有误、需补充 |
| `forget` | 用户说"删掉/归档/不重要了" |
| `review` | 查看概览、类型统计 |
| `permanent` | 管理永久记忆 |

### 3.5 web_server.py —— Web 前端服务器

**职责**：提供 REST API + 静态文件服务，手机/PC 浏览器可直接访问

**REST API 端点**：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/types` | 所有类型配置+各类型计数 |
| GET | `/api/entries?type=&period=` | 记忆列表（按类型+周期过滤） |
| GET | `/api/entries/{id}` | 单条记忆详情 |
| GET | `/api/search?q=` | 全文搜索 |
| GET | `/api/permanent` | 永久记忆列表 |
| GET | `/api/stats` | 系统概览统计 |
| POST | `/api/entries` | 新增记忆 |
| PUT | `/api/entries/{id}` | 更新记忆 |
| DELETE | `/api/entries/{id}` | 删除记忆 |

### 3.6 config.yaml —— 配置文件

```yaml
# 完整配置项
tagger:
  enabled: true/false
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com/v1"
  api_key: "sk-..."

embedding:
  enabled: true/false
  model: "text-embedding-004"
  api_key: "your-gemini-api-key"

server:
  transport: "streamable-http"  # streamable-http / sse / stdio
  host: "0.0.0.0"
  port: 8000

database:
  path: "./data/burrow.db"
```

---

## 四、关键业务流程

### 4.1 记忆写入流程（remember）

```
AI 调用 remember(content="今天面试穿了白衬衫...")

1. tagger.extract_tags(content)
   └─→ DeepSeek: "面试,白衬衫,穿搭..." | domain:工作 | valence:0.6 | arousal:0.5

2. embedder.generate_embedding(content)
   └─→ Gemini Embedding API → [0.123, -0.456, ...]

3. db.create_entry(params)
   └─→ INSERT INTO entries (id,type,title,content,fields,tags,domain,valence,arousal,event_time,embedding,...)
   └─→ INSERT INTO entries_fts (rowid,title,content,tags)  ← 中文分词预处理后

4. 返回 "[journal] 今天面试穿了白衬衫 (ID:abc123)"
```

### 4.2 记忆召回流程（recall）

```
场景 A：无参数 recall()

  1. 第1层：今天所有记忆（importance DESC, event_time DESC，取5条）
  2. 第2层：昨天 importance≥6 的记忆（取3条）
  3. 第3层：近7天 importance≥7 的记忆（取2条）
  4. 第4层：浮动类型（floats_in_default=1，如 todo）不限时间（取3条）
  5. 合并去重 → 按 _calculate_score 排序 → 取 max_results 条


场景 B：有 query（如 recall(query="面试")）

  1. FTS5 搜索（trigram）→ 未命中则 LIKE 兜底
  2. 按 domain 过滤（如果传了 domain）
  3. 语义搜索增强（如果 embedding 启用）：
     - 对 query 生成 query_vec
     - 对搜索结果中带 embedding 的条目算余弦相似度
     - 语义结果优先，FTS5 结果补充
  4. _calculate_score 加权排序（时间衰减 + 重要度）
  5. 触发经期预测（如果 query 含"经期/period"等关键词）


场景 C：按 type 查询（如 recall(type="todo")）

  1. 精确匹配 type + is_archived=0
  2. 按 event_time DESC 排序
  3. 取 max_results 条


场景 D：按 domain 查询

  1. domain LIKE '%关键词%'
  2. 可与 type 组合、与日期范围组合


加权排序算法 _calculate_score(entry)：

  time_score = e^(-0.02 * 距今天数) × 5.0    ← 时间亲近指数衰减
  imp_score = importance (0~10)
  total_score = time_score + imp_score (0~15)
```

### 4.3 编辑流程（edit）

```
AI 调用 edit(id="abc123", content="修正后的内容")

1. 获取原记忆 → 检查存在性
2. 如果 content 变了 → 自动重新打标（tags/domain/valence/arousal）→ 重新生成 embedding
3. 字段合并 → UPDATE entries SET ...
4. 如果 title/content/tags 变了 → 同步更新 FTS5 索引
5. 返回 "已修改 [...]"
```

### 4.4 删除/归档流程（forget）

```
AI 调用 forget(id="abc123", hard=False)

soft=false（默认）→ 软归档：
  1. is_archived=1
  2. 日常 recall 不浮现，但仍可通过 search 找到

hard=true → 真删除：
  1. DELETE FROM entries_fts WHERE rowid=?
  2. DELETE FROM entries WHERE id=?
  3. 不可恢复
```

### 4.5 经期预测流程

```
recall(query="经期") 或 recall(type="period") 时触发

1. 获取最近 3 条 period 记录（按 event_time 排序）
2. 解析 fields 中的 start_date / end_date
3. 判断：当前是否在经期中 → "当前经期:第X天"
4. 计算：如果 ≥2 条记录 → 算周期长度 → 预测下次 → "预计下次:还有X天"
5. 追加在 recall 结果的 "---" 后面
```

### 4.6 永久记忆管理流程

```
permanent(action="suggest")
  → 推荐 importance≥8 且未归档的记忆

permanent(action="promote", id="abc123")
  → is_permanent=1，recall() 中变为"不受时间衰减影响"

permanent(action="demote", id="abc123")
  → is_permanent=0

permanent(action="list")
  → 列出所有永久记忆
```

---

## 五、数据流总图

```
┌─────────────┐     remember()     ┌──────────────────┐
│  AI对话     │ ──────────────────→ │ tagger (LLM打标) │──→  tags/domain/valence/arousal
│  (Rikkahub) │                    └──────────────────┘
│             │                    ┌──────────────────┐
│             │ ──────────────────→ │ embedder (向量)   │──→ embedding (binary)
│             │                    └──────────────────┘
│             │                    ┌──────────────────┐
│             │ ←──────────────────│  db.create_entry │──→ entries 表 + entries_fts
│             │     "已记住..."    └──────────────────┘
│             │
│             │     recall()       ┌──────────────────┐
│             │ ──────────────────→ │ db.recall()      │──→ FTS5 / 语义搜索 / 排序
│             │                    └──────────────────┘
│             │                    ┌──────────────────┐
│             │ ←──────────────────│ _calculate_score │──→ 格式化输出
│             │     [event_time]..  └──────────────────┘
└─────────────┘

┌─────────────┐                  ┌──────────────────┐
│  Web 前端   │ ─── REST API ──→ │ web_server.py    │──→ db.py (read-only CRUD)
│  浏览器     │ ←─────────────── │ JSON response    │
└─────────────┘                  └──────────────────┘
```

## 六、部署与运行

两种运行模式：

### MCP 服务器（供 AI 客户端连接）

```bash
python server.py
# 启动后监听 http://0.0.0.0:8000/mcp
# 在 Rikkahub 中添加 Streamable HTTP MCP 服务器
```

### Web 服务器（用户端直接查看/管理）

```bash
python web_server.py
# 启动后访问 http://localhost:8080
# 手机/PC 浏览器均可访问
```

### 配置项

- `config.yaml` 控制 tagger/embedding/server/database 开关和参数
- API key 支持从环境变量 `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` 读取
- tagger 或 embedding 关闭时，功能降级但系统正常工作

---

## 七、局限与待优化

1. **情感字段未利用**：`valence`/`arousal` 已存储但未被搜索或展示使用，未来可做情感趋势图
2. **fields 不可搜索**：结构化字段（outfit 的上装/下装等）不在 FTS5 索引中，无法直接搜索
3. **中文搜索精度**：FTS5 trigram 对中文的召回率有限，依赖 LIKE 兜底
4. **单线程**：SQLite 单实例，高并发需外部上锁
5. **向量搜索范围小**：语义搜索仅在前一步 FTS5 的结果集内重排序，不是全局向量搜索
