from db import find_songs_by_title, get_track_info, recommend_songs
from collections import Counter


class PlaylistManager:
    def __init__(self):
        self._playlists: dict[str, list[dict]] = {}
        self._current: str | None = None
        self._pending_additions: list[dict] | None = None
        self._recommendation_cache: list[str] | None = None

        self.create_playlist("default")
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

    def get_summary(self, playlist: str | None = None, format_duration_func=None) -> str:
        """Generate a detailed summary of a playlist.
        
        Args:
            playlist: Optional playlist name (uses current if None)
            format_duration_func: Function to format duration in ms
            
        Returns:
            HTML formatted summary with statistics and track listing
        """
        # Default duration formatter if none provided
        if format_duration_func is None:
            def format_duration_func(duration_ms: int | None) -> str:
                if not duration_ms or duration_ms <= 0:
                    return "Unknown"
                seconds = duration_ms // 1000
                minutes = seconds // 60
                secs = seconds % 60
                return f"{minutes}:{secs:02d}"
        
        # Determine which playlist we're summarizing
        target_playlist = playlist or self._current
        
        items = self.view(playlist)
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
            display_duration = format_duration_func(duration_ms)
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
            parts.append(f"<li>Total duration: <strong>{format_duration_func(total_duration_ms)}</strong></li>")
        else:
            parts.append(f"<li>Total duration: <strong>Unknown</strong></li>")
        if avg_duration_ms:
            parts.append(f"<li>Average track length: <strong>{format_duration_func(avg_duration_ms)}</strong></li>")
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

    @staticmethod
    def get_help() -> str:
        """Return playlist command help text."""
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
            "<br> - /pl auto [description]   (auto-create playlist from description, e.g., 'sad love songs')"
            "<br> - /pl recommend <playlist> (Item co-occurrence)"
            "<br> - Use /qa for information about track or artists"
        )


shared_playlists = PlaylistManager()
