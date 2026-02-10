import logging
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def setup_routes(app):
    class ChatRequest(BaseModel):
        prompt: str
        stream: Optional[bool] = True
        preprocess: Optional[bool] = True
        user_info: Optional[dict] = {}

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "AI Node MCP is running", "version": "1.3.0"}

    @app.post("/api/chat")
    async def api_chat(request: Request, body: ChatRequest):
        agent = getattr(request.app.state, "agent", None)
        if not agent:
            return JSONResponse(status_code=503, content={"error": "Agent 未配置，请设置 AI API 密钥"})
        prompt = body.prompt
        if body.preprocess:
            preprocessor = getattr(request.app.state, "preprocessor", None)
            if preprocessor:
                prompt = await preprocessor.process(prompt)
        if body.stream:
            async def generate():
                import json
                async for chunk in agent.chat(prompt, stream=True):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
            )
        result = {"think": "", "say": "", "tool_calls": []}
        async for chunk in agent.chat(prompt, stream=False):
            if chunk.get("type") == "complete":
                result["think"] = chunk.get("think", "")
                result["say"] = chunk.get("say", "")
                result["token_stats"] = chunk.get("token_stats")
            elif chunk.get("type") == "error":
                return JSONResponse(status_code=500, content={"error": chunk.get("content", "未知错误")})
        return JSONResponse(content=result)
