from db import create_db_and_load_mpd, configure_sqlite_once, ensure_indexes_once, find_song_in_db, find_songs_by_title


class PlaylistManager:
    def __init__(self):
        self._current = None
        self._playlists = {}

    def create_playlist(self, name: str):
        if name in self._playlists:
            self.switch_playlist(name)
            return f"Playlist '{name}' already exists. Switched to it."
            
        self._playlists[name] = []
        self._current = name
        print("create playlist:" + name)
        return f"Created playlist '{name}'."
    
    def remove_playlist(self, name:str):
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

    def view(self, playlist: str | None = None):
        target = playlist or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."
        represent = self._playlists.get(target, [])
        print("playlist :" + str(playlist))
        return f"playlist :" + str(represent)
    
    def view_playlists(self):
        return list(self._playlists.keys())

    def clear(self, playlist: str | None = None):        
        target = playlist or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."
        
        self._playlists[target] = []
        print("clear :" + str(playlist))
        return f"Cleared playlist '{target}'."


    def add_song(self, song_spec: str, pending_list: list | None = None, playlist: str | None = None):
        """
        Add a song to the playlist. Handles:
        - "Artist: Title" format
        - "Title" only (finds candidates in DB)
        - Multiple matches (requires choosing)
        """
        target = playlist or self._current
        if not target:
            return "No active playlist. Use '/pl create [name]' first."

        # If artist:title format
        if ":" in song_spec:
            artist, title = song_spec.split(":", 1)
            song = {"artist": artist.strip(), "title": title.strip(), "id": f"{artist.strip()}-{title.strip()}"}
            entries = self._playlists.setdefault(target, [])
            if any(e["id"] == song["id"] for e in entries):
                return f"Song already in playlist '{target}': {song['artist']} - {song['title']}."
            entries.append(song)
            print("add_song :" + str(song) + " to playlist: " + str(playlist))
            return f"Added to '{target}': {song['artist']} - {song['title']}."

        # If only title
        title = song_spec.strip()
        candidates = find_songs_by_title(title)
        if not candidates:
            return f"No songs found with title '{title}'."
        if len(candidates) == 1:
            song = candidates[0]
            entries = self._playlists.setdefault(target, [])
            if any(e["id"] == song["id"] for e in entries):
                return f"Song already in playlist '{target}': {song['artist']} - {song['title']}."
            entries.append(song)
            print("add_song :" + str(song) + " to playlist: " + str(playlist))
            return f"Added to '{target}': {song['artist']} - {song['title']}."

        # Multiple candidates: return list for choosing
        if pending_list is not None:
            pending_list.clear()
            pending_list.extend(candidates[:10])  # keep top 10
        return "Multiple matches: <br>" + "<br>".join(
            [f"{i+1}. {c['artist']} : {c['title']}" for i, c in enumerate(candidates[:10])]
        ) + "<br>Use '/pl choose [number]' to select. This option is a one-time use."

    def remove_song(self, song_spec: str, playlist: str | None = None):
        """
        Remove a song by "Artist: Title" or just "Title".
        If only title is provided, remove first match.
        """
        target = playlist or self._current
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
                (i for i, e in enumerate(entries) if e["title"].lower() == title.lower()),
                None
            )

        if idx is None:
            return f"Song not found in playlist '{target}': {song_spec}."

        removed = entries.pop(idx)
        print("remove_song :" + str(song_spec))
        return f"Removed from '{target}': {removed['artist']} - {removed['title']}."