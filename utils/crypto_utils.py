"""
Utility functions for encrypting and decrypting sensitive data
"""
import os
from base64 import b64encode, b64decode
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# This should be a constant secret key, stored securely in production
# In a real application, consider using environment variables or a key management service
SECRET_KEY = b'your-secret-key-here-32-char-long'  # Replace with your secret key (32 bytes)
SALT = b'some-random-salt'  # This should be constant for your application

def get_fernet():
    """Create a Fernet instance with our key derivation"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    key = b64encode(kdf.derive(SECRET_KEY))
    return Fernet(key)

def encrypt_password(password: str) -> str:
    """Encrypt a password"""
    f = get_fernet()
    return f.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt a password"""
    f = get_fernet()
    try:
        return f.decrypt(encrypted_password.encode()).decode()
    except (InvalidToken, ValueError):
        raise ValueError("Invalid encrypted password")

if __name__ == "__main__":
    # Example usage
    password = "my_secure_password"
    encrypted = encrypt_password(password)
    print(f"Encrypted: {encrypted}")
    decrypted = decrypt_password(encrypted)
    print(f"Decrypted: {decrypted}")
