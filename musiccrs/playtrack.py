# musiccrs/playback_commands.py
"""Playback command handlers for playing tracks."""

from db import get_track_info


def handle_play_track(artist: str, title: str, spotify_client, render_player_func) -> str:
    """Handle play track command.
    
    Args:
        artist: Artist name
        title: Track title
        spotify_client: SpotifyClient instance
        render_player_func: Function to render player
        
    Returns:
        HTML formatted player
    """
    info = get_track_info(artist, title)
    if not info:
        return f"Track not found: {artist} - {title}."
    uri = info.get("spotify_uri")
    if not uri:
        return f"No Spotify URI found for {artist} - {title}. Try '/qa track {artist}: {title} spotify' to check."
    return render_player_func(uri, label=f"{artist} - {title}")


def handle_play_uri(uri: str, render_player_func) -> str:
    """Handle play URI command.
    
    Args:
        uri: Spotify URI or URL
        render_player_func: Function to render player
        
    Returns:
        HTML formatted player
    """
    return render_player_func(uri, label="Spotify track")


def render_player(spotify_uri_or_url: str, label: str, spotify_client) -> str:
    """Render a player for a Spotify track.
    
    Args:
        spotify_uri_or_url: Spotify URI or URL
        label: Display label
        spotify_client: SpotifyClient instance
        
    Returns:
        HTML formatted player
    """
    link = spotify_client.open_spotify_track_url(spotify_uri_or_url) or "#"
    preview = spotify_client.get_preview_url(spotify_uri_or_url)
    if preview:
        return (
            f"<div><strong>Playing preview:</strong> {label}<br>"
            f"<audio controls src=\"{preview}\" preload=\"none\"></audio>"
            f"<br><a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
        )
    # Fallback: Spotify embed (30s preview UI) without requiring SDK or login
    track_id = spotify_client.parse_spotify_track_id(spotify_uri_or_url)
    if track_id:
        embed = (
            f"<iframe style=\"border-radius:12px\" "
            f"src=\"https://open.spotify.com/embed/track/{track_id}\" "
            f"width=\"100%\" height=\"80\" frameborder=\"0\" allow=\"autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture\" loading=\"lazy\"></iframe>"
        )
        return (
            f"<div><strong>Preview:</strong> {label}<br>{embed}"
            f"<br><a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
        )
    return (
        f"<div>No preview available for {label}. "
        f"<a href=\"{link}\" target=\"_blank\">Open in Spotify</a></div>"
    )


def get_play_help() -> str:
    """Return playback command help text."""
    return (
        "Play commands:"
        "<br> - /play track [Artist]: [Title]"
        "<br> - /play uri [spotify track uri or open.spotify.com link]"
    )
