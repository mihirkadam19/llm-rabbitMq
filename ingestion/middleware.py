# ingestion/auth_middleware.py
import asyncio, os
import jwt
from jwt import PyJWKClient
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class TenantAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, tenant: str):
        super().__init__(app)
        self.tenant = tenant
        self.jwks = PyJWKClient(os.environ["OIDC_JWKS_URL"])
        self.issuer = os.environ["OIDC_ISSUER"]
        self.audience = os.environ["OIDC_AUDIENCE"]

    def _verify(self, token: str) -> dict:
        key = self.jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key, algorithms=["RS256"],
            issuer=self.issuer, audience=self.audience,
        )

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "missing token"}, status_code=401)

        try:
            claims = await asyncio.to_thread(self._verify, auth.removeprefix("Bearer "))
        except jwt.PyJWTError:
            return JSONResponse({"detail": "invalid token"}, status_code=401)

        if claims.get("tenant") != self.tenant:
            return JSONResponse({"detail": "tenant mismatch"}, status_code=403)

        request.state.tenant = self.tenant
        return await call_next(request)