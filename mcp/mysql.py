"""MySQL MCP 服务：连接、查询、执行、库表列表、服务器信息"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import mysql.connector
except ImportError:
    mysql = None


class MySQLService:
    def __init__(self):
        self.connections: Dict[str, Any] = {}

    def _connect_sync(self, host: str, port: int, user: str, password: str, database: Optional[str]) -> Dict[str, Any]:
        if mysql is None:
            return {"success": False, "error": "未安装 mysql-connector-python，请 pip install mysql-connector-python"}
        try:
            conn = mysql.connector.connect(
                host=host, port=port, user=user, password=password, database=database
            )
            conn_id = f"{host}:{port}:{user}:{database or ''}"
            self.connections[conn_id] = conn
            cur = conn.cursor()
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.close()
            return {"success": True, "message": "连接成功", "conn_id": conn_id, "server_version": version,
                    "host": host, "port": port, "user": user, "database": database}
        except Exception as e:
            logger.error(f"连接 MySQL 失败: {e}")
            return {"success": False, "error": str(e)}

    def _disconnect_sync(self, conn_id: str) -> Dict[str, Any]:
        try:
            if conn_id in self.connections:
                self.connections[conn_id].close()
                del self.connections[conn_id]
                return {"success": True, "message": "断开连接成功"}
            return {"success": False, "error": "连接不存在"}
        except Exception as e:
            logger.error(f"断开 MySQL 连接失败: {e}")
            return {"success": False, "error": str(e)}

    def _execute_query_sync(self, conn_id: str, query: str) -> Dict[str, Any]:
        try:
            if conn_id not in self.connections:
                return {"success": False, "error": "连接不存在"}
            conn = self.connections[conn_id]
            cur = conn.cursor(dictionary=True)
            cur.execute(query)
            rows = cur.fetchall()
            columns = [i[0] for i in cur.description] if cur.description else []
            cur.close()
            return {"success": True, "query": query, "rows": rows, "columns": columns, "row_count": len(rows)}
        except Exception as e:
            logger.error(f"执行 MySQL 查询失败: {e}")
            return {"success": False, "query": query, "error": str(e)}

    def _execute_statement_sync(self, conn_id: str, statement: str) -> Dict[str, Any]:
        try:
            if conn_id not in self.connections:
                return {"success": False, "error": "连接不存在"}
            conn = self.connections[conn_id]
            cur = conn.cursor()
            cur.execute(statement)
            conn.commit()
            row_count = cur.rowcount
            cur.close()
            return {"success": True, "statement": statement, "row_count": row_count}
        except Exception as e:
            logger.error(f"执行 MySQL 语句失败: {e}")
            if conn_id in self.connections:
                self.connections[conn_id].rollback()
            return {"success": False, "statement": statement, "error": str(e)}

    def _get_server_info_sync(self, conn_id: str) -> Dict[str, Any]:
        try:
            if conn_id not in self.connections:
                return {"success": False, "error": "连接不存在"}
            conn = self.connections[conn_id]
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT VERSION() as version")
            version = cur.fetchone()
            cur.close()
            return {"success": True, "version": version}
        except Exception as e:
            logger.error(f"获取 MySQL 服务器信息失败: {e}")
            return {"success": False, "error": str(e)}


mysql_service = MySQLService()


async def connect(host: str, port: int = 3306, user: str = "root", password: str = "", database: str = None) -> Dict[str, Any]:
    return await asyncio.to_thread(mysql_service._connect_sync, host, port, user, password, database)


async def disconnect(conn_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(mysql_service._disconnect_sync, conn_id)


async def query(conn_id: str, query: str) -> Dict[str, Any]:
    return await asyncio.to_thread(mysql_service._execute_query_sync, conn_id, query)


async def execute(conn_id: str, statement: str) -> Dict[str, Any]:
    return await asyncio.to_thread(mysql_service._execute_statement_sync, conn_id, statement)


async def get_databases(conn_id: str) -> Dict[str, Any]:
    return await query(conn_id, "SHOW DATABASES")


async def get_tables(conn_id: str, database: str = None) -> Dict[str, Any]:
    q = f"SHOW TABLES FROM `{database}`" if database else "SHOW TABLES"
    return await query(conn_id, q)


async def get_server_info(conn_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(mysql_service._get_server_info_sync, conn_id)


def register_tools() -> Dict[str, Any]:
    return {
        "connect": connect,
        "disconnect": disconnect,
        "query": query,
        "execute": execute,
        "get_databases": get_databases,
        "get_tables": get_tables,
        "get_server_info": get_server_info,
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "mysql_connect", "description": "连接到 MySQL 数据库", "parameters": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}, "user": {"type": "string"}, "password": {"type": "string"}, "database": {"type": "string"}}, "required": ["host", "password"]}}},
        {"type": "function", "function": {"name": "mysql_disconnect", "description": "断开 MySQL 连接", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}}, "required": ["conn_id"]}}},
        {"type": "function", "function": {"name": "mysql_query", "description": "执行 MySQL 查询（SELECT）", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}, "query": {"type": "string"}}, "required": ["conn_id", "query"]}}},
        {"type": "function", "function": {"name": "mysql_execute", "description": "执行 MySQL 语句（INSERT/UPDATE/DELETE 等）", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}, "statement": {"type": "string"}}, "required": ["conn_id", "statement"]}}},
        {"type": "function", "function": {"name": "mysql_get_databases", "description": "获取 MySQL 数据库列表", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}}, "required": ["conn_id"]}}},
        {"type": "function", "function": {"name": "mysql_get_tables", "description": "获取 MySQL 表列表", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}, "database": {"type": "string"}}, "required": ["conn_id"]}}},
        {"type": "function", "function": {"name": "mysql_get_server_info", "description": "获取 MySQL 服务器信息", "parameters": {"type": "object", "properties": {"conn_id": {"type": "string"}}, "required": ["conn_id"]}}},
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
