# musiccrs/agent.py
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.core.intent import Intent

from db import find_song_in_db, find_songs_by_title, get_track_info, get_artist_stats
from playlist import PlaylistManager
from llm import LLMClient
from config import DB_PATH
from dialoguekit.core.dialogue_act import DialogueAct
from spotify import SpotifyClient
from collections import Counter

_INTENT_OPTIONS = Intent("OPTIONS")


class MusicCRS(Agent):
    def __init__(self, use_llm=True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")
        self._llm = LLMClient() if use_llm else None
        self.playlists = PlaylistManager()
        self._pending_additions = None
        self._spotify = SpotifyClient()

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
        # /pl summary|stats|info [name]
        """

        parts = command.split(" ", 1)
        if not parts:
            return self._pl_help()
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if action in ("use", "new"):
            return self.playlists.use(arg)
        elif action == "add":
            # Support either "Artist: Title" or just "Title"
            if ":" in arg:
                artist, title = self._parse_song_spec(arg)
                if not artist or not title:
                    return "Please provide both artist and title, e.g., '/pl add \"Artist\": \"Song Title\"'."
                # Look up the exact song in the DB (case-insensitive)
                song = find_song_in_db(artist, title)
                if not song:
                    return f"No exact match found in database for: {artist} - {title}."
                return self.playlists.add_song(song)
            else:
                title = arg  # If no colon, treat request as title only
                candidates = find_songs_by_title(title)
                if not candidates:
                    return f"No songs found with title '{title}'."
                if len(candidates) == 1:
                    return self.playlists.add_song(candidates[0])
                # Keep up to top 10 candidates for selection
                self._pending_additions = candidates
                return "Multiple matches: <br>" + "<br>".join([f"{i+1}. {c['artist']} : {c['title']}" for i, c in enumerate(candidates)]) + "<br>Use '/pl choose [number]' to select. This option is a one-time use."
        elif action == "remove":
            artist, title = self._parse_song_spec(arg)
            return self.playlists.remove_song(artist, title)
        elif action in ("choose"):
            if not self._pending_additions:
                return self._pl_help()
            try:
                idx = int(arg) - 1
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
            items = self.playlists.view(arg or None)
            if not items:
                return "Playlist is empty."
            return "<br>".join([f"{i+1}. {s['artist']} - {s['title']}" for i, s in enumerate(items)])
        elif action == "clear":
            return self.playlists.clear(arg or None)
        
        # NEW: summary / stats / info
        elif action in ("summary", "stats", "info"):
            items = self.playlists.view(arg or None)
            if not items:
                return "Playlist is empty."

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
            parts.append(f"<div><h3>Playlist {self.playlists._current if not arg else arg} summary</h3>")
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
        
        else:
            return self._pl_help()

    def _pl_help(self) -> str:
        help_text = (
            "Playlist commands:"
            "<br> - /pl use [playlist name]   (create/switch playlist)"
            "<br> - /pl add [artist]: [song title]"
            "<br> - /pl add [song title]   (disambiguate if needed with '/pl choose a number from the list')"
            "<br> - /pl remove [artist]: [song title]"
            "<br> - /pl view [playlist name]"
            "<br> - /pl clear [plalylist name]"
            "<br> - /pl choose [index of the list of songs]"
        )
        return help_text

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

        if target == "track":
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

        if target == "uri":
            return self._render_player(rest, label="Spotify track")

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

        if target == "track":
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

        elif target == "artist":
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
        else:
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
