# musiccrs/auto_playlist.py
"""Auto playlist generation functionality."""

from collections import Counter
from db import search_tracks_by_keywords


def generate_playlist_name(description: str, tracks: list[dict]) -> str:
    """Generate a creative playlist name based on description and selected songs.
    
    Args:
        description: User's original description
        tracks: List of selected tracks
        
    Returns:
        Generated playlist name
    """
    # Analyze the tracks to generate a contextual name
    artists = [t['artist'] for t in tracks if t.get('artist')]
    
    # Count artist frequency
    artist_counts = Counter(artists)
    top_artists = artist_counts.most_common(3)
    
    # Name generation strategies
    description_clean = description.strip().title()
    
    # Strategy 1: If dominated by one artist (50%+), use artist name
    if top_artists and top_artists[0][1] >= len(tracks) * 0.5:
        dominant_artist = top_artists[0][0]
        return f"{dominant_artist} Mix"
    
    # Strategy 2: If 2-3 artists dominate, mention them
    if len(top_artists) >= 2 and (top_artists[0][1] + top_artists[1][1]) >= len(tracks) * 0.6:
        artist1 = top_artists[0][0]
        artist2 = top_artists[1][0]
        return f"{artist1} & {artist2} Vibes"
    
    # Strategy 3: Use time-of-day/mood prefixes for common keywords
    mood_prefixes = {
        'chill': 'Late-Night',
        'relax': 'Evening',
        'calm': 'Sunday Morning',
        'sad': 'Midnight',
        'happy': 'Sunny Day',
        'party': 'Weekend',
        'workout': 'Morning',
        'gym': 'Power',
        'sleep': 'Bedtime',
        'study': 'Focus',
        'energetic': 'High Energy',
        'dance': 'Party Night',
        'love': 'Romantic',
        'rock': 'Classic',
        'jazz': 'Smooth',
        'pop': 'Top',
        'indie': 'Indie',
    }
    
    # Check if any mood keywords exist in description
    description_lower = description.lower()
    for keyword, prefix in mood_prefixes.items():
        if keyword in description_lower:
            # Remove the keyword from description and capitalize rest
            remaining = description_clean.replace(keyword.title(), '').strip()
            if remaining:
                return f"{prefix} {remaining}"
            else:
                return f"{prefix} Mix"
    
    # Strategy 4: Default - capitalize and clean up description
    if len(description_clean) <= 30:
        return description_clean
    else:
        # Truncate long descriptions
        return description_clean[:27] + "..."


def determine_playlist_length(description: str) -> int:
    """Intelligently determine playlist length based on context clues.
    
    Args:
        description: User's playlist description
        
    Returns:
        Number of songs to include (between 5 and 50)
    """
    description_lower = description.lower()
    
    # Activity-based length determination
    activity_lengths = {
        # Short playlists (5-10 songs)
        'quick': 8,
        'short': 8,
        'brief': 8,
        'few': 8,
        
        # Medium playlists (10-20 songs)
        'workout': 12,
        'gym': 12,
        'commute': 12,
        'coffee': 12,
        'shower': 10,
        'cooking': 15,
        'dinner': 15,
        'lunch': 10,
        'breakfast': 10,
        'focus': 15,
        'study': 20,
        'work': 20,
        'reading': 15,
        
        # Long playlists (20-40 songs)
        'party': 30,
        'road': 35,
        'trip': 35,
        'drive': 35,
        'long': 35,
        'marathon': 40,
        'mix': 25,
        'collection': 30,
        'best': 25,
        'top': 25,
        'essential': 25,
        'ultimate': 30,
        
        # Very long playlists (40-50 songs)
        'all': 50,
        'complete': 50,
        'everything': 50,
        'comprehensive': 50,
    }
    
    # Check for activity keywords
    for keyword, length in activity_lengths.items():
        if keyword in description_lower:
            return length
    
    # Check for time-based indicators
    if 'hour' in description_lower:
        # Try to extract number
        if '1' in description_lower or 'one' in description_lower:
            return 15  # ~1 hour playlist (assuming 4 min per song)
        elif '2' in description_lower or 'two' in description_lower:
            return 30  # ~2 hour playlist
        elif '3' in description_lower or 'three' in description_lower:
            return 45  # ~3 hour playlist
        else:
            return 20  # Default hour-based
    
    # Check for number words
    number_words = {
        'five': 5, 'ten': 10, 'fifteen': 15, 'twenty': 20,
        'thirty': 30, 'forty': 40, 'fifty': 50,
        '5': 5, '10': 10, '15': 15, '20': 20,
        '25': 25, '30': 30, '40': 40, '50': 50
    }
    
    for num_word, count in number_words.items():
        if num_word in description_lower.split():
            return min(count, 50)  # Cap at 50
    
    # Artist-specific playlists tend to be longer
    if any(word in description_lower for word in ['artist', 'band', 'singer', 'hits']):
        return 25
    
    # Genre playlists tend to be medium-long
    genres = ['rock', 'pop', 'jazz', 'hip', 'rap', 'country', 'classical', 
              'electronic', 'metal', 'indie', 'folk', 'blues', 'r&b', 'soul']
    if any(genre in description_lower for genre in genres):
        return 20
    
    # Mood playlists tend to be shorter
    moods = ['sad', 'happy', 'chill', 'relax', 'calm', 'energetic', 'angry', 'love']
    if any(mood in description_lower for mood in moods):
        return 15
    
    # Default: medium-sized playlist
    return 15


