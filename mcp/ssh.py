"""SSH MCP 服务：远程主机执行命令与系统信息"""
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from module.ssh_manager import ssh_manager

ALLOWED_COMMANDS = [
    "ls", "cat", "head", "tail", "grep", "find", "du", "df",
    "ps", "top", "free", "uptime", "uname", "hostname", "whoami", "kill",
    "date", "systemctl", "service", "docker", "docker-compose",
    "netstat", "ss", "ip", "ifconfig", "ping", "curl", "wget",
    "apt-get", "apt", "yum", "dnf", "pip", "pip3", "nginx",
]


def is_command_allowed(command: str) -> bool:
    cmd = command.strip().split()[0] if command.strip() else ""
    for allowed in ALLOWED_COMMANDS:
        if cmd.startswith(allowed.split()[0]):
            return True
    return False


async def ssh_list_hosts() -> Dict[str, Any]:
    return {"success": True, "hosts": ssh_manager.list_hosts()}


async def ssh_add_host(alias: str, host: str, port: int = 22, username: str = "root",
                       password: str = None, key_file: str = None, name: str = None) -> Dict[str, Any]:
    if not alias or not host:
        return {"success": False, "error": "alias 和 host 是必需的"}
    ssh_manager.add_host(alias=alias, host=host, port=port, username=username,
                         password=password, key_file=key_file, name=name)
    return {"success": True, "message": f"主机 {alias} 添加成功"}


async def ssh_remove_host(alias: str) -> Dict[str, Any]:
    if not alias:
        return {"success": False, "error": "alias 是必需的"}
    ssh_manager.remove_host(alias)
    return {"success": True, "message": f"主机 {alias} 已移除"}


async def ssh_execute(alias: str, command: str) -> Dict[str, Any]:
    if not alias or not command:
        return {"success": False, "error": "alias 和 command 是必需的"}
    if not is_command_allowed(command):
        return {"success": False, "error": f"命令不在白名单中: {command}。仅支持: {', '.join(ALLOWED_COMMANDS[:12])}..."}
    result = ssh_manager.execute(alias, command)
    return result


async def ssh_get_metrics(alias: str) -> Dict[str, Any]:
    if not alias:
        return {"success": False, "error": "alias 是必需的"}
    metrics = ssh_manager.get_metrics(alias)
    if "error" in metrics:
        return {"success": False, **metrics}
    return {"success": True, "metrics": metrics}


async def ssh_get_system_info(alias: str) -> Dict[str, Any]:
    if not alias:
        return {"success": False, "error": "alias 是必需的"}
    info = ssh_manager.get_system_info(alias)
    if "error" in info:
        return {"success": False, **info}
    return {"success": True, "info": info}


def register_tools() -> Dict[str, Any]:
    return {
        "list_hosts": ssh_list_hosts,
        "add_host": ssh_add_host,
        "remove_host": ssh_remove_host,
        "execute": ssh_execute,
        "get_metrics": ssh_get_metrics,
        "get_system_info": ssh_get_system_info,
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "ssh_list_hosts", "description": "列出所有已配置的 SSH 主机", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "ssh_add_host", "description": "添加 SSH 主机", "parameters": {"type": "object", "properties": {"alias": {"type": "string"}, "host": {"type": "string"}, "port": {"type": "integer"}, "username": {"type": "string"}, "password": {"type": "string"}, "key_file": {"type": "string"}, "name": {"type": "string"}}, "required": ["alias", "host"]}}},
        {"type": "function", "function": {"name": "ssh_remove_host", "description": "移除 SSH 主机", "parameters": {"type": "object", "properties": {"alias": {"type": "string"}}, "required": ["alias"]}}},
        {"type": "function", "function": {"name": "ssh_execute", "description": "在指定 SSH 主机上执行白名单命令（ls, cat, df, ps, top 等）", "parameters": {"type": "object", "properties": {"alias": {"type": "string"}, "command": {"type": "string"}}, "required": ["alias", "command"]}}},
        {"type": "function", "function": {"name": "ssh_get_metrics", "description": "获取主机系统指标（CPU、内存、磁盘）", "parameters": {"type": "object", "properties": {"alias": {"type": "string"}}, "required": ["alias"]}}},
        {"type": "function", "function": {"name": "ssh_get_system_info", "description": "获取主机系统信息（主机名、操作系统、内核等）", "parameters": {"type": "object", "properties": {"alias": {"type": "string"}}, "required": ["alias"]}}},
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
