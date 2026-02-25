from src.core.session import get_db
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from jose import jwt
from jose import JWTError
from sqlalchemy.orm import Session
from src.auth.service import decode_access_token
from src.auth.model import Guest, Host


import logging

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer()


# HTTPBearer version for WebSocket and other endpoints
def get_current_host(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Host:
    """Get current authenticated host using HTTPBearer scheme"""
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        host_id_str = payload.get("sub")

        if not host_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing host ID",
            )

        host_id = host_id_str
        host = db.query(Host).filter(Host.id == host_id).first()

        if not host:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Host not found",
            )

        if not host.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Host is inactive",
            )

        return host

    except HTTPException:
        # Let our custom HTTPExceptions pass through
        raise

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
        )

    except Exception as e:
        logger.error(f"Unexpected authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
