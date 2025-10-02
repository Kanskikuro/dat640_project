# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent

from db import create_db_and_load_mpd, configure_sqlite_once, ensure_indexes_once, find_song_in_db, find_songs_by_title
from playlist import PlaylistManager
from llm import LLMClient
from config import DB_PATH
from dialoguekit.core.dialogue_act import DialogueAct

_INTENT_OPTIONS = Intent("OPTIONS")


class MusicCRS(Agent):
    def __init__(self, use_llm=True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")
        self._llm = LLMClient() if use_llm else None
        create_db_and_load_mpd(DB_PATH)
        configure_sqlite_once()
        ensure_indexes_once()
        self.playlists = PlaylistManager()
        self._pending_additions = None

    def welcome(self) -> None:
        """Sends the agent's welcome message."""
        utterance = AnnotatedUtterance(
            "Hello, I'm MusicCRS. What are you in the mood for?",
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def goodbye(self) -> None:
        """Quits the conversation."""
        utterance = AnnotatedUtterance(
            "It was nice talking to you. Bye",
            dialogue_acts=[DialogueAct(intent=self.stop_intent)],
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def receive_utterance(self, utterance: Utterance) -> None:
        """Gets called each time there is a new user utterance.

        For now the agent only understands specific command.

        Args:
            utterance: User utterance.
        """
        response = ""
        dialogue_acts = []
        if utterance.text.startswith("/info"):
            response = self._info()
        elif utterance.text.startswith("/ask_llm "):
            prompt = utterance.text[9:]
            response = self._ask_llm(prompt)
        elif utterance.text.startswith("/options"):
            options = [
                "Play some jazz music",
                "Recommend me some pop songs",
                "Create a workout playlist",
            ]
            response = self._options(options)
            dialogue_acts = [
                DialogueAct(
                    intent=_INTENT_OPTIONS,
                    annotations=[
                        SlotValueAnnotation("option", option) for option in options
                    ],
                )
            ]
        elif utterance.text == "/quit":
            self.goodbye()
            return
        elif utterance.text.startswith("/pl"):
            response = self._handle_playlist_command(utterance.text[4:].strip())
        else:
            response = "I'm sorry, I don't understand that command."

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )

    def _handle_playlist_command(self, command: str) -> str:
        """
        # Supported:
        # /pl use <name>
        # /pl add <artist>: <title>
        # /pl remove <artist>: <title>
        # /pl view [name]
        # /pl clear [name]
        # /pl choose <n>
        """

        parts = command.split(" ", 1)
        if not parts:
            return self._pl_help()
        action = parts[0].lower()
        song_request = parts[1].strip() if len(parts) > 1 else ""

        if action in ("use", "new"):
            return self.playlists.use(song_request)
        elif action == "add":
            # Support either "Artist: Title" or just "Title"
            if ":" in song_request:
                artist, title = self._parse_song_spec(song_request)
                return self.playlists.add_song({"artist": artist, "title": title, "id": f"{artist}-{title}"})
            else:
                title = song_request  # If no colon, treat request as title only
                candidates = find_songs_by_title(title)
                if not candidates:
                    return f"No songs found with title '{title}'."
                if len(candidates) == 1:
                    return self.playlists.add_song(candidates[0])
                # Keep up to top 10 candidates for selection
                self._pending_additions = candidates
                return "Multiple matches: <br>" + "<br>".join([f"{i+1}. {c['artist']} : {c['title']}" for i, c in enumerate(candidates)]) + "<br>Use '/pl choose [number]' to select."
        elif action == "remove":
            artist, title = self._parse_song_spec(song_request)
            return self.playlists.remove_song(artist, title)
        elif action in ("choose"):
            if not self._pending_additions:
                return self._pl_help()
            try:
                idx = int(song_request) - 1
            except ValueError:
                return "Please provide a valid number, e.g., '/pl choose 1'."
            if idx < 0 or idx >= len(self._pending_additions):
                return f"Please choose a number between 1 and {len(self._pending_additions)}."
            song = self._pending_additions[idx]
            # Clear pending to avoid accidental reuse
            self._pending_additions = None
                # If song is a string, split into artist/title
            if isinstance(song, str):
                if " - " in song:
                    artist, title = song.split(" - ", 1)
                else:
                    artist, title = None, song
                return self.playlists.add_song({"artist": artist, "title": title, "id": f"{artist}-{title}"})
            
            # Otherwise assume dict with artist/title
            return self.playlists.add_song(song)
        elif action == "view":
            items = self.playlists.view(song_request or None)
            if not items:
                return "Playlist is empty."
            return "<br>".join([f"{i+1}. {s['artist']} - {s['title']}" for i, s in enumerate(items)])
        elif action == "clear":
            return self.playlists.clear(song_request or None)
        else:
            return self._pl_help()

    def _pl_help(self) -> str:
        help_text = (
            "Playlist commands:"
            "<br> - /pl use [playlist name]   (create/switch playlist)"
            "<br> - /pl add [artist]: [title]"
            "<br> - /pl add [title]   (disambiguate if needed with '/pl choose a number from the list')"
            "<br> - /pl remove [artist]: [title]"
            "<br> - /pl view [name]"
            "<br> - /pl clear [name]"
            "<br> - /pl choose [index of the list of songs]"
        )
        return help_text

    def _parse_song_spec(self, spec: str) -> tuple[str, str]:
        if ":" not in spec:
            return "", ""
        artist, title = spec.split(":", 1)
        return artist.strip(), title.strip()

    def _info(self):
        return """I am MusicCRS, a conversational recommender system for music. 
                I can help you create playlists and recommend songs. 
                You can ask me to add or remove songs from your playlist, view your current playlist, or clear it. 
                You can also ask me for music recommendations based on your mood or preferences. 
                To get started, you can use commands like '/ask_llm <your prompt>' to interact with a large language model, or '/options' to see some example options.  
                For playlist management, use commands starting with '/pl'. Type '/pl' for help on playlist commands.
                Type '/quit' to end the conversation.
                """

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )
