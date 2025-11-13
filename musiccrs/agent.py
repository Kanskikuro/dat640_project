# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent
import json
import re
from datetime import datetime
from db import search_tracks_by_keywords, find_song_in_db
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
from mood_analyzer import mood_analyzer


class MusicCRS(Agent):
    def __init__(self, use_llm=True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")
        self._llm = LLMClient() if use_llm else None
        self._spotify = SpotifyClient()
        self.playlists = shared_playlists
        
        #Session-based user context tracking
        self._session_context = {
            "artists": Counter(),  # Track artist preferences
            "moods": [],  # Track mood history
            "recent_songs": []  # Recent additions/plays
        }

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
                # Otherwise, song added - track it
                if res.startswith("Added"):
                    # Extract artist and title for tracking
                    try:
                        if ":" in arg:
                            parts = arg.split(":", 1)
                            artist = parts[0].strip()
                            title = parts[1].strip()
                            self._track_song_interaction(artist, title)
                    except:
                        pass
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
                    # Track the chosen song
                    pending = getattr(self.playlists, "_pending_additions", None)
                    if pending and 0 <= idx < len(pending):
                        song = pending[idx]
                        self._track_song_interaction(song["artist"], song["title"])
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
                # R7.1: Use mood and taste-aware recommendation
                if arg and self._llm:
                    return self._recommend_with_mood_and_taste(arg)
                else:
                    # Fallback to standard recommendation
                    res = self.playlists.recommend(arg or None)
                    return res
            
            case "select":
                try:
                    indices = [int(x) for x in arg.split()]
                except ValueError:
                    return "Please provide valid numbers, e.g., '/pl select 1 2 3'."
                res = self.playlists.select_recommendations(indices)
                # Track selected songs
                cache = getattr(self.playlists, "_recommendation_cache", None)
                if cache:
                    # Handle both cache formats
                    if isinstance(cache, tuple):
                        # Regular collaborative filtering: (rec_dict, recommended_data)
                        rec, recommended_data = cache
                        for idx in indices:
                            if 0 < idx <= len(recommended_data):
                                song_id, _ = recommended_data[idx - 1]
                                song_info = rec[song_id]  # "Artist : Title"
                                artist, title = song_info.split(" : ", 1)
                                self._track_song_interaction(artist, title)
                    elif isinstance(cache, list):
                        # Mood-aware: list of {"artist": ..., "title": ...}
                        for idx in indices:
                            if 0 < idx <= len(cache):
                                song = cache[idx - 1]
                                self._track_song_interaction(song["artist"], song["title"])
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
        # Get the playlist before auto-creation
        old_playlist_songs = set()
        if self.playlists._current:
            current_songs = self.playlists.view(self.playlists._current)
            if isinstance(current_songs, list):
                old_playlist_songs = {(s['artist'], s['title']) for s in current_songs}
        
        # Create the auto playlist
        result = create_auto_playlist(
            description=description,
            playlist_manager=self.playlists,
            emit_pl_func=self._emit_pl
        )
        
        # Track all newly added songs for R7.1 context
        if self.playlists._current:
            new_songs = self.playlists.view(self.playlists._current)
            if isinstance(new_songs, list):
                for song in new_songs:
                    # Only track songs that weren't in the old playlist
                    if (song['artist'], song['title']) not in old_playlist_songs:
                        self._track_song_interaction(song['artist'], song['title'])
        
        return result
    
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
            # Handle both cache formats: tuple (collaborative) or list (mood-aware)
            if isinstance(self.playlists._recommendation_cache, tuple):
                # Collaborative filtering: (rec_dict, recommended_data)
                rec, recommended_data = self.playlists._recommendation_cache 
                recommendation_enum = [
                    f"{i+1}. {rec[song_id]} (song appears in {freq} playlists)"
                    for i, (song_id, freq) in enumerate(recommended_data) if song_id in rec
                ]
            elif isinstance(self.playlists._recommendation_cache, list):
                # Mood-aware: list of {"artist": ..., "title": ...}
                recommendation_enum = [
                    f"{i+1}. {song['artist']} : {song['title']}"
                    for i, song in enumerate(self.playlists._recommendation_cache)
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
    - "description": for "auto" or "recommend" intent, the natural language description
    - "reply": the full text reply from you, the llm.
    
    CRITICAL - Distinguish between "recommend" and "auto":
    - Use "recommend" when user wants to GET SUGGESTIONS/RECOMMENDATIONS to browse or add to EXISTING playlist
      Examples: "recommend me some happy songs", "suggest upbeat music", "find me sad songs"
    - Use "auto" when user wants to CREATE/GENERATE A NEW PLAYLIST from scratch
      Examples: "create a playlist with relaxing music", "make a workout playlist", "build a sad playlist"
    - If user says "recommend" or "suggest" or "find" → use "recommend"
    - If user says "create" or "make" or "build" or "generate" a PLAYLIST → use "auto"
    
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
            
            # Fix common JSON issues from LLM responses
            # Replace invalid escape sequences like \' with proper escapes
            llm_reply = llm_reply.replace(r"\'", "'")  # Remove backslash before single quotes
            llm_reply = llm_reply.replace(r'\"', '"')  # This is valid, but normalize it

            data = json.loads(llm_reply)
        except json.JSONDecodeError as e:
            return f"Could not parse intent: {e}. Raw LLM response: {llm_reply}"
        
        # Parse all fields first
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
        
        # Debug output
        print("LLM reply:", llm_reply)
        print(f"Parsed intent: '{intent}', artist: '{artist}', song: '{song}', playlist: '{playlist_name}', description: '{description}'")
        
        # Check if intent is empty or invalid
        if not intent:
            print("⚠️ No intent found in LLM response!")
            if llm_reply_text:
                return llm_reply_text
            return "I couldn't understand what you want to do. Please try rephrasing."
        
        # Check if LLM needs more information for certain intents
        needs_song = intent in ["add", "remove"] and not song and not artist
        needs_description = intent == "auto" and not description
        needs_playlist_name = intent in ["create", "switch"] and not playlist_name
        needs_idx = intent in ["choose", "select"] and not idx_list
        
        # If LLM is asking for more information, return the reply instead of executing
        if needs_song or needs_description or needs_playlist_name or needs_idx:
            # Return LLM's reply if provided, otherwise use fallback messages
            if llm_reply_text:
                return llm_reply_text
            elif needs_song:
                return "Which song would you like to add/remove? Please specify the artist and title."
            elif needs_description:
                return "What kind of playlist would you like to create? Please describe it."
            elif needs_playlist_name:
                return "What would you like to name the playlist?"
            elif needs_idx:
                return "Which song(s) would you like to choose? Please specify the number(s)."
        
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
            case "create" | "switch" | "view" | "summary" |"clear":
                cmd = f"{intent} {playlist_name}"
            case "recommend":
                # R7.1: Use mood-aware recommendation with original text
                if self._llm:
                    return self._recommend_with_mood_and_taste(text)
                else:
                    cmd = f"{intent} {playlist_name}"
            case "auto":
                cmd = f"{intent} {description}"
            case _:
                return "No intent matched, here's your LLM reply: " + llm_reply_text if llm_reply_text else "I didn't understand that command."

        print(f"Executing playlist command: /pl {cmd}")
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
    
    # Session context tracking
    def _track_song_interaction(self, artist: str, title: str):
        """Track user interactions with songs for personality profiling.
        
        Args:
            artist: Artist name
            title: Song title
        """
        # Update artist preference counter
        self._session_context["artists"][artist] += 1
        
        # Track recent songs (keep last 20)
        self._session_context["recent_songs"].append({
            "artist": artist,
            "title": title
        })
        if len(self._session_context["recent_songs"]) > 20:
            self._session_context["recent_songs"].pop(0)
    
    def _get_user_taste_profile(self) -> dict:
        """Build user taste profile from session context.
        
        Returns:
            dict with:
                - top_artists: List of top 3 artists
                - artist_preferences: All artist counts
        """
        top_artists = [
            artist for artist, _ in 
            self._session_context["artists"].most_common(3)
        ]
        
        return {
            "top_artists": top_artists,
            "artist_preferences": dict(self._session_context["artists"])
        }
    
    def _detect_automatic_context(self) -> dict:
        """R7.1.3: Automatic context detection based on time of day and previous behavior.
        
        Returns:
            dict with:
                - time_of_day: morning/afternoon/evening/night
                - suggested_mood: Mood suggestion based on time
                - context_description: Human-readable context description
        """
        current_hour = datetime.now().hour
        
        # Time of day detection
        if 5 <= current_hour < 12:
            time_of_day = "morning"
            suggested_mood = "energetic"
            context_desc = "morning energy boost"
        elif 12 <= current_hour < 17:
            time_of_day = "afternoon"
            suggested_mood = "upbeat"
            context_desc = "afternoon productivity"
        elif 17 <= current_hour < 21:
            time_of_day = "evening"
            suggested_mood = "relaxing"
            context_desc = "evening wind-down"
        else:  # 21-5
            time_of_day = "night"
            suggested_mood = "calm"
            context_desc = "late-night chill"
        
        # Analyze behavioral patterns
        recent_moods = self._session_context["moods"][-10:]  # Last 10 mood requests
        if recent_moods:
            mood_counter = Counter(m["mood"] for m in recent_moods)
            most_common_mood = mood_counter.most_common(1)[0][0]
            context_desc += f", you often enjoy {most_common_mood} music"
        
        print(f"\n⏰ AUTOMATIC CONTEXT DETECTION (R7.1.3)")
        print(f"   Time: {time_of_day} ({current_hour}:00)")
        print(f"   Suggested Mood: {suggested_mood}")
        print(f"   Context: {context_desc}\n")
        
        return {
            "time_of_day": time_of_day,
            "suggested_mood": suggested_mood,
            "context_description": context_desc
        }
    
    def _recommend_with_mood_and_taste(self, user_request: str) -> str:
        """R7.1: LLM-based mood and personality-aware recommendation.
        
        NEW APPROACH:
        1. Analyze emotion with BERT
        2. Get user's taste profile from session
        3. Ask LLM to recommend songs based on mood + taste context
        4. Verify LLM recommendations exist in database
        5. Fallback to database search if needed
        
        Args:
            user_request: Natural language request from user
            
        Returns:
            HTML formatted recommendation response
        """
        if not self._llm:
            return "LLM is required for mood-aware recommendations. Please enable LLM."
        
        # Step 1: Analyze user's emotional context with BERT
        mood_data = mood_analyzer.analyze_emotion(user_request)
        primary_emotion = mood_data["primary_emotion"]
        music_mood = mood_data["music_mood"]
        
        # Print BERT emotion detection results
        print("\n" + "="*60)
        print("🎭 BERT EMOTION ANALYSIS")
        print("="*60)
        print(f"📝 User Input: '{user_request}'")
        print(f"🎯 Primary Emotion: {primary_emotion}")
        print(f"🎵 Music Mood: {music_mood}")
        if mood_data['emotions']:
            top_emotions = ', '.join([f"{e['label']}({e['score']:.2f})" for e in mood_data['emotions'][:3]])
            print(f"🔑 Top Emotions: {top_emotions}")
        print("="*60 + "\n")
        
        # Track mood in session
        self._session_context["moods"].append({
            "emotion": primary_emotion,
            "mood": music_mood,
            "text": user_request
        })
        
        # Step 2: Get user taste profile
        taste_profile = self._get_user_taste_profile()
        top_artists = taste_profile["top_artists"]
        artist_preferences = taste_profile["artist_preferences"]
        
        print("👤 USER TASTE PROFILE")
        print(f"   Top Artists: {', '.join(top_artists) if top_artists else 'None yet'}")
        print(f"   Total Interactions: {sum(self._session_context['artists'].values())}")
        
        # Step 2.5: R7.1.3 - Automatic context detection
        auto_context = self._detect_automatic_context()
        time_context = auto_context["context_description"]
        suggested_mood = auto_context["suggested_mood"]
        
        # Step 3: Get current playlist for context
        current_playlist = self.playlists._current
        playlist_songs = self.playlists.view(current_playlist) if current_playlist else []
        if isinstance(playlist_songs, str):
            playlist_songs = []
        
        # Format playlist context for LLM
        playlist_context = ""
        if playlist_songs:
            playlist_artists = {}
            for song in playlist_songs[:20]:  # Limit to recent 20
                artist = song.get("artist", "Unknown")
                playlist_artists[artist] = playlist_artists.get(artist, 0) + 1
            
            playlist_context = "User's current playlist:\n"
            for artist, count in sorted(playlist_artists.items(), key=lambda x: x[1], reverse=True)[:10]:
                playlist_context += f"  - {artist} ({count} song{'s' if count > 1 else ''})\n"
        
        # Step 4: Ask LLM to recommend songs
        print("🤖 ASKING LLM FOR RECOMMENDATIONS...")
        
        llm_prompt = f"""
        You are a music recommendation expert. Based on the user's emotional state and musical taste, recommend 20 songs.

        IMPORTANT DATABASE CONSTRAINT:
        - The song database contains playlists from Spotify created between JANUARY 2010 and NOVEMBER 2017
        - DO NOT recommend songs released after November 2017
        - Only recommend songs that existed on Spotify by November 2017
        - Focus on songs from 2010-2017 or earlier

        EMOTION ANALYSIS (from BERT):
        - Primary Emotion: {primary_emotion}
        - Music Mood: {music_mood}
        - User Request: "{user_request}"

        AUTOMATIC CONTEXT (R7.1.3 - Time & Behavioral Patterns):
        - Current Context: {time_context}
        - Time-Based Suggestion: {suggested_mood} music recommended for this time
        - Consider this context when making recommendations

        USER'S TASTE PROFILE:
        {playlist_context if playlist_context else "No playlist history yet"}
        Top Artists: {', '.join(top_artists) if top_artists else 'No preferences yet'}
        Artist Interaction Counts: {', '.join([f'{a}({c})' for a, c in sorted(artist_preferences.items(), key=lambda x: x[1], reverse=True)[:5]]) if artist_preferences else 'None'}

        TASK:
        Recommend 20 songs that match:
        1. The user's requested mood ({music_mood})
        2. The automatic time-based context ({suggested_mood} for {time_context})
        3. The user's taste profile
        4. Songs that existed by November 2017 (database constraint)

        CRITICAL RULES:
        1. ONLY recommend songs released before December 2017
        2. Balance user's explicit mood request with time-appropriate suggestions
        3. If user has favorite artists, PRIORITIZE songs from those artists that match the mood
        4. Match the emotional tone: {primary_emotion} / {music_mood}
        5. Consider the time of day context for appropriate energy levels
        6. Include variety but stay within the user's taste preferences
        7. Return ONLY a JSON array with this exact format:

        [
        {{"artist": "Artist Name", "title": "Song Title", "reason": "brief explanation"}},
        {{"artist": "Artist Name", "title": "Song Title", "reason": "brief explanation"}},
        ...
        ]

        IMPORTANT: 
        - If user likes metal, recommend metal songs matching the mood (e.g., romantic metal, sad metal)
        - If user has no preferences, recommend popular songs matching the mood
        - Output ONLY the JSON array, no other text
        - Ensure artist and title are spelled correctly
        - Remember: Database only has songs available on Spotify up to November 2017"""
        
        # Step 5: Get LLM recommendations
        llm_response = self._llm.ask(llm_prompt)
        
        # Step 6: Parse LLM response
        llm_recommendations = []
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', llm_response, re.DOTALL)
            if json_match:
                llm_recommendations = json.loads(json_match.group(0))
                print(f"✅ LLM suggested {len(llm_recommendations)} songs")
            else:
                print(f"⚠️ Could not parse JSON from LLM response")
                print(f"Response: {llm_response[:200]}...")
        except Exception as e:
            print(f"❌ Error parsing LLM response: {e}")
        
        # Step 7: Verify songs in database
        verified_songs = []
        for idx, song_data in enumerate(llm_recommendations, 1):
            artist = song_data.get("artist", "").strip()
            title = song_data.get("title", "").strip()
            reason = song_data.get("reason", "")
            
            if not artist or not title:
                continue
            
            # Check if song exists in database
            db_result = find_song_in_db(artist, title)
            
            if db_result:
                verified_songs.append({
                    "artist": artist,
                    "title": title,
                    "reason": reason,
                    "source": "llm"
                })
                print(f"   ✓ Found: {artist} - {title}")
            else:
                print(f"   ✗ Not in DB: {artist} - {title}")
            
            # Limit to 10 verified songs
            if len(verified_songs) >= 10:
                break
        
        print(f"\n📊 RESULTS: {len(verified_songs)}/10 songs verified in database\n")
        
        # Step 8: Fallback to database search if not enough verified songs
        if len(verified_songs) < 5:
            print("⚠️ Not enough LLM songs in database, falling back to keyword search...")
            
            mood_keywords = mood_analyzer.get_mood_keywords(mood_data)
            fallback_songs = search_tracks_by_keywords(
                mood_keywords,
                limit=10
            )
            
            # Add fallback songs to fill the gap
            for song in fallback_songs:
                if len(verified_songs) >= 10:
                    break
                
                # Don't duplicate
                key = f"{song['artist']}::{song['title']}"
                if not any(f"{s['artist']}::{s['title']}" == key for s in verified_songs):
                    verified_songs.append({
                        "artist": song["artist"],
                        "title": song["title"],
                        "reason": f"Matches {music_mood} mood",
                        "source": "fallback"
                    })
            
            print(f"   Added {len([s for s in verified_songs if s['source'] == 'fallback'])} fallback songs")
        
        if not verified_songs:
            return f"I couldn't find songs matching your mood ({music_mood}). Try adding songs to your playlist first or be more specific."
        
        # Step 9: Format response
        response_lines = []
        
        # Mood explanation with automatic context (R7.1.3)
        emotion_desc = f"detected {primary_emotion}" if primary_emotion != "neutral" else "neutral mood"
        taste_desc = f"your taste for {', '.join(top_artists)}" if top_artists else "the vibe you're looking for"
        
        # Include automatic context in explanation
        response_lines.append(f"<strong>🎭 Based on {emotion_desc}, {taste_desc}, and {time_context}:</strong><br><br>")
        
        # Recommendations with explanations
        for idx, rec in enumerate(verified_songs, 1):
            artist = rec["artist"]
            title = rec["title"]
            reason = rec["reason"]
            source = rec.get("source", "llm")
            
            # Format explanation
            explanation = reason if reason else f"Matches {music_mood} mood"
            if artist in top_artists and "favorite" not in explanation.lower():
                explanation += f" (one of your favorites)"
            
            source_icon = "🤖" if source == "llm" else "🔍"
            
            response_lines.append(
                f"{idx}. <strong>{artist}</strong>: {title}<br>"
                f"   <em>{source_icon} {explanation}</em><br>"
            )
        
        response_lines.append(
            f"<br><em>Use '/pl select 1 2 3' to add songs to your playlist.</em>"
        )
        
        # Store for selection
        self.playlists._recommendation_cache = [
            {"artist": r["artist"], "title": r["title"]}
            for r in verified_songs
        ]
        
        return "".join(response_lines)

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
