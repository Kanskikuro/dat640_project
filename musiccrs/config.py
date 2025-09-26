from dotenv import load_dotenv
from dialoguekit.core.intent import Intent
import os

load_dotenv()
OLLAMA_HOST = "https://ollama.ux.uis.no"
OLLAMA_MODEL = "llama3.3:70b"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

DB_FOLDER = "data"
DB_PATH = "data/spotify.db" 
MPD_DATA = "mpd.v1\data"

_INTENT_OPTIONS = Intent("OPTIONS")