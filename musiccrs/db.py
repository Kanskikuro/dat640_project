import os
import json
import sqlite3
from threading import Lock
from config import DB_PATH, MPD_DATA
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import unicodedata
import re
from rapidfuzz import process, fuzz
_indexes_lock = Lock()
_indexes_done = False
_sqlite_cfg_lock = Lock()
_sqlite_cfg_done = False

# Indexes → make queries fast
def ensure_indexes_once(): 
    global _indexes_done
    if _indexes_done:
        print("Indexes already ensured.")
        return
    with _indexes_lock:
        if _indexes_done:
            print("Indexes already ensured.")
            return
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_songs_title_artist_nocase ON songs(title COLLATE NOCASE, artist COLLATE NOCASE)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_songs_artist_title_nocase ON songs(artist COLLATE NOCASE, title COLLATE NOCASE)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlist_songs_song_playlist ON playlist_songs(song_id, playlist_id)"
        )
        # Add index on playlist names for fast auto-playlist search
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlists_name ON playlists(name COLLATE NOCASE)"
        )
        # Add index on playlist followers for fast sorting
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlists_followers ON playlists(num_followers DESC)"
        )
        conn.commit()
        conn.close()
        _indexes_done = True

# PRAGMA settings → make writes fast and safe
def configure_sqlite_once():
    global _sqlite_cfg_done
    if _sqlite_cfg_done:
        print("SQLite already configured.")
        return
    with _sqlite_cfg_lock:
        if _sqlite_cfg_done:
            print("SQLite already configured.")
            return
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        try:
            cur.execute("PRAGMA analyze;")
        except Exception:
            pass
        conn.commit()
        conn.close()
        _sqlite_cfg_done = True


