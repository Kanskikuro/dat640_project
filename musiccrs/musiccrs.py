from dialoguekit.platforms import FlaskSocketPlatform
from shared_playlist import shared_playlists

from agent import MusicCRS

def run_server():
    platform = FlaskSocketPlatform(MusicCRS)  
    
    @platform.socketio.on('pl_switch')
    def handle_switch(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.switch_playlist(playlistName)
        platform.socketio.emit('pl_response', {'text': result})
    
    @platform.socketio.on('pl_create')
    def handle_create_playlist(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.create_playlist(playlistName)
        platform.socketio.emit('pl_response', {'text': result})
        
    @platform.socketio.on('pl_remove_playlist')
    def handle_remove_playlist(data):
        playlistName = data.get('playlistName', '')
        result = shared_playlists.remove_playlist(playlistName)
        platform.socketio.emit('pl_response', {'text': result})    
        
    @platform.socketio.on('pl_view')
    def handle_view(data):
        playlistName = data.get('playlistName', None)
        songs = shared_playlists.view(playlistName)
        platform.socketio.emit('pl_response', {'text': f"Playlist: {songs}"})
        
    @platform.socketio.on('pl_view_playlists')
    def handle_view_playlists(data):
        playlists = shared_playlists.view_playlists()
        platform.socketio.emit('pl_response', {'text': playlists})

    @platform.socketio.on('pl_clear')
    def handle_clear(data):
        playlistName = data.get('playlistName', None)
        result = shared_playlists.clear(playlistName)
        platform.socketio.emit('pl_response', {'text': result})
                
                
    @platform.socketio.on('pl_add')
    def handle_add_song(data):
        song = data.get('song', {})
        playlistName = data.get('playlistName', None)
        result = shared_playlists.add_song(song, playlistName)
        platform.socketio.emit('pl_response', {'text': result})

    @platform.socketio.on('pl_remove')
    def handle_remove_song(data):
        artist = data.get('artist', '')
        title = data.get('title', '')
        result = shared_playlists.remove_song(artist, title)
        platform.socketio.emit('pl_response', {'text': result})
    platform.start()

if __name__ == "__main__":
    run_server()
