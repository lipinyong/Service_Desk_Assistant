import os
import sys
import importlib.util
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from threading import Lock, Thread
import time

logger = logging.getLogger(__name__)


class MCPService:
    def __init__(self, name: str, module_path: Path):
        self.name = name
        self.module_path = module_path
        self.module = None
        self.tools: Dict[str, Callable] = {}
        self.loaded = False
        self.last_modified: float = 0

    def load(self) -> bool:
        try:
            module_name = f"mcp_{self.name}"
            if module_name in sys.modules:
                del sys.modules[module_name]
            spec = importlib.util.spec_from_file_location(module_name, self.module_path)
            self.module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = self.module
            spec.loader.exec_module(self.module)
            if hasattr(self.module, 'register_tools'):
                self.tools = self.module.register_tools()
            elif hasattr(self.module, 'TOOLS'):
                self.tools = self.module.TOOLS
            self.loaded = True
            self.last_modified = self.module_path.stat().st_mtime
            logger.info(f"MCP服务已加载: {self.name}")
            return True
        except Exception as e:
            logger.error(f"MCP服务加载失败 {self.name}: {e}")
            return False

    def unload(self) -> bool:
        module_name = f"mcp_{self.name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        self.module = None
        self.tools = {}
        self.loaded = False
        logger.info(f"MCP服务已卸载: {self.name}")
        return True

    def is_modified(self) -> bool:
        try:
            return self.module_path.stat().st_mtime > self.last_modified
        except Exception:
            return False

    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        if not self.loaded:
            raise RuntimeError(f"MCP服务未加载: {self.name}")
        if tool_name not in self.tools:
            raise ValueError(f"工具不存在: {tool_name}")
        tool_func = self.tools[tool_name]
        if asyncio.iscoroutinefunction(tool_func):
            return await tool_func(**kwargs)
        return tool_func(**kwargs)

class MCPServerManager:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.services: Dict[str, MCPService] = {}
        self.services_path = Path("mcp")
        self._initialized = True
        self._hot_reload_enabled = False
        self._hot_reload_thread: Optional[Thread] = None
        self._hot_reload_interval = 2.0
        self._stop_hot_reload = False

    def set_services_path(self, path: str):
        self.services_path = Path(path)

    def discover_services(self) -> List[str]:
        if not self.services_path.exists():
            return []
        return [
            py_file.stem for py_file in self.services_path.glob("*.py")
            if not py_file.name.startswith("_")
        ]

    def load_service(self, name: str) -> bool:
        module_path = self.services_path / f"{name}.py"
        if not module_path.exists():
            logger.error(f"MCP服务文件不存在: {module_path}")
            return False
        service = MCPService(name, module_path)
        if service.load():
            self.services[name] = service
            return True
        return False

    def unload_service(self, name: str) -> bool:
        if name in self.services:
            self.services[name].unload()
            del self.services[name]
            return True
        return False

    def reload_service(self, name: str) -> bool:
        self.unload_service(name)
        return self.load_service(name)

    def get_service(self, name: str) -> Optional[MCPService]:
        return self.services.get(name)

    def list_services(self) -> List[Dict[str, Any]]:
        return [
            {"name": name, "loaded": s.loaded, "tools": list(s.tools.keys())}
            for name, s in self.services.items()
        ]

    async def call_tool(self, service_name: str, tool_name: str, **kwargs) -> Any:
        service = self.get_service(service_name)
        if not service:
            raise ValueError(f"MCP服务不存在: {service_name}")
        return await service.call_tool(tool_name, **kwargs)

    def check_and_reload_modified(self) -> List[str]:
        reloaded = []
        for name, service in list(self.services.items()):
            if service.is_modified() and self.reload_service(name):
                reloaded.append(name)
        for name in set(self.discover_services()) - set(self.services.keys()):
            if self.load_service(name):
                reloaded.append(name)
        return reloaded

mcp_manager = MCPServerManager()
