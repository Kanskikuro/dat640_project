# musiccrs/auto_playlist.py
"""Auto playlist generation functionality."""

from collections import Counter
from db import search_tracks_by_keywords


def generate_playlist_name(description: str, tracks: list[dict]) -> str:
    """Generate a creative playlist name based on description and selected songs.
    
    Uses multi-strategy approach analyzing:
    - Artist dominance and diversity
    - Song titles for thematic patterns
    - Description keywords and context
    - Musical era and genre signals
    - Creative combinations and wordplay
    
    Args:
        description: User's original description
        tracks: List of selected tracks
        
    Returns:
        Generated playlist name (max 40 characters for readability)
    """
    # Analyze the tracks
    artists = [t['artist'] for t in tracks if t.get('artist')]
    titles = [t['title'].lower() for t in tracks if t.get('title')]
    
    # Count artist frequency
    artist_counts = Counter(artists)
    top_artists = artist_counts.most_common(5)
    
    # Analyze description
    description_clean = description.strip()
    description_lower = description_clean.lower()
    desc_words = description_lower.split()
    
    # === STRATEGY 1: SINGLE ARTIST DOMINANCE ===
    if top_artists and top_artists[0][1] >= len(tracks) * 0.5:
        dominant_artist = top_artists[0][0]
        
        # Check for collection/best-of indicators
        if any(word in description_lower for word in ['all', 'complete', 'every', 'entire', 'whole']):
            return f"{dominant_artist}: Complete Collection"
        if any(word in description_lower for word in ['best', 'top', 'greatest', 'hit']):
            return f"Best of {dominant_artist}"
        if any(word in description_lower for word in ['essential', 'must']):
            return f"{dominant_artist} Essentials"
        if any(word in description_lower for word in ['classic', 'vintage', 'old']):
            return f"{dominant_artist} Classics"
        
        # Default single artist
        return f"{dominant_artist} Mix"
    
    # === STRATEGY 2: DUAL ARTIST FOCUS ===
    if len(top_artists) >= 2:
        artist1_count = top_artists[0][1]
        artist2_count = top_artists[1][1]
        
        # Two artists dominate roughly equally
        if artist1_count + artist2_count >= len(tracks) * 0.6:
            artist1 = top_artists[0][0]
            artist2 = top_artists[1][0]
            
            # Check for versus/battle context
            if any(word in description_lower for word in ['vs', 'versus', 'or', 'battle']):
                return f"{artist1} vs {artist2}"
            # Check for blend/mix context
            return f"{artist1} & {artist2}"
    
    # === STRATEGY 3: MULTI-ARTIST DIVERSITY ===
    unique_artists = len(artist_counts)
    if unique_artists >= len(tracks) * 0.7:  # High diversity
        # Genre-based naming
        genre_names = {
            'rock': 'Rock', 'pop': 'Pop', 'jazz': 'Jazz', 'hip': 'Hip-Hop',
            'rap': 'Rap', 'country': 'Country', 'classical': 'Classical',
            'electronic': 'Electronic', 'edm': 'EDM', 'metal': 'Metal',
            'indie': 'Indie', 'folk': 'Folk', 'blues': 'Blues',
            'r&b': 'R&B', 'soul': 'Soul', 'funk': 'Funk', 'disco': 'Disco',
            'reggae': 'Reggae', 'punk': 'Punk', 'alternative': 'Alternative'
        }
        
        for keyword, genre in genre_names.items():
            if keyword in description_lower:
                if any(word in description_lower for word in ['best', 'top', 'greatest']):
                    return f"Top {genre} Tracks"
                if any(word in description_lower for word in ['new', 'modern', 'current', 'today']):
                    return f"Modern {genre}"
                if any(word in description_lower for word in ['classic', 'old', 'vintage', 'retro']):
                    return f"Classic {genre}"
                return f"{genre} Mix"
    
    # === STRATEGY 4: MOOD & EMOTION ANALYSIS ===
    # Analyze song titles for common emotional words
    title_words = ' '.join(titles)
    emotional_patterns = {
        'love': ['Love', 'Romantic', 'Hearts'],
        'heart': ['Heartfelt', 'From the Heart', 'Matters of the Heart'],
        'night': ['Midnight', 'Late Night', 'Night Vibes'],
        'dream': ['Dreamscape', 'Sweet Dreams', 'Dream State'],
        'fire': ['On Fire', 'Burning Tracks', 'Blazing'],
        'star': ['Starlight', 'Stars Align', 'Stellar'],
        'soul': ['Soulful', 'Soul Sessions', 'For the Soul'],
        'time': ['Timeless', 'Through Time', 'Time Capsule'],
        'day': ['Daytime', 'Daily Vibes', 'Daybreak'],
        'life': ['Life Soundtrack', 'Living', 'Alive'],
    }
    
    for word, name_options in emotional_patterns.items():
        if title_words.count(word) >= 3:  # Word appears in multiple titles
            import random
            return random.choice(name_options)
    
    # Mood-based naming from description
    mood_templates = {
        'chill': ['Chill Vibes', 'Late Night Chill', 'Laid Back'],
        'relax': ['Relaxation Station', 'Easy Listening', 'Unwind'],
        'calm': ['Calm Waters', 'Peaceful Moments', 'Serenity'],
        'sad': ['In My Feelings', 'Melancholy', 'Rainy Day'],
        'happy': ['Good Vibes Only', 'Feel Good Hits', 'Happiness'],
        'energetic': ['High Energy', 'Pump Up', 'Adrenaline'],
        'upbeat': ['Upbeat & Positive', 'Feel Alive', 'Energy Boost'],
        'angry': ['Rage Mode', 'Angry Anthems', 'Let It Out'],
        'love': ['Love Songs', 'Hopeless Romantic', 'Falling in Love'],
        'heartbreak': ['Heartbreak Hotel', 'Crying Hours', 'Moving On'],
        'nostalgic': ['Memory Lane', 'Throwback Vibes', 'Remember When'],
        'motivation': ['Motivational Mix', 'Keep Going', 'Unstoppable'],
        'party': ['Party Starters', 'Turn Up', 'Dance Floor'],
        'dance': ['Dance Party', 'Move Your Body', 'Groove'],
        'workout': ['Workout Mode', 'Gym Motivation', 'Beast Mode'],
        'study': ['Study Focus', 'Deep Concentration', 'Brain Power'],
        'sleep': ['Sleep Sounds', 'Bedtime', 'Sweet Dreams'],
        'romantic': ['Romance & Wine', 'Date Night', 'Love in the Air'],
    }
    
    for keyword, name_options in mood_templates.items():
        if keyword in description_lower:
            import random
            return random.choice(name_options)
    
    # === STRATEGY 5: ACTIVITY & CONTEXT ===
    activity_names = {
        'workout': 'Workout Playlist', 'gym': 'Gym Sessions',
        'running': 'Running Tracks', 'cardio': 'Cardio Beats',
        'yoga': 'Yoga Flow', 'meditation': 'Meditation Sounds',
        'party': 'Party Mix', 'celebration': 'Celebration Time',
        'road': 'Road Trip', 'drive': 'Driving Tunes', 'car': 'Car Vibes',
        'commute': 'Commute Companion', 'travel': 'Travel Soundtrack',
        'work': 'Work Flow', 'office': 'Office Background',
        'study': 'Study Session', 'focus': 'Focus Mode',
        'cooking': 'Kitchen Jams', 'dinner': 'Dinner Music',
        'coffee': 'Coffee Shop Vibes', 'morning': 'Morning Motivation',
        'evening': 'Evening Wind Down', 'night': 'Night Owl',
        'shower': 'Shower Singalongs', 'cleaning': 'Cleaning Soundtrack',
        'gaming': 'Gaming Zone', 'reading': 'Reading Ambience',
    }
    
    for activity, name in activity_names.items():
        if activity in description_lower:
            return name
    
    # === STRATEGY 6: ERA & DECADE ===
    decade_names = {
        '60s': "60's Classics", '70s': "70's Gold", '80s': "80's Hits",
        '90s': "90's Nostalgia", '00s': "2000's Throwback", '10s': "2010's Mix",
        'sixties': "Sixties Soul", 'seventies': "Seventies Rock",
        'eighties': "Eighties Pop", 'nineties': "Nineties Vibes",
        'retro': 'Retro Mix', 'vintage': 'Vintage Collection',
        'classic': 'Timeless Classics', 'oldies': 'Golden Oldies',
        'throwback': 'Throwback Thursday', 'nostalgic': 'Nostalgia Trip',
        'new': 'Fresh Picks', 'modern': 'Modern Mix', 'current': 'Current Rotation',
    }
    
    for decade, name in decade_names.items():
        if decade in description_lower:
            return name
    
    # === STRATEGY 7: SCOPE & SIZE INDICATORS ===
    if any(word in description_lower for word in ['ultimate', 'complete', 'comprehensive']):
        return "Ultimate Collection"
    if any(word in description_lower for word in ['essential', 'must', 'need']):
        return "Essential Tracks"
    if any(word in description_lower for word in ['best', 'top', 'greatest']):
        return "Greatest Hits"
    if any(word in description_lower for word in ['favorite', 'fav', 'favs']):
        return "My Favorites"
    if any(word in description_lower for word in ['discover', 'explore', 'find']):
        return "Discovery Mix"
    
    # === STRATEGY 8: CREATIVE TITLE FROM ARTISTS ===
    # If we have 3+ distinct artists, create a creative blend name
    if len(top_artists) >= 3:
        # Use first letters of top 3 artists
        initials = ''.join([a[0][0].upper() for a in top_artists[:3]])
        if len(initials) == 3:
            return f"{initials} Mix"
    
    # === STRATEGY 9: SMART DESCRIPTION PARSING ===
    # Remove common stop words and create title
    stop_words = {'a', 'an', 'the', 'for', 'to', 'of', 'in', 'on', 'with', 'by', 'from', 'and', 'or'}
    meaningful_words = [w.capitalize() for w in desc_words if w not in stop_words and len(w) > 2]
    
    if meaningful_words:
        title = ' '.join(meaningful_words[:4])  # Use up to 4 words
        if len(title) <= 35:
            return title
    
    # === STRATEGY 10: DEFAULT FALLBACK ===
    # Clean up description and use it directly
    if len(description_clean) <= 35:
        return description_clean.title()
    else:
        # Truncate intelligently at word boundary
        truncated = description_clean[:32]
        if ' ' in truncated:
            truncated = truncated.rsplit(' ', 1)[0]
        return truncated.title() + "..."


