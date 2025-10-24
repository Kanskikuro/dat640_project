from db import find_songs_by_title, recommend_songs


class PlaylistManager:
    def __init__(self):
        self._playlists: dict[str, list[dict]] = {}
        self._current: str | None = None
        self._pending_additions: list[dict] | None = None
        self._recommendation_cache: list[str] | None = None
        self.create_playlist("a")
        self.add_song("kendrick lamar : humble.")
    # Playlist functions

    def create_playlist(self, name: str):
        if name in self._playlists:
            self.switch_playlist(name)
            return f"Playlist '{name}' already exists. Switched to it."

        self._playlists[name] = []
        self._current = name
        print("create playlist:" + name)
        return f"Created playlist '{name}'."

    def remove_playlist(self, name: str):
        if name in self._playlists:
            del self._playlists[name]
            print(f'Playlist "{name}" deleted.')
            return "Deleted" + name
        else:
            print(f'Playlist "{name}" not found.')
            return f'Playlist "{name}" not found.'

    def switch_playlist(self, name: str):
        if name not in self._playlists:
            self.create_playlist(name)
            return f"Playlist '{name}' does not exist. Created and switched to it."

        self._current = name
        print("switch :" + name)
        return f"Switched to '{name}'."

    def view(self, playlist_name: str | None = None):
        target = playlist_name or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."

        if not self._playlists.get(target, []):
            return f"'{target}' is empty"
        return self._playlists.get(target, [])

    def view_playlists(self):
        return list(self._playlists.keys())

    def clear(self, playlist_name: str | None = None):
        target = playlist_name or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."

        self._playlists[target] = []
        print("clear :" + str(playlist_name))
        return f"Cleared playlist '{target}'."

    # Song functions

    def add_song(self, song_spec: str, playlist_name: str | None = None) -> str:
        """
        Add a song to the playlist. Handles:
        - "Artist: Title" format
        - "Title" only (finds candidates in DB)
        - Multiple matches (requires choosing)
        """
        target = playlist_name or self._current
        if not target:
            print("No active playlist. Use '/pl create [name]' first.")
            return "No active playlist. Use '/pl create [name]' first."

        # Artist:Title format
        if ":" in song_spec:
            artist, title = map(str.strip, song_spec.split(":", 1))

            # Check if song in db DB 
            candidates = find_songs_by_title(title)
            matched = next((c for c in candidates if c["artist"].lower() == artist.lower()), None)

            if not matched:
                print(f"No song found in DB: {artist} : {title}")
                return f"No song found in DB: {artist} : {title}"

            # Add to playlist
            song = {"artist": matched["artist"],
                    "title": matched["title"], "id": matched["id"]}
            entries = self._playlists.setdefault(target, [])
            if any(e["id"] == song["id"] for e in entries):
                print(
                    f"Song already in playlist '{target}': {song['artist']} : {song['title']}'.")
                return f"Song already in playlist '{target}': {song['artist']} : {song['title']}'."

            entries.append(song)
            print(f"Added '{song['artist']} : {song['title']}' to '{target}'.")
            return f"Added '{song['artist']} : {song['title']}' to '{target}'."
        
        # Only title: search DB
        else:
            title = song_spec.strip()
            candidates = find_songs_by_title(title)
            if not candidates:
                print(f"No songs found with title '{title}'.")
                return f"No songs found with title '{title}'."

            if len(candidates) == 1:
                song = candidates[0]
                entries = self._playlists.setdefault(target, [])
                if any(e["id"] == song["id"] for e in entries):
                    print(
                        f"Song already in playlist '{target}: {song['artist']} : {song['title']}'.")
                    return f"Song already in playlist '{target}: {song['artist']} : {song['title']}'."
                entries.append(song)
                print(
                    f"Added '{song['artist']} : {song['title']}' to '{target}'.")
                return f"Added '{song['artist']} : {song['title']}' to '{target}'."
            # Multiple candidates -> store pending
            self._pending_additions = candidates[:10]  # limit top 10
            print("Multiple matches: <br>" + "<br>".join(
                [f"{i+1}. {c['artist']} : {c['title']}" for i,
                    c in enumerate(self._pending_additions)]
            ) + "<br>Use '/pl choose [number]' to select.")
            return "Multiple matches: <br>" + "<br>".join(
                [f"{i+1}. {c['artist']} : {c['title']}" for i,
                    c in enumerate(self._pending_additions)]
            ) + "<br>Use '/pl choose [number]' to select."

    def choose_song(self, idx: int, playlist_name: str | None = None) -> str:
        if not self._pending_additions:
            return "No pending songs to choose from."

        if idx < 0 or idx >= len(self._pending_additions):
            return f"Please choose a number between 1 and {len(self._pending_additions)}."

        song = self._pending_additions[idx]
        target = playlist_name or self._current
        entries = self._playlists.setdefault(target, [])
        if any(e["id"] == song["id"] for e in entries):
            self._pending_additions = None
            return f"Song already in playlist '{target}': {song['artist']} : {song['title']}."

        entries.append(song)
        self._pending_additions = None
        print(f"Added '{song['artist']} : {song['title']} to '{target}.")
        return f"Added '{song['artist']} : {song['title']} to '{target}."

    def remove_song(self, song_spec: str, playlist_name: str | None = None):
        """
        Remove a song by "Artist: Title" or just "Title".
        If only title is provided, remove first match.
        """
        target = playlist_name or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."

        entries = self._playlists.get(target, [])
        if ":" in song_spec:
            artist, title = map(str.strip, song_spec.split(":", 1))
            idx = next(
                (i for i, e in enumerate(entries)
                 if e["artist"].lower() == artist.lower() and e["title"].lower() == title.lower()),
                None
            )
        else:
            title = song_spec.strip()
            idx = next(
                (i for i, e in enumerate(entries)
                 if e["title"].lower() == title.lower()),
                None
            )

        if idx is None:
            return f"Song not found in playlist '{target}': {song_spec}."

        removed = entries.pop(idx)
        print("remove_song :" + str(song_spec))
        return f"Removed from '{target}': {removed['artist']} : {removed['title']}."

    def recommend(self, playlist_name: str | None = None) -> str:
        playlist_list = self._playlists.get(playlist_name or self._current, [])
        if not playlist_list:
            return "Playlist is empty or invalid."

        # Filter valid songs
        songs = [song for song in playlist_list if "artist" in song and "title" in song]
        if not songs:
            return "No valid songs in the playlist."

        rec , recommended_data = recommend_songs(songs)
        if rec:
            self._recommendation_cache = rec , recommended_data
            result = [
                f"{i+1}. {rec[song_id]} (song appears in {freq} playlists)"
                for i, (song_id, freq) in enumerate(recommended_data) if song_id in rec
            ]
            return "Recommends:<br>" + "<br>".join(result) + "<br>Use '/pl select [numbers]' to add."
        else:
                return "No recommendations found."
            
    def select_recommendations(self, indices: list[int]) -> str:
        if not self._recommendation_cache:
            return "No recommendations to choose from. Use '/pl recommend' first."

        rec, recommended_data = self._recommendation_cache  # unpack tuple
        added_songs = []

        for idx in indices:
            if idx < 1 or idx > len(recommended_data):
                return f"Please choose numbers between 1 and {len(recommended_data)}."

            song_id, _ = recommended_data[idx - 1]
            song_info = rec[song_id]  # "Artist : Title"
            artist, title = song_info.split(" : ", 1)
            arg = f"{artist}:{title}"
            self.add_song(arg)
            added_songs.append(song_info)

        if added_songs:
            return "Added: <br>" + "<br>".join(added_songs)
        else:
            return "No songs added."



shared_playlists = PlaylistManager()
