from typing import Optional
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> bool:
    """
    Verify API key from Authorization header
    
    Supports both:
    - Bearer token: Authorization: Bearer sk-xxx
    - Direct API key: Authorization: sk-xxx
    """
    # Import here to avoid circular import
    from app.main import settings
    
    if not settings.api_key:
        raise HTTPException(
            status_code=500,
            detail="API key not configured on server"
        )
    
    # Try to get token from HTTPBearer credentials
    token = None
    if credentials:
        token = credentials.credentials
    
    # If not found, try to get from Authorization header directly
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            # Remove 'Bearer ' prefix if present
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            else:
                token = auth_header
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Please provide Authorization header with Bearer token."
        )
    
    if token != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return True


def get_api_key_optional() -> Optional[str]:
    """Get API key if set, otherwise return None"""
    from app.main import settings
    return settings.api_key if settings.api_key else None

