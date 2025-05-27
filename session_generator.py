#!/usr/bin/env python3
"""
Manual ICICI Breeze Session Generator
Simple manual input of session token
"""

import json
import urllib.parse
import webbrowser
import configparser
from datetime import datetime, timedelta
import os
from utils.crypto_utils import decrypt_password

# Load your existing config
config = configparser.ConfigParser()
config.read("config.ini")
API_KEY = config.get("APICredentials", "api_key", fallback="")
USER_ID = config.get("APICredentials", "user_id", fallback="")
PASSWORD = config.get("APICredentials", "password", fallback="")


class ManualBreezeAuth:
    def __init__(self):
        self.api_key = API_KEY
        self.user_id = USER_ID

        # Decrypt the password when initializing
        try:
            self.password = decrypt_password(PASSWORD)
        except Exception as e:
            print(f"❌ Error decrypting password: {e}")
            print(
                "⚠️  Make sure the password is encrypted and the encryption key is correct"
            )
            raise

        # Use absolute path for the session file
        self.session_dir = os.path.abspath("")
        self.session_file = os.path.join(self.session_dir, "session.json")
        # Ensure session directory exists
        os.makedirs(self.session_dir, exist_ok=True)
        # Create empty session file if it doesn't exist
        if not os.path.exists(self.session_file):
            with open(self.session_file, "w") as f:
                json.dump({}, f)  # Initialize with empty JSON object

    def save_session_token(self, session_token, hours_valid=8):
        """Save the session token to both JSON and config files"""
        try:
            expires_at = datetime.now() + timedelta(hours=hours_valid)

            # Save to JSON for continuous trader
            session_data = {
                "session_token": session_token,
                "created_at": datetime.now().isoformat(),
                "expires_at": expires_at.isoformat(),
                "api_key": self.api_key,
                "valid_hours": hours_valid,
                "method": "manual_input",
            }

            # Directory already created in __init__
            with open(self.session_file, "w") as f:
                json.dump(session_data, f, indent=2)

            # Update config.ini
            if not config.has_section("APICredentials"):
                config.add_section("APICredentials")

            config.set("APICredentials", "session_token", session_token)
            with open("config.ini", "w") as f:
                config.write(f)

            print(f"✅ Session token saved to:")
            print(f"   • {self.session_file}")
            print(f"   • config.ini")
            print(
                f"⏰ Valid for {hours_valid} hours (until {expires_at.strftime('%Y-%m-%d %H:%M:%S')})"
            )

            return True
        except Exception as e:
            print(f"❌ Error saving session: {e}")
            return False

    def check_existing_session(self):
        """Check if we have a valid existing session"""
        try:
            with open(self.session_file, "r") as f:
                session_data = json.load(f)

            expires_at = datetime.fromisoformat(session_data.get("expires_at", ""))
            time_remaining = expires_at - datetime.now()

            if time_remaining.total_seconds() > 0:
                hours_left = time_remaining.total_seconds() / 3600
                return session_data["session_token"], hours_left

            return None, 0
        except FileNotFoundError:
            return None, 0
        except Exception as e:
            print(f"⚠️ Error reading existing session: {e}")
            return None, 0

    def manual_session_generation(self):
        """Manual session token input"""
        print("\n" + "=" * 60)
        print("📝 MANUAL ICICI BREEZE SESSION GENERATOR")
        print("=" * 60)

        # Check existing session first
        existing_token, hours_left = self.check_existing_session()

        if existing_token and hours_left > 0.5:  # More than 30 minutes left
            print(f"✅ Valid session found!")
            print(f"⏰ Expires in: {hours_left:.1f} hours")
            print(f"🔑 Token: {existing_token}")
            print("👍 Using existing session - ready to trade!")
            return existing_token

        print("\nNeed to generate Session Token")
        print(f"\n📋 MANUAL PROCESS:")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"1️⃣  Browser will open ICICI login")
        print(f"2️⃣  Login with your credentials:")
        print(f"    👤 User ID: {self.user_id}")
        print(
            f"    🔐 Password: {'*' * len(self.password) if self.password else '(not saved)'}"
        )
        print(f"    📱 OTP from mobile")
        print(f"3️⃣  After OTP, browser will redirect to localhost:5000")
        print(f"4️⃣  Copy the 'apisession' value from the URL")
        print(f"5️⃣  Paste it below")

        # Create login URL
        encoded_api_key = urllib.parse.quote_plus(self.api_key)
        login_url = (
            f"https://api.icicidirect.com/apiuser/login?api_key={encoded_api_key}"
        )

        print(f"\n🌐 Opening login URL...")
        print(f"📋 URL: {login_url}")

        # Open browser
        try:
            webbrowser.open(login_url)
            print(f"✅ Browser opened successfully")
        except Exception as e:
            print(f"⚠️ Could not open browser automatically: {e}")
            print(f"📋 Please manually open: {login_url}")

        print(f"\n" + "─" * 60)
        print(f"📌 AFTER LOGIN & OTP:")
        print(f"   • Browser will redirect to: localhost:5000/?apisession=XXXXXXXX")
        print(f"   • Copy the number after 'apisession='")
        print(f"   • Example: If URL is localhost:5000/?apisession=51636057")
        print(f"   • Then copy: 51636057")
        print(f"─" * 60)

        # Get session token from user
        while True:
            session_token = input(f"\n🔢 Paste your session token here: ").strip()

            if not session_token:
                print(f"❌ Please enter a session token")
                continue

            # Basic validation
            if not session_token.isdigit():
                print(
                    f"⚠️ Session token should be numeric. You entered: {session_token}"
                )
                confirm = input(f"🤔 Use this token anyway? (y/N): ").strip().lower()
                if confirm != "y":
                    continue

            if len(session_token) < 5:
                print(f"⚠️ Session token seems too short. You entered: {session_token}")
                confirm = input(f"🤔 Use this token anyway? (y/N): ").strip().lower()
                if confirm != "y":
                    continue

            # Save the session token
            print(f"\n💾 Saving session token: {session_token}")

            if self.save_session_token(session_token):
                print(f"\n🎉 SUCCESS! Session token saved successfully!")
                print(f"📊 Your trading system is now ready!")
                return session_token
            else:
                print(f"❌ Failed to save session token")
                retry = input(f"🔄 Try again? (Y/n): ").strip().lower()
                if retry == "n":
                    return None

        return None


def main():
    """Main function"""
    print(f"🚀 ICICI Breeze Session Generator")

    # Validate config first
    if not API_KEY:
        print(f"❌ API Key not found in config.ini")
        print(f"📋 Please add your API key to config.ini under [APICredentials]")
        return

    if not USER_ID:
        print(f"❌ User ID not found in config.ini")
        print(f"📋 Please add your User ID to config.ini under [APICredentials]")
        return

    auth = ManualBreezeAuth()

    try:
        session_token = auth.manual_session_generation()

        if session_token:
            print(f"\n" + "=" * 60)
            print(f"📋 READY TO TRADE!")
            print(f"=" * 60)
            print(f"   🔑 Session token: {session_token}")
            print(f"   📊 Run trader: python3 trader.py")
            print(f"   🔧 Start service: ./service/trader_service.sh start")
            print(f"   ⏰ Valid for ~8 hours")
            print(f"=" * 60)
        else:
            print(f"\n❌ Session generation failed")

    except KeyboardInterrupt:
        print(f"\n👋 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
