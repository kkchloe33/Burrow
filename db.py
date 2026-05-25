"""
Burrow 数据库层 —— SQLite 操作封装
负责建表、CRUD、全文搜索、类型配置管理
"""

import sqlite3
import uuid
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional


def _tokenize_for_fts(text: str) -> str:
    """中文分词预处理：在中文字符间插入空格，使 FTS5 trigram 能正确匹配"""
    # 在 CJK 字符前后插入空格
    result = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            result.append(f' {ch} ')
        else:
            result.append(ch)
    # 合并多余空格
    return re.sub(r'\s+', ' ', ''.join(result)).strip()


# 获取东八区时间戳字符串
def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class BurrowDB:
    """Burrow 数据库封装"""

    def __init__(self, db_path: str = "./burrow.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()
        self._init_type_config()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """将数据库行转为dict，并自动解析fields JSON为dict"""
        d = dict(row)
        if isinstance(d.get("fields"), str):
            try:
                d["fields"] = json.loads(d["fields"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ==================== 初始化 ====================

    def _init_tables(self):
        """建表"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'general',
                title TEXT,
                content TEXT NOT NULL,
                fields TEXT DEFAULT '{}',
                tags TEXT DEFAULT '',
                domain TEXT DEFAULT '',
                valence REAL DEFAULT 0.5,
                arousal REAL DEFAULT 0.3,
                event_time TEXT,
                embedding BLOB,
                importance INTEGER DEFAULT 5,
                is_permanent INTEGER DEFAULT 0,
                is_archived INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS type_config (
                type TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                icon TEXT DEFAULT '',
                floats_in_default INTEGER DEFAULT 0,
                fields_schema TEXT DEFAULT '{}',
                sort_order INTEGER DEFAULT 0
            );

            -- FTS5 全文搜索（外部内容表，trigram 分词器支持中文）
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                title, content, tags,
                tokenize='trigram',
                content=entries, content_rowid=rowid
            );
        """)
        # 兼容旧表：如果表已存在但缺少新字段，用 ALTER 添加（忽略已存在错误）
        new_columns = [
            "ALTER TABLE entries ADD COLUMN domain TEXT DEFAULT ''",
            "ALTER TABLE entries ADD COLUMN valence REAL DEFAULT 0.5",
            "ALTER TABLE entries ADD COLUMN arousal REAL DEFAULT 0.3",
            "ALTER TABLE entries ADD COLUMN event_time TEXT",
        ]
        for stmt in new_columns:
            try:
                self.conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # 字段已存在

        # 为已有 todo 类型补上 done 字段
        try:
            self.conn.execute(
                "UPDATE type_config SET fields_schema='{\"done\":false}' WHERE type='todo' AND fields_schema='{}'"
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def _init_type_config(self):
        """初始化预设类型（幂等，已存在则跳过）"""
        defaults = [
            ("general", "普通", "📄", 0, '{}', 0),
            ("journal", "日记", "📝", 0, '{"mood":""}', 2),
            ("thought", "想法", "💡", 0, '{}', 3),
            ("todo",    "待办", "📋", 1, '{"done":false}', 4),
            ("outfit",  "穿搭", "👗", 0,
             '{"top":"","bottom":"","shoes":"","accessories":"","weather":"","mood":"","occasion":""}', 5),
            ("diet",    "饮食", "🍽️", 0,
             '{"meal":"","foods":[],"drink":"","location":"","with_who":"","rating":0}', 6),
            ("period",  "经期", "🩸", 0,
             '{"start_date":"","end_date":"","flow":0,"symptoms":[],"mood":"","notes":""}', 7),
            ("bowel",   "排便", "💩", 0,
             '{"time":"","consistency":"","color":"","note":""}', 8),
        ]
        for t in defaults:
            self.conn.execute(
                "INSERT OR IGNORE INTO type_config(type,label,icon,floats_in_default,fields_schema,sort_order) "
                "VALUES(?,?,?,?,?,?)", t
            )
        self.conn.commit()

    # ==================== CRUD ====================

    def create_entry(
        self,
        content: str,
        type: str = "general",
        title: Optional[str] = None,
        fields: Optional[dict] = None,
        tags: str = "",
        domain: str = "",
        valence: float = 0.5,
        arousal: float = 0.3,
        event_time: Optional[str] = None,
        importance: int = 5,
        is_permanent: bool = False,
        embedding: Optional[bytes] = None,
    ) -> dict:
        """创建一条记忆，返回完整记录"""
        eid = uuid.uuid4().hex[:12]
        ts = now_iso()
        evt = event_time or ts
        fields_json = json.dumps(fields or {}, ensure_ascii=False)

        self.conn.execute(
            """INSERT INTO entries(id,type,title,content,fields,tags,domain,
               valence,arousal,event_time,embedding,
               importance,is_permanent,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, type, title, content, fields_json, tags, domain,
             valence, arousal, evt, embedding,
             importance, int(is_permanent), ts, ts)
        )
        # 同步 FTS5 索引（中文预分词）
        row = self.conn.execute("SELECT rowid FROM entries WHERE id=?", (eid,)).fetchone()
        if row:
            self.conn.execute(
                "INSERT INTO entries_fts(rowid,title,content,tags) VALUES(?,?,?,?)",
                (row["rowid"], _tokenize_for_fts(title or ""),
                 _tokenize_for_fts(content), _tokenize_for_fts(tags))
            )
        self.conn.commit()
        return self.get_entry(eid)

    def get_entry(self, eid: str) -> Optional[dict]:
        """获取单条记忆"""
        row = self.conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        return self._row_to_dict(row) if row else None

    def update_entry(self, eid: str, **kwargs) -> Optional[dict]:
        """更新记忆字段"""
        allowed = {"title","content","fields","tags","domain","valence","arousal","event_time","importance","is_permanent","is_archived","embedding"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_entry(eid)

        updates["updated_at"] = now_iso()
        if "fields" in updates and isinstance(updates["fields"], dict):
            updates["fields"] = json.dumps(updates["fields"], ensure_ascii=False)

        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [eid]
        self.conn.execute(f"UPDATE entries SET {sets} WHERE id=?", vals)

        # 同步 FTS5（如果文本字段有变化）
        if any(k in updates for k in ("title","content","tags")):
            row = self.conn.execute("SELECT rowid,title,content,tags FROM entries WHERE id=?", (eid,)).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE entries_fts SET title=?,content=?,tags=? WHERE rowid=?",
                    (_tokenize_for_fts(row["title"] or ""),
                     _tokenize_for_fts(row["content"]),
                     _tokenize_for_fts(row["tags"] or ""),
                     row["rowid"])
                )
        self.conn.commit()
        return self.get_entry(eid)

    def delete_entry(self, eid: str):
        """真删除"""
        row = self.conn.execute("SELECT rowid FROM entries WHERE id=?", (eid,)).fetchone()
        if row:
            self.conn.execute("DELETE FROM entries_fts WHERE rowid=?", (row["rowid"],))
        self.conn.execute("DELETE FROM entries WHERE id=?", (eid,))
        self.conn.commit()

    def archive_entry(self, eid: str):
        """软归档（标记为已归档，不删除）"""
        return self.update_entry(eid, is_archived=1)

    def set_permanent(self, eid: str, permanent: bool = True):
        """设为/取消永久记忆"""
        return self.update_entry(eid, is_permanent=int(permanent))

    # ==================== 搜索与召回 ====================

    def search_fts(self, query: str, limit: int = 20, include_archived: bool = False) -> list[dict]:
        """
        FTS5 全文关键词搜索 + LIKE 中文兜底
        先尝试 FTS5 trigram，如果没命中且含中文则回退到 LIKE 模糊匹配

        Args:
            include_archived: 是否包含已归档的记忆，默认 False
        """
        archived_filter = "" if include_archived else "AND e.is_archived=0"
        rows = self.conn.execute(
            f"""SELECT e.* FROM entries_fts f
               JOIN entries e ON e.rowid = f.rowid
               WHERE entries_fts MATCH ? {archived_filter}
               ORDER BY rank
               LIMIT ?""",
            (_tokenize_for_fts(query), limit)
        ).fetchall()

        # FTS5 对中文命中率低时，用 LIKE 兜底
        if len(rows) == 0:
            like_pattern = f"%{query}%"
            archived_filter_sql = "" if include_archived else "AND is_archived=0"
            rows = self.conn.execute(
                f"""SELECT * FROM entries
                   WHERE (title LIKE ? OR content LIKE ? OR tags LIKE ?)
                   {archived_filter_sql}
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (like_pattern, like_pattern, like_pattern, limit)
            ).fetchall()

        return [self._row_to_dict(r) for r in rows]

    def recall(
        self,
        query: Optional[str] = None,
        type: Optional[str] = None,
        domain: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_results: int = 10,
        include_archived: bool = False,
    ) -> list[dict]:
        """
        回忆 —— 核心召回函数

        - 无参数：返回近期重要记忆（按 event_time + importance 混合排序）
        - 有 type：精确查该类型
        - 有 query：全局 FTS5 搜索
        - 有 domain：预筛领域
        - date_from/date_to 基于 event_time 过滤
        """
        if query:
            # 全局搜索模式
            entries = self.search_fts(query, max_results * 2, include_archived)
            if domain:
                entries = [e for e in entries if domain in e.get("domain", "")]
            return entries[:max_results]

        conditions = []
        params = []

        if not include_archived:
            conditions.append("is_archived=0")

        if domain:
            conditions.append("domain LIKE ?")
            params.append(f"%{domain}%")

        if type:
            conditions.append("type=?")
            params.append(type)
        else:
            # 无 type 时：取未归档 + 未永久的
            conditions.append("is_permanent=0")

        if date_from:
            conditions.append("event_time>=?")
            params.append(date_from)
        if date_to:
            conditions.append("event_time<=?")
            params.append(date_to)

        where = " AND ".join(conditions) if conditions else "1=1"

        if query is None and type is None:
            # 无参 recall：全类型加权浮动
            # 取近30天 + 高重要度记忆，统一按时间衰减+重要度加权排序
            # 未完成的待办记忆将被提升到最前
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
            future = (now + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")

            rows = self.conn.execute(
                f"""SELECT * FROM entries WHERE {where}
                   AND (event_time >= ? OR event_time IS NULL OR importance >= 6)
                   AND event_time < ?
                   ORDER BY importance DESC, event_time DESC
                   LIMIT ?""",
                params + [month_ago, future, 50]
            ).fetchall()

            import math
            entries = [self._row_to_dict(r) for r in rows]
            for e in entries:
                raw_time = e.get("event_time") or e.get("created_at", "")
                try:
                    evt = datetime.fromisoformat(str(raw_time))
                    days_ago = max(0, (now - evt).total_seconds() / 86400)
                    time_score = math.exp(-0.02 * days_ago) * 5.0
                except (ValueError, TypeError):
                    time_score = 0.0
                imp_score = float(e.get("importance", 5))
                score = time_score + imp_score

                # 未完成待办 → 大权重提升，确保排在最前
                if e.get("type") == "todo":
                    f = e.get("fields", {}) or {}
                    if not isinstance(f, dict):
                        try:
                            f = json.loads(f) if isinstance(f, str) else {}
                        except (json.JSONDecodeError, TypeError):
                            f = {}
                    if not f.get("done", False):
                        score += 20

                e["_score"] = score

            entries.sort(key=lambda x: x["_score"], reverse=True)
            entries = entries[:max_results]
        else:
            # 有 type 限定：按 event_time DESC 排序
            order_field = "COALESCE(event_time, created_at)"
            rows = self.conn.execute(
                f"SELECT * FROM entries WHERE {where} ORDER BY {order_field} DESC LIMIT ?",
                params + [max_results]
            ).fetchall()
            entries = [self._row_to_dict(r) for r in rows]

        return [self._row_to_dict(r) for r in entries]

    # ==================== 类型管理 ====================

    def get_types(self) -> list[dict]:
        """获取所有类型配置（按 sort_order 排序）"""
        rows = self.conn.execute(
            "SELECT * FROM type_config ORDER BY sort_order"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_type_counts(self) -> dict:
        """获取各类型记忆数量统计"""
        rows = self.conn.execute(
            "SELECT type, COUNT(*) as count FROM entries WHERE is_archived=0 GROUP BY type"
        ).fetchall()
        return {r["type"]: r["count"] for r in rows}

    # ==================== 永久记忆 ====================

    def list_permanent(self) -> list[dict]:
        """列出所有永久记忆"""
        rows = self.conn.execute(
            "SELECT * FROM entries WHERE is_permanent=1 ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def suggest_permanent(self) -> list[dict]:
        """推荐可提升为永久记忆的条目（重要度>=8 且未归档）"""
        rows = self.conn.execute(
            "SELECT * FROM entries WHERE importance>=8 AND is_permanent=0 AND is_archived=0 "
            "ORDER BY importance DESC, created_at DESC LIMIT 10"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]



    # ==================== 统计与概览 ====================

    def stats(self) -> dict:
        """系统概览统计"""
        total = self.conn.execute("SELECT COUNT(*) FROM entries WHERE is_archived=0").fetchone()[0]
        permanent = self.conn.execute("SELECT COUNT(*) FROM entries WHERE is_permanent=1").fetchone()[0]
        archived = self.conn.execute("SELECT COUNT(*) FROM entries WHERE is_archived=1").fetchone()[0]
        last_active = self.conn.execute(
            "SELECT MAX(updated_at) FROM entries"
        ).fetchone()[0]
        return {
            "total": total,
            "permanent": permanent,
            "archived": archived,
            "last_active": last_active,
            "type_counts": self.get_type_counts(),
        }

    def get_all_with_embedding(self, include_archived: bool = False) -> list[dict]:
        """获取所有有 embedding 向量的记忆（用于全局语义搜索）"""
        archived_filter = "" if include_archived else "AND is_archived=0"
        rows = self.conn.execute(
            f"SELECT * FROM entries WHERE embedding IS NOT NULL {archived_filter}"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def close(self):
        self.conn.close()
