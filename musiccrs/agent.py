# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent

from db import create_db_and_load_mpd, configure_sqlite_once, ensure_indexes_once, find_song_in_db, find_songs_by_title
from playlist import shared_playlists
from llm import LLMClient
from config import DB_PATH
from dialoguekit.core.dialogue_act import DialogueAct
_INTENT_OPTIONS = Intent("OPTIONS")
from events import emit as emit_event


class MusicCRS(Agent):
    def __init__(self, use_llm=True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")
        self._llm = LLMClient() if use_llm else None
        self.playlists = shared_playlists

    # --- small helpers ---
    def _emit_pl(self, event_type: str, data):
        try:
            emit_event("pl_response", {"type": event_type, "data": data})
        except Exception:
            pass

    def _emit_songs_for_current(self):
        cur = getattr(self.playlists, "_current", None)
        if not cur:
            return
        items = self.playlists.view(cur)
        if isinstance(items, list):
            song_strings = [f"{s['artist']}:{s['title']}" for s in items]
            self._emit_pl("songs", song_strings)

    def _ask_llm(self, prompt: str) -> str:
        if not self._llm:
            return "LLM is disabled."
        try:
            return self._llm.ask(prompt)
        except Exception as e:
            return f"LLM error: {e}"

    def welcome(self) -> None:
        """Sends the agent's welcome message."""
        utterance = AnnotatedUtterance(
            "Hello, I'm MusicCRS. Type '/info' for more information. What are you in the mood for?",
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
            response = self._handle_playlist_command(
                utterance.text[4:].strip())
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
        """Playlist commands via chat (/pl ...). Emits UI updates over Socket.IO."""
        parts = command.split(" ", 1)
        if not parts:
            return self._pl_help()
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Playlist ops
        if action == "create":
            res = self.playlists.create_playlist(arg)
            if res.startswith("Created"):
                self._emit_pl("created", arg)
            else:
                self._emit_pl("switched", arg)
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            self._emit_songs_for_current()
            return res

        if action == "switch":
            res = self.playlists.switch_playlist(arg)
            self._emit_pl("switched", arg)
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            self._emit_songs_for_current()
            return res

        if action == "view":
            items = self.playlists.view(arg or None)
            if isinstance(items, str):
                return items
            # emit view for UI too
            song_strings = [f"{s['artist']}:{s['title']}" for s in items]
            self._emit_pl("songs", song_strings)
            return "<br>".join(f"{s['title']} : {s['artist']}" for s in items)

        if action == "clear":
            res = self.playlists.clear(arg or None)
            target = arg or getattr(self.playlists, "_current", None)
            self._emit_pl("cleared", target)
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            self._emit_pl("songs", [])
            return res

        # Song ops
        if action == "add":
            res = self.playlists.add_song(arg)
            # Multiple matches case: manager stores pending
            pending = getattr(self.playlists, "_pending_additions", None)
            if pending:
                candidates = [{"artist": c["artist"], "title": c["title"]} for c in pending]
                self._emit_pl("multiple_matches", candidates)
                return res
            # Otherwise, song added
            self._emit_pl("added", arg)
            self._emit_songs_for_current()
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            return res

        if action == "choose":
            try:
                idx = int(arg) - 1
            except ValueError:
                return "Please provide a valid number, e.g., '/pl choose 1'."
            res = self.playlists.choose_song(idx)
            if res.startswith("Added"):
                self._emit_pl("added", res)
            self._emit_songs_for_current()
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            return res

        if action == "remove":
            res = self.playlists.remove_song(arg)
            if res.startswith("Removed"):
                self._emit_pl("removed", arg)
            self._emit_songs_for_current()
            if hasattr(self.playlists, "view_playlists"):
                self._emit_pl("playlists", self.playlists.view_playlists())
            return res

        # Help / unknown
        return self._pl_help()

    def _pl_help(self) -> str:
        return (
            "Playlist commands:"
            "<br> - /pl create [playlist name]   (create playlist)"
            "<br> - /pl switch [playlist name]   (switch to existing or create new playlist)"
            "<br> - /pl add [artist]: [song title]"
            "<br> - /pl add [song title]   (disambiguate if needed with '/pl choose a number from the list')"
            "<br> - /pl remove [artist]: [song title]"
            "<br> - /pl view [playlist name] or none for current"
            "<br> - /pl clear [playlist name] or none for current]"
            "<br> - /pl choose [index of the list of songs]"
        )

    def _parse_song_spec(self, spec: str) -> tuple[str, str]:
        if ":" not in spec:
            return "", ""
        artist, title = spec.split(":", 1)
        return artist.strip(), title.strip()

    def _info(self):
        return """   I am MusicCRS, a conversational recommender system for music. 
                <br> I can help you create playlists and recommend songs. 
                <br> You can ask me to add or remove songs from your playlist, view your current playlist, or clear it. 
                <br> You can also ask me for music recommendations based on your mood or preferences. 
                <br> To get started, you can use commands like '/ask_llm <your prompt>' to interact with a large language model, or '/options' to see some example options.  
                <br> For playlist management, use commands starting with '/pl'. Type '/pl help' for help on playlist commands.
                <br> Type '/quit' to end the conversation.
                """

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )
