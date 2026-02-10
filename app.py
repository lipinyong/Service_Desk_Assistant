"""
v1.3 FastAPI 入口：Agent + MCP + RAG 运维 API
"""
import os
import logging
import uvicorn
from fastapi import FastAPI
from pathlib import Path

from module.config_manager import ConfigManager
from module.router import setup_routes
from module.auth import AuthMiddleware
from module.mcpserver import MCPServerManager
from module.aiagent import AIAgent, PromptPreprocessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    if not os.path.isabs(config_path):
        config_path = str(Path(__file__).parent / config_path)
    config_manager = ConfigManager(config_path)
    config = config_manager.get_config()
    app = FastAPI(title="FastAPI AI CLI", description="Agent + MCP + RAG 运维 API", version="1.3.0")
    if config.get("auth", {}).get("enabled", False):
        app.add_middleware(AuthMiddleware, config_manager=config_manager)
    mcp_config = config.get("mcp", {})
    services_path = mcp_config.get("services_path", "mcp")
    if not os.path.isabs(services_path):
        services_path = str(Path(__file__).parent / services_path)
    mcp_manager = MCPServerManager()
    mcp_manager.set_services_path(services_path)
    for name in mcp_manager.discover_services():
        mcp_manager.load_service(name)
    logger.info(f"已加载 MCP 服务: {[s['name'] for s in mcp_manager.list_services()]}")
    ai_config = config.get("ai", {})
    provider = ai_config.get("provider", "deepseek")
    providers = ai_config.get("providers", {})
    provider_config = providers.get(provider, {})
    api_key = provider_config.get("api_key", "")
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        api_key = os.environ.get(api_key[2:-1].split(":-")[0], "")
    if api_key:
        ai_config = {**ai_config, "api_key": api_key, "knowledge_base": config.get("knowledge_base", {})}
        app.state.agent = AIAgent(ai_config, mcp_manager)
        app.state.preprocessor = PromptPreprocessor(config.get("web", {}).get("root", "web"))
    else:
        logger.warning("未配置 AI API 密钥，/api/chat 将不可用")
    setup_routes(app)
    return app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "false").lower() == "true"
    uvicorn.run("app:app", host=host, port=port, reload=reload, log_level="info")
