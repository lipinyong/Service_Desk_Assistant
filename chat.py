#!/usr/bin/env python3
"""v1.3 命令行入口：Agent + MCP + RAG 运维对话"""
import sys
import os
import json
import asyncio
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

script_dir = Path(os.path.realpath(__file__)).parent
env_path = script_dir / ".env"
load_dotenv(env_path, override=True)
sys.path.insert(0, str(script_dir))

from module.aiagent import AIAgent, PromptPreprocessor
from module.mcpserver import MCPServerManager
from module.config_manager import ConfigManager


def load_config() -> dict:
    """加载配置（含 config.yaml + ai.yaml 合并）"""
    try:
        return ConfigManager(str(script_dir / "config.yaml")).get_config()
    except Exception as e:
        print(f"配置加载失败: {e}")
        return {}


def print_colored(text: str, color: str = "default"):
    colors = {"default": "\033[0m", "green": "\033[32m", "yellow": "\033[33m", "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m", "gray": "\033[90m", "reset": "\033[0m"}
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def typewriter_print(text: str, delay: float = 0.02):
    for c in text:
        sys.stdout.write(c)
        sys.stdout.flush()
        time.sleep(delay)


async def chat_stream(agent, preprocessor, prompt: str, typewriter: bool = True, delay: float = 0.02, preprocess: bool = True, quiet: bool = False):
    if not quiet:
        print_colored(f"\n[问题] {prompt}", "cyan")
        print_colored("-" * 50, "gray")
    if preprocess:
        prompt = await preprocessor.process(prompt)
    think_buffer = say_buffer = ""
    current_type = None
    token_stats = None
    try:
        async for chunk in agent.chat(prompt, stream=True):
            msg_type = chunk.get("type", "")
            content = chunk.get("content", "")
            if msg_type == "think":
                if not quiet:
                    if current_type != "think":
                        if current_type:
                            print()
                        print_colored("\n[思考]", "magenta")
                        current_type = "think"
                    typewriter_print(content, delay) if typewriter else (sys.stdout.write(content), sys.stdout.flush())
                think_buffer += content
            elif msg_type == "say":
                if not quiet:
                    if current_type != "say":
                        if current_type:
                            print()
                        print_colored("\n[回答]", "green")
                        current_type = "say"
                    typewriter_print(content, delay) if typewriter else (sys.stdout.write(content), sys.stdout.flush())
                say_buffer += content
            elif msg_type == "tool_call" and not quiet:
                if current_type:
                    print()
                current_type = None
                print_colored(f"\n[工具] {chunk.get('tool_name', '')}", "blue")
                print_colored(f"  参数: {json.dumps(chunk.get('arguments', {}), ensure_ascii=False, indent=2)}", "gray")
            elif msg_type == "tool_result" and not quiet:
                print_colored(f"\n[结果] {chunk.get('tool_name', '')}", "blue")
            elif msg_type == "error" and not quiet:
                print_colored(f"\n[错误] {content}", "yellow")
            if msg_type == "complete":
                token_stats = chunk.get("token_stats")
        if not quiet and token_stats:
            print()
            print_colored("-" * 50, "gray")
            print_colored(f"  耗时: {token_stats.get('elapsed_seconds', 0):.1f}s  API: {token_stats.get('api_calls', 0)}  工具: {token_stats.get('tool_calls', 0)}  Token: ~{token_stats.get('total_tokens', 0)}", "gray")
        elif not quiet and say_buffer:
            print()
    except KeyboardInterrupt:
        if not quiet:
            print_colored("\n[中断]", "yellow")


async def interactive_mode(agent, preprocessor, typewriter: bool = True, delay: float = 0.02, quiet: bool = False):
    if not quiet:
        print_colored("=" * 60, "cyan")
        print_colored("  v1.3 AI 运维助手 (Agent + MCP + RAG)", "cyan")
        print_colored("  输入问题开始对话，exit/quit 退出", "gray")
        print_colored("=" * 60, "cyan")
    while True:
        try:
            prompt = input("\033[36m请输入问题: \033[0m").strip() if not quiet else input().strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q", "bye"):
                if not quiet:
                    print_colored("再见！", "green")
                break
            await chat_stream(agent, preprocessor, prompt, typewriter, delay, quiet=quiet)
        except (KeyboardInterrupt, EOFError):
            if not quiet:
                print_colored("\n再见！", "green")
            break


async def async_main():
    parser = argparse.ArgumentParser(description="v1.3 AI 运维助手 CLI")
    parser.add_argument("-p", "--prompt", help="直接提问（非交互）")
    parser.add_argument("-d", "--delay", type=float, default=0.02, help="打字机延迟")
    parser.add_argument("--no-typewriter", action="store_true", help="禁用打字机效果")
    parser.add_argument("--no-preprocess", action="store_true", help="禁用提示词预处理")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    parser.add_argument("--debug", action="store_true", help="调试日志")
    args = parser.parse_args()
    import logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    config = load_config()
    ai_config = config.get("ai", {})
    provider = ai_config.get("provider", "deepseek")
    providers = ai_config.get("providers", {})
    provider_config = providers.get(provider, {})
    api_key = provider_config.get("api_key", "")
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        api_key = os.environ.get(api_key[2:-1], "")
    if not api_key:
        print_colored(f"[错误] 未配置 AI API 密钥 (provider: {provider})，请设置 .env 或 config.yaml", "yellow")
        return
    ai_config = {**ai_config, "api_key": api_key, "knowledge_base": config.get("knowledge_base", {})}
    mcp_manager = MCPServerManager()
    mcp_config = config.get("mcp", {})
    services_path = script_dir / mcp_config.get("services_path", "mcp")
    mcp_manager.set_services_path(str(services_path))
    for name in mcp_manager.discover_services():
        mcp_manager.load_service(name)
    if not args.quiet:
        print(f"MCP 服务: {[s['name'] for s in mcp_manager.list_services()]}")
    agent = AIAgent(ai_config, mcp_manager)
    preprocessor = PromptPreprocessor(config.get("web", {}).get("root", "web"))
    if args.prompt:
        await chat_stream(agent, preprocessor, args.prompt, typewriter=not args.no_typewriter, delay=args.delay, preprocess=not args.no_preprocess, quiet=args.quiet)
    else:
        await interactive_mode(agent, preprocessor, typewriter=not args.no_typewriter, delay=args.delay, quiet=args.quiet)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
