"""
Burrow MCP 服务器 —— 兔子洞记忆库的核心
通过 MCP 协议接入 Rikkahub，提供 6 个工具：
  remember / recall / edit / forget / review / permanent
"""

import asyncio
import json
import math
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from db import BurrowDB, now_iso
from tagger import Tagger
from embedder import Embedder

# ==================== 初始化 ====================

# 配置文件路径：优先当前目录，其次脚本所在目录
CONFIG_PATH = "config.yaml"
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = str(Path(__file__).parent / "config.yaml")

# 加载服务器配置
_server_cfg = {"transport": "streamable-http", "host": "0.0.0.0", "port": 8000}
if os.path.exists(CONFIG_PATH):
    import yaml
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
        _cfg = yaml.safe_load(_f) or {}
    _svr = _cfg.get("server", {})
    _server_cfg["transport"] = _svr.get("transport", _server_cfg["transport"])
    _server_cfg["host"] = _svr.get("host", _server_cfg["host"])
    _server_cfg["port"] = int(_svr.get("port", _server_cfg["port"]))

_transport = _server_cfg["transport"]
if _transport == "stdio":
    mcp = FastMCP("Burrow")
else:
    mcp = FastMCP("Burrow", host=_server_cfg["host"], port=_server_cfg["port"])

db = BurrowDB()
tagger = Tagger(CONFIG_PATH)
embedder = Embedder(CONFIG_PATH)

# ==================== 辅助函数 ====================

def _serialize(entry: dict) -> dict:
    """将数据库行转为 JSON 安全字典（去掉二进制 embedding）"""
    result = {}
    for k, v in entry.items():
        if k == "embedding":
            result[k] = True if v else False  # 只告诉前端有没有向量
        elif k.startswith("_"):
            result[k] = v
        else:
            result[k] = v
    return result


def _format_entry(entry: dict) -> str:
    """
    将一条记忆格式化为省 token 的可读文本
    格式：[event_time] [type] 标题 | 结构化信息 | ID:id
    不包含已归档/永久标记（由场景决定）
    """
    eid = entry["id"]
    etype = entry["type"]
    # 优先用 event_time，没有则用 created_at
    raw_time = entry.get("event_time") or entry["created_at"]
    event_time = raw_time[:10] if raw_time else "?"
    title = entry.get("title") or entry.get("content", "")[:30]

    # 按 type 展开 fields dict 为可读文本
    fields_str = ""
    f_dict = entry.get("fields", {})
    if f_dict:
        try:
            if etype == "outfit":
                parts = []
                if f_dict.get("top"): parts.append(f_dict["top"])
                if f_dict.get("bottom"): parts.append(f_dict["bottom"])
                if f_dict.get("shoes"): parts.append(f_dict["shoes"])
                fields_str = f" |穿搭:{'+'.join(parts)}" if parts else ""
            elif etype == "diet":
                foods = f_dict.get("foods", [])
                if isinstance(foods, list):
                    foods_str = ",".join(str(f) for f in foods)[:20]
                else:
                    foods_str = str(foods)[:20]
                fields_str = f" |吃:{foods_str}" if foods_str else ""
            elif etype == "period":
                start = str(f_dict.get("start_date", ""))[:10]
                end = str(f_dict.get("end_date", ""))[:10]
                flow = f_dict.get("flow", "")
                parts = []
                if start and end:
                    try:
                        from datetime import datetime
                        sd = datetime.fromisoformat(start)
                        ed = datetime.fromisoformat(end)
                        day = (ed - sd).days + 1
                        parts.append(f"第{day}天")
                    except: pass
                if flow:
                    parts.append(f"流量:{flow}")
                fields_str = f" |{'|'.join(parts)}" if parts else ""
            elif etype == "journal":
                mood = f_dict.get("mood", "")
                if mood:
                    fields_str = f" |心情:{mood}"
            elif etype == "bowel":
                parts = []
                if f_dict.get("consistency"): parts.append(f"性状:{f_dict['consistency']}")
                if f_dict.get("color"): parts.append(f"颜色:{f_dict['color']}")
                if f_dict.get("time"): parts.append(f"时间:{f_dict['time']}")
                fields_str = f" |便便:{'|'.join(parts)}" if parts else ""
        except (TypeError, ValueError):
            pass

    # 正文预览（前100字）
    content_preview = (entry.get("content") or "")[:100]
    content_str = f" |{content_preview}" if content_preview else ""

    return f"[{event_time}] [{etype}] {title}{content_str}{fields_str} | ID:{eid}"


