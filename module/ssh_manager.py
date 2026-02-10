"""SSH 连接管理器"""
import threading
import logging
from typing import Dict, Any, Optional
from io import StringIO

logger = logging.getLogger(__name__)

try:
    import paramiko
except ImportError:
    paramiko = None


class SSHConnection:
    def __init__(self, host: str, port: int = 22, username: str = "root",
                 password: Optional[str] = None, key_file: Optional[str] = None,
                 key_content: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.key_content = key_content
        self.client = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        if paramiko is None:
            logger.error("未安装 paramiko，请 pip install paramiko")
            return False
        with self._lock:
            if self.client and self.client.get_transport() and self.client.get_transport().is_active():
                return True
            try:
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                connect_kwargs = {"hostname": self.host, "port": self.port, "username": self.username, "timeout": 10}
                if self.key_content:
                    key = paramiko.RSAKey.from_private_key(StringIO(self.key_content))
                    connect_kwargs["pkey"] = key
                elif self.key_file:
                    connect_kwargs["key_filename"] = self.key_file
                elif self.password:
                    connect_kwargs["password"] = self.password
                self.client.connect(**connect_kwargs)
                logger.info(f"SSH 连接成功: {self.username}@{self.host}:{self.port}")
                return True
            except Exception as e:
                logger.error(f"SSH 连接失败: {self.host} - {e}")
                self.client = None
                return False

    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        if not self.connect():
            return {"success": False, "error": "连接失败"}
        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="ignore")
            error = stderr.read().decode("utf-8", errors="ignore")
            exit_code = stdout.channel.recv_exit_status()
            return {"success": exit_code == 0, "output": output, "error": error, "exit_code": exit_code}
        except Exception as e:
            logger.error(f"SSH 命令执行失败: {command} - {e}")
            return {"success": False, "error": str(e)}

    def close(self):
        with self._lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def is_connected(self) -> bool:
        if not self.client:
            return False
        transport = self.client.get_transport()
        return transport and transport.is_active()


class SSHManager:
    def __init__(self):
        self.connections: Dict[str, SSHConnection] = {}
        self.hosts_config: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add_host(self, alias: str, host: str, port: int = 22, username: str = "root",
                 password: Optional[str] = None, key_file: Optional[str] = None,
                 key_content: Optional[str] = None, name: Optional[str] = None) -> bool:
        with self._lock:
            self.hosts_config[alias] = {
                "host": host, "port": port, "username": username,
                "password": password, "key_file": key_file, "key_content": key_content,
                "name": name or alias,
            }
            return True

    def remove_host(self, alias: str) -> bool:
        with self._lock:
            if alias in self.connections:
                self.connections[alias].close()
                del self.connections[alias]
            if alias in self.hosts_config:
                del self.hosts_config[alias]
            return True

    def get_connection(self, alias: str) -> Optional[SSHConnection]:
        with self._lock:
            if alias not in self.hosts_config:
                return None
            if alias not in self.connections:
                cfg = self.hosts_config[alias]
                self.connections[alias] = SSHConnection(
                    host=cfg["host"], port=cfg["port"], username=cfg["username"],
                    password=cfg.get("password"), key_file=cfg.get("key_file"),
                    key_content=cfg.get("key_content"),
                )
            return self.connections[alias]

    def execute(self, alias: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        conn = self.get_connection(alias)
        if not conn:
            return {"success": False, "error": f"未找到主机: {alias}"}
        return conn.execute(command, timeout)

    def get_system_info(self, alias: str) -> Dict[str, Any]:
        conn = self.get_connection(alias)
        if not conn:
            return {"error": f"未找到主机: {alias}"}
        info = {}
        for cmd, key in [("hostname", "hostname"), ("uname -r", "kernel"), ("uname -m", "arch"), ("uptime -p 2>/dev/null || uptime", "uptime")]:
            r = conn.execute(cmd)
            if r.get("success") and r.get("output"):
                info[key] = r["output"].strip()
        r = conn.execute("cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION)=' | head -2")
        if r.get("success") and r.get("output"):
            for line in r["output"].strip().split("\n"):
                if line.startswith("NAME="):
                    info["os_name"] = line.split("=", 1)[1].strip('"')
                elif line.startswith("VERSION="):
                    info["os_version"] = line.split("=", 1)[1].strip('"')
        return info

    def get_metrics(self, alias: str) -> Dict[str, Any]:
        conn = self.get_connection(alias)
        if not conn:
            return {"error": f"未找到主机: {alias}"}
        metrics = {}
        r = conn.execute("nproc")
        if r.get("success") and r.get("output"):
            try:
                metrics["cpu_cores"] = int(r["output"].strip())
            except Exception:
                metrics["cpu_cores"] = 1
        r = conn.execute("free -b | grep Mem")
        if r.get("success") and r.get("output"):
            parts = r["output"].split()
            if len(parts) >= 3:
                try:
                    total, used = int(parts[1]), int(parts[2])
                    metrics["mem_total"], metrics["mem_used"] = total, used
                    metrics["mem_percent"] = round(used / total * 100, 2) if total > 0 else 0
                except Exception:
                    pass
        r = conn.execute("df -B1 / | tail -1")
        if r.get("success") and r.get("output"):
            parts = r["output"].split()
            if len(parts) >= 5:
                try:
                    total, used = int(parts[1]), int(parts[2])
                    metrics["disk_total"], metrics["disk_used"] = total, used
                    metrics["disk_percent"] = round(used / total * 100, 2) if total > 0 else 0
                except Exception:
                    pass
        return metrics

    def list_hosts(self) -> list:
        hosts = []
        for alias, config in self.hosts_config.items():
            conn = self.connections.get(alias)
            hosts.append({
                "alias": alias, "name": config.get("name", alias),
                "host": config["host"], "port": config["port"], "username": config["username"],
                "connected": conn.is_connected() if conn else False,
            })
        return hosts

    def close_all(self):
        with self._lock:
            for conn in self.connections.values():
                conn.close()
            self.connections.clear()


ssh_manager = SSHManager()
