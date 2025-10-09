from dialoguekit.platforms import FlaskSocketPlatform
from playlist import shared_playlists
from agent import MusicCRS
from events import set_emitter


def run_server():
    platform = FlaskSocketPlatform(MusicCRS)
    # Bridge Socket.IO emitter for modules (e.g., agent) to push UI updates
    set_emitter(lambda event, payload: platform.socketio.emit(event, payload))

    @platform.socketio.on('pl_switch')
    def handle_switch(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.switch_playlist(playlistName)
        platform.socketio.emit(
            'pl_response', {
                'type': 'switched',
                'data': playlistName
            })

    @platform.socketio.on('pl_create')
    def handle_create_playlist(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.create_playlist(playlistName)
        
        if "Created" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'created',
                    'data': playlistName
                })
        else:
            # Already exists, just switched
            platform.socketio.emit(
                'pl_response', {
                    'type': 'switched',
                    'data': playlistName
                })

    @platform.socketio.on('pl_remove_playlist')
    def handle_remove_playlist(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.remove_playlist(playlistName)
        
        if "Deleted" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'deleted',
                    'data': playlistName
                })
        else:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': result
                })

    @platform.socketio.on('pl_view')
    def handle_view(data):
        playlistName = data.get('playlistName', None)
        songs = shared_playlists.view(playlistName)
        
        if isinstance(songs, list):
            # Convert song list to "Artist:Title" format
            song_strings = [f"{s['artist']}:{s['title']}" for s in songs]
            platform.socketio.emit(
                'pl_response', {
                    'type': 'songs',
                    'data': song_strings
                })
        else:
            # It's an error message string
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': songs
                })

    @platform.socketio.on('pl_view_playlists')
    def handle_view_playlists(data):
        playlists = shared_playlists.view_playlists()
        platform.socketio.emit(
            'pl_response', {
                'type': 'playlists',
                'data': playlists
            })

    @platform.socketio.on('pl_clear')
    def handle_clear(data):
        playlistName = data.get('playlistName', None)
        result = shared_playlists.clear(playlistName)
        
        if "Cleared" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'cleared',
                    'data': playlistName or shared_playlists._current
                })
        else:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': result
                })

    @platform.socketio.on('pl_add')
    def handle_add_song(data):
        song = data.get('song', '')
        playlistName = data.get('playlistName', None)
        result = shared_playlists.add_song(song, playlistName)

        # Check for multiple matches (pending additions)
        if shared_playlists._pending_additions:
            # Format candidates for frontend
            candidates = [
                {'artist': c['artist'], 'title': c['title']}
                for c in shared_playlists._pending_additions
            ]
            platform.socketio.emit(
                'pl_response', {
                    'type': 'multiple_matches',
                    'data': candidates
                })
        elif "Added" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'added',
                    'data': song
                })
        else:
            # Error case
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': result
                })

    @platform.socketio.on('pl_choose')
    def handle_choose_song(data):
        idx = data.get('index', 1) - 1  # Convert 1-based to 0-based
        playlistName = data.get('playlistName', None)
        result = shared_playlists.choose_song(idx, playlistName)
        
        if "Added" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'added',
                    'data': result
                })
        else:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': result
                })

    @platform.socketio.on('pl_remove')
    def handle_remove_song(data):
        artist = data.get('artist', '')
        title = data.get('title', '')
        song_spec = f"{artist}:{title}" if artist else title
        result = shared_playlists.remove_song(song_spec)
        
        if "Removed" in result:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'removed',
                    'data': song_spec
                })
        else:
            platform.socketio.emit(
                'pl_response', {
                    'type': 'error',
                    'data': result
                })

    platform.start()


if __name__ == "__main__":
    run_server()