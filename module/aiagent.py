"""
v1.3 AI Agent：大模型 + MCP 工具 + RAG 知识库
"""
import re
import json
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Any, Optional, List
from pathlib import Path

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 2.5
MAX_TOOL_RESULT_TOKENS = 80000


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN)


def clean_utf8(text: str) -> str:
    if not isinstance(text, str):
        return text
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')


def redact_sensitive_data(data: Any, sensitive_keys: set = None) -> Any:
    if sensitive_keys is None:
        sensitive_keys = {'access_token', 'token', 'password', 'secret', 'api_key'}
    if isinstance(data, dict):
        return {
            k: '***REDACTED***' if (k.lower() in sensitive_keys or any(sk in k.lower() for sk in sensitive_keys))
            else redact_sensitive_data(v, sensitive_keys)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_sensitive_data(item, sensitive_keys) for item in data]
    if isinstance(data, str):
        if len(data) > 50 and any(c.isalnum() for c in data):
            for sk in sensitive_keys:
                if sk in data.lower():
                    return '***REDACTED***'
        return clean_utf8(data)
    return data


class AIAgent:
    def __init__(self, config: Dict[str, Any], mcp_manager=None, user_info: Dict[str, Any] = None):
        self.config = config
        self.provider = config.get('provider', 'deepseek')
        providers = config.get('providers', {})
        provider_config = providers.get(self.provider, {})
        self.base_url = provider_config.get('base_url', 'https://api.deepseek.com')
        self.api_key = provider_config.get('api_key', '')
        self.model = provider_config.get('model', 'deepseek-chat')
        self.temperature = provider_config.get('temperature', config.get('temperature', 0.7))
        self.max_tokens = provider_config.get('max_tokens', config.get('max_tokens', 4096))
        self.max_iterations = config.get('max_iterations', 100)
        self.mcp_manager = mcp_manager
        self.user_info = user_info or {}
        self.knowledge_base = config.get('knowledge_base', {})
        self.token_stats = {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "api_calls": 0, "tool_calls": 0, "current_prompt": ""
        }
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def reset_token_stats(self, prompt: str = ""):
        self.token_stats = {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "api_calls": 0, "tool_calls": 0, "current_prompt": prompt,
            "start_time": time.time(), "elapsed_seconds": 0
        }

    def get_token_stats(self) -> Dict[str, Any]:
        return self.token_stats.copy()

    def get_tools(self) -> List[Dict[str, Any]]:
        if not self.mcp_manager:
            return []
        tools = []
        for service in self.mcp_manager.services.values():
            if hasattr(service.module, 'TOOL_DEFINITIONS'):
                tools.extend(service.module.TOOL_DEFINITIONS)
            elif hasattr(service.module, 'get_tool_definitions'):
                tools.extend(service.module.get_tool_definitions())
        return tools

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.mcp_manager:
            return {"error": "MCP管理器未配置"}
        parts = tool_name.split('_', 1)
        if len(parts) < 2:
            return {"error": f"无效的工具名称: {tool_name}"}
        service_name, func_name = parts[0], parts[1]
        service = self.mcp_manager.get_service(service_name)
        if not service:
            return {"error": f"MCP服务不存在: {service_name}"}
        if func_name not in service.tools:
            return {"error": f"工具不存在: {func_name}"}
        try:
            result = await service.call_tool(func_name, **arguments)
            return result
        except Exception as e:
            logger.error(f"工具执行失败: {e}")
            return {"error": str(e)}

    def _compress_messages_if_needed(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        total_tokens = sum(estimate_tokens(json.dumps(m, ensure_ascii=False)) for m in messages)
        if total_tokens <= max_tokens:
            return messages
        logger.info(f"消息历史过长 ({total_tokens} tokens)，开始压缩...")
        compressed = []
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if estimate_tokens(content) > 10000:
                    try:
                        result = json.loads(content)
                        summary = {"compressed": True, "keys": list(result.keys())[:10] if isinstance(result, dict) else [], "note": "结果已压缩"}
                        compressed.append({**msg, "content": json.dumps(summary, ensure_ascii=False)})
                        continue
                    except Exception:
                        pass
            compressed.append(msg)
        return compressed

    async def _auto_chunk_large_result(self, result_json: str, tool_name: str) -> Dict[str, Any]:
        """大结果仅截断，不依赖 data_processor"""
        truncated = result_json[:50000] + f"\n\n... [数据过大已截断，原始长度: {len(result_json)} 字符]"
        return {"success": True, "chunked": False, "truncated": True, "data": truncated, "message": "数据过大已截断"}

    async def _stream_chat_with_tools(self, prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        self.reset_token_stats(prompt)
        user_context = ""
        if self.user_info:
            u, c = self.user_info.get('username', ''), self.user_info.get('cname', '')
            if u:
                user_context = f"\n\n当前登录用户: {c or u} (用户名: {u})。"
        system_prompt = f"""你是一个智能运维助手，可以使用工具帮助用户完成任务。
重要规则：
0. 回答运维、故障排查、部署、配置等问题时，优先调用 knowledge_retrieve 从知识库检索相关文档，再结合其他工具执行操作；若已提供“参考以下知识库内容”，则直接基于该内容与工具完成任务。
1. 回答时请使用中文。{user_context}"""
        cleaned_prompt = clean_utf8(prompt)
        kb = self.knowledge_base or {}
        if kb.get("enabled") and kb.get("auto_rag") and cleaned_prompt.strip():
            try:
                from mcp.knowledge import knowledge_retrieve
                n_results = kb.get("n_results", 5)
                ret = await knowledge_retrieve(cleaned_prompt, n_results=n_results)
                if ret.get("success") and ret.get("documents"):
                    docs_text = "\n\n".join(f"[{i+1}] {d.get('content', '').strip()}" for i, d in enumerate(ret["documents"]))
                    cleaned_prompt = f"参考以下知识库内容：\n{docs_text}\n\n---\n用户问题：{cleaned_prompt}"
            except Exception as e:
                logger.warning(f"知识库自动检索失败: {e}")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": cleaned_prompt}
        ]
        tools = self.get_tools()
        max_iterations = self.max_iterations
        iteration = 0
        MAX_HISTORY_TOKENS = 80000

        while iteration < max_iterations:
            iteration += 1
            messages = self._compress_messages_if_needed(messages, MAX_HISTORY_TOKENS)
            stream_response = None
            for retry in range(3):
                try:
                    if tools:
                        stream_response = await self.client.chat.completions.create(
                            model=self.model, messages=messages, temperature=self.temperature,
                            max_tokens=self.max_tokens, tools=tools, tool_choice="auto", stream=True
                        )
                    else:
                        stream_response = await self.client.chat.completions.create(
                            model=self.model, messages=messages, temperature=self.temperature,
                            max_tokens=self.max_tokens, stream=True
                        )
                    break
                except Exception as e:
                    if retry == 2:
                        raise
                    await asyncio.sleep(2 * (retry + 1))

            collected_content = ""
            collected_tool_calls = {}
            thinking_content = ""
            say_content = ""
            in_thinking = False
            has_tool_calls = False
            self.token_stats["api_calls"] += 1
            self.token_stats["prompt_tokens"] += estimate_tokens(json.dumps(messages, ensure_ascii=False))

            async for chunk in stream_response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.tool_calls:
                    has_tool_calls = True
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            collected_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                collected_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                collected_tool_calls[idx]["arguments"] += tc.function.arguments
                if delta.content:
                    content = delta.content
                    collected_content += content
                    if "<think>" in content:
                        in_thinking = True
                        content = content.replace("<think>", "")
                    if "</think>" in content:
                        in_thinking = False
                        parts = content.split("</think>")
                        if parts[0]:
                            thinking_content += parts[0]
                        if len(parts) > 1 and parts[1]:
                            say_content += parts[1]
                            yield {"type": "say", "content": parts[1], "partial": True}
                        continue
                    if in_thinking:
                        thinking_content += content
                        yield {"type": "think", "content": content, "partial": True}
                    else:
                        say_content += content
                        yield {"type": "say", "content": content, "partial": True}

            if has_tool_calls and collected_tool_calls:
                tool_calls_list = [
                    {"id": collected_tool_calls[i]["id"], "type": "function",
                     "function": {"name": collected_tool_calls[i]["name"], "arguments": collected_tool_calls[i]["arguments"]}}
                    for i in sorted(collected_tool_calls.keys())
                ]
                messages.append({"role": "assistant", "content": collected_content or "", "tool_calls": tool_calls_list})
                for tc_data in tool_calls_list:
                    tool_name = tc_data["function"]["name"]
                    try:
                        arguments = json.loads(tc_data["function"]["arguments"])
                    except Exception:
                        arguments = {}
                    self.token_stats["tool_calls"] += 1
                    yield {"type": "tool_call", "tool_name": tool_name, "arguments": redact_sensitive_data(arguments)}
                    result = await self.execute_tool(tool_name, arguments)
                    result_json = json.dumps(result, ensure_ascii=False)
                    result_tokens = estimate_tokens(result_json)
                    if result_tokens > MAX_TOOL_RESULT_TOKENS:
                        yield {"type": "process_info", "message": f"数据量过大，正在截断..."}
                        chunked_result = await self._auto_chunk_large_result(result_json, tool_name)
                        yield {"type": "tool_result", "tool_name": tool_name, "result": {"message": "数据已截断", "data": chunked_result.get("data", "")[:500]}}
                        messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": json.dumps(chunked_result, ensure_ascii=False)})
                    else:
                        yield {"type": "tool_result", "tool_name": tool_name, "result": redact_sensitive_data(result)}
                        messages.append({"role": "tool", "tool_call_id": tc_data["id"], "content": result_json})
                continue

            self.token_stats["completion_tokens"] += estimate_tokens(collected_content)
            self.token_stats["total_tokens"] = self.token_stats["prompt_tokens"] + self.token_stats["completion_tokens"]
            self.token_stats["elapsed_seconds"] = time.time() - self.token_stats.get("start_time", time.time())
            yield {"type": "complete", "think": thinking_content, "say": say_content, "token_stats": self.token_stats.copy()}
            return

        if tools:
            messages.append({"role": "user", "content": "请根据上述工具调用结果，简要总结回答用户的问题。"})
            try:
                final_response = await self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=self.temperature,
                    max_tokens=self.max_tokens, stream=True
                )
                final_content = ""
                async for chunk in final_response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        c = chunk.choices[0].delta.content
                        final_content += c
                        yield {"type": "say", "content": c, "partial": True}
                self.token_stats["completion_tokens"] += estimate_tokens(final_content)
                self.token_stats["total_tokens"] = self.token_stats["prompt_tokens"] + self.token_stats["completion_tokens"]
                self.token_stats["elapsed_seconds"] = time.time() - self.token_stats.get("start_time", time.time())
                yield {"type": "complete", "think": "", "say": final_content, "token_stats": self.token_stats.copy()}
            except Exception as e:
                logger.error(f"最终总结失败: {e}")
                yield {"type": "complete", "think": "", "say": "（已达到最大工具调用次数）", "token_stats": self.token_stats.copy()}

    async def _sync_chat_with_tools(self, prompt: str) -> Dict[str, Any]:
        result = {"type": "complete", "think": "", "say": "", "tool_calls": []}
        async for chunk in self._stream_chat_with_tools(prompt):
            if chunk.get("type") == "tool_call":
                result["tool_calls"].append({"name": chunk.get("tool_name"), "arguments": chunk.get("arguments")})
            elif chunk.get("type") == "tool_result":
                for tc in result["tool_calls"]:
                    if tc["name"] == chunk.get("tool_name"):
                        tc["result"] = chunk.get("result")
            elif chunk.get("type") == "think" and chunk.get("partial"):
                result["think"] += chunk.get("content", "")
            elif chunk.get("type") == "say" and chunk.get("partial"):
                result["say"] += chunk.get("content", "")
            elif chunk.get("type") == "complete":
                result["think"] = chunk.get("think", "")
                result["say"] = chunk.get("say", "")
        return result

    async def chat(self, prompt: str, stream: bool = True) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            if stream:
                async for chunk in self._stream_chat_with_tools(prompt):
                    yield chunk
            else:
                result = await self._sync_chat_with_tools(prompt)
                yield result
        except Exception as e:
            logger.error(f"AI聊天错误: {e}", exc_info=True)
            self.token_stats["elapsed_seconds"] = time.time() - self.token_stats.get("start_time", time.time())
            yield {"type": "error", "content": str(e), "token_stats": self.token_stats.copy()}


class PromptPreprocessor:
    def __init__(self, web_root: str = "web"):
        self.web_root = Path(web_root)
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def process(self, prompt: str) -> str:
        pattern = r'@\{([^}]+)\}'
        result = prompt
        for match in reversed(list(re.finditer(pattern, prompt))):
            replacement = await self._evaluate_expression(match.group(1).strip())
            result = result[:match.start()] + replacement + result[match.end():]
        return result

    async def _evaluate_expression(self, expression: str) -> str:
        if expression.startswith('file(') and expression.endswith(')'):
            file_path = expression[5:-1].strip().strip('"\'')
            return await self._load_file(file_path)
        if expression.startswith('api(') and expression.endswith(')'):
            url = expression[4:-1].strip().strip('"\'')
            return await self._call_api(url)
        return f"[未知表达式: {expression}]"

    async def _load_file(self, file_path: str) -> str:
        try:
            full_path = self.web_root / file_path
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return f"[文件不存在: {file_path}]"
        except Exception as e:
            return f"[文件读取错误: {e}]"

    async def _call_api(self, url: str) -> str:
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"[API调用错误: {e}]"

    async def close(self):
        await self.http_client.aclose()
