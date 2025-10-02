class PlaylistManager:
    def __init__(self):
        self._current = None
        self._playlists = {}

    def use(self, name: str):
        if not name:
            return "Please provide a playlist name."
        if name not in self._playlists:
            self._playlists[name] = []
        self._current = name
        return f"Switched to playlist '{name}'."

    def add_song(self, song: dict, playlist: str | None = None):
        target = playlist or self._current
        if not target:
            return "No active playlist. Use '/pl use [name]' first."
        entries = self._playlists.setdefault(target, [])
        if any(e["id"] == song["id"] for e in entries):
            return f"Song already in playlist '{target}': {song['artist']} - {song['title']}."
        entries.append(song)
        return f"Added to '{target}': {song['artist']} - {song['title']}."

    def remove_song(self, artist: str, title: str):
        target = self._current
        if not target:
            return "No active playlist. Use '/pl use [name]' first."
        entries = self._playlists.get(target, [])
        idx = next((i for i, e in enumerate(entries) if e["artist"].lower(
        ) == artist.lower() and e["title"].lower() == title.lower()), None)
        if idx is None:
            return f"Song not found in playlist '{target}': {artist} - {title}."
        removed = entries.pop(idx)
        return f"Removed from '{target}': {removed['artist']} - {removed['title']}."

    def view(self, playlist: str | None = None):
        target = playlist or self._current
        return self._playlists.get(target, [])

    def clear(self, playlist: str | None = None):
        target = playlist or self._current
        if not target:
            return "No active playlist. Use '/pl use [name]' first."
        self._playlists[target] = []
        return f"Cleared playlist '{target}'."
