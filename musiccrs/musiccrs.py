"""MusicCRS conversational agent."""
import os
import json
import ollama
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.platforms import FlaskSocketPlatform
from config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_API_KEY, DB_PATH, MPD_DATA, DB_FOLDER, _INTENT_OPTIONS
import sqlite3
import json
import os

class MusicCRS(Agent):
    def __init__(self, use_llm: bool = True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")

        if use_llm:
            self._llm = ollama.Client(
                host=OLLAMA_HOST,
                headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
            )
        else:
            self._llm = None
            
        self._create_db_and_load_mpd()  # Create and load the database if it doesn't exist
        self._current_playlist: str | None = None  # Name of active playlist
        # Stores playlists as: name -> list of entries {id:int, artist:str, title:str}
        self._playlists: dict[str, list[dict]] = {}

    # --- playlist functions ---
    def add_playlist(self, playlist_name: str) -> str:
        if not playlist_name:
            return "Please provide a playlist name."
        if playlist_name in self._playlists:
            self._current_playlist = playlist_name
            return f"Switched to existing playlist '{playlist_name}'."
        self._playlists[playlist_name] = []
        self._current_playlist = playlist_name
        return f"Created and switched to playlist '{playlist_name}'."
    
    def add_song_to_playlist(self, artist: str, title: str, playlist_name: str | None = None) -> str:
        if not artist or not title:
            return "Please provide both artist and title as '[artist]: [title]'."
        song = self._find_song_in_db(artist, title)
        if not song:
            return f"Song not found in database: '{artist}: {title}'."
        target = playlist_name or self._current_playlist
        if not target:
            return "No active playlist. Use '/pl use [name]' to create/select a playlist first."
        # prevent duplicates by id
        entries = self._playlists.setdefault(target, [])
        if any(entry["id"] == song["id"] for entry in entries):
            return f"Song already in playlist '{target}': {artist} - {title}."
        entries.append({"id": song["id"], "artist": song["artist"], "title": song["title"]})
        return f"Added to '{target}': {artist} - {title}."
                 
            
    def remove_song_from_playlist(self, artist: str, title: str, playlist_name: str | None = None) -> str:
        target = playlist_name or self._current_playlist
        if not target:
            return "No active playlist. Use '/pl use [name]' first."
        entries = self._playlists.get(target, [])
        idx = next((i for i, e in enumerate(entries) if e["artist"].lower() == artist.lower() and e["title"].lower() == title.lower()), None)
        if idx is None:
            return f"Song not found in playlist '{target}': {artist} - {title}."
        removed = entries.pop(idx)
        return f"Removed from '{target}': {removed['artist']} - {removed['title']}."
        
    def view_playlist(self, playlist_name: str | None = None) -> list[dict]:
        target = playlist_name or self._current_playlist
        if not target:
            return []
        return self._playlists.get(target, [])
    
    def clear_playlist(self, playlist_name: str | None = None) -> str:
        target = playlist_name or self._current_playlist
        if not target:
            return "No active playlist. Use '/pl use [name]' first."
        self._playlists[target] = []
        return f"Cleared playlist '{target}'."

    # --- Dialogue functions ---

    def welcome(self) -> None:
        """Sends the agent's welcome message."""
        utterance = AnnotatedUtterance(
            "Hello, I'm MusicCRS. For more info on me, type '/info'. What are you in the mood for?",
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def goodbye(self) -> None:
        """Quits the conversation."""
        utterance = AnnotatedUtterance(
            "It was nice talking to you. Bye",
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def receive_utterance(self, utterance: Utterance) -> None:
        """Gets called each time there is a new user utterance.

        For now the agent only understands specific command.

        Args:
            utterance: User utterance.
        """
        text = (utterance.text or "").strip()
        response = ""
        if text.startswith("/pl "):
            response = self._handle_playlist_command(text[4:].strip())
        elif text.startswith("/info"):
            response = self._info()
        elif text.startswith("/ask_llm "):
            prompt = text[9:]
            response = self._ask_llm(prompt)
        elif text.startswith("/options"):
            options = [
                "Play some jazz music",
                "Recommend me some pop songs",
                "Create a workout playlist",
            ]
            response = self._options(options)
        elif text == "/quit":
            self.goodbye()
            return
        else:
            response = "I'm sorry, I don't understand that command."

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
            )
        )

    # --- Playlist command handling ---
    def _handle_playlist_command(self, command: str) -> str:
        # Supported:
        # /pl use <name>
        # /pl add <artist>: <title>
        # /pl remove <artist>: <title>
        # /pl view [name]
        # /pl clear [name]
        parts = command.split(" ", 1)
        if not parts:
            return self._pl_help()
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if action in ("use", "new"):
            return self.add_playlist(arg)
        elif action == "add":
            artist, title = self._parse_song_spec(arg)
            return self.add_song_to_playlist(artist, title)
        elif action == "remove":
            artist, title = self._parse_song_spec(arg)
            return self.remove_song_from_playlist(artist, title)
        elif action == "view":
            name = arg or None
            items = self.view_playlist(name)
            if not items:
                return "Playlist is empty or not selected. Use '/pl use [name]' first."
            lines = [f"{i+1}. {it['artist']} - {it['title']}" for i, it in enumerate(items)]
            target = name or (self._current_playlist or "(none)")
            return "Playlist '" + target + "':\n" + "\n".join(lines)
        elif action == "clear":
            name = arg or None
            return self.clear_playlist(name)
        else:
            return self._pl_help()

    def _pl_help(self) -> str:
        return (
            "Playlist commands:\n"
            "- /pl use [name]   (create/switch)\n"
            "- /pl add [artist]: [title]\n"
            "- /pl remove [artist]: [title]\n"
            "- /pl view [name]\n"
            "- /pl clear [name]"
        )

    def _parse_song_spec(self, spec: str) -> tuple[str, str]:
        if ":" not in spec:
            return "", ""
        artist, title = spec.split(":", 1)
        return artist.strip(), title.strip()

    # --- Response handlers ---

    def _info(self) -> str:
        """Gives information about the agent."""
        return "I am MusicCRS, a conversational recommender system for music. I can help you create playlists and recommend songs. You can ask me to add or remove songs from your playlist, view your current playlist, or clear it. You can also ask me for music recommendations based on your mood or preferences. To get started, you can use commands like '/ask_llm <your prompt>' to interact with a large language model, or '/options' to see some example options."

    def _ask_llm(self, prompt: str) -> str:
        """Calls a large language model (LLM) with the given prompt.

        Args:
            prompt: Prompt to send to the LLM.

        Returns:
            Response from the LLM.
        """
        if not self._llm:
            return "The agent is not configured to use an LLM"

        llm_response = self._llm.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={
                "stream": False,
                "temperature": 0.7,  # optional: controls randomness
                "max_tokens": 100,  # optional: limits the length of the response
            },
        )

        return f"LLM response: {llm_response['response']}"

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )

    # --- database functions ---

    def _create_db_and_load_mpd(self, db_file=DB_PATH, mpd_folder=MPD_DATA):
        db_dir = os.path.dirname(db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Ensure MPD data folder exists
        if not os.path.exists(mpd_folder):
            raise FileNotFoundError(f"MPD data folder not found: {mpd_folder}")

        if os.path.exists(db_file):
            print(f"Database file '{db_file}' already exists. Skipping _create_db_and_load_mpd.")
            return
         
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        # Create song, playlist and playlist_song(relation) tables
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT NOT NULL,
            title TEXT NOT NULL,
            album TEXT,
            duration_ms INTEGER,
            spotify_uri TEXT,
            UNIQUE(artist, title)
        );

        CREATE TABLE IF NOT EXISTS playlists (
            pid INTEGER PRIMARY KEY,
            name TEXT,
            collaborative BOOLEAN,
            modified_at INTEGER,
            num_tracks INTEGER,
            num_artists INTEGER,
            num_albums INTEGER,
            num_followers INTEGER,
            num_edits INTEGER,
            duration_ms INTEGER
        );

        CREATE TABLE IF NOT EXISTS playlist_songs (
            playlist_id INTEGER,
            song_id INTEGER,
            pos INTEGER,
            PRIMARY KEY (playlist_id, song_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(pid),
            FOREIGN KEY (song_id) REFERENCES songs(id)
        );
        """)
        

        # Iterate all slices
        for slice_file in sorted(os.listdir(mpd_folder)):
            if not slice_file.endswith(".json"):
                continue
            with open(os.path.join(mpd_folder, slice_file), "r", encoding="utf-8") as f:
                data = json.load(f)
                playlists = data.get("playlists", [])
                for pl in playlists:
                    # Insert playlist
                    cursor.execute("""
                        INSERT OR IGNORE INTO playlists
                        (pid, name, collaborative, modified_at, num_tracks, num_artists, num_albums, num_followers, num_edits, duration_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pl["pid"], pl["name"], pl.get("collaborative", False), pl["modified_at"],
                        pl["num_tracks"], pl["num_artists"], pl["num_albums"],
                        pl["num_followers"], pl["num_edits"], pl["duration_ms"]
                    ))

                    # Insert tracks
                    for track in pl.get("tracks", []):
                        cursor.execute("""
                            INSERT OR IGNORE INTO songs (artist, title, album, duration_ms, spotify_uri)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            track["artist_name"], track["track_name"], track["album_name"],
                            track["duration_ms"], track["track_uri"]
                        ))
                        # Get song id
                        cursor.execute("SELECT id FROM songs WHERE artist=? AND title=?", 
                                    (track["artist_name"], track["track_name"]))
                        song_id = cursor.fetchone()[0]

                        # Link playlist to song
                        cursor.execute("""
                            INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id, pos)
                            VALUES (?, ?, ?)
                        """, (pl["pid"], song_id, track["pos"]))

            print(f"Loaded {slice_file}")

        conn.commit()
        conn.close()
        print("All slices loaded into database successfully.")

    def _find_song_in_db(self, artist: str, title: str) -> dict | None:
        """Return a single song dict if found exactly (case-insensitive), else None."""
        if not artist or not title:
            return None
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, artist, title FROM songs WHERE artist = ? COLLATE NOCASE AND title = ? COLLATE NOCASE",
            (artist, title),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        sid, sartist, stitle = row
        return {"id": sid, "artist": sartist, "title": stitle}
        
if __name__ == "__main__":
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
