from dotenv import load_dotenv
import os

load_dotenv()
OLLAMA_HOST = "https://ollama.ux.uis.no"
OLLAMA_MODEL = "llama3.3:70b"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

BACKEND_PATH = "musiccrs"
DB_FOLDER = "db"
DB_PATH = f"{BACKEND_PATH}/{DB_FOLDER}/music.db"
MPD_DATA = "mpd.v1\data"