def create_db_and_load_mpd(db_file=DB_PATH, mpd_folder=MPD_DATA):
    # Ensure the database directory exists and create one if it doesn't
    db_dir = os.path.dirname(db_file)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(mpd_folder):
        raise FileNotFoundError(f"MPD data folder not found: {mpd_folder}")

    conn = sqlite3.connect(db_file, timeout=30)
    cursor = conn.cursor()
    # Unique constraint on (artist, title, album) to avoid duplicates of the same song from the same artist in different playlists or albums
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artist TEXT NOT NULL,
        artist_uri TEXT,
        title TEXT NOT NULL,
        album TEXT,
        album_uri TEXT,
        duration_ms INTEGER,
        spotify_uri TEXT,
        UNIQUE(artist, title, album)
    );

    CREATE TABLE IF NOT EXISTS playlists (
        pid INTEGER PRIMARY KEY,
        name TEXT,
        collaborative BOOLEAN,
        modified_at INTEGER,
        num_tracks INTEGER,
        num_artists INTEGER,
        num_albums INTEGER,
        num_followers INTEGER,
        num_edits INTEGER,
        duration_ms INTEGER
    );

    CREATE TABLE IF NOT EXISTS playlist_songs (
        playlist_id INTEGER,
        song_id INTEGER,
        pos INTEGER,
        PRIMARY KEY (playlist_id, song_id),
        FOREIGN KEY (playlist_id) REFERENCES playlists(pid),
        FOREIGN KEY (song_id) REFERENCES songs(id)
    );
    """)

    # Check if tables already have data
    cursor.execute("SELECT COUNT(*) FROM songs")
    songs_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM playlists")
    playlists_count = cursor.fetchone()[0]

    if songs_count > 0 and playlists_count > 0:
        print("Songs and playlists already loaded. Skipping slice loading.")
        conn.close()
        return

    for slice_file in sorted(os.listdir(mpd_folder)):
        if not slice_file.endswith(".json"):
            continue
        with open(os.path.join(mpd_folder, slice_file), "r", encoding="utf-8") as f:
            data = json.load(f)
            for pl in data.get("playlists", []):
                cursor.execute("""
                    INSERT OR IGNORE INTO playlists
                    (pid, name, collaborative, modified_at, num_tracks, num_artists, num_albums, num_followers, num_edits, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pl["pid"], pl["name"], pl.get(
                        "collaborative", False), pl["modified_at"],
                    pl["num_tracks"], pl["num_artists"], pl["num_albums"],
                    pl["num_followers"], pl.get(
                        "num_edits", 0), pl.get("duration_ms", 0)
                ))

                for track in pl.get("tracks", []):
                    cursor.execute("""
                        INSERT OR IGNORE INTO songs (artist, artist_uri, title, album, album_uri, duration_ms, spotify_uri)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        track["artist_name"], track.get("artist_uri"),
                        track["track_name"], track.get("album_name"),
                        track.get("album_uri"), track.get("duration_ms"),
                        track.get("track_uri")
                    ))
                    cursor.execute("SELECT id FROM songs WHERE artist=? AND title=? AND album=?",
                                   (track["artist_name"], track["track_name"], track.get("album_name")))
                    song_id = cursor.fetchone()[0]
                    cursor.execute("""
                        INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id, pos)
                        VALUES (?, ?, ?)
                    """, (pl["pid"], song_id, track["pos"]))
        print(f"Loaded {slice_file}")
        conn.commit()
    conn.close()
    print("All slices loaded successfully.")


def find_song_in_db(artist: str, title: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, artist, title FROM songs WHERE artist = ? COLLATE NOCASE AND title = ? COLLATE NOCASE",
        (artist, title),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "artist": row[1], "title": row[2]}


def find_songs_by_title(title: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.artist, s.title, COUNT(DISTINCT ps.playlist_id) AS popularity
        FROM songs s
        LEFT JOIN playlist_songs ps ON ps.song_id = s.id
        WHERE s.title = ? COLLATE NOCASE
        GROUP BY s.id, s.artist, s.title
        ORDER BY popularity DESC, s.artist COLLATE NOCASE ASC
        LIMIT 10
    """, (title,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": sid, "artist": artist, "title": stitle} for (sid, artist, stitle, _) in rows]


def get_track_info(artist: str, title: str) -> dict | None:
    """Return detailed information for a track.

    Picks the most "popular" variant (by playlist count) if multiple rows exist
    for the same artist/title across different albums.

    Returns a dict with keys:
      id, artist, title, album, duration_ms, spotify_uri, popularity
    or None if not found.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()
    # Find the best matching song id by popularity
    cur.execute(
        """
        SELECT s.id, s.artist, s.title, s.album, s.duration_ms, s.spotify_uri,
               COUNT(DISTINCT ps.playlist_id) AS popularity
        FROM songs s
        LEFT JOIN playlist_songs ps ON ps.song_id = s.id
        WHERE s.artist = ? COLLATE NOCASE AND s.title = ? COLLATE NOCASE
        GROUP BY s.id, s.artist, s.title, s.album, s.duration_ms, s.spotify_uri
        ORDER BY popularity DESC, s.album COLLATE NOCASE ASC
        LIMIT 1
        """,
        (artist, title),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    sid, sartist, stitle, album, duration_ms, spotify_uri, popularity = row
    return {
        "id": sid,
        "artist": sartist,
        "title": stitle,
        "album": album,
        "duration_ms": duration_ms,
        "spotify_uri": spotify_uri,
        "popularity": popularity or 0,
    }


def get_artist_stats(artist: str) -> dict:
    """Return aggregate stats for an artist.

    Returns dict with keys:
      num_tracks, num_albums, num_playlists, top_tracks (list of {title, popularity})
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM songs WHERE artist = ? COLLATE NOCASE",
        (artist,),
    )
    num_tracks = cur.fetchone()[0] or 0

    cur.execute(
        """
        SELECT COUNT(DISTINCT album)
        FROM songs
        WHERE artist = ? COLLATE NOCASE AND album IS NOT NULL AND album <> ''
        """,
        (artist,),
    )
    num_albums = cur.fetchone()[0] or 0

    cur.execute(
        """
        SELECT COUNT(DISTINCT ps.playlist_id)
        FROM songs s
        JOIN playlist_songs ps ON ps.song_id = s.id
        WHERE s.artist = ? COLLATE NOCASE
        """,
        (artist,),
    )
    num_playlists = cur.fetchone()[0] or 0

    cur.execute(
        """
        SELECT s.title, COUNT(DISTINCT ps.playlist_id) AS popularity
        FROM songs s
        LEFT JOIN playlist_songs ps ON ps.song_id = s.id
        WHERE s.artist = ? COLLATE NOCASE
        GROUP BY s.title
        ORDER BY popularity DESC, s.title COLLATE NOCASE ASC
        LIMIT 10
        """,
        (artist,),
    )
    top_tracks = [
        {"title": t, "popularity": (p or 0)} for (t, p) in cur.fetchall()
    ]

    conn.close()
    return {
        "num_tracks": num_tracks,
        "num_albums": num_albums,
        "num_playlists": num_playlists,
        "top_tracks": top_tracks,
    }


