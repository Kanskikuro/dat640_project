# musiccrs/qa_commands.py
"""QA (Question-Answer) command handlers for tracks and artists."""

from db import get_track_info, get_artist_stats


def handle_qa_track(song_spec: str, qtype: str, parse_song_spec_func, format_duration_func) -> str:
    """Handle track QA command.
    
    Args:
        song_spec: Song specification (Artist: Title)
        qtype: Question type (album, duration, popularity, spotify, all)
        parse_song_spec_func: Function to parse song specification
        format_duration_func: Function to format duration
        
    Returns:
        HTML formatted answer
    """
    qtypes = {"album", "duration", "popularity", "spotify", "all"}
    
    if qtype not in qtypes:
        return f"Unknown track question '{qtype}'. Try: album, duration, popularity, spotify, all."
    
    if ":" not in song_spec:
        return "Please specify the song as 'Artist: Title'."
    
    artist, title = parse_song_spec_func(song_spec)
    info = get_track_info(artist, title)
    if not info:
        return f"Track not found: {artist} - {title}."
    
    answers = []
    if qtype in ("album", "all"):
        answers.append(f"Album: {info.get('album') or 'Unknown'}")
    if qtype in ("duration", "all"):
        answers.append(f"Duration: {format_duration_func(info.get('duration_ms'))}")
    if qtype in ("popularity", "all"):
        answers.append(f"Popularity: appears in {info.get('popularity', 0)} playlists")
    if qtype in ("spotify", "all"):
        uri = info.get("spotify_uri") or "N/A"
        answers.append(f"Spotify URI: {uri}")
    
    return "<br>".join(answers)


def handle_qa_artist(artist: str, qtype: str) -> str:
    """Handle artist QA command.
    
    Args:
        artist: Artist name
        qtype: Question type (tracks, albums, top, playlists, all)
        
    Returns:
        HTML formatted answer
    """
    qtypes = {"tracks", "albums", "top", "playlists", "all"}
    
    if qtype not in qtypes:
        return f"Unknown artist question '{qtype}'. Try: tracks, albums, top, playlists, all."
    
    stats = get_artist_stats(artist.strip())
    answers = []
    
    if qtype in ("tracks", "all"):
        answers.append(f"Tracks in collection: {stats['num_tracks']}")
    if qtype in ("albums", "all"):
        answers.append(f"Albums in collection: {stats['num_albums']}")
    if qtype in ("playlists", "all"):
        answers.append(f"Artist appears in {stats['num_playlists']} playlists")
    if qtype in ("top", "all"):
        if stats["top_tracks"]:
            top = "<br>".join([
                f"{i+1}. {t['title']} (in {t['popularity']} playlists)"
                for i, t in enumerate(stats["top_tracks"])
            ])
            answers.append(f"Top tracks:<br>{top}")
        else:
            answers.append("Top tracks: N/A")
    
    return "<br>".join(answers)


def get_qa_help() -> str:
    """Return QA command help text."""
    return (
        "QA commands:"
        "<br> - /qa track [Artist]: [Title] (album|duration|popularity|spotify|all)"
        "<br> - /qa artist [Artist] (tracks|albums|top|playlists|all)"
    )
