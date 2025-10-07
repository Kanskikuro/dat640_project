import base64
import time
from typing import Optional

import requests
import os


class SpotifyClient:
    """Minimal Spotify client using Client Credentials for preview URLs.

    This does NOT control playback; it only retrieves `preview_url` and builds
    open.spotify.com links. If credentials are missing, it degrades gracefully
    by returning None for preview and only providing a public link.
    """

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    TRACK_URL = "https://api.spotify.com/v1/tracks/{}"

    def __init__(self,
                 client_id: Optional[str] = None,
                 client_secret: Optional[str] = None):
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    def _have_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> Optional[str]:
        now = time.time()
        if self._access_token and now < self._expires_at - 30:
            return self._access_token

        if not self._have_credentials():
            return None

        try:
            auth_str = f"{self.client_id}:{self.client_secret}".encode()
            b64 = base64.b64encode(auth_str).decode()
            headers = {
                "Authorization": f"Basic {b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            resp = requests.post(self.TOKEN_URL, headers=headers, data={"grant_type": "client_credentials"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            self._expires_at = now + expires_in
            return self._access_token
        except Exception:
            # Degrade gracefully
            self._access_token = None
            self._expires_at = 0
            return None

    @staticmethod
    def parse_spotify_track_id(spotify_uri_or_url: str) -> Optional[str]:
        s = spotify_uri_or_url.strip()
        if s.startswith("spotify:track:"):
            return s.split(":")[-1]
        if "open.spotify.com/track/" in s:
            try:
                path = s.split("open.spotify.com/track/")[-1]
                track_id = path.split("?")[0].split("#")[0]
                return track_id
            except Exception:
                return None
        if len(s) == 22 and s.isalnum():  # raw id
            return s
        return None

    @staticmethod
    def open_spotify_track_url(track_id_or_uri: str) -> Optional[str]:
        # Accept both full uri/url or raw id
        tid = SpotifyClient.parse_spotify_track_id(track_id_or_uri) or track_id_or_uri
        if not tid:
            return None
        return f"https://open.spotify.com/track/{tid}"

    def get_preview_url(self, spotify_uri_or_url: str) -> Optional[str]:
        track_id = self.parse_spotify_track_id(spotify_uri_or_url)
        if not track_id:
            return None

        token = self._get_token()
        if not token:
            return None

        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(self.TRACK_URL.format(track_id), headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("preview_url")
        except Exception:
            return None
