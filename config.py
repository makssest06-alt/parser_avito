import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1993831036").split(',')))