def determine_playlist_length(description: str) -> int:
    """Intelligently determine playlist length based on context clues.
    
    Analyzes the description for implicit signals about desired playlist length:
    - Activity duration (workout, commute, party, etc.)
    - Scope keywords (all, best, few, etc.)
    - Time indicators (hour, minute, etc.)
    - Content type (artist, genre, mood)
    - Multiple combined factors
    
    Args:
        description: User's playlist description
        
    Returns:
        Number of songs to include (between 5 and 50)
    """
    description_lower = description.lower()
    words = description_lower.split()
    
    # Score-based approach: accumulate signals and calculate final length
    # Randomize base slightly for variety (13-17)
    import random
    base_length = random.randint(13, 17)
    length_modifiers = []
    
    # 1. EXPLICIT TIME INDICATORS (highest priority)
    # Check for hour-based durations
    if 'hour' in description_lower or 'hr' in description_lower:
        # Extract numbers before "hour"
        import re
        hour_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hr)', description_lower)
        if hour_match:
            hours = float(hour_match.group(1))
            # Assuming average song is 3.5 minutes
            return min(int(hours * 60 / 3.5), 50)
        # Look for written numbers
        hour_numbers = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'half': 0.5, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5
        }
        for word, hours in hour_numbers.items():
            if word in words and ('hour' in description_lower or 'hr' in description_lower):
                return min(int(hours * 60 / 3.5), 50)
    
    # Check for minute-based durations
    if 'minute' in description_lower or 'min' in description_lower:
        import re
        min_match = re.search(r'(\d+)\s*(?:minute|min)', description_lower)
        if min_match:
            minutes = int(min_match.group(1))
            return max(5, min(int(minutes / 3.5), 50))
    
    # 2. EXPLICIT COUNT INDICATORS
    # Check for explicit numbers mentioned
    number_words = {
        'five': 5, 'ten': 10, 'fifteen': 15, 'twenty': 20,
        'thirty': 30, 'forty': 40, 'fifty': 50,
        '5': 5, '10': 10, '15': 15, '20': 20,
        '25': 25, '30': 30, '35': 35, '40': 40, '50': 50
    }
    
    for num_word, count in number_words.items():
        # Check if number is followed by song-related words
        if num_word in words:
            idx = words.index(num_word)
            if idx + 1 < len(words) and words[idx + 1] in ['song', 'songs', 'track', 'tracks']:
                return min(count, 50)
            # Or just standalone number as strong hint
            return min(count, 50)
    
    # 3. SCOPE/SIZE INDICATORS (strong modifiers)
    scope_modifiers = {
        # Very short
        'quick': -7, 'short': -7, 'brief': -7, 'few': -7, 'small': -5,
        # Short
        'mini': -5, 'little': -3, 'compact': -3,
        # Long
        'long': 20, 'extended': 15, 'lengthy': 15,
        # Very long
        'complete': 35, 'all': 35, 'every': 35, 'everything': 35,
        'comprehensive': 30, 'full': 30, 'entire': 30, 'whole': 30,
        'ultimate': 25, 'essential': 20, 'definitive': 25,
        'collection': 25, 'anthology': 35, 'compilation': 25,
        # Curated (medium)
        'best': 20, 'top': 20, 'greatest': 25, 'favorite': 18,
        'must': 15, 'classics': 20,
    }
    
    for keyword, modifier in scope_modifiers.items():
        if keyword in description_lower:
            length_modifiers.append(modifier)
            # For very strong indicators, return immediately
            if abs(modifier) > 25:
                return max(5, min(base_length + modifier, 50))
    
    # 4. ACTIVITY-BASED LENGTH (context-specific durations)
    activity_contexts = {
        # Very short activities (5-10 songs)
        'shower': 8, 'wake': 8, 'wakeup': 8, 'nap': 7,
        'elevator': 5, 'warmup': 8, 'cooldown': 8,
        
        # Short activities (8-12 songs)
        'coffee': 10, 'breakfast': 10, 'lunch': 10, 'snack': 8,
        'walk': 12, 'jog': 12, 'run': 12,
        
        # Medium activities (12-20 songs)
        'workout': 15, 'gym': 15, 'exercise': 15, 'yoga': 15,
        'commute': 12, 'train': 15, 'bus': 12, 'subway': 12,
        'cooking': 15, 'dinner': 18, 'meal': 15,
        'clean': 18, 'cleaning': 18, 'housework': 20,
        'study': 20, 'studying': 20, 'homework': 20,
        'work': 25, 'working': 25, 'office': 20,
        'focus': 20, 'concentration': 20, 'reading': 18,
        
        # Long activities (20-40 songs)
        'party': 35, 'dance': 30, 'celebration': 30,
        'road': 40, 'drive': 35, 'driving': 35, 'trip': 40,
        'travel': 35, 'flight': 30, 'plane': 30,
        'marathon': 45, 'endurance': 40,
        'hangout': 25, 'chill': 20, 'relax': 18, 'lounge': 20,
        'background': 30, 'ambien': 25, 'atmospheric': 20,
    }
    
    for activity, length in activity_contexts.items():
        if activity in description_lower:
            return length
    
    # 5. CONTENT TYPE ANALYSIS (what kind of music)
    
    # Artist/Band focused - usually want comprehensive collection
    artist_indicators = ['artist', 'band', 'singer', 'musician', 'by ', 'from ']
    if any(indicator in description_lower for indicator in artist_indicators):
        # Check if it's asking for specific subset
        if any(word in description_lower for word in ['hit', 'popular', 'famous', 'known']):
            length_modifiers.append(8)  # Top hits - medium playlist
        else:
            length_modifiers.append(15)  # General artist - longer playlist
    
    # Genre-based playlists - add modifier instead of returning
    genre_keywords = {
        # Specific genres tend to be longer (exploration)
        'rock': 7, 'pop': 5, 'jazz': 3, 'classical': 10,
        'hip': 5, 'hop': 5, 'rap': 5, 'r&b': 3,
        'country': 5, 'folk': 3, 'blues': 3,
        'electronic': 10, 'edm': 10, 'house': 10, 'techno': 10,
        'metal': 7, 'punk': 3, 'indie': 5, 'alternative': 5,
        'soul': 3, 'funk': 3, 'disco': 5, 'reggae': 3,
    }
    
    for genre, modifier in genre_keywords.items():
        if genre in description_lower:
            length_modifiers.append(modifier)
            break  # Only apply first genre match
    
    # Mood/Emotion-based playlists - add modifier instead of returning
    mood_keywords = {
        'sad': -3, 'happy': 0, 'calm': -3, 'peaceful': -3,
        'energetic': 3, 'upbeat': 3, 'positive': 0,
        'melancholic': -3, 'nostalgic': 0, 'romantic': 0,
        'angry': -3, 'aggressive': 0, 'intense': 0,
        'chill': 3, 'relax': 0, 'soothing': -3, 'mellow': 0,
        'motivation': 0, 'inspiring': 0, 'pump': 0,
        'love': 3, 'heartbreak': -3, 'emotional': -3,
    }
    
    for mood, modifier in mood_keywords.items():
        if mood in description_lower:
            length_modifiers.append(modifier)
            break  # Only apply first mood match
    
    # 6. ERA/DECADE INDICATORS (nostalgic collections tend to be longer)
    decades = ['60s', '70s', '80s', '90s', '00s', '10s', '20s',
               'sixties', 'seventies', 'eighties', 'nineties',
               'retro', 'vintage', 'classic', 'oldies', 'throwback']
    if any(decade in description_lower for decade in decades):
        length_modifiers.append(10)  # Era playlists tend to be exploratory
    
    # 7. COMBINATION ANALYSIS
    # Multiple artists mentioned = comparison/mix playlist
    artist_count = sum(1 for word in ['and', '&', 'vs', 'versus', ','] if word in description_lower)
    if artist_count >= 2:
        length_modifiers.append(10)  # Mix of multiple artists
    
    # Description length as signal (longer description = more specific = shorter playlist)
    word_count = len(words)
    if word_count > 10:
        length_modifiers.append(-3)  # Very specific request
    elif word_count <= 3:
        length_modifiers.append(5)  # Broad request
    
    # 8. CALCULATE FINAL LENGTH
    if length_modifiers:
        final_length = base_length + sum(length_modifiers)
    else:
        final_length = base_length
    
    # Ensure within bounds
    return max(5, min(int(final_length), 50))


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
    
    # Step 4: Generate smart playlist name and ensure uniqueness
    base_playlist_name = generate_playlist_name(description, tracks)
    playlist_name = base_playlist_name
    
    # Check if playlist name already exists and make it unique
    existing_playlists = playlist_manager.view_playlists() if hasattr(playlist_manager, 'view_playlists') else []
    if playlist_name in existing_playlists:
        # Append number to make it unique
        counter = 2
        while f"{base_playlist_name} ({counter})" in existing_playlists:
            counter += 1
        playlist_name = f"{base_playlist_name} ({counter})"
    
    create_result = playlist_manager.create_playlist(playlist_name)
    
    if not create_result.startswith("Created"):
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
