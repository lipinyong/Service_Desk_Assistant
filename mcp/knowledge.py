"""
知识库 MCP 服务 - RAG 检索
从 Chroma 集合中检索与用户问题相关的文档，供 Agent 结合 MCP 工具进行运维。
"""
import asyncio
import os
import re
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
from mcp.chroma import ChromaClient

logger = logging.getLogger(__name__)
_kb_config_cache: Optional[Dict[str, Any]] = None


def _expand_env(s: str) -> str:
    if not isinstance(s, str) or "${" not in s:
        return s
    m = re.match(r"^\$\{([^:}]+)(?::-([^}]*))?\}$", s.strip())
    if m:
        key, default = m.group(1), (m.group(2) or "")
        return os.environ.get(key, default)
    return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), s)


def _get_kb_config() -> Dict[str, Any]:
    global _kb_config_cache
    if _kb_config_cache is not None:
        return _kb_config_cache
    config_path = _project_root / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        kb = raw.get("knowledge_base") or {}
        chroma_cfg = raw.get("chroma") or {}
        base_url = kb.get("chroma_base_url") or chroma_cfg.get("base_url") or "http://127.0.0.1:8000"
        if isinstance(base_url, str):
            base_url = _expand_env(base_url)
        _kb_config_cache = {
            "enabled": kb.get("enabled", True),
            "collection_name": kb.get("collection_name") or "ops_docs",
            "chroma_base_url": base_url,
            "n_results": int(kb.get("n_results") or 5),
        }
        return _kb_config_cache
    except Exception as e:
        logger.warning(f"加载知识库配置失败: {e}")
        _kb_config_cache = {"enabled": True, "collection_name": "ops_docs", "chroma_base_url": os.environ.get("CHROMA_BASE_URL", "http://127.0.0.1:8000"), "n_results": 5}
        return _kb_config_cache


async def knowledge_retrieve(
    query: str,
    n_results: Optional[int] = None,
    collection_name: Optional[str] = None,
    chroma_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = _get_kb_config()
    if not cfg.get("enabled", True):
        return {"success": False, "error": "知识库未启用", "documents": []}
    coll = collection_name or cfg["collection_name"]
    base_url = chroma_base_url or cfg["chroma_base_url"]
    n = n_results if n_results is not None else cfg["n_results"]
    client = ChromaClient(base_url)
    try:
        out = await asyncio.to_thread(client.query, coll, [query], n)
    except Exception as e:
        logger.exception(f"知识库检索失败: {e}")
        return {"success": False, "error": str(e), "documents": []}
    if not out.get("success"):
        return {"success": False, "error": out.get("error", "query failed"), "documents": []}
    raw_results = out.get("results") or {}
    ids = (raw_results.get("ids") or [[]])[0]
    docs = (raw_results.get("documents") or [[]])[0]
    metadatas = (raw_results.get("metadatas") or [[]])[0]
    distances = (raw_results.get("distances") or [[]])[0]
    documents = []
    for i, doc in enumerate(docs):
        meta = metadatas[i] if i < len(metadatas) else {}
        dist = distances[i] if i < len(distances) else None
        documents.append({"id": ids[i] if i < len(ids) else "", "content": doc, "metadata": meta, "distance": dist})
    return {"success": True, "collection": coll, "query": query, "n_results": len(documents), "documents": documents}


def register_tools() -> Dict[str, Any]:
    return {"retrieve": knowledge_retrieve}


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "knowledge_retrieve",
                "description": "从运维知识库中检索与问题相关的文档。回答运维、故障排查、部署等问题前，应优先调用此工具获取文档，再结合其他工具执行操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索问句或关键词"},
                        "n_results": {"type": "integer", "description": "返回文档条数"},
                        "collection_name": {"type": "string", "description": "集合名"},
                        "chroma_base_url": {"type": "string", "description": "Chroma 服务地址"},
                    },
                    "required": ["query"],
                },
            },
        },
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
