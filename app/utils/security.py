from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
from app.config import settings
from cryptography.fernet import Fernet
import base64
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLE_ADMIN = "admin"
ROLE_RESELLER = "reseller"
ROLE_USER = "user"

SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"

# --- NEW: Reversible Encryption Setup ---
# Fernet requires a 32-byte base64-encoded key. 
# We derive it from your existing SECRET_KEY to keep things consistent.
def get_fernet_suite():
    # Ensure the key is 32 bytes and base64 encoded
    key = base64.urlsafe_b64encode(SECRET_KEY.encode().ljust(32)[:32])
    return Fernet(key)

cipher_suite = get_fernet_suite()

def encrypt_viewable_password(password: str) -> str:
    """Encrypts password into a reversible string for Admin viewing."""
    return cipher_suite.encrypt(password.encode()).decode()

def decrypt_viewable_password(encrypted_password: str) -> str:
    """Decrypts the string back to plain text."""
    try:
        return cipher_suite.decrypt(encrypted_password.encode()).decode()
    except Exception:
        return "Decryption Error"
# ----------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict):
    expire = datetime.now(IST) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)