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
        self._current_playlist = str()  # Initialize what playlist the user is on
        self._playlists = {}  # Stores the current playlist

    # --- playlist functions ---
    def add_playlist(self, playlist_name: str) -> None:
        if playlist_name in self._playlists:
            self._current_playlist = playlist_name
            print(f"Playlist '{playlist_name}' already exists. Switched to '{playlist_name}'.")
            return
        self._playlists[playlist_name] = []
        self._current_playlist = playlist_name
        print(f"Created and switched to playlist '{playlist_name}'.")
    
    def add_song_to_playlist(self, artist_song: str, playlist_name:str) -> None:
        songs = self.check_song_in_db(artist_song)
        if songs:
            print(f"'{artist_song}' not found in database.")
            return
        if artist_song in self._current_playlist:
            print(f"'{artist_song}' is already in the playlist.")
            return
        
        
        if playlist_name is None and len(songs) == 1:
            self._playlists[self._current_playlist].append(artist_song)
            print(f"Added '{artist_song}' to the '{self._current_playlist}' playlist.")
        else:
            self._playlists[self.playlist_name].append(artist_song)
            
        if playlist_name and len(songs) > 1:
            # TODO rank it acording to popularity or similarity
            print(f"Multiple songs found for '{artist_song}'. Please specify the playlist to add to.")
            
            
    def remove_song_from_playlist(self, artist_song: str) -> None:
        if artist_song not in self._current_playlist:
            print(f"Song '{artist_song}' is not in the playlist.")
            return
            
        self._current_playlist[self._current_playlist].remove(artist_song)
        print(f"Removed '{artist_song}' from playlist.")
        
    def view_playlist(self, playlist_name) -> list[str]:
        return self._playlists[playlist_name]
    
    def clear_playlist(self, playlist_name):
        if playlist_name in self._playlists:
            self._playlists[playlist_name] = []

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
        else:
            response = "I'm sorry, I don't understand that command."

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )

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
            print(f"Database file '{db_file}' already exists. Skipping creation.")
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

    def check_song_in_db(self, artist: str, title: str) -> bool:
        """Check if a song exists in the database."""
        if artist is None and title is None:
            Print( "Artist and title cannot both be None")
            return []
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if title and artist:
            cursor.execute("SELECT 1 FROM songs WHERE artist=? AND title=?", (artist, title))
            songs = cursor.fetchall()
        elif title:
            cursor.execute("SELECT 1 FROM songs WHERE title=?", (title,)) # What happens when there are multiple songs with the same title?
            songs = cursor.fetchall()
            
            ranked_songs = []
            for song_id, song_title in songs:
                # Ranking them by popularity (number of playlists they are in)
                cursor.execute("SELECT COUNT(DISTINCT playlist_id) FROM playlist_songs WHERE song_id=?", (song_id,))
                playlist_count = cursor.fetchone()[0]
                ranked_songs.append((song_id, song_title, playlist_count))

            # Sort by number of playlists, descending
            songs = ranked_songs.sort(key=lambda x: x[2], reverse=True)
            
        conn.close()
        return songs
        
if __name__ == "__main__":
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
    platform.start()
