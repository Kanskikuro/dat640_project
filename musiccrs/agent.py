# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent
import json
from db import get_track_info, get_artist_stats, search_tracks_by_keywords
from spotify import SpotifyClient
from collections import Counter
from playlist import shared_playlists
from llm import LLMClient
from config import DB_PATH
_INTENT_OPTIONS = Intent("OPTIONS")
from events import emit as emit_event

# Import modular command handlers
from auto_playlist import create_auto_playlist
from qa_commands import handle_qa_track, handle_qa_artist, get_qa_help
from playtrack import handle_play_track, handle_play_uri, render_player, get_play_help


class MusicCRS(Agent):
    def __init__(self, use_llm=True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")
        self._llm = LLMClient() if use_llm else None
        self._spotify = SpotifyClient()
        self.playlists = shared_playlists

    # --- small helpers to update frontend ---
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
            response = self._llm.ask(prompt)
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
        elif utterance.text.startswith("/play"):
            response = self._handle_play_command(utterance.text[5:].strip())
        elif utterance.text.startswith("/qa"):
            response = self._handle_qa_command(utterance.text[3:].strip())
        elif utterance.text.startswith("/pl"):
            response = self._handle_playlist_command(
                utterance.text[4:].strip())
        else:
            response = self._handle_nl_playlist_intent(utterance.text)

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )

    def _handle_playlist_command(self, command: str) -> str:
        """Playlist commands via chat (/pl ...). Emits UI updates over Socket.IO.
        
        Supported:
        - /pl create <name>
        - /pl switch <name>
        - /pl add <artist>: <title>
        - /pl remove <artist>: <title>
        - /pl view [name]
        - /pl clear [name]
        - /pl choose <n>
        - /pl summary|stats|info [name]
        - /pl auto <description>
        - /pl recommend <playlist>
        """
        parts = command.split(" ", 1)
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match action:
            case "create":
                res = self.playlists.create_playlist(arg)
                self._emit_pl("created" if res.startswith("Created") else "switched", arg)
                if hasattr(self.playlists, "view_playlists"):
                    self._emit_pl("playlists", self.playlists.view_playlists())
                self._emit_songs_for_current()
                return res

            case "switch":
                res = self.playlists.switch_playlist(arg)
                self._emit_pl("switched", arg)
                if hasattr(self.playlists, "view_playlists"):
                    self._emit_pl("playlists", self.playlists.view_playlists())
                self._emit_songs_for_current()
                return res

            case "view":
                items = self.playlists.view(arg or None)
                if isinstance(items, str):
                    return items
                # emit view for UI too
                song_strings = [f"{s['artist']}:{s['title']}" for s in items]
                self._emit_pl("songs", song_strings)
                return "<br>".join(f"{s['artist']} : {s['title']}" for s in items)

            case "clear":
                res = self.playlists.clear(arg or None)
                target = arg or getattr(self.playlists, "_current", None)
                self._emit_pl("cleared", target)
                if hasattr(self.playlists, "view_playlists"):
                    self._emit_pl("playlists", self.playlists.view_playlists())
                self._emit_pl("songs", [])
                return res

            # Song ops
            case "add":
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
            
            case "choose":
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

            case "remove":
                res = self.playlists.remove_song(arg)
                if res.startswith("Removed"):
                    self._emit_pl("removed", arg)
                self._emit_songs_for_current()
                if hasattr(self.playlists, "view_playlists"):
                    self._emit_pl("playlists", self.playlists.view_playlists())
                return res
            
            case "summary" | "stats" | "info":
                return self.playlists.get_summary(
                playlist=arg or None,
                format_duration_func=self._format_duration
            )

            case "auto":
                return self._handle_auto_playlist(arg)
            
            case "recommend":
                res = self.playlists.recommend(arg or None)
                return res
            case "select":
                try:
                    indices = [int(x) for x in arg.split()]
                except ValueError:
                    return "Please provide valid numbers, e.g., '/pl select 1 2 3'."
                res = self.playlists.select_recommendations(indices)
                self._emit_songs_for_current()
                if hasattr(self.playlists, "view_playlists"):
                    self._emit_pl("playlists", self.playlists.view_playlists())
                return res
            case _:
                return self._pl_help()
            
    def _handle_auto_playlist(self, description: str) -> str:
        """Automatically create a playlist from a natural language description.
        
        Delegates to the modular auto_playlist.create_auto_playlist() function.
        
        Args:
            description: Natural language description (e.g., "sad love songs" or "energetic gym music")
            
        Returns:
            HTML formatted response with playlist creation results
        """
        return create_auto_playlist(
            description=description,
            playlist_manager=self.playlists,
            emit_pl_func=self._emit_pl
        )

    def _handle_nl_playlist_intent(self, text: str) -> str:
        """
        Handle natural language playlist commands.
        Examples:
        "Add Hey Jude by The Beatles"
        "Remove Shape of You"
        "Show my playlist"
        "Clear the current playlist"
        """
        if not self._llm:
            return "LLM is disabled."

        if self.playlists._recommendation_cache:
            rec , recommended_data = self.playlists._recommendation_cache 
            recommendation_enum = [
                f"{i+1}. {rec[song_id]} (song appears in {freq} playlists)"
                for i, (song_id, freq) in enumerate(recommended_data) if song_id in rec
                ]
        else:
            recommendation_enum = []

        prompt = f"""
    You are an intent parser using free natural language for a music playlist system.
    Only output a single JSON object with no extra text.
    The JSON object must have the keys:
    - "intent": one of ["create", "choose", "select", "remove", "switch", "view", "view_playlists", "clear", "add", "summary", "recommend"]
    - "song": the song title 
    - "artist": the artist name or empty string if not given.
    - "idx": the index number for choosing from multiple options (1-based)
    - "playlist_name": the playlist name or empty string if not given.  
    - "reply": the full text reply from you, the llm.
    
    Check for if the song is valid and for fix any obvious typos in artist or title.
    If there is no song, but artist, find a song from that artist that is not already in the playlist.
    if there is no artist but song and the intent is add. return "intent" as "add", artist "song" as the title. 
    If the user wants to select songs from the recommended list, always return the selection as "idx": a list of 1-based numbers corresponding to the order in the recommendation list, not song titles. Do not put song names in "idx".
    Dont add songs that are already in the playlist.
    Always include the chosen song name in the "song" field, even if the user only mentioned the artist.
    
    Allow users to express their intentions for playlist manipulation and interacting with recommendations using free natural language text instead of/in addition to using commands with a fixed syntax. 
    Allow users to refer to tracks and artists without exact string matching (including lack of proper capitalization and punctuation) and resolve ambiguities (eg, many artists have a song called “Love”).
    Allow the user to make a natural language selection, with support for adding all songs, some selected songs (eg, "add the first two" or "add them except the one by Metallica"), or no songs at all.
    
    User input: "{text}"
    User playlist : "{self.playlists.view(self.playlists._current)}"
    Recomended songs: "{recommendation_enum}"

    Respond with JSON only.
    """

        try:
            llm_reply = self._llm.ask(prompt)
            if not llm_reply:
                return "Could not parse intent: LLM returned empty response"

            # Remove any code fences
            if llm_reply.startswith("```"):
                llm_reply = (
                    llm_reply.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )

            data = json.loads(llm_reply)
        except json.JSONDecodeError as e:
            return f"Could not parse intent: {e}. Raw LLM response: {llm_reply}"

        intent = data.get("intent", "").lower()
        idx_list = data.get('idx', []) or []  # Handle None case
        idx_list = [i for i in idx_list if isinstance(i, int) and i > 0]
        artist = data.get("artist", "") or ""
        song = data.get("song", "") or ""
        playlist_name = data.get("playlist_name", "") or ""
        arg = f"{artist}:{song}"
        if artist == "":
            arg = song
        
        print(llm_reply)
        print(recommendation_enum)
        match intent:
            case "view_playlists" :
                cmd = intent
            case "add" | "remove":
                cmd = f"{intent} {arg}"
            case "choose" | "select":
                cmd = f"{intent} {' '.join(map(str, idx_list))}"
            case "create" | "switch" | "view" | "recommend" | "summary" |"clear":
                cmd = f"{intent} {playlist_name}"
            case _:
                return "No intent, here's your LLM reply back: " + llm_reply

        return self._handle_playlist_command(cmd)

    def _pl_help(self) -> str:
        """Return playlist command help text."""
        return self.playlists.get_help()

    def _parse_song_spec(self, spec: str) -> tuple[str, str]:
        if ":" not in spec:
            return "", ""
        artist, title = spec.split(":", 1)
        return artist.strip(), title.strip()

    # --- Playback commands ---
    def _handle_play_command(self, command: str) -> str:
        """
        Play commands:
          - /play track <artist>: <title>
          - /play uri <spotify_track_uri_or_url>
        
        Delegates to modular playback_commands functions.
        """
        if not command:
            return get_play_help()

        parts = command.split(None, 1)
        if len(parts) < 2:
            return get_play_help()

        target = parts[0].lower()
        rest = parts[1].strip()

        if target == "track":
            if ":" not in rest:
                return "Please specify the song as 'Artist: Title'."
            artist, title = self._parse_song_spec(rest)
            return handle_play_track(artist, title, self._spotify, self._render_player)

        if target == "uri":
            return handle_play_uri(rest, self._render_player)

        return get_play_help()

    def _render_player(self, spotify_uri_or_url: str, label: str) -> str:
        """Render a player for a Spotify track.
        
        Delegates to modular playback_commands.render_player() function.
        """
        return render_player(spotify_uri_or_url, label, self._spotify)

    def _play_help(self) -> str:
        """Return playback command help text."""
        return get_play_help()

    # --- QA commands ---
    def _handle_qa_command(self, command: str) -> str:
        """
        QA commands:
          - /qa track <artist>: <title> (album|duration|popularity|spotify|all)
          - /qa artist <artist> (tracks|albums|top|playlists|all)
        
        Delegates to modular qa_commands functions.
        """
        if not command:
            return get_qa_help()

        parts = command.split(None, 1)
        if len(parts) < 2:
            return get_qa_help()

        target = parts[0].lower()
        rest = parts[1].strip()

        if target == "track":
            # Expect "<artist>: <title> <qtype>"
            if " " not in rest:
                return "Please provide a question type. Example: /qa track Artist: Title album, duration, popularity, spotify, all"
            song_spec, qtype = rest.rsplit(" ", 1)
            qtype = qtype.lower()
            return handle_qa_track(song_spec, qtype, self._parse_song_spec, self._format_duration)
        elif target == "artist":
            # Expect "<artist> <qtype>"
            if " " not in rest:
                return "Please provide a question type. Example: /qa artist Artist Name top, albums, tracks, playlists, all"
            artist, qtype = rest.rsplit(" ", 1)
            qtype = qtype.lower()
            return handle_qa_artist(artist, qtype)
        else:
            return get_qa_help()

    def _qa_help(self) -> str:
        """Return QA command help text."""
        return get_qa_help()

    def _format_duration(self, duration_ms: int | None) -> str:
        if not duration_ms or duration_ms <= 0:
            return "Unknown"
        seconds = duration_ms // 1000
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    def _info(self):
        return """   I am MusicCRS, a conversational recommender system for music. 
                <br> I can help you create playlists and recommend songs. 
                <br> You can ask me to add or remove songs from your playlist, view your current playlist, or clear it. 
                <br> You can also ask me for music recommendations based on your mood or preferences. 
                <br> To get started, you can use commands like '/ask_llm <your prompt>' to interact with a large language model, or '/options' to see some example options.  
                <br> For playlist management, use commands starting with '/pl'. Type '/pl help' for help on playlist commands.
                <br> For playing tracks, use commands starting with '/play'. Type '/play help' for help on playback commands.
                <br> For questions about tracks or artists, use commands starting with '/qa'. Type
                <br> Type '/quit' to end the conversation.
                """

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )
