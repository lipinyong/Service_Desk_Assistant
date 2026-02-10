import logging
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger(__name__)


class ChromaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def ping(self) -> Dict[str, Any]:
        try:
            response = self.session.get(f"{self.base_url}/api/v1/ping")
            response.raise_for_status()
            return {"success": True, "response": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_collection(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/collections",
                json={"name": name, "metadata": metadata or {}}
            )
            response.raise_for_status()
            return {"success": True, "collection": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_collections(self) -> Dict[str, Any]:
        try:
            response = self.session.get(f"{self.base_url}/api/v1/collections")
            response.raise_for_status()
            return {"success": True, "collections": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add(self, collection_name: str, ids: List[str], documents: List[str],
            embeddings: Optional[List[List[float]]] = None,
            metadatas: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/collections/{collection_name}/add",
                json={"ids": ids, "documents": documents, "embeddings": embeddings, "metadatas": metadatas}
            )
            response.raise_for_status()
            return {"success": True, "response": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def query(self, collection_name: str, query_texts: List[str], n_results: int = 5,
              where: Optional[Dict[str, Any]] = None,
              where_document: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/collections/{collection_name}/query",
                json={"query_texts": query_texts, "n_results": n_results, "where": where, "where_document": where_document}
            )
            response.raise_for_status()
            return {"success": True, "results": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}


def register_tools() -> Dict[str, Any]:
    _clients = {}

    async def ping(base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        if base_url not in _clients:
            _clients[base_url] = ChromaClient(base_url)
        return _clients[base_url].ping()

    async def create_collection(name: str, metadata: Optional[Dict[str, Any]] = None, base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        if base_url not in _clients:
            _clients[base_url] = ChromaClient(base_url)
        return _clients[base_url].create_collection(name, metadata)

    async def list_collections(base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        if base_url not in _clients:
            _clients[base_url] = ChromaClient(base_url)
        return _clients[base_url].list_collections()

    async def add(collection_name: str, ids: List[str], documents: List[str],
                  embeddings: Optional[List[List[float]]] = None,
                  metadatas: Optional[List[Dict[str, Any]]] = None, base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        if base_url not in _clients:
            _clients[base_url] = ChromaClient(base_url)
        return _clients[base_url].add(collection_name, ids, documents, embeddings, metadatas)

    async def query(collection_name: str, query_texts: List[str], n_results: int = 5,
                    where: Optional[Dict[str, Any]] = None, where_document: Optional[Dict[str, Any]] = None,
                    base_url: str = "http://127.0.0.1:8000") -> Dict[str, Any]:
        if base_url not in _clients:
            _clients[base_url] = ChromaClient(base_url)
        return _clients[base_url].query(collection_name, query_texts, n_results, where, where_document)

    return {"ping": ping, "create_collection": create_collection, "list_collections": list_collections, "add": add, "query": query}


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "chroma_ping", "description": "检查Chroma服务是否可用", "parameters": {"type": "object", "properties": {"base_url": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "chroma_create_collection", "description": "创建Chroma集合", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "metadata": {"type": "object"}, "base_url": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "chroma_list_collections", "description": "列出所有Chroma集合", "parameters": {"type": "object", "properties": {"base_url": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "chroma_add", "description": "向Chroma集合中添加文档", "parameters": {"type": "object", "properties": {"collection_name": {"type": "string"}, "ids": {"type": "array", "items": {"type": "string"}}, "documents": {"type": "array", "items": {"type": "string"}}, "base_url": {"type": "string"}}, "required": ["collection_name", "documents"]}}},
        {"type": "function", "function": {"name": "chroma_query", "description": "查询Chroma集合中的文档", "parameters": {"type": "object", "properties": {"collection_name": {"type": "string"}, "query_texts": {"type": "array", "items": {"type": "string"}}, "n_results": {"type": "integer"}, "base_url": {"type": "string"}}, "required": ["collection_name", "query_texts"]}}},
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