def _calculate_score(entry: dict) -> float:
    """
    搜索排序加权分（简化版）：
    - 时间亲近：event_time 越近越高（指数衰减，0~5分）
    - 重要度：0~10分
    总分 0~15
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # 时间亲近分
    raw_time = entry.get("event_time") or entry.get("created_at", "")
    try:
        evt = datetime.fromisoformat(raw_time)
        days_ago = max(0, (now - evt).total_seconds() / 86400)
        time_score = math.exp(-0.02 * days_ago) * 5.0
    except (ValueError, TypeError):
        time_score = 0.0

    # 重要度分
    imp_score = float(entry.get("importance", 5))

    return time_score + imp_score


# ==================== MCP 工具 ====================

@mcp.tool()
async def remember(
    content: str,
    type: str = "general",
    title: str = "",
    fields: str = "{}",
    importance: int = 5,
    is_permanent: bool = False,
    event_time: str = "",
) -> str:
    """
    记住一条新记忆。主模型只需传入内容，系统自动打标、分析情感、生成向量。

    Args:
        content: 记忆正文内容
        type: 记忆类型，可选 general/journal/thought/todo/outfit/diet/period/bowel，默认 general
        title: 可选标题（不传则自动取正文前30字）
        fields: JSON字符串，类型专属结构化字段
        importance: 重要度 1-10，默认 5
        is_permanent: 是否设为永久记忆
        event_time: 记忆事件发生的真实时间（ISO格式），不传则默认当前时间
    """
    # 解析 fields
    try:
        fields_dict = json.loads(fields) if fields else {}
    except json.JSONDecodeError:
        fields_dict = {}

    # 标题为空时取内容前 30 字
    if not title:
        title = content.strip()[:30]

    # LLM 打标（异步）- 现在返回 dict: {tags, domain, valence, arousal}
    tag_result = await tagger.extract_tags(content)
    tags = tag_result.get("tags", "")
    domain = tag_result.get("domain", "")
    valence = tag_result.get("valence", 0.5)
    arousal = tag_result.get("arousal", 0.3)

    # 生成向量（异步）
    emb_bytes = None
    if embedder.enabled:
        vec = await embedder.generate_embedding(content)
        if vec:
            emb_bytes = embedder.pack_embedding(vec)

    # event_time：AI 指定或默认当前时间
    evt = event_time if event_time else None

    # 写入数据库
    entry = db.create_entry(
        content=content,
        type=type,
        title=title,
        fields=fields_dict,
        tags=tags,
        domain=domain,
        valence=valence,
        arousal=arousal,
        event_time=evt,
        importance=importance,
        is_permanent=is_permanent,
        embedding=emb_bytes,
    )

    return f"\u5df2\u8bb0\u4f4f [{entry['type']}] {entry['title']} (ID:{entry['id']})"


@mcp.tool()
async def recall(
    query: str = "",
    type: str = "",
    domain: str = "",
    max_results: int = 10,
    include_archived: bool = False,
    date_from: str = "",
    date_to: str = "",
) -> str:
    """
    回忆记忆。聊到某个话题时，AI 自动调用此工具搜索相关记忆。

    无参数时：返回近期重要记忆（按时间+重要度混合排序）
    有 query 时：双层搜索（关键词 + 语义），全局搜索所有类型
    有 type 时：精确查询该类型
    有 domain 时：预筛该主题领域

    Args:
        query: 搜索关键词（为空则返回默认浮现的记忆）
        type: 限定类型
        domain: 限定主题领域（如"编程/生活/健康"）
        max_results: 最大返回条数，默认 10
        include_archived: 是否包含已归档记忆，默认 False
        date_from: 起始时间（ISO格式），按 event_time 过滤
        date_to: 结束时间（ISO格式），按 event_time 过滤
    """
    # 数据库召回
    entries = db.recall(
        query=query if query else None,
        type=type if type else None,
        domain=domain if domain else None,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None,
        max_results=50 if query else max_results,
        include_archived=include_archived,
    )

    # 如果有 query 且 embedding 开启：FTS5 + 全局向量搜索 → 合并去重 → 加权排序
    if query and embedder.enabled:
        query_vec = await embedder.generate_embedding(query)
        if query_vec:
            # 全局向量搜索（从数据库所有有向量的条目中）
            sem_results = embedder.search_similar_global(query_vec, db, top_k=20)
            # 合并去重：FTS5 结果 + 向量结果
            sem_ids = {e["id"] for e in sem_results}
            merged = entries.copy()
            for e in sem_results:
                if e["id"] not in sem_ids:
                    merged.append(e)
            entries = merged

    # 按加权分数排序
    for e in entries:
        e["_score"] = _calculate_score(e)
    entries.sort(key=lambda e: e["_score"], reverse=True)

    entries = entries[:max_results]

    if not entries:
        return "没有找到相关记忆。"

    lines = [_format_entry(e) for e in entries]
    result = "\n".join(lines)

    # 经期预测：如果查询涉及经期或有 period 类型记忆
    should_predict = (
        (query and any(kw in query for kw in ["\u7ecf\u671f", "\u6708\u7ecf", "\u751f\u7406\u671f", "\u5927\u59d1\u5988", "period"]))
        or type == "period"
    )
    if should_predict:
        period_prediction = _predict_period()
        if period_prediction:
            result += "\n---\n" + period_prediction

    return result


def _predict_period() -> str:
    """
    经期预测：基于历史 period 记录计算当前周期和下次预测
    """
    from datetime import datetime, timezone, timedelta

    # 获取最近 3 条 period 记录（按 event_time 排序）
    periods = db.recall(type="period", max_results=3, include_archived=False)
    if not periods:
        return ""

    # 按 event_time/created_at 排序（最新的在前）
    periods.sort(key=lambda e: e.get("event_time") or e.get("created_at", ""), reverse=True)

    lines = []
    now = datetime.now(timezone.utc)

    for p in periods:
        fields = p.get("fields", {}) or {}
        if not fields:
            continue

        start = fields.get("start_date", "")
        end = fields.get("end_date", "")
        if not start or not end:
            continue

        try:
            sd = datetime.fromisoformat(start)
            ed = datetime.fromisoformat(end)
        except (ValueError, TypeError):
            continue

        # 当前是否在经期中
        if sd <= now <= ed + timedelta(days=1):
            day_num = (now - sd).days + 1
            lines.append(f"\u5f53\u524d\u7ecf\u671f:\u7b2c{day_num}\u5929")

        # 计算周期长度
        if len(periods) >= 2:
            p1_fields = periods[0].get("fields", {}) or {}
            p2_fields = periods[1].get("fields", {}) or {}
            if p1_fields and p2_fields:
                try:
                    s1 = datetime.fromisoformat(str(p1_fields.get("start_date", "")))
                    s2 = datetime.fromisoformat(str(p2_fields.get("start_date", "")))
                    cycle_days = (s2 - s1).days
                    if cycle_days > 0 and cycle_days < 60:
                        next_start = ed + timedelta(days=cycle_days)
                        remaining = (next_start - now).days
                        if remaining > 0:
                            lines.append(f"\u9884\u8ba1\u4e0b\u6b21:\u8fd8\u6709{remaining}\u5929")
                        elif remaining == 0:
                            lines.append("\u9884\u8ba1\u4eca\u5929\u5f00\u59cb")
                except (ValueError, TypeError):
                    pass

        break  # 只处理最新一条

    if lines:
        return "\u7ecf\u671f\u9884\u6d4b: " + " | ".join(lines)
    return ""


@mcp.tool()
async def forget(id: str, hard: bool = False) -> str:
    """
    淡忘一条记忆。

    Args:
        id: 记忆 ID（从 remember 或 recall 返回结果中获取）
        hard: 是否真删除（默认 false = 软归档，仍可搜索但日常不浮现）
    """
    entry = db.get_entry(id)
    if not entry:
        return f"未找到记忆 (ID:{id})"

    if hard:
        db.delete_entry(id)
        return f"已永久删除 [{entry['type']}] {entry['title']}"
    else:
        db.archive_entry(id)
        return f"已归档 [{entry['type']}] {entry['title']}（仍可通过 search 找到）"


@mcp.tool()
async def edit(
    id: str,
    title: str = "",
    content: str = "",
    type: str = "",
    fields: str = "",
    tags: str = "",
    domain: str = "",
    importance: int = 0,
    event_time: str = "",
    valence: float = -1.0,
    arousal: float = -1.0,
) -> str:
    """
    修改一条已有记忆。只传需要修改的字段，不传的保留原值。

    Args:
        id: 记忆 ID（必填）
        title: 新标题（空=不修改）
        content: 新内容（空=不修改）
        type: 新类型（空=不修改）
        fields: 新 JSON 字段（空=不修改）
        tags: 新标签（空=不修改）
        domain: 新领域（空=不修改）
        importance: 新重要度 1-10（0=不修改）
        event_time: 新事件时间（空=不修改）
        valence: 新情感效价 0~1（-1=不修改）
        arousal: 新唤醒度 0~1（-1=不修改）
    """
    entry = db.get_entry(id)
    if not entry:
        return f"未找到记忆 (ID:{id})"

    updates = {}

    if title:
        updates["title"] = title
    if content:
        updates["content"] = content
        # 内容变了，重新打标和生成向量
        tag_result = await tagger.extract_tags(content)
        if tag_result.get("tags"):
            updates["tags"] = tag_result["tags"]
        if tag_result.get("domain"):
            updates["domain"] = tag_result["domain"]
        if tag_result.get("valence", -1) >= 0:
            updates["valence"] = tag_result["valence"]
        if tag_result.get("arousal", -1) >= 0:
            updates["arousal"] = tag_result["arousal"]
        # 重新生成 embedding
        if embedder.enabled:
            vec = await embedder.generate_embedding(content)
            if vec:
                updates["embedding"] = embedder.pack_embedding(vec)
    if type:
        updates["type"] = type
    if fields:
        try:
            updates["fields"] = json.loads(fields)
        except json.JSONDecodeError:
            return f"fields 格式无效，应为 JSON 字符串"
    if tags:
        updates["tags"] = tags
    if domain:
        updates["domain"] = domain
    if importance > 0:
        updates["importance"] = min(10, max(1, importance))
    if event_time:
        updates["event_time"] = event_time
    if valence >= 0:
        updates["valence"] = max(0.0, min(1.0, valence))
    if arousal >= 0:
        updates["arousal"] = max(0.0, min(1.0, arousal))

    if not updates:
        return "没有需要修改的字段。请至少传入一个要修改的字段。"

    updated = db.update_entry(id, **updates)
    if not updated:
        return f"更新失败 (ID:{id})"

    return f"已修改 [{updated['type']}] {updated['title']} (ID:{updated['id']})"


@mcp.tool()
async def review(type: str = "", period: str = "week") -> str:
    """
    回望记忆。查看系统概览或某类型的近期列表。

    Args:
        type: 限定类型（为空则显示系统概览）
        period: 时间范围 today/week/month/year，默认 week
    """
    if not type:
        # 系统概览
        stats = db.stats()
        types = db.get_types()
        type_lines = []
        for t in types:
            count = stats["type_counts"].get(t["type"], 0)
            float_mark = " (浮动)" if t["floats_in_default"] else ""
            type_lines.append(f"  {t['icon']} {t['label']}: {count}条{float_mark}")

        return (
            f"Burrow 记忆库概览:\n"
            f"  总记忆: {stats['total']}条\n"
            f"  永久记忆: {stats['permanent']}条\n"
            f"  已归档: {stats['archived']}条\n"
            f"  最后活跃: {stats['last_active'] or '无'}\n"
            f"各类型统计:\n" + "\n".join(type_lines)
        )

    # 获取该类型近期记录
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    periods = {"today": 1, "week": 7, "month": 30, "year": 365}
    days = periods.get(period, 7)
    date_from = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")

    entries = db.recall(type=type, date_from=date_from, max_results=20)
    if not entries:
        return f"近期没有 {type} 类型的记忆。"

    lines = [_format_entry(e) for e in entries]
    return f"{type} 近期记忆 ({period}):\n" + "\n".join(lines)


@mcp.tool()
async def permanent(action: str = "list", id: str = "") -> str:
    """
    永久记忆管理。

    Args:
        action: 操作类型
            list     - 列出所有永久记忆
            promote  - 将一条记忆提升为永久（需提供 id）
            demote   - 取消永久标记（需提供 id）
            suggest  - 推荐可提升为永久的高重要度记忆
        id: 记忆 ID（promote/demote 时必填）
    """
    if action == "list":
        entries = db.list_permanent()
        if not entries:
            return "还没有永久记忆。重要度 >= 8 的记忆会被推荐提升。"
        lines = [_format_entry(e) for e in entries]
        return f"永久记忆 ({len(entries)}条):\n" + "\n".join(lines)

    elif action == "promote":
        if not id:
            return "请提供要提升的记忆 ID，例如 permanent(action='promote', id='abc123')"
        entry = db.set_permanent(id, True)
        if not entry:
            return f"未找到记忆 (ID:{id})"
        return f"已提升为永久记忆 [{entry['type']}] {entry['title']}"

    elif action == "demote":
        if not id:
            return "请提供要取消的记忆 ID"
        entry = db.set_permanent(id, False)
        if not entry:
            return f"未找到记忆 (ID:{id})"
        return f"已取消永久标记 [{entry['type']}] {entry['title']}"

    elif action == "suggest":
        candidates = db.suggest_permanent()
        if not candidates:
            return "没有符合条件的高重要度记忆（重要度 >= 8 且未归档）。"
        lines = [_format_entry(e) for e in candidates]
        return f"推荐提升为永久记忆:\n" + "\n".join(lines)

    else:
        return f"未知操作: {action}，可选: list / promote / demote / suggest"


# ==================== 启动 ====================

def main():
    """MCP 服务器启动"""
    transport = _server_cfg["transport"]
    host = _server_cfg["host"]
    port = _server_cfg["port"]

    print(f"Burrow 启动 | 传输: {transport}")
    if transport != "stdio":
        print(f"监听地址: http://{host}:{port}/mcp")
        print("请在 Rikkahub 中添加 MCP 服务器：")
        print(f"  类型: streamable-http")
        print(f"  URL:  http://127.0.0.1:{port}/mcp")

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
