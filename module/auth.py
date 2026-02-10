import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "ai-node-mcp-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config_manager):
        super().__init__(app)
        self.config_manager = config_manager

    async def dispatch(self, request: Request, call_next):
        auth_config = self.config_manager.auth
        if not auth_config.get('enabled', False):
            return await call_next(request)
        path = request.url.path
        allow_paths = auth_config.get('allow_paths', [])
        for allow_path in allow_paths:
            if path == allow_path or path.startswith(allow_path + '/') or path.startswith(allow_path + '?'):
                return await call_next(request)
        token = request.cookies.get("access_token") or (request.headers.get("Authorization") or "").replace("Bearer ", "")
        if not token:
            if request.url.path.startswith("/api/"):
                return JSONResponse(status_code=401, content={"error": "未授权访问"})
            return RedirectResponse(url=f"/login?redirect={path}")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            request.state.user = payload
        except JWTError:
            return JSONResponse(status_code=401, content={"error": "无效的认证令牌"})
        return await call_next(request)
