"""SQLite MCP 服务：连接、查询、执行、表列表（基于文件路径）"""
import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 路径 -> 连接（可选持久化，这里每次按 path 操作也可不缓存）
_connections: Dict[str, sqlite3.Connection] = {}
MAX_ROWS = 10000
MAX_RESULT_LENGTH = 50000


def _get_connection(path: str):
    """获取或创建 SQLite 连接（只读/读写由调用方控制）"""
    path = str(Path(path).resolve())
    if not Path(path).exists():
        return None, f"文件不存在: {path}"
    if path in _connections:
        return _connections[path], None
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        _connections[path] = conn
        return conn, None
    except Exception as e:
        return None, str(e)


def _execute_query_sync(path: str, query: str) -> Dict[str, Any]:
    conn, err = _get_connection(path)
    if err:
        return {"success": False, "error": err, "query": query}
    try:
        cur = conn.cursor()
        cur.execute(query)
        rows = [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()] if cur.description else []
        cur.close()
        if len(rows) > MAX_ROWS:
            rows = rows[:MAX_ROWS]
            note = f"结果已截断，仅返回前 {MAX_ROWS} 行"
        else:
            note = None
        return {"success": True, "query": query, "rows": rows, "row_count": len(rows), "note": note}
    except Exception as e:
        logger.error(f"SQLite 查询失败: {e}")
        return {"success": False, "query": query, "error": str(e)}


def _execute_statement_sync(path: str, statement: str) -> Dict[str, Any]:
    conn, err = _get_connection(path)
    if err:
        return {"success": False, "error": err, "statement": statement}
    try:
        cur = conn.cursor()
        cur.execute(statement)
        conn.commit()
        row_count = cur.rowcount
        cur.close()
        return {"success": True, "statement": statement, "row_count": row_count}
    except Exception as e:
        logger.error(f"SQLite 执行失败: {e}")
        if conn:
            conn.rollback()
        return {"success": False, "statement": statement, "error": str(e)}


def _get_tables_sync(path: str) -> Dict[str, Any]:
    conn, err = _get_connection(path)
    if err:
        return {"success": False, "error": err}
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        return {"success": True, "tables": tables, "path": path}
    except Exception as e:
        logger.error(f"获取 SQLite 表列表失败: {e}")
        return {"success": False, "error": str(e)}


def _get_schema_sync(path: str, table: Optional[str] = None) -> Dict[str, Any]:
    conn, err = _get_connection(path)
    if err:
        return {"success": False, "error": err}
    try:
        cur = conn.cursor()
        if table:
            cur.execute(f"PRAGMA table_info(`{table}`)")
            columns = [{"cid": r[0], "name": r[1], "type": r[2], "notnull": r[3], "default": r[4], "pk": r[5]} for r in cur.fetchall()]
            cur.close()
            return {"success": True, "table": table, "columns": columns, "path": path}
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        result = {}
        for t in tables:
            cur.execute(f"PRAGMA table_info(`{t}`)")
            result[t] = [{"name": r[1], "type": r[2]} for r in cur.fetchall()]
        cur.close()
        return {"success": True, "schema": result, "path": path}
    except Exception as e:
        logger.error(f"获取 SQLite schema 失败: {e}")
        return {"success": False, "error": str(e)}


def _close_sync(path: str) -> Dict[str, Any]:
    global _connections
    path = str(Path(path).resolve())
    if path in _connections:
        try:
            _connections[path].close()
        except Exception:
            pass
        del _connections[path]
        return {"success": True, "message": f"已关闭连接: {path}"}
    return {"success": True, "message": "连接不存在或已关闭"}


async def query(path: str, query: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_execute_query_sync, path, query)


async def execute(path: str, statement: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_execute_statement_sync, path, statement)


async def get_tables(path: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_tables_sync, path)


async def get_schema(path: str, table: str = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_get_schema_sync, path, table)


async def close(path: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_close_sync, path)


def register_tools() -> Dict[str, Any]:
    return {
        "query": query,
        "execute": execute,
        "get_tables": get_tables,
        "get_schema": get_schema,
        "close": close,
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "sqlite_query", "description": "对 SQLite 数据库执行查询（SELECT）", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "数据库文件路径，如 ./data/app.db"}, "query": {"type": "string", "description": "SQL 查询语句"}}, "required": ["path", "query"]}}},
        {"type": "function", "function": {"name": "sqlite_execute", "description": "对 SQLite 数据库执行语句（INSERT/UPDATE/DELETE 等）", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "数据库文件路径"}, "statement": {"type": "string", "description": "SQL 语句"}}, "required": ["path", "statement"]}}},
        {"type": "function", "function": {"name": "sqlite_get_tables", "description": "获取 SQLite 数据库中的表列表", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "数据库文件路径"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "sqlite_get_schema", "description": "获取 SQLite 表结构（列名、类型）；不传 table 时返回所有表的结构", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "table": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "sqlite_close", "description": "关闭指定路径的 SQLite 连接", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
