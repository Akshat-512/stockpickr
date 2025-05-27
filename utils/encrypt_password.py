from crypto_utils import encrypt_password
import configparser

# Load current config
config = configparser.ConfigParser()
config.read('config.ini')

# Get the current password
current_password = config.get('APICredentials', 'password')

# Encrypt the password
encrypted_password = encrypt_password(current_password)

# Update the config
config.set('APICredentials', 'password', encrypted_password)

# Save the config
with open('config.ini', 'w') as f:
    config.write(f)

print("Password has been encrypted and saved to config.ini")
