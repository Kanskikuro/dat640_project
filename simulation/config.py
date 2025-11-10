"""Configuration for the MusicCRS simulator."""
import os

MUSICCRS_SERVER_URL = "http://127.0.0.1:5000"  # URL of your MusicCRS agent

GROUP_ID = 7
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")  # TODO: Set to your Ollama API key (str)

# TODO: Configure the commands recognized by your MusicCRS agent.
# Keys represent intents and must not be changed; only modify the values.
COMMANDS = {
    "ADD_TRACK": "/pl add [artist]: [track]",
    "GREETING": "Hello!",
    "QUIT": "/quit",
    "REMOVE_TRACK": "/pl remove [artist]: [track]",
    "RECOMMEND": "/pl recommend",
    "SHOW_PLAYLIST": "/pl view",
}
