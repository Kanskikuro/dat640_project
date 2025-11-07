import os
import json
import sqlite3
from threading import Lock
from config import DB_PATH, MPD_DATA
import numpy as np
from collections import defaultdict

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

# --------------------------- Embedding-based recommendations -----------

def add_embedding_column():
    """Ensure songs and playlists tables have an embedding column (JSON text)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Check if column exists
    cur.execute("PRAGMA table_info(songs)")
    columns = [col[1] for col in cur.fetchall()]
    if "embedding" not in columns:
        cur.execute("ALTER TABLE songs ADD COLUMN embedding TEXT")
        print("Added 'embedding' column to songs.")
    else:
        print("'embedding' column already exists.")
    conn.commit()
    conn.close()

def store_song_embedding(song_id: int, embedding: np.ndarray):
    """Store song embedding as JSON string."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE songs SET embedding = ? WHERE id = ?",
        (json.dumps(embedding.tolist()), song_id)
    )
    conn.commit()
    conn.close()

def compute_playlist_embedding(pid: int):
    """Compute average embedding of all songs in a playlist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.embedding
        FROM songs s
        JOIN playlist_songs ps ON s.id = ps.song_id
        WHERE ps.playlist_id = ?
    """, (pid,))
    rows = [json.loads(r[0]) for r in cur.fetchall() if r[0]]
    conn.close()
    if not rows:
        return None
    avg = np.mean(np.array(rows), axis=0)
    return avg / np.linalg.norm(avg)

def recommend_by_cosine(seed_song_ids: list[int], limit: int = 10):
    """Recommend songs similar to seed songs using cosine similarity of embeddings."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Get seed embeddings
    placeholders = ",".join("?" * len(seed_song_ids))
    cur.execute(f"SELECT embedding FROM songs WHERE id IN ({placeholders})", seed_song_ids)
    seed_embeds = [json.loads(r[0]) for r in cur.fetchall() if r[0]]
    if not seed_embeds:
        conn.close()
        return []
    # Compute centroid of seeds
    centroid = np.mean(np.array(seed_embeds), axis=0)
    centroid /= np.linalg.norm(centroid)
    # Fetch candidate embeddings
    cur.execute("SELECT id, embedding FROM songs WHERE embedding IS NOT NULL")
    results = []
    for sid, emb_json in cur.fetchall():
        emb = np.array(json.loads(emb_json))
        sim = float(np.dot(centroid, emb) / (np.linalg.norm(emb) + 1e-9))
        results.append((sid, sim))
    conn.close()
    # Sort by similarity
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]

def hybrid_recommend(seed_song_ids: list[int], top_k: int = 10, alpha: float = 0.5):
    """
    Hybrid recommender using:
      - Playlist co-occurrence frequency
      - Cosine similarity of embeddings

    Args:
        seed_song_ids: list of seed song IDs
        top_k: number of recommendations to return
        alpha: weight for co-occurrence (0.0 = only cosine, 1.0 = only co-occurrence)

    Returns:
        List of dicts: {"id", "artist", "title", "score"}
    """
    if not seed_song_ids:
        return []

    # --- Step 1: Get co-occurrence recommendations ---
    co_songs_info, co_data = recommend_songs(
        [{"id": sid} for sid in seed_song_ids],
        limit=top_k * 5  # get more to allow reranking
    )

    if not co_data:
        co_songs_info = {}
        co_data = []

    co_scores = {song_id: freq for song_id, freq in co_data}

    # --- Step 2: Get cosine similarity recommendations ---
    cosine_results = recommend_by_cosine(seed_song_ids, limit=top_k * 5)
    cosine_scores = {song_id: score for song_id, score in cosine_results}

    # --- Step 3: Combine scores ---
    combined_scores = {}
    for song_id in set(co_scores.keys()) | set(cosine_scores.keys()):
        co_score = co_scores.get(song_id, 0)
        cos_score = cosine_scores.get(song_id, 0)
        # Normalize co-occurrence (divide by max)
        max_co = max(co_scores.values()) if co_scores else 1
        norm_co = co_score / max_co
        # Combine
        combined = alpha * norm_co + (1 - alpha) * cos_score
        combined_scores[song_id] = combined

    # --- Step 4: Get song metadata ---
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in combined_scores)
    cur.execute(f"SELECT id, artist, title FROM songs WHERE id IN ({placeholders})", list(combined_scores.keys()))
    songs_meta = {row[0]: {"id": row[0], "artist": row[1], "title": row[2]} for row in cur.fetchall()}
    conn.close()

    # --- Step 5: Return top_k sorted by combined score ---
    top_songs = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {**songs_meta[song_id], "score": combined_scores[song_id]}
        for song_id, _ in top_songs
    ]
    
    
# ----------- Evaluation metrics -----------
    
def precision_at_k(recommended: list[int], ground_truth: list[int], k: int):
    recommended = recommended[:k]
    hits = sum(1 for r in recommended if r in ground_truth)
    return hits / k

def recall_at_k(recommended: list[int], ground_truth: list[int], k: int):
    recommended = recommended[:k]
    hits = sum(1 for r in recommended if r in ground_truth)
    return hits / len(ground_truth) if ground_truth else 0.0

def average_precision(recommended: list[int], ground_truth: list[int], k: int):
    recommended = recommended[:k]
    hits = 0
    score = 0.0
    for i, r in enumerate(recommended, start=1):
        if r in ground_truth:
            hits += 1
            score += hits / i
    return score / min(len(ground_truth), k) if ground_truth else 0.0

def ndcg_at_k(recommended: list[int], ground_truth: list[int], k: int):
    recommended = recommended[:k]
    dcg = 0.0
    idcg = sum(1 / np.log2(i+1) for i in range(1, min(len(ground_truth), k)+1))
    if idcg == 0:
        return 0.0
    for i, r in enumerate(recommended, start=1):
        if r in ground_truth:
            dcg += 1 / np.log2(i+1)
    return dcg / idcg

def generate_seed_playlists_from_db(sample_size: int = 50, seed_per_playlist: int = 2):
    """
    Create pseudo-ground-truth from playlists in DB.
    
    Args:
        sample_size: Number of playlists to sample
        seed_per_playlist: Number of songs to use as seeds in each playlist

    Returns:
        List of dicts: {"seed_song_ids": [...], "ground_truth": [...]}
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Get random playlists with enough songs
    cur.execute(f"""
        SELECT pid
        FROM playlists
        WHERE num_tracks > {seed_per_playlist}
        ORDER BY RANDOM()
        LIMIT {sample_size}
    """)
    playlists = [row[0] for row in cur.fetchall()]
    
    seed_playlists = []
    for pid in playlists:
        cur.execute("""
            SELECT song_id
            FROM playlist_songs
            WHERE playlist_id = ?
            ORDER BY pos ASC
        """, (pid,))
        songs = [row[0] for row in cur.fetchall()]
        if len(songs) <= seed_per_playlist:
            continue
        seed_ids = songs[:seed_per_playlist]
        ground_truth = songs[seed_per_playlist:]
        seed_playlists.append({
            "seed_song_ids": seed_ids,
            "ground_truth": ground_truth
        })
    conn.close()
    return seed_playlists

