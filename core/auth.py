"""
Enhanced Authentication and Authorization Module
Provides robust, secure user management with advanced security features.
"""
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, validator, Field
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from db.client import get_db_connection
from core.logger import logger

# Security Configuration
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password Security - using argon2 (more secure, no 72-byte limit)
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

# Account Security
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
MIN_PASSWORD_LENGTH = 8
PASSWORD_HISTORY_COUNT = 5

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Pydantic Models
class Token(BaseModel):
    """Authentication token response."""
    access_token: str = Field(..., description="The JWT access token used for authenticated requests.")
    token_type: str = Field(..., description="The type of the token, typically 'bearer'.")
    expires_in: int = Field(..., description="The number of seconds until the access token expires.")
    refresh_token: Optional[str] = Field(None, description="An optional refresh token to obtain new access tokens.")

class RefreshTokenRequest(BaseModel):
    """Request body for refreshing an access token."""
    refresh_token: str = Field(..., description="The valid refresh token.")

class TokenData(BaseModel):
    """Data encoded within the JWT token."""
    username: Optional[str] = Field(None, description="The username of the authenticated user.")
    role: Optional[str] = Field(None, description="The role assigned to the user (e.g., 'ADMIN', 'USER').")

class UserBase(BaseModel):
    """Base schema for user-related information."""
    username: str = Field(..., description="Unique username for the account.")
    email: Optional[EmailStr] = Field(None, description="Valid email address for communications.")
    role: str = Field("USER", description="Access level role assigned to the user.")
    is_active: bool = Field(True, description="Status indicating if the account is currently active.")

class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., description="Strong password for the new account.")

    @validator('password')
    def password_strength(cls, v):
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters long')

        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')

        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')

        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')

        # Check for common weak passwords
        weak_passwords = ['password', '123456', 'qwerty', 'admin', 'letmein']
        if v.lower() in weak_passwords:
            raise ValueError('Password is too common')

        return v

class UserUpdate(BaseModel):
    """Schema for updating user details."""
    email: Optional[EmailStr] = Field(None, description="New email address to update.")
    is_active: Optional[bool] = Field(None, description="New activation status.")

class UserInDB(UserBase):
    """Complete user representation as stored in the database."""
    user_id: int = Field(..., description="Unique internal database ID.")
    hashed_password: str = Field(..., description="Salted and hashed password string.")
    is_verified: bool = Field(False, description="Flag indicating if the email has been verified.")
    failed_attempts: int = Field(0, description="Count of consecutive failed login attempts.")
    locked_until: Optional[datetime] = Field(None, description="Timestamp until the account is locked out.")
    last_login: Optional[datetime] = Field(None, description="Timestamp of the last successful login.")
    last_failed_login: Optional[datetime] = Field(None, description="Timestamp of the last failed login attempt.")
    password_changed_at: datetime = Field(..., description="Timestamp of the last password change.")
    created_at: datetime = Field(..., description="Timestamp of account creation.")
    updated_at: datetime = Field(..., description="Timestamp of the last update to the account.")

class PasswordChange(BaseModel):
    """Schema for password change requests."""
    current_password: str = Field(..., description="The user's current password for verification.")
    new_password: str = Field(..., description="The new strong password to set.")

class LoginRequest(BaseModel):
    """Schema for manual login requests (non-OAuth2)."""
    username: str = Field(..., description="The user's username.")
    password: str = Field(..., description="The user's password.")

@dataclass
class SecurityEvent:
    event_type: str
    username: str
    ip_address: str
    user_agent: str
    timestamp: datetime
    details: Dict[str, Any]

# Utility Functions
def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)

def hash_password(password: str) -> str:
    """Hash a password using argon2."""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise ValueError(f"Password hashing failed: {str(e)}")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False

def is_account_locked(locked_until: Optional[datetime]) -> bool:
    """Check if an account is currently locked."""
    if locked_until is None:
        return False
    return locked_until > datetime.now(timezone.utc)

def calculate_lockout_time(failed_attempts: int) -> datetime:
    """Calculate lockout duration based on failed attempts."""
    # Exponential backoff: 15min, 30min, 1hr, 2hr, 4hr
    duration_minutes = LOCKOUT_DURATION_MINUTES * (2 ** min(failed_attempts - 1, 4))
    return datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

