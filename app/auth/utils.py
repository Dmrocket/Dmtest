"""
Authentication utilities: hashing, JWT, encryption
"""
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import logging
from app.config import settings

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token encryption (for Instagram tokens)
try:
    # Fernet key must be 32 url-safe base64-encoded bytes (44 characters)
    # We strip any whitespace just in case
    key_bytes = settings.ENCRYPTION_KEY.strip().encode()
    cipher_suite = Fernet(key_bytes)
except Exception as e:
    logger.warning(f"Invalid ENCRYPTION_KEY provided. Generating a temporary one for this session. Error: {e}")
    cipher_suite = Fernet(Fernet.generate_key())

def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    """Create JWT access token using JWT_SECRET_KEY"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token using JWT_SECRET_KEY"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def verify_token(token: str) -> dict | None:
    """Verify and decode JWT token using JWT_SECRET_KEY"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT Verification failed: {e}")
        return None

def encrypt_token(token: str) -> str:
    """Encrypt Instagram access token"""
    if not token:
        return ""
    # Ensure we are encrypting bytes, then returning a string
    return cipher_suite.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt Instagram access token"""
    if not encrypted_token:
        return ""
    try:
        # Decrypt bytes, then decode back to string
        return cipher_suite.decrypt(encrypted_token.encode()).decode()
    except Exception as e:
        logger.error(f"Token decryption failed: {e}")
        # Return empty string or raise error depending on preference. 
        # Returning empty string prevents crash but will fail auth check later.
        return ""