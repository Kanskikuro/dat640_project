# server/app.py
from dialoguekit.platforms import FlaskSocketPlatform
from agent import MusicCRS


def run_server():
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()


if __name__ == "__main__":
    run_server()
