"""
Rate limiting middleware for HR Agent API.
"""

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting.
    
    Limits requests per IP address to prevent abuse.
    """
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)
    
    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path in ['/health', '/docs', '/redoc', '/openapi.json']:
            return await call_next(request)
        
        client_ip = request.client.host if request.client else 'unknown'
        now = time.time()
        minute_ago = now - 60
        
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > minute_ago
        ]
        
        if len(self._requests[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail='Too many requests. Please wait a moment.'
            )
        
        self._requests[client_ip].append(now)
        
        return await call_next(request)