# Database Operations
def get_user(username: str) -> Optional[UserInDB]:
    """Retrieve user from database by username."""
    try:
        with get_db_connection() as conn:
            row = conn.execute("""
                SELECT user_id, username, email, hashed_password, role, is_active,
                       is_verified, failed_attempts, locked_until, last_login,
                       last_failed_login, password_changed_at, created_at, updated_at
                FROM users WHERE username = ?
            """, (username,)).fetchone()

            if row:
                return UserInDB(
                    user_id=row[0],
                    username=row[1],
                    email=row[2],
                    hashed_password=row[3],
                    role=row[4],
                    is_active=bool(row[5]),
                    is_verified=bool(row[6]),
                    failed_attempts=row[7],
                    locked_until=row[8] if row[8] else None,
                    last_login=row[9] if row[9] else None,
                    last_failed_login=row[10] if row[10] else None,
                    password_changed_at=row[11],
                    created_at=row[12],
                    updated_at=row[13]
                )
    except Exception as e:
        logger.error(f"Error retrieving user {username}: {str(e)}")
    return None

def create_user(user_data: UserCreate) -> UserInDB:
    """Create a new user in the database."""
    hashed_password = hash_password(user_data.password)

    try:
        with get_db_connection(read_only=False) as conn:
            cursor = conn.execute("""
                INSERT INTO users (username, email, hashed_password, role, is_active, is_verified)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_data.username,
                user_data.email,
                hashed_password,
                user_data.role,
                user_data.is_active,
                False  # New users need email verification
            ))

            user_id = cursor.lastrowid
            conn.commit()

            logger.info(f"User created: {user_data.username}")

            return UserInDB(
                user_id=user_id,
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed_password,
                role=user_data.role,
                is_active=user_data.is_active,
                is_verified=False,
                failed_attempts=0,
                locked_until=None,
                last_login=None,
                last_failed_login=None,
                password_changed_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
    except Exception as e:
        logger.error(f"Error creating user {user_data.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )

def update_user(username: str, updates: Dict[str, Any]) -> bool:
    """Update user information."""
    try:
        with get_db_connection(read_only=False) as conn:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [username]

            conn.execute(f"""
                UPDATE users
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
            """, values)
            conn.commit()

            logger.info(f"User updated: {username}")
            return True
    except Exception as e:
        logger.error(f"Error updating user {username}: {str(e)}")
        return False

# Authentication Functions
def authenticate_user(username: str, password: str, request: Request = None) -> Optional[UserInDB]:
    """Authenticate a user with enhanced security checks."""
    user = get_user(username)

    if not user:
        logger.warning(f"Login attempt for non-existent user: {username}")
        return None

    # Check if account is locked
    if is_account_locked(user.locked_until):
        logger.warning(f"Login attempt on locked account: {username}")
        return None

    # Verify password
    if not verify_password(password, user.hashed_password):
        # Record failed attempt
        failed_attempts = user.failed_attempts + 1
        updates = {
            'failed_attempts': failed_attempts,
            'last_failed_login': datetime.now(timezone.utc)
        }

        # Lock account if too many failed attempts
        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            updates['locked_until'] = calculate_lockout_time(failed_attempts)

        update_user(username, updates)

        logger.warning(f"Failed login attempt for user: {username} (attempt {failed_attempts})")
        return None

    # Check if user is active
    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {username}")
        return None

    # Successful login - reset failed attempts and update last login
    update_user(username, {
        'failed_attempts': 0,
        'locked_until': None,
        'last_login': datetime.now(timezone.utc)
    })

    logger.info(f"Successful login for user: {username}")
    return user

def change_password(username: str, current_password: str, new_password: str) -> bool:
    """Change user password with validation."""
    user = get_user(username)
    if not user:
        return False

    # Verify current password
    if not verify_password(current_password, user.hashed_password):
        return False

    # Hash new password
    hashed_new_password = hash_password(new_password)

    # Update password
    return update_user(username, {
        'hashed_password': hashed_new_password,
        'password_changed_at': datetime.now(timezone.utc)
    })

# JWT Token Functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        token_type: str = payload.get("type")

        if username is None or token_type != "access":
            return None

        return TokenData(username=username, role=role)
    except JWTError:
        return None

# Dependency Functions
async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(token)
    if token_data is None:
        raise credentials_exception

    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin_user(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Get current admin user."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user