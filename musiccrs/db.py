import os
import json
import sqlite3
from threading import Lock
from config import DB_PATH, MPD_DATA
import numpy as np

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
        # Critical for recommendation queries - covers both directions
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlist_songs_playlist_song ON playlist_songs(playlist_id, song_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_playlist_songs_song ON playlist_songs(song_id)"
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

    if os.path.exists(db_file):
        print(f"Database '{db_file}' already exists. Skipping load.")
        return

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

def recommend_songs(song_entries: list[dict], limit: int = 5) -> list[dict]:
    """Recommend songs based on co-occurrence in playlists using song IDs.
       Returns normalized score between 0 and 1 for each song.
    """
    if not song_entries:
        return []

    song_ids = [song["id"] for song in song_entries if "id" in song]
    if not song_ids:
        return []

    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()

    # Find playlists containing seed songs (limited to prevent slowdown)
    placeholders = ",".join("?" for _ in song_ids)
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

    # Find songs in those playlists (excluding seeds)
    placeholders_pl = ",".join("?" for _ in playlist_ids)
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

    # Fetch song details
    recommended_ids = [row[0] for row in recommended_data]
    max_freq = max(row[1] for row in recommended_data)
    id_placeholders = ",".join("?" for _ in recommended_ids)
    
    cur.execute(f"""
        SELECT id, title, artist 
        FROM songs 
        WHERE id IN ({id_placeholders})
    """, recommended_ids)
    songs_info = {row[0]: f"{row[2]} : {row[1]}" for row in cur.fetchall()}

    conn.close()

    # Normalize freq to [0,1]
    return [{"song": songs_info.get(sid, f"Unknown (ID: {sid})"), "score": freq / max_freq} 
            for sid, freq in recommended_data if sid in songs_info]


# --------------------------- Embedding-based recommendations -----------
def recommend_by_playlist_cosine(seed_song_ids: list[int], limit: int = 10, max_playlists: int = 5000):
    """Recommend songs similar to seed songs using playlist co-occurrence (cosine sim).
    
    Optimized approach:
    1. Fetch playlists containing seed songs (limited to top playlists)
    2. Use SQL to aggregate co-occurrence counts
    3. Compute cosine similarity with set operations in Python for top candidates only
    
    Args:
        seed_song_ids: List of song IDs to base recommendations on
        limit: Number of recommendations to return
        max_playlists: Maximum number of playlists to consider (prevents slowdown on popular songs)
    """
    if not seed_song_ids:
        return []

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # --- Step 1: Get playlists containing seed songs (limited) ---
    placeholders = ",".join("?" for _ in seed_song_ids)
    cur.execute(f"""
        SELECT DISTINCT playlist_id
        FROM playlist_songs
        WHERE song_id IN ({placeholders})
        LIMIT ?
    """, seed_song_ids + [max_playlists])
    
    seed_playlists = [row[0] for row in cur.fetchall()]
    if not seed_playlists:
        conn.close()
        return []

    num_seed_playlists = len(seed_playlists)

    # --- Step 2: Get candidate songs with co-occurrence counts using SQL aggregation ---
    pl_placeholders = ",".join("?" for _ in seed_playlists)
    seed_placeholders = ",".join("?" for _ in seed_song_ids)
    
    # Optimized query: shared_playlists already gives us what we need
    # No need for expensive subquery - COUNT(DISTINCT ps.playlist_id) gives us
    # how many seed playlists each candidate appears in
    cur.execute(f"""
        SELECT 
            ps.song_id,
            COUNT(DISTINCT ps.playlist_id) AS shared_playlists
        FROM playlist_songs ps
        WHERE ps.playlist_id IN ({pl_placeholders})
          AND ps.song_id NOT IN ({seed_placeholders})
        GROUP BY ps.song_id
        HAVING shared_playlists > 0
        ORDER BY shared_playlists DESC
        LIMIT ?
    """, seed_playlists + seed_song_ids + [limit * 10])
    
    candidates = cur.fetchall()
    if not candidates:
        conn.close()
        return []

    # --- Step 3: Compute cosine similarity ---
    # For binary vectors in playlist space:
    # cosine_sim = dot_product / (||seed|| * ||candidate||)
    # 
    # When we union seed songs into one vector:
    # - dot_product = number of seed playlists the candidate appears in
    # - ||seed|| = sqrt(num_seed_playlists) [number of playlists with ANY seed song]
    # - ||candidate|| = sqrt(candidate's occurrences in seed playlists)
    #
    # This gives better scaling: songs that appear in many of the same playlists
    # as our seeds get higher scores (closer to 1.0)
    
    seed_norm = num_seed_playlists ** 0.5
    results = []
    
    for song_id, shared_count in candidates:
        # shared_count is already the candidate's occurrences in seed playlists
        candidate_norm = shared_count ** 0.5 if shared_count > 0 else 1.0
        cosine_sim = shared_count / (seed_norm * candidate_norm + 1e-9)
        results.append((song_id, cosine_sim))
    
    # Sort by similarity and take top results
    results.sort(key=lambda x: x[1], reverse=True)
    top_results = results[:limit]

    # --- Step 4: Fetch song names ---
    if not top_results:
        conn.close()
        return []
    
    result_ids = [sid for sid, _ in top_results]
    id_placeholders = ",".join("?" for _ in result_ids)
    cur.execute(f"""
        SELECT id, artist, title 
        FROM songs 
        WHERE id IN ({id_placeholders})
    """, result_ids)
    
    id_to_name = {row[0]: f"{row[1]} : {row[2]}" for row in cur.fetchall()}
    conn.close()

    return [{"song": id_to_name.get(sid, f"Unknown (ID: {sid})"), "score": score} 
            for sid, score in top_results if sid in id_to_name]

def hybrid_recommend(seed_song_ids: list[int], top_k: int = 10, alpha: float = 0.5):
    """Hybrid recommendation: co-occurrence + playlist cosine (rescaled).
    
    Args:
        seed_song_ids: List of song IDs to base recommendations on
        top_k: Number of recommendations to return
        alpha: Weight for co-occurrence (0-1). 1 = pure co-occurrence, 0 = pure cosine
    """
    if not seed_song_ids:
        return []

    # Fetch more candidates for better blending
    candidate_multiplier = 5
    
    # Step 1: Co-occurrence recommendations
    co_list = recommend_songs([{"id": sid} for sid in seed_song_ids], limit=top_k * candidate_multiplier)
    co_scores = {item["song"]: item["score"] for item in co_list}

    # Step 2: Cosine similarity recommendations
    cosine_results = recommend_by_playlist_cosine(seed_song_ids, limit=top_k * candidate_multiplier)
    cosine_scores = {row['song']: row['score'] for row in cosine_results}

    # Step 3: Normalize scores to [0, 1] range
    max_co = max(co_scores.values()) if co_scores else 1.0
    max_cos = max(cosine_scores.values()) if cosine_scores else 1.0
    
    co_norm = {song: score / max_co for song, score in co_scores.items()}
    cos_norm = {song: score / max_cos for song, score in cosine_scores.items()}

    # Step 4: Combine scores with weighted average
    combined_scores = {}
    all_songs = set(co_norm.keys()) | set(cos_norm.keys())
    
    for song_name in all_songs:
        co_score = co_norm.get(song_name, 0.0)
        cos_score = cos_norm.get(song_name, 0.0)
        combined_scores[song_name] = alpha * co_score + (1 - alpha) * cos_score

    # Step 5: Sort and return top K
    top_combined = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"song": song_name, "score": score} for song_name, score in top_combined]


# Auto-initialize database on module import
# This runs once when the module is first imported, ensuring indexes and config
# are set up for all code that uses this module
configure_sqlite_once()
ensure_indexes_once()


if __name__ == "__main__":
    # When run directly, also ensure database is loaded
    create_db_and_load_mpd(DB_PATH)
    print("Database setup complete.")

    
    