def search_tracks_by_keywords(keywords: list[str], limit: int) -> list[dict]:
    """Search for tracks with diversity and quality.
    
    Strategy:
    1. Check playlist names first for context
    2. Get diverse songs from high-follower playlists
    3. Fallback to artist search if no playlists match
    
    Args:
        keywords: List of search terms
        limit: Maximum number of tracks to return
        
    Returns:
        List of dicts with keys: id, artist, title, album, spotify_uri, popularity
    """
    if not keywords:
        return []
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()
    
    # STRATEGY 1: Search playlists first (gives diversity + context)
    conditions = []
    params_playlist = []
    for kw in keywords:
        conditions.append("name LIKE ? COLLATE NOCASE")
        params_playlist.append(f"%{kw}%")
    
    where_clause = " OR ".join(conditions)
    params_playlist.append(30)  # Top 30 matching playlists
    
    playlist_query = f"""
        SELECT pid, num_followers FROM playlists
        WHERE {where_clause}
        ORDER BY num_followers DESC
        LIMIT ?
    """
    
    cur.execute(playlist_query, params_playlist)
    playlists = cur.fetchall()
    
    if playlists:
        playlist_ids = [row[0] for row in playlists]
        placeholders = ','.join('?' * len(playlist_ids))
        
        # Get diverse songs with popularity tracking
        # Use RANDOM() to ensure variety across multiple playlists
        songs_query = f"""
            SELECT s.id, s.artist, s.title, s.album, s.spotify_uri,
                   COUNT(DISTINCT ps.playlist_id) AS popularity
            FROM songs s
            INNER JOIN playlist_songs ps ON ps.song_id = s.id
            WHERE ps.playlist_id IN ({placeholders})
            GROUP BY s.id, s.artist, s.title, s.album, s.spotify_uri
            HAVING COUNT(DISTINCT s.artist) <= ?
            ORDER BY popularity DESC, RANDOM()
            LIMIT ?
        """
        
        # Limit diversity: max songs per result should have varied artists
        cur.execute(songs_query, playlist_ids + [limit // 2, limit * 2])
        rows = cur.fetchall()
        
        if rows:
            # Ensure artist diversity in final results
            seen_artists = set()
            diverse_results = []
            other_results = []
            
            for row in rows:
                artist = row[1]
                if artist not in seen_artists or len(seen_artists) >= limit // 3:
                    diverse_results.append(row)
                    seen_artists.add(artist)
                else:
                    other_results.append(row)
                
                if len(diverse_results) >= limit:
                    break
            
            # Fill remaining slots with other songs if needed
            if len(diverse_results) < limit:
                diverse_results.extend(other_results[:limit - len(diverse_results)])
            
            conn.close()
            return [
                {
                    "id": row[0],
                    "artist": row[1],
                    "title": row[2],
                    "album": row[3] or "Unknown",
                    "spotify_uri": row[4],
                    "popularity": row[5] or 0
                }
                for row in diverse_results[:limit]
            ]
    
    # STRATEGY 2: Fallback to artist search if no playlists match
    for kw in keywords:
        artist_query = """
            SELECT DISTINCT s.id, s.artist, s.title, s.album, s.spotify_uri,
                   COUNT(DISTINCT ps.playlist_id) AS popularity
            FROM songs s
            LEFT JOIN playlist_songs ps ON ps.song_id = s.id
            WHERE s.artist LIKE ? COLLATE NOCASE
            GROUP BY s.id, s.artist, s.title, s.album, s.spotify_uri
            ORDER BY popularity DESC
            LIMIT ?
        """
        cur.execute(artist_query, (f"%{kw}%", limit))
        rows = cur.fetchall()
        
        if rows:
            conn.close()
            return [
                {
                    "id": row[0],
                    "artist": row[1],
                    "title": row[2],
                    "album": row[3] or "Unknown",
                    "spotify_uri": row[4],
                    "popularity": row[5] or 0
                }
                for row in rows
            ]
    
    conn.close()
    return []


def recommend_songs(song_entries: list[dict], limit: int = 5) -> list[str]:
    """ Recommend songs based on co-occurrence in playlists using song IDs.
    Input: list of {"id": str, "artist": str, "title": str}.
    
    Returns: list of "ARTIST : TITLE (freq)".
    """
    if not song_entries:
        return []

    song_ids = [song["id"] for song in song_entries if "id" in song]
    if not song_ids:
        return []

    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    # Indexing for faster lookups
    cur.executescript("""
        CREATE INDEX IF NOT EXISTS idx_playlist_songs_song 
        ON playlist_songs(song_id);
        CREATE INDEX IF NOT EXISTS idx_playlist_songs_playlist 
        ON playlist_songs(playlist_id);
    """)
    conn.commit()


    placeholders = ",".join("?" for _ in song_ids)
    #Limit the number of playlists touched.
    #   smaller limit = faster but less accurate. 
    #   bigger  limit = more accurate but slower.  
    #   LIMIT : 1000 - 2500 for 0.1-0.25% of db playlists
    #   Order by random makes it non-biased because of playlist order
    #   Order by playlist follower recommends based on mainstream taste
    playlist_query = f"""
        SELECT DISTINCT playlist_id
        FROM playlist_songs
        WHERE song_id IN ({placeholders})
        LIMIT 2000
    """
    cur.execute(playlist_query, song_ids)
    playlist_ids = [row[0] for row in cur.fetchall()]
    if not playlist_ids:
        conn.close()
        return []

    placeholders_pl = ",".join("?" for _ in playlist_ids)
    # Co-occurrence counting
    query = f"""
        SELECT ps2.song_id, COUNT(*) AS freq
        FROM playlist_songs ps2
        WHERE ps2.playlist_id IN ({placeholders_pl})
          AND ps2.song_id NOT IN ({placeholders})
        GROUP BY ps2.song_id
        ORDER BY freq DESC
        LIMIT ?
    """
    params = playlist_ids + song_ids + [limit]
    cur.execute(query, params)
    recommended_data = cur.fetchall()
    if not recommended_data:
        conn.close()
        return []

    recommended_ids = [row[0] for row in recommended_data]
    placeholders = ",".join("?" for _ in recommended_ids)
    # Map song IDs to artist : song
    cur.execute(f"""
        SELECT id, title, artist 
        FROM songs 
        WHERE id IN ({placeholders})
    """, recommended_ids)
    songs_info = {row[0]: f"{row[2]} : {row[1]}" for row in cur.fetchall()}



    conn.close()
    return songs_info, recommended_data


# --- AcousticBrainz feature fetching and storing ---


def audio_feature_columns():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for col, col_type in [
        ("ab_energy", "REAL"),
        ("ab_danceability", "REAL"),
        ("ab_tempo", "REAL"),
        ("ab_key", "INTEGER"),
        ("ab_loudness", "REAL"),
        ("ab_features_json", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE songs ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()



BATCH_SIZE = 25      # Max 25 songs per API bulk request
DB_COMMIT_BATCH = 500
MAX_WORKERS = 10     # Parallel batch threads
RETRIES = 3          # Retry failed requests


# --- MBID Cache ---
mbid_cache = {}
def normalize_text(text: str) -> str:
    """Lowercase, remove accents & punctuation for fuzzy matching."""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9 ]', '', text)
    return text

def clean_title(title: str) -> str:
    """Remove parentheses, brackets, and trailing dashes for fuzzy MBID lookup."""
    # Remove (feat ...), (live), [remix], etc.
    title = re.sub(r"[\(\[].*?[\)\]]", "", title)
    # Remove extra whitespace and trailing dashes
    title = re.sub(r"[-–—]+$", "", title).strip()
    return title

def get_mbid(title: str, artist: str) -> str | None:
    """Fetch MBID from MusicBrainz with fallback to cleaned title."""
    norm_title = normalize_text(title)
    norm_artist = normalize_text(artist)

    # Try exact title first
    mbid = mbid_search(norm_title, norm_artist)
    if mbid:
        return mbid

    # If fails, try cleaned title
    clean = clean_title(title)
    if clean != title:
        norm_clean = normalize_text(clean)
        mbid = mbid_search(norm_clean, norm_artist)
        if mbid:
            return mbid

    return None

def mbid_search(title: str, artist: str) -> str | None:
    """Perform MusicBrainz search and fuzzy match."""
    url = "https://musicbrainz.org/ws/2/recording/"
    params = {
        "query": f'recording:"{title}" AND artist:"{artist}"',
        "fmt": "json",
        "limit": 10
    }
    headers = {"User-Agent": "SongFeatureCollector/1.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        recordings = data.get("recordings", [])
        if not recordings:
            return None

        titles = [normalize_text(rec.get("title", "")) for rec in recordings]
        best_match, score, idx = process.extractOne(title, titles, scorer=fuzz.ratio)

        if score < 70:
            return None

        return recordings[idx]["id"]
    except requests.RequestException:
        return None

def get_mbid_cached(title: str, artist: str) -> str | None:
    """Cache MBID lookups to reduce repeated MusicBrainz requests."""
    key = f"{artist}|{title}"
    if key in mbid_cache:
        return mbid_cache[key]

    mbid = get_mbid(title, artist)
    mbid_cache[key] = mbid
    return mbid


# --- Feature extraction for one song ---
def get_acousticbrainz_features(mbid, level="high-level"):
    base = "https://acousticbrainz.org/api/v1"
    url = f"{base}/{mbid}/{level}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def fetch_features_for_song(song):
    song_id, title, artist = song
    mbid = get_mbid_cached(title, artist)
    if not mbid:
        return None
    features = get_acousticbrainz_features(mbid)
    if not features:
        return None

    hl = features.get("highlevel", {})
    ll = features.get("lowlevel", {})
    rhythm = features.get("rhythm", {})
    tonal = features.get("tonal", {})

    energy = float(hl.get("energy", {}).get("probability", 0.0))
    danceability = float(hl.get("danceability", {}).get("probability", 0.0))
    tempo = float(rhythm.get("bpm", 0.0))
    key = int(tonal.get("key_key", -1))
    loudness = float(ll.get("loudness", 0.0))

    return song_id, energy, danceability, tempo, key, loudness

# --- Main batch processing ---
from collections import Counter
def store_features_in_db_parallel():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, artist FROM songs")
    songs = cursor.fetchall()
    total_songs = len(songs)
    print(f"Total songs to process: {total_songs}")

    results = []
    failures = []
    error_types = Counter()

    def process_batch(batch_songs):
        batch_results = []
        batch_failures = 0
        batch_errors = Counter()

        for song in batch_songs:
            success = None
            error_reason = None

            for attempt in range(RETRIES):
                try:
                    success = fetch_features_for_song(song)
                    if success:
                        batch_results.append(success)
                        break
                    else:
                        error_reason = "No MBID or features"
                        time.sleep(0.2)
                except requests.RequestException:
                    error_reason = "RequestException"
                    time.sleep(0.2)
                except Exception as e:
                    error_reason = type(e).__name__
                    time.sleep(0.2)

            if not success:
                batch_failures += 1
                batch_errors[error_reason] += 1

        return batch_results, batch_failures, batch_errors

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for i in range(0, total_songs, BATCH_SIZE):
            batch = songs[i:i + BATCH_SIZE]
            futures.append(executor.submit(process_batch, batch))

        processed_count = 0
        for future in as_completed(futures):
            batch_results, batch_failures_count, batch_errors = future.result()
            results.extend(batch_results)
            failures.extend([None] * batch_failures_count)  # just count them
            error_types.update(batch_errors)
            processed_count += len(batch_results) + batch_failures_count

            print(f"Processed {processed_count}/{total_songs} songs "
                  f"(Success so far: {len(results)}, Failed so far: {len(failures)})")
            if batch_errors:
                print(f"Batch error summary: {dict(batch_errors)}")

    # Commit to DB in larger batches
    print("Starting batch updates to database...")
    for batch_start in range(0, len(results), DB_COMMIT_BATCH):
        batch = results[batch_start:batch_start + DB_COMMIT_BATCH]
        cursor.executemany(
            """
            UPDATE songs
            SET ab_energy=?, ab_danceability=?, ab_tempo=?, ab_key=?, ab_loudness=?
            WHERE id=?
            """,
            [(e, d, t, k, l, sid) for sid, e, d, t, k, l in batch]
        )
        conn.commit()
        print(f"Committed batch {batch_start}-{batch_start + len(batch)} "
              f"(Success in batch: {len(batch)}, Total failed: {len(failures)})")

    conn.close()
    print(f"Finished processing all songs. Total Success: {len(results)}, Total Failed: {len(failures)}")
    if error_types:
        print("Summary of error types:")
        for err, count in error_types.most_common():
            print(f"{err}: {count}")

if __name__ == "__main__":
    configure_sqlite_once()
    create_db_and_load_mpd(DB_PATH)
    ensure_indexes_once()
    print("Database setup complete.")
    audio_feature_columns()
    store_features_in_db_parallel()

    
