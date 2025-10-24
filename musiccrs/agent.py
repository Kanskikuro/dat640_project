# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent
import json
from db import get_track_info, get_artist_stats
from spotify import SpotifyClient
from collections import Counter
from playlist import shared_playlists
from llm import LLMClient
from config import DB_PATH
_INTENT_OPTIONS = Intent("OPTIONS")
from events import emit as emit_event


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
        """
        # Supported:
        # /pl create <playlist name or None>
        # /pl switch <playlist name or None>
        # /pl add <artist>: <title>
        # /pl remove <artist>: <title>
        # /pl view [playlist name or None]
        # /pl clear [playlist name or None]
        # /pl choose <n>
        # /pl summary|stats|info [name]
        # /pl recommend <playlist name or None>
        """

        """Playlist commands via chat (/pl ...). Emits UI updates over Socket.IO."""
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
                # Determine which playlist we're summarizing
                target_playlist = arg.strip() if arg else self.playlists._current
                items = self.playlists.view(arg or None)
                # Check if items is a string (error message) or empty list
                if isinstance(items, str) or not items:
                    return items if isinstance(items, str) else "Playlist is empty."

                num_tracks = len(items)
                # Count artists
                artist_counts = Counter([(s.get("artist") or "Unknown").strip() for s in items])
                num_artists = len([a for a in artist_counts.keys() if a and a != "Unknown"])

                # Enrich with DB info where possible (duration, album, spotify_uri)
                total_duration_ms = 0
                album_counts = Counter()
                track_rows = []
                for s in items:
                    artist = s.get("artist") or "Unknown"
                    title = s.get("title") or s.get("track") or ""
                    info = None
                    try:
                        info = get_track_info(artist, title)
                    except Exception:
                        info = None
                    duration_ms = info.get("duration_ms") if info else None
                    album = info.get("album") if info else None
                    spotify_uri = info.get("spotify_uri") if info else None
                    if duration_ms:
                        total_duration_ms += duration_ms
                    if album:
                        album_counts[album] += 1
                    display_duration = self._format_duration(duration_ms)
                    track_rows.append({"artist": artist, "title": title, "duration": display_duration, "spotify_uri": spotify_uri})

                avg_duration_ms = int(total_duration_ms / num_tracks) if num_tracks and total_duration_ms else None
                num_albums = len([a for a in album_counts if a and a.strip()])

                top_artists = artist_counts.most_common(5)
                top_albums = album_counts.most_common(5)

                # Build HTML summary
                parts = []
                parts.append(f"<div><h3>Playlist '{target_playlist or '(current)'}' summary</h3>")
                parts.append("<ul>")
                parts.append(f"<li>Tracks: <strong>{num_tracks}</strong></li>")
                parts.append(f"<li>Unique artists: <strong>{num_artists}</strong></li>")
                parts.append(f"<li>Albums in playlist: <strong>{num_albums}</strong></li>")
                if total_duration_ms:
                    parts.append(f"<li>Total duration: <strong>{self._format_duration(total_duration_ms)}</strong></li>")
                else:
                    parts.append(f"<li>Total duration: <strong>Unknown</strong></li>")
                if avg_duration_ms:
                    parts.append(f"<li>Average track length: <strong>{self._format_duration(avg_duration_ms)}</strong></li>")
                parts.append("</ul>")

                # Top artists
                if top_artists:
                    parts.append("<strong>Top artists:</strong><br><ol>")
                    for a, cnt in top_artists[:5]:
                        parts.append(f"<li>{a} ({cnt} track{'s' if cnt!=1 else ''})</li>")
                    parts.append("</ol>")

                # Top albums
                if top_albums:
                    parts.append("<strong>Top albums:</strong><br><ol>")
                    for a, cnt in top_albums[:5]:
                        parts.append(f"<li>{a} ({cnt} track{'s' if cnt!=1 else ''})</li>")
                    parts.append("</ol>")

                # Track listing table
                parts.append("<strong>Tracks:</strong>")
                parts.append("<table style='width:100%;border-collapse:collapse'>")
                parts.append("<thead><tr><th style='text-align:left;padding:4px'>#</th><th style='text-align:left;padding:4px'>Artist</th><th style='text-align:left;padding:4px'>Title</th><th style='text-align:left;padding:4px'>Duration</th></tr></thead>")
                parts.append("<tbody>")
                for i, row in enumerate(track_rows):
                    spotify_link = f" <a href='{row['spotify_uri']}' target='_blank'>♫</a>" if row.get("spotify_uri") else ""
                    parts.append(f"<tr style='border-top:1px solid #eee'><td style='padding:4px'>{i+1}</td><td style='padding:4px'>{row['artist']}</td><td style='padding:4px'>{row['title']}{spotify_link}</td><td style='padding:4px'>{row['duration']}</td></tr>")
                parts.append("</tbody></table></div>")

                return "".join(parts)
            
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

        prompt = f"""
    You are an intent parser using free natural language for a music playlist system.
    Only output a single JSON object with no extra text.
    The JSON object must have the keys:
    - "intent": one of ["create", "choose",  "remove", "switch", "view", "view_playlists", "clear", "add", "summary", "recommend"]
    - "song": the song title 
    - "artist": the artist name or empty string if not given.
    - "idx": the index number for choosing from multiple options (1-based)
    - "playlist_name": the playlist name or empty string if not given.  
    - "reply": the full text reply from you, the llm.
    
    Check for if the song is valid and for fix any obvious typos in artist or title.
    If there is no song, but artist, find a song from that artist that is not already in the playlist.
    if there is no artist but song and the intent is add. return "intent" as "add", artist "song" as the title. 
    Allow users to express their intentions for playlist manipulation and interacting with recommendations using free natural language text instead of/in addition to using commands with a fixed syntax. 
    Allow users to refer to tracks and artists without exact string matching (including lack of proper capitalization and punctuation) and resolve ambiguities (eg, many artists have a song called “Love”).
    Dont add songs that are already in the playlist.
    
    
    User input: "{text}"
    User playlist : "{self.playlists.view(self.playlists._current)}"

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

        intent = data.get("intent").lower()
        idx = data.get('idx', 1)
        artist = data.get("artist", "")
        song = data.get("song", "")
        playlist_name = data.get("playlist_name", "")
        arg = f"{artist}:{song}"
        if artist == "":
            arg = song
        
        print(llm_reply)
        
        match intent:
            case "add":
                return self._handle_playlist_command(f"add {arg}")
            case "choose":
                return self._handle_playlist_command(f"choose {idx}")
            case "remove":
                return self._handle_playlist_command(f"remove {arg}")
            case "view":
                return self._handle_playlist_command(f"view")
            case "view_playlists":
                return self._handle_playlist_command(f"view_playlists")
            case "clear":
                return self._handle_playlist_command(f"clear")
            case "create":
                return self._handle_playlist_command(f"create {playlist_name}")
            case "switch":
                return self._handle_playlist_command(f"switch {playlist_name}")
            case "summary" | "recommend":
                return self._handle_playlist_command(f"{intent} {playlist_name}")
            case _:
                return "No intent, heres your llm reply back: " + llm_reply

    def _pl_help(self) -> str:
        return (
            "Playlist commands:"
            "<br> - /pl create [playlist name]   (create playlist)"
            "<br> - /pl switch [playlist name]   (switch to existing)"
            "<br> - /pl add [artist]: [song title]"
            "<br> - /pl add [song title]   (disambiguate if needed with '/pl choose a number from the list')"
            "<br> - /pl choose [index of the list of songs]"
            "<br> - /pl remove [artist]: [song title]"
            "<br> - /pl view [playlist name] or none for current"
            "<br> - /pl clear [playlist name] or none for current]"
            "<br> - /pl summary|stats|info [playlist name] or none for current]"
            "<br> - /pl recommend <playlist> (Item co-occurrence)"
            "<br> - Use /qa for information about track or artists"
        )

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
        Renders an HTML5 <audio> with preview if available, else a link.
        """
        if not command:
            return self._play_help()

        parts = command.split(None, 1)
        if len(parts) < 2:
            return self._play_help()

        target = parts[0].lower()
        rest = parts[1].strip()

        match target:
            case "track":
                if ":" not in rest:
                    return "Please specify the song as 'Artist: Title'."
                artist, title = self._parse_song_spec(rest)
                info = get_track_info(artist, title)
                if not info:
                    return f"Track not found: {artist} - {title}."
                uri = info.get("spotify_uri")
                if not uri:
                    return (
                        f"No Spotify URI found for {artist} - {title}. Try '/qa track {artist}: {title} spotify' to check."
                    )
                return self._render_player(uri, label=f"{artist} - {title}")
            case "uri":
                return self._render_player(rest, label="Spotify track")
            case _:
                return self._play_help()

    def _render_player(self, spotify_uri_or_url: str, label: str) -> str:
        link = self._spotify.open_spotify_track_url(spotify_uri_or_url) or "#"
        preview = self._spotify.get_preview_url(spotify_uri_or_url)
        if preview:
            return (
                f"<div><strong>Playing preview:</strong> {label}<br>"
                f"<audio controls src=\"{preview}\" preload=\"none\"></audio>"
                f"<br><a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
            )
        # Fallback: Spotify embed (30s preview UI) without requiring SDK or login
        track_id = self._spotify.parse_spotify_track_id(spotify_uri_or_url)
        if track_id:
            embed = (
                f"<iframe style=\"border-radius:12px\" "
                f"src=\"https://open.spotify.com/embed/track/{track_id}\" "
                f"width=\"100%\" height=\"80\" frameborder=\"0\" allow=\"autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture\" loading=\"lazy\"></iframe>"
            )
            return (
                f"<div><strong>Preview:</strong> {label}<br>{embed}"
                f"<br><a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
            )
        return (
            f"<div>No preview available for {label}. "
            f"<a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
        )

    def _play_help(self) -> str:
        return (
            "Play commands:"
            "<br> - /play track [Artist]: [Title]"
            "<br> - /play uri [spotify track uri or open.spotify.com link]"
        )

    # --- QA commands ---
    def _handle_qa_command(self, command: str) -> str:
        """
        QA commands:
          - /qa track <artist>: <title> (album|duration|popularity|spotify|all)
          - /qa artist <artist> (tracks|albums|top|playlists|all)
        """
        if not command:
            return self._qa_help()

        parts = command.split(None, 1)
        if len(parts) < 2:
            return self._qa_help()

        target = parts[0].lower()
        rest = parts[1].strip()

        match target:
            case "track":
                # Expect "<artist>: <title> <qtype>"
                qtypes = {"album", "duration", "popularity", "spotify", "all"}
                if " " not in rest:
                    return (
                        "Please provide a question type. Example: /qa track Artist: Title album"
                    )
                song_spec, qtype = rest.rsplit(" ", 1)
                qtype = qtype.lower()
                if qtype not in qtypes:
                    return (
                        f"Unknown track question '{qtype}'. Try: album, duration, popularity, spotify, all."
                    )

                if ":" not in song_spec:
                    return "Please specify the song as 'Artist: Title'."
                artist, title = self._parse_song_spec(song_spec)
                info = get_track_info(artist, title)
                if not info:
                    return f"Track not found: {artist} - {title}."

                answers = []
                if qtype in ("album", "all"):
                    answers.append(f"Album: {info.get('album') or 'Unknown'}")
                if qtype in ("duration", "all"):
                    answers.append(
                        f"Duration: {self._format_duration(info.get('duration_ms'))}"
                    )
                if qtype in ("popularity", "all"):
                    answers.append(
                        f"Popularity: appears in {info.get('popularity', 0)} playlists"
                    )
                if qtype in ("spotify", "all"):
                    uri = info.get("spotify_uri") or "N/A"
                    answers.append(f"Spotify URI: {uri}")
                return "<br>".join(answers)
            
            case "artist":
                # Expect "<artist> <qtype>"
                qtypes = {"tracks", "albums", "top", "playlists", "all"}
                if " " not in rest:
                    return (
                        "Please provide a question type. Example: /qa artist Artist Name top"
                    )
                artist, qtype = rest.rsplit(" ", 1)
                qtype = qtype.lower()
                if qtype not in qtypes:
                    return (
                        f"Unknown artist question '{qtype}'. Try: tracks, albums, top, playlists, all."
                    )

                stats = get_artist_stats(artist.strip())
                answers = []
                if qtype in ("tracks", "all"):
                    answers.append(f"Tracks in collection: {stats['num_tracks']}")
                if qtype in ("albums", "all"):
                    answers.append(f"Albums in collection: {stats['num_albums']}")
                if qtype in ("playlists", "all"):
                    answers.append(
                        f"Artist appears in {stats['num_playlists']} playlists"
                    )
                if qtype in ("top", "all"):
                    if stats["top_tracks"]:
                        top = "<br>".join(
                            [
                                f"{i+1}. {t['title']} (in {t['popularity']} playlists)"
                                for i, t in enumerate(stats["top_tracks"])
                            ]
                        )
                        answers.append(f"Top tracks:<br>{top}")
                    else:
                        answers.append("Top tracks: N/A")
                return "<br>".join(answers)
            case _:
                return self._qa_help()

    def _qa_help(self) -> str:
        return (
            "QA commands:"
            "<br> - /qa track [Artist]: [Title] (album|duration|popularity|spotify|all)"
            "<br> - /qa artist [Artist] (tracks|albums|top|playlists|all)"
        )

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
