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
            # Check if it's a question (natural language QA)
            response = self._handle_natural_language(utterance.text)

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
    
    def _handle_natural_language(self, text: str) -> str:
        """Route natural language input to QA or playlist handlers.
        
        Determines if the user is asking a question about music (QA)
        or giving a playlist command.
        
        Args:
            text: Natural language user input
            
        Returns:
            Response from appropriate handler
        """
        if not self._llm:
            return "I'm sorry, I don't understand that command. Use /info for help."
        
        # Use LLM to classify intent
        classification_prompt = f"""
            Classify the following user input as either "question" or "playlist_command" if not those two then "neither".

            A "question" is when the user asks for information about with the qa commands and if they dont ask about the qa commands respond with the llm reply as "neither":
            - These are question types: 
                - /qa track [Artist]: [Title] (album|duration|popularity|spotify|all)"
                - /qa artist [Artist] (tracks|albums|top|playlists|all)"
            - A specific track (album, duration, popularity, Spotify URI)
            - An artist (number of tracks, albums, top songs, playlists)
            - Examples: "What album is Hey Jude on?", "How long is Bohemian Rhapsody?", "Who are The Beatles' top songs?"

            A "playlist_command" is when the user wants to:
            - These are playlist commands: ["create", "choose", "select", "remove", "switch", "view", "view_playlists", "clear", "add", "summary", "recommend", "auto"]
            - Add/remove songs, create playlists, view playlists, get recommendations, etc.
            - Examples: "Add Hey Jude", "Create a workout playlist", "Show my playlist"

            When user input does not clearly fit either category, respond with "neither" then just return the llm response directly.

            User input: "{text}"

            Respond with ONLY ONE WORD: either "question" or "playlist_command"
            """
        
        try:
            classification = self._llm.ask(classification_prompt).strip().lower()
            print("Classification:", classification)
            
            if "question" in classification:
                return self._handle_nl_qa(text)
            elif "playlist_command" in classification:
                return self._handle_nl_playlist_intent(text)
            elif "neither" in classification:
                return self._llm.ask(text)
        except Exception as e:
            # Fallback to playlist intent if classification fails
            return self._llm.ask(text)

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

        # Build context about pending additions and recommendations
        pending_additions = []
        if self.playlists._pending_additions:
            pending_additions = [
                f"{i+1}. {s['artist']} : {s['title']}"
                for i, s in enumerate(self.playlists._pending_additions)
            ]
        
        recommendation_enum = []
        if self.playlists._recommendation_cache:
            rec , recommended_data = self.playlists._recommendation_cache 
            recommendation_enum = [
                f"{i+1}. {rec[song_id]} (song appears in {freq} playlists)"
                for i, (song_id, freq) in enumerate(recommended_data) if song_id in rec
            ]

        prompt = f"""
    You are an intent parser using free natural language for a music playlist system.
    Only output a single JSON object with no extra text.
    The JSON object must have the keys:
    - "intent": one of ["create", "choose", "select", "remove", "switch", "view", "view_playlists", "clear", "add", "summary", "recommend", "auto"]
    - "song": the song title 
    - "artist": the artist name or empty string if not given.
    - "idx": the index number for choosing from multiple options (1-based)
    - "playlist_name": the playlist name or empty string if not given.
    - "description": for "auto" intent, the natural language description of the playlist to create (e.g. "sad love songs", "energetic gym music")
    - "reply": the full text reply from you, the llm.
    
    IMPORTANT - Distinguish between "choose" and "select":
    - Use "choose" when selecting from pending song additions (multiple matches for a song title)
    - Use "select" when selecting from recommended songs
    - If there are pending additions, use "choose". If there are recommendations, use "select".
    
    Check for if the song is valid and for fix any obvious typos in artist or title.
    If there is no song, but artist, find a song from that artist that is not already in the playlist.
    if there is no artist but song and the intent is add. return "intent" as "add", artist "song" as the title. 
    If the user wants to select songs from the recommended list, always return the selection as "idx": a list of 1-based numbers corresponding to the order in the recommendation list, not song titles. Do not put song names in "idx".
    If the user wants to choose from pending additions (song matches), return "idx" as a single number (1-based).
    Dont add songs that are already in the playlist.
    Always include the chosen song name in the "song" field, even if the user only mentioned the artist.
    
    For "auto" intent: When the user wants to create a playlist from scratch based on a description (like an artist name, genre, mood, or theme), 
    set "intent" to "auto" and put the description in the "description" field. Examples:
    - "create a playlist with relaxing music" → {{"intent": "auto", "description": "relaxing music"}}
    - "make a sad playlist" → {{"intent": "auto", "description": "sad songs"}}
    - "playlist for working out" → {{"intent": "auto", "description": "energetic gym music"}}
    
    Allow users to express their intentions for playlist manipulation and interacting with recommendations using free natural language text instead of/in addition to using commands with a fixed syntax. 
    Allow users to refer to tracks and artists without exact string matching (including lack of proper capitalization and punctuation) and resolve ambiguities (eg, many artists have a song called “Love”).
    Allow the user to make a natural language selection, with support for adding all songs, some selected songs (eg, "add the first two" or "add them except the one by Metallica"), or no songs at all.
    
    User input: "{text}"
    User playlist: "{self.playlists.view(self.playlists._current)}"
    Pending song additions (use "choose" for these): "{pending_additions}"
    Recommended songs (use "select" for these): "{recommendation_enum}"

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
        
        print("LLM reply:", llm_reply)

        intent = data.get("intent", "").lower()
        idx_raw = data.get('idx', []) or []
        # Handle both single int and list of ints
        if isinstance(idx_raw, int):
            idx_list = [idx_raw] if idx_raw > 0 else []
        elif isinstance(idx_raw, list):
            idx_list = [i for i in idx_raw if isinstance(i, int) and i > 0]
        else:
            idx_list = []
        artist = data.get("artist", "") or ""
        song = data.get("song", "") or ""
        playlist_name = data.get("playlist_name", "") or ""
        description = data.get("description", "") or ""
        llm_reply_text = data.get("reply", "") or ""
        
        # Check if LLM needs more information for certain intents
        needs_song = intent in ["add", "remove"] and not song and not artist
        needs_description = intent == "auto" and not description
        needs_playlist_name = intent in ["create", "switch"] and not playlist_name
        needs_idx = intent in ["choose", "select"] and not idx_list
        
        # If LLM is asking for more information, return the reply instead of executing
        if needs_song or needs_description or needs_playlist_name or needs_idx:
            # Fallback messages if no reply provided
            if needs_song:
                return "Which song would you like to add/remove? Please specify the artist and title."
            elif needs_description:
                return "What kind of playlist would you like to create? Please describe it."
            elif needs_playlist_name:
                return "What would you like to name the playlist?"
            elif needs_idx:
                return "Which song(s) would you like to choose? Please specify the number(s)."
            elif llm_reply_text:
                return llm_reply_text
        
        arg = f"{artist}:{song}"
        if artist == "":
            arg = song

        # Only print the relevant list based on intent
        if intent == "choose" and pending_additions:
            print("Pending additions:", pending_additions)
        elif intent == "select" and recommendation_enum:
            print("Recommendations:", recommendation_enum)
        
        match intent:
            case "view_playlists" :
                cmd = intent
            case "add" | "remove":
                cmd = f"{intent} {arg}"
            case "choose" | "select":
                cmd = f"{intent} {' '.join(map(str, idx_list))}"
            case "create" | "switch" | "view" | "recommend" | "summary" |"clear":
                cmd = f"{intent} {playlist_name}"
            case "auto":
                cmd = f"{intent} {description}"
            case _:
                return "No intent, here's your LLM reply back: " + llm_reply

        return self._handle_playlist_command(cmd)
    

    def _handle_nl_qa(self, text: str) -> str:
        """Handle natural language questions about tracks and artists.
        
        Uses LLM to extract:
        - Question type (track or artist)
        - What information is being asked (album, duration, etc.)
        - Track/artist name
        
        Args:
            text: Natural language question
            
        Returns:
            Answer to the question
        """
        if not self._llm:
            return "LLM is disabled."
        
        prompt = f"""
            You are a query parser for a music information system.
            Extract the following information from the user's question and output ONLY a JSON object:

            {{
                "target": "track" or "artist",
                "artist": "artist name" (empty string if not mentioned),
                "title": "song title" (empty string if not mentioned or if target is artist),
                "question_type": one of ["album", "duration", "popularity", "spotify", "tracks", "albums", "top", "playlists", "all"]
            }}

            Question type mapping:
            - For tracks: "album" (what album), "duration" (how long), "popularity" (how popular), "spotify" (Spotify URI), "all" (everything)
            - For artists: "tracks" (how many songs), "albums" (how many albums), "top" (top songs), "playlists" (in how many playlists), "all" (everything)

            If the question asks for general info or multiple things, use "all".
            Fix any obvious typos in artist or song names.

            User question: "{text}"

            Respond with JSON only, no explanation.
            """
        
        try:
            llm_reply = self._llm.ask(prompt)
            if not llm_reply:
                return "Could not understand the question."
            
            # Remove code fences if present
            if llm_reply.startswith("```"):
                llm_reply = (
                    llm_reply.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
            print("LLM Reply:", llm_reply)
            data = json.loads(llm_reply)
            target = data.get("target", "").lower()
            artist = data.get("artist", "") or ""
            title = data.get("title", "") or ""
            qtype = data.get("question_type", "all") or "all"
            
            if target == "track":
                if not artist or not title:
                    # Question doesn't fit QA structure, ask LLM instead
                    return self._llm.ask(text)
                
                song_spec = f"{artist}:{title}"
                return handle_qa_track(song_spec, qtype, self._parse_song_spec, self._format_duration)
            
            elif target == "artist":
                if not artist:
                    # Question doesn't fit QA structure, ask LLM instead
                    return self._llm.ask(text)
                
                # Check if this is a QA-type question or a general question
                # QA questions: tracks, albums, top, playlists
                # General questions: who is, what is, tell me about, etc.
                if qtype not in ["tracks", "albums", "top", "playlists", "all"]:
                    # Not a valid QA type, ask LLM instead
                    return self._llm.ask(text)
                
                return handle_qa_artist(artist, qtype)
            
            else:
                # Couldn't determine target, ask LLM instead
                return self._llm.ask(text)
        
        except json.JSONDecodeError as e:
            # Couldn't parse JSON, ask LLM instead
            return self._llm.ask(text)
        except Exception as e:
            # Any other error, ask LLM instead
            return self._llm.ask(text)

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
                <br> <strong>NEW:</strong> You can ask me questions in natural language! For example:
                <br> - "What album is Hey Jude on?"
                <br> - "How long is Bohemian Rhapsody by Queen?"
                <br> - "What are The Beatles' top songs?"
                <br> - "Add some upbeat songs to my playlist"
                <br> To get started, you can use commands like '/ask_llm <your prompt>' to interact with a large language model, or '/options' to see some example options.  
                <br> For playlist management, use commands starting with '/pl'. Type '/pl help' for help on playlist commands.
                <br> For playing tracks, use commands starting with '/play'. Type '/play help' for help on playback commands.
                <br> For questions about tracks or artists, use commands starting with '/qa' or just ask in natural language.
                <br> Type '/quit' to end the conversation.
                """

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )
