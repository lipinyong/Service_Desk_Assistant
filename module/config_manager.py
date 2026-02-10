import os
import re
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)


def expand_env_vars(obj: Any) -> Any:
    if isinstance(obj, str):
        pattern = r'\$\{([^}]+)\}'
        def replace_env(match):
            env_var = match.group(1)
            default = None
            if ':-' in env_var:
                env_var, default = env_var.split(':-', 1)
            return os.environ.get(env_var, default or match.group(0))
        return re.sub(pattern, replace_env, obj)
    elif isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(item) for item in obj]
    return obj


class ConfigManager:
    _instance = None
    _lock = Lock()

    def __new__(cls, config_path: str = "config.yaml"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = "config.yaml"):
        if getattr(self, '_initialized', False):
            return
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._callbacks = []
        self._initialized = True
        self.reload()

    def _load_ai_config(self) -> Dict[str, Any]:
        """从 ai.yaml（或 ai.config_file 指定路径）加载并合并到 config['ai']"""
        ai_section = self._config.get("ai") or {}
        config_file = ai_section.get("config_file")
        if not config_file:
            return ai_section
        ai_path = self.config_path.parent / config_file
        if not ai_path.exists():
            logger.warning(f"AI 配置文件不存在: {ai_path}，使用 config 内 ai 配置")
            return ai_section
        try:
            with open(ai_path, "r", encoding="utf-8") as f:
                raw_ai = yaml.safe_load(f) or {}
            loaded = expand_env_vars(raw_ai)
            # 合并：provider 优先用 config.yaml 的，其余用 ai.yaml
            provider = ai_section.get("provider") or loaded.get("default", "deepseek")
            providers = loaded.get("providers", {})
            return {
                "provider": provider,
                "providers": providers,
                "temperature": loaded.get("temperature", 0.7),
                "max_tokens": loaded.get("max_tokens", 8192),
                "max_iterations": loaded.get("max_iterations", 100),
                **{k: v for k, v in ai_section.items() if k not in ("provider", "providers", "config_file")},
            }
        except Exception as e:
            logger.error(f"加载 AI 配置失败 {ai_path}: {e}")
            return ai_section

    def reload(self) -> None:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f) or {}
            self._config = expand_env_vars(raw_config)
            if self._config.get("ai"):
                self._config["ai"] = self._load_ai_config()
            logger.info(f"配置已加载: {self.config_path}")
            for callback in self._callbacks:
                try:
                    callback(self._config)
                except Exception as e:
                    logger.error(f"配置回调执行失败: {e}")
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise

    def get_config(self) -> Dict[str, Any]:
        return self._config.copy()

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def register_callback(self, callback) -> None:
        self._callbacks.append(callback)

    @property
    def auth(self) -> Dict[str, Any]:
        return self._config.get('auth', {})

    @property
    def ai(self) -> Dict[str, Any]:
        return self._config.get('ai', {})