def extract_keywords(description: str) -> list[str]:
    """Extract keywords from user description.
    
    Args:
        description: User's playlist description
        
    Returns:
        List of keywords
    """
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
                  'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'it'}
    words = description.lower().split()
    # Keep words that are 2+ characters
    keywords = [w.strip() for w in words if len(w) >= 2 and w not in stop_words]
    return keywords


def create_auto_playlist(description: str, playlist_manager, emit_pl_func) -> str:
    """Create an auto-generated playlist from a natural language description.
    
    Args:
        description: User's playlist description
        playlist_manager: PlaylistManager instance
        emit_pl_func: Function to emit playlist events
        
    Returns:
        HTML formatted response
    """
    if not description or not description.strip():
        return "Please provide a description for the playlist. Example: /pl auto sad love songs"
    
    description = description.strip()
    
    # Step 1: Extract keywords
    keywords = extract_keywords(description)
    
    if not keywords:
        return "Could not extract meaningful keywords from the description."
    
    # Step 2: Determine playlist length intelligently
    playlist_length = determine_playlist_length(description)
    
    # Step 3: Search database for matching tracks
    tracks = search_tracks_by_keywords(keywords, limit=playlist_length)
    
    if not tracks:
        return f"No tracks found matching '{description}'. Keywords searched: {', '.join(keywords)}"
    
    # Step 4: Generate smart playlist name
    playlist_name = generate_playlist_name(description, tracks)
    create_result = playlist_manager.create_playlist(playlist_name)
    
    if not create_result.startswith("Created") and not create_result.startswith("Switched"):
        return f"Failed to create playlist: {create_result}"
    
    # Step 5: Add tracks to playlist
    added_count = 0
    skipped_count = 0
    for track in tracks:
        song_spec = f"{track['artist']}: {track['title']}"
        result = playlist_manager.add_song(song_spec)
        if result.startswith("Added"):
            added_count += 1
        else:
            skipped_count += 1
    
    # Step 6: Emit UI updates
    if create_result.startswith("Created"):
        emit_pl_func("created", playlist_name)
    else:
        emit_pl_func("switched", playlist_name)
    
    if hasattr(playlist_manager, "view_playlists"):
        emit_pl_func("playlists", playlist_manager.view_playlists())
    
    # Emit songs for current playlist
    cur = getattr(playlist_manager, "_current", None)
    if cur:
        items = playlist_manager.view(cur)
        if isinstance(items, list):
            song_strings = [f"{s['artist']}:{s['title']}" for s in items]
            emit_pl_func("songs", song_strings)
    
    # Step 7: Build response
    parts = []
    parts.append(f"<div><h3>✨ Auto-generated Playlist</h3>")
    parts.append(f"<p><strong>Description:</strong> {description}</p>")
    parts.append(f"<p><strong>Keywords searched:</strong> {', '.join(keywords)}</p>")
    parts.append(f"<p><strong>Playlist name:</strong> {playlist_name}</p>")
    parts.append(f"<p><strong>Target length:</strong> {playlist_length} songs (determined intelligently)</p>")
    parts.append(f"<p><strong>Tracks added:</strong> {added_count}</p>")
    if skipped_count > 0:
        parts.append(f"<p><em>(Skipped {skipped_count} duplicates)</em></p>")
    
    # Show first 5 tracks
    parts.append("<strong>Sample tracks:</strong><br>")
    parts.append("<ol>")
    for i, track in enumerate(tracks[:5]):
        spotify_link = f" <a href='{track['spotify_uri']}' target='_blank'>♫</a>" if track.get('spotify_uri') else ""
        parts.append(f"<li>{track['artist']} - {track['title']}{spotify_link}</li>")
    parts.append("</ol>")
    
    if len(tracks) > 5:
        parts.append(f"<p><em>...and {len(tracks) - 5} more tracks</em></p>")
    
    parts.append(f"<p>Use <code>/pl view</code> to see all tracks or <code>/pl summary</code> for full statistics.</p>")
    parts.append("</div>")
    
    return "".join(parts)
