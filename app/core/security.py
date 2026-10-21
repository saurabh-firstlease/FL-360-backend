import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import ADMIN_TOKEN

bearer = HTTPBearer(auto_error=False)


def is_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> bool:
    # Fails closed: with no ADMIN_TOKEN configured nobody is an admin.
    if not ADMIN_TOKEN or creds is None:
        return False
    return hmac.compare_digest(creds.credentials.encode(), ADMIN_TOKEN.encode())


def require_admin(admin: bool = Depends(is_admin)) -> None:
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token missing or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
