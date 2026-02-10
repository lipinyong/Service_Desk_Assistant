"""Shell MCP 服务：本地命令执行（白名单 + 危险命令过滤）"""
import asyncio
import subprocess
import shlex
import logging
import os
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf /*", ":(){ :|:& };:", "> /dev/sda", "mkfs.", "dd if=/dev/zero",
    "chmod -R 777 /", "chown -R", "sudo rm", "sudo dd", "sudo mkfs", "sudo chmod",
    "shutdown", "reboot", "init 0", "init 6", "halt", "poweroff", ":(){", "fork bomb",
]
BLOCKED_COMMANDS = [
    "sudo", "su", "passwd", "useradd", "userdel", "groupadd", "groupdel", "visudo",
    "mount", "umount", "fdisk", "mkfs", "fsck", "iptables", "firewall-cmd", "systemctl", "service", "init", "telinit",
]
MAX_TIMEOUT = 60
DEFAULT_TIMEOUT = 30
MAX_OUTPUT_LENGTH = 50000


def is_command_safe(command: str) -> tuple:
    command_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in command_lower:
            return False, f"检测到危险命令模式: {pattern}"
    parts = shlex.split(command)
    if not parts:
        return False, "空命令"
    base_cmd = os.path.basename(parts[0])
    if base_cmd in BLOCKED_COMMANDS:
        return False, f"命令被禁止: {base_cmd}"
    if base_cmd == "rm":
        if "-rf" in parts and ("/" in parts or "/*" in parts or ".." in parts):
            return False, "禁止递归删除根目录或上级目录"
        if any(p.startswith("/") and p.count("/") <= 2 for p in parts[1:] if not p.startswith("-")):
            return False, "禁止删除系统级目录"
    return True, ""


async def execute_command(
    command: str,
    working_dir: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
    confirm_delete: bool = False,
) -> Dict[str, Any]:
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        logger.warning(f"命令被拒绝: {command}, 原因: {reason}")
        return {"success": False, "error": reason, "command": command}
    parts = shlex.split(command)
    base_cmd = os.path.basename(parts[0]) if parts else ""
    if base_cmd == "rm" and len(parts) > 1:
        if not any(p in ["--help", "-h"] for p in parts) and not confirm_delete:
            return {"success": False, "error": "删除命令需要确认。请设置 confirm_delete=True 来执行此操作", "command": command}
    if timeout > MAX_TIMEOUT:
        timeout = MAX_TIMEOUT
    work_dir = working_dir or os.getcwd()
    if not os.path.isdir(work_dir):
        return {"success": False, "error": f"工作目录不存在: {work_dir}", "command": command}
    logger.info(f"执行命令: {command}, 目录: {work_dir}, 超时: {timeout}s")
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env={**os.environ, **(env or {})},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"success": False, "error": f"命令执行超时 ({timeout}秒)", "command": command, "return_code": -1}
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        if len(stdout_str) > MAX_OUTPUT_LENGTH:
            stdout_str = stdout_str[:MAX_OUTPUT_LENGTH] + f"\n... (输出被截断，总长度: {len(stdout_str)})"
        if len(stderr_str) > MAX_OUTPUT_LENGTH:
            stderr_str = stderr_str[:MAX_OUTPUT_LENGTH] + f"\n... (输出被截断，总长度: {len(stderr_str)})"
        return {
            "success": process.returncode == 0,
            "command": command,
            "return_code": process.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "working_dir": work_dir,
        }
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        return {"success": False, "error": str(e), "command": command}


async def execute_script(
    script: str,
    interpreter: str = "bash",
    working_dir: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    if interpreter not in ["bash", "sh", "python", "python3"]:
        return {"success": False, "error": f"不支持的解释器: {interpreter}", "allowed": ["bash", "sh", "python", "python3"]}
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in script.lower():
            return {"success": False, "error": f"脚本包含危险模式: {pattern}"}
    for cmd in BLOCKED_COMMANDS:
        if cmd in script.split():
            return {"success": False, "error": f"脚本包含被禁止的命令: {cmd}"}
    full_command = f"{interpreter} -c {shlex.quote(script)}"
    return await execute_command(full_command, working_dir, timeout)


def register_tools() -> Dict[str, Any]:
    return {"execute": execute_command, "script": execute_script}


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "shell_execute",
                "description": "执行本地命令行命令。仅禁止危险命令；删除文件时需 confirm_delete=True。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令，如 'ls -la'、'cat file.txt'"},
                        "working_dir": {"type": "string", "description": "工作目录，默认为当前目录"},
                        "timeout": {"type": "integer", "description": "超时时间（秒），默认30，最大60"},
                        "confirm_delete": {"type": "boolean", "description": "删除操作需设为 true"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "shell_script",
                "description": "执行简单脚本。支持 bash、sh、python、python3。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "脚本内容"},
                        "interpreter": {"type": "string", "enum": ["bash", "sh", "python", "python3"], "description": "解释器，默认 bash"},
                        "working_dir": {"type": "string", "description": "工作目录"},
                        "timeout": {"type": "integer", "description": "超时时间（秒）"},
                    },
                    "required": ["script"],
                },
            },
        },
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
