from dotenv import load_dotenv
import os

load_dotenv()

EMAIL = os.getenv("TT_EMAIL")
PASSWORD = os.getenv("TT_PASSWORD")

BASE_URL = "https://www.tendertiger.co.in"