def test_recommenders(seed_playlists: list[dict], k: int = 10, alpha: float = 0.5):
    """
    Evaluate co-occurrence, cosine similarity, and hybrid recommenders.

    Args:
        seed_playlists: List of dicts {"seed_song_ids": [id1, id2], "ground_truth": [id3, ...]}
        k: Top-K recommendations
        alpha: Weight for hybrid
    """
    metrics = defaultdict(lambda: defaultdict(list))

    for pl in seed_playlists:
        seed_ids = pl["seed_song_ids"]
        ground_truth = pl["ground_truth"]

        # Co-occurrence
        co_info, co_data = recommend_songs([{"id": sid} for sid in seed_ids], limit=k)
        co_recs = [sid for sid, freq in co_data]

        # Cosine
        cos_recs_data = recommend_by_cosine(seed_ids, limit=k)
        cos_recs = [sid for sid, score in cos_recs_data]

        # Hybrid
        hybrid_recs_data = hybrid_recommend(seed_ids, top_k=k, alpha=alpha)
        hybrid_recs = [r["id"] for r in hybrid_recs_data]

        # Compute metrics
        for name, recs in [("co_occurrence", co_recs), ("cosine", cos_recs), ("hybrid", hybrid_recs)]:
            metrics[name]["precision"].append(precision_at_k(recs, ground_truth, k))
            metrics[name]["recall"].append(recall_at_k(recs, ground_truth, k))
            metrics[name]["map"].append(average_precision(recs, ground_truth, k))
            metrics[name]["ndcg"].append(ndcg_at_k(recs, ground_truth, k))

    # Aggregate results
    results = {}
    for name, m in metrics.items():
        results[name] = {metric: np.mean(values) for metric, values in m.items()}

    return results

def test_recommenders_auto(sample_size: int = 50, k: int = 10, alpha: float = 0.5):
    """
    Test recommenders using pseudo-ground-truth generated from playlists.
    """
    seed_playlists = generate_seed_playlists_from_db(sample_size=sample_size)
    return test_recommenders(seed_playlists, k=k, alpha=alpha)

if __name__ == "__main__":
    configure_sqlite_once()
    ensure_indexes_once()
    create_db_and_load_mpd(DB_PATH)
    print("Database setup complete.")
    
    results = test_recommenders_auto(sample_size=50, k=10, alpha=0.5)
    for recommender, scores in results.items():
        print(f"--- {recommender} ---")
        for metric, value in scores.items():
            print(f"{metric}: {value:.4f}")
    
    
