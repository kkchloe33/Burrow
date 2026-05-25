"""
Burrow 嵌入模块 —— 调用 Gemini Embedding API 生成向量 + 语义搜索
"""

import httpx
import yaml
import os
import struct
import math
from pathlib import Path
from typing import Optional


class Embedder:
    """向量嵌入与语义搜索"""

    def __init__(self, config_path: str = "config.yaml"):
        self.enabled = False
        self.model = "text-embedding-004"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.api_key = ""
        self.client: httpx.AsyncClient | None = None
        self._load_config(config_path)

    def _load_config(self, config_path: str):
        """从 config.yaml 加载配置"""
        path = Path(config_path)
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        emb_cfg = cfg.get("embedding", {}) if cfg else {}
        self.enabled = emb_cfg.get("enabled", False)
        self.model = emb_cfg.get("model", self.model)
        self.base_url = emb_cfg.get("base_url", self.base_url)
        self.api_key = emb_cfg.get("api_key", "")
        if not self.api_key:
            self.api_key = os.environ.get("EMBEDDING_API_KEY", "")
            # 兼容旧的环境变量名
            if not self.api_key:
                self.api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            self.enabled = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client

    # ==================== 向量生成 ====================

    async def generate_embedding(self, text: str) -> Optional[list[float]]:
        """
        生成文本向量
        自动识别 API 格式：
        - base_url 含 "googleapis" → Gemini 原生格式
        - 其他 → OpenAI 兼容格式
        返回 float 列表，失败返回 None
        """
        if not self.enabled or not self.api_key:
            return None
        if not text.strip():
            return None

        try:
            client = await self._get_client()
            is_gemini = "googleapis" in self.base_url

            if is_gemini:
                # Gemini 原生格式
                url = f"{self.base_url.rstrip('/')}/models/{self.model}:embedContent?key={self.api_key}"
                payload = {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                }
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["embedding"]["values"]
            else:
                # OpenAI 兼容格式
                url = f"{self.base_url.rstrip('/')}/embeddings"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "input": text,
                }
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
        except Exception:
            return None

    @staticmethod
    def pack_embedding(vec: list[float]) -> bytes:
        """将 float 列表打包为二进制（4字节小端 × 维度数）"""
        return struct.pack(f"<{len(vec)}f", *vec)

    @staticmethod
    def unpack_embedding(data: bytes) -> list[float]:
        """从二进制解包为 float 列表"""
        n = len(data) // 4
        return list(struct.unpack(f"<{n}f", data))

    # ==================== 相似度计算 ====================

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def search_similar(
        self,
        query_vec: list[float],
        entries: list[dict],
        top_k: int = 10,
        min_score: float = 0.3,
    ) -> list[dict]:
        """
        在 entries 列表中按余弦相似度排序
        返回带 _score 字段的结果列表（仅包含有 embedding 的条目）
        """
        results = []
        for entry in entries:
            emb_data = entry.get("embedding")
            if emb_data is None:
                continue
            try:
                entry_vec = self.unpack_embedding(emb_data)
            except Exception:
                continue
            score = self.cosine_similarity(query_vec, entry_vec)
            if score >= min_score:
                entry_copy = dict(entry)
                entry_copy["_score"] = score
                results.append(entry_copy)
        results.sort(key=lambda x: x["_score"], reverse=True)
        return results[:top_k]

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None
