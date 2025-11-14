"""Test the /pl recommend flow to ensure it works end-to-end."""
from playlist import PlaylistManager
from db import find_song_in_db, configure_sqlite_once, ensure_indexes_once

if __name__ == "__main__":
    print("Setting up...")
    configure_sqlite_once()
    ensure_indexes_once()
    
    # Create a playlist manager
    pm = PlaylistManager()
    
    # Add some test songs
    print("\n1. Adding songs to playlist...")
    songs_to_add = [
        ("Kendrick Lamar", "HUMBLE."),
        ("Eminem", "Lose Yourself"),
        ("Drake", "God's Plan")
    ]
    
    for artist, title in songs_to_add:
        song = find_song_in_db(artist, title)
        if song:
            result = pm.add_song(f"{artist}:{title}")
            print(f"   {result}")
        else:
            print(f"   Song not found: {artist} - {title}")
    
    # View the playlist
    print("\n2. Current playlist:")
    playlist_items = pm.view()
    if isinstance(playlist_items, list):
        for i, song in enumerate(playlist_items, 1):
            print(f"   {i}. {song['artist']} - {song['title']}")
    
    # Get recommendations
    print("\n3. Getting recommendations...")
    try:
        recommendations = pm.recommend()
        print(recommendations)
        print("\n✅ Recommendation generation works!")
    except Exception as e:
        print(f"\n❌ Error during recommendation: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    # Test selecting a recommendation
    print("\n4. Testing selection...")
    try:
        if pm._recommendation_cache:
            select_result = pm.select_recommendations([1])
            print(select_result)
            print("\n✅ Selection works!")
            
            # View updated playlist
            print("\n5. Updated playlist:")
            playlist_items = pm.view()
            if isinstance(playlist_items, list):
                for i, song in enumerate(playlist_items, 1):
                    print(f"   {i}. {song['artist']} - {song['title']}")
        else:
            print("   No recommendations in cache to test selection")
    except Exception as e:
        print(f"\n❌ Error during selection: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    print("\n✅ Complete recommendation flow works!")
