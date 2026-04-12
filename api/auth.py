"""
Authentication module - JWT-based auth
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.config import settings

# Password hashing - use a simpler scheme for demo
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT config
JWT_SECRET = settings.app.jwt_secret
JWT_ALGORITHM = settings.app.jwt_algorithm
JWT_EXPIRE_HOURS = settings.app.jwt_expire_hours

# Security scheme
security = HTTPBearer()


class TokenData(BaseModel):
    """Token payload"""
    username: Optional[str] = None


class User(BaseModel):
    """User model"""
    username: str
    is_admin: bool = True


# Admin credentials (simple check, hash computed on demand)
_ADMIN_PASSWORD = settings.app.admin_password[:32]  # Truncate for bcrypt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    try:
        return pwd_context.verify(plain_password[:32], hashed_password)
    except Exception:
        # Fallback for demo: plain text comparison
        return plain_password == settings.app.admin_password


def get_password_hash(password: str) -> str:
    """Hash a password"""
    try:
        return pwd_context.hash(password[:32])
    except Exception:
        # Fallback for demo
        return password


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Authenticate user credentials
    
    Phase 1: Only supports single admin user from environment
    """
    if username != settings.app.admin_username:
        return None
    
    # Simple comparison for demo
    if password != settings.app.admin_password:
        return None
    
    return User(username=username, is_admin=True)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return encoded_jwt


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Verify JWT token from Authorization header
    
    Returns:
        User object if token is valid
        
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token_data = TokenData(username=username)
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = User(username=token_data.username, is_admin=True)
    
    return user


# Optional auth for routes that can work with or without auth
async def optional_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[User]:
    """Optional authentication - returns None if no valid token"""
    try:
        return await verify_token(credentials)
    except HTTPException:
        return None
