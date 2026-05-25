"""
Burrow 打标模块 —— 调用 LLM 提取关键词标签
仅做关键词提取，不分析情感/领域/唤醒度
"""

import httpx
import yaml
import os
from pathlib import Path

# ==================== 打标 Prompt ====================

TAGGER_SYSTEM_PROMPT = """你是一个记忆整理助手。用户会给你一段个人记录的内容，请你：

第一步——精准提取：从原文抽取 3~5 个真正的核心词标签
第二步——引申扩展：自动补充 8~10 个语义相关词（近义词、上位词、关联场景词）
两步合并为一个标签列表，总计 10~15 个

同时分析以下信息：
- domain：主题领域（1-2个词），可选：编程/生活/健康/学习/社交/娱乐/财务/旅行/美食/运动/家庭/工作/情感/购物/出行/宠物/艺术/其他
- valence：情感效价 0~1，0=消极 0.5=中性 1=积极
- arousal：唤醒度 0~1，0=平静 0.5=普通 1=激动

输出严格遵循以下格式（单行，不要换行、不要多余解释）：
标签,列表,逗号分隔 | domain:主题领域 | valence:0.X | arousal:0.Y

示例：
面试,白衬衫,牛仔裤,穿搭,求职,正装,通勤,职场,会议,约会,日常,休闲,搭配,风格 | domain:生活,工作 | valence:0.6 | arousal:0.5"""

TAGGER_USER_PROMPT = "请为以下内容提取关键词标签、主题领域和情感坐标，严格按格式返回：\n\n{content}"


class Tagger:
    """关键词标签提取器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.enabled = False
        self.model = "deepseek-chat"
        self.base_url = "https://api.deepseek.com/v1"
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
        tagger_cfg = cfg.get("tagger", {}) if cfg else {}
        self.enabled = tagger_cfg.get("enabled", False)
        self.model = tagger_cfg.get("model", self.model)
        self.base_url = tagger_cfg.get("base_url", self.base_url)
        self.api_key = tagger_cfg.get("api_key", "")
        # 也检查环境变量
        if not self.api_key:
            self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        # 没有 API key 则禁用
        if not self.api_key:
            self.enabled = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client

    async def extract_tags(self, content: str) -> dict:
        """
        从内容中提取关键词标签、领域、情感坐标

        Returns:
            dict: {
                "tags": "逗号分隔的标签字符串",
                "domain": "领域字符串",
                "valence": float,
                "arousal": float
            }
            失败返回含空值字典
        """
        result = {"tags": "", "domain": "", "valence": 0.5, "arousal": 0.3}

        if not self.enabled or not self.api_key:
            return result

        # 内容太短不值得打标
        if len(content.strip()) < 20:
            return result

        try:
            client = await self._get_client()
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": TAGGER_SYSTEM_PROMPT},
                    {"role": "user", "content": TAGGER_USER_PROMPT.format(content=content)},
                ],
                "temperature": 0.3,
                "max_tokens": 200,
            }
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # 解析结构化输出: 标签... | domain:X | valence:Y | arousal:Z
            # 先按 | 分割
            parts = [p.strip() for p in raw.split("|")]
            tags_raw = parts[0] if len(parts) > 0 else ""

            # 解析 domain
            domain = ""
            for p in parts[1:]:
                if p.lower().startswith("domain:") or p.lower().startswith("domain："):
                    domain = p.split(":", 1)[-1].split("：", 1)[-1].strip()
                    break

            # 解析 valence
            valence = 0.5
            for p in parts[1:]:
                if p.lower().startswith("valence:") or p.lower().startswith("valence："):
                    try:
                        valence = float(p.split(":", 1)[-1].split("：", 1)[-1].strip())
                        valence = max(0.0, min(1.0, valence))
                    except (ValueError, IndexError):
                        valence = 0.5
                    break

            # 解析 arousal
            arousal = 0.3
            for p in parts[1:]:
                if p.lower().startswith("arousal:") or p.lower().startswith("arousal："):
                    try:
                        arousal = float(p.split(":", 1)[-1].split("：", 1)[-1].strip())
                        arousal = max(0.0, min(1.0, arousal))
                    except (ValueError, IndexError):
                        arousal = 0.3
                    break

            # 清洗标签
            tags_raw = tags_raw.replace("、", ",").replace("，", ",")
            tags_raw = tags_raw.strip("。，'\",")
            result["tags"] = tags_raw
            result["domain"] = domain
            result["valence"] = valence
            result["arousal"] = arousal
            return result

        except Exception:
            return result

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None


# 便捷同步封装（用于不想写 async 的场景）
def extract_tags_sync(content: str, config_path: str = "config.yaml") -> dict:
    """同步提取标签（内部封装异步调用）"""
    import asyncio
    tagger = Tagger(config_path)
    try:
        return asyncio.run(tagger.extract_tags(content))
    except Exception:
        return ""
