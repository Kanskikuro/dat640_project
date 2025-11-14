"""Quick performance test for recommendation functions."""
import time
from db import (
    find_song_in_db,
    recommend_by_playlist_cosine,
    hybrid_recommend,
    recommend_songs,
    ensure_indexes_once,
    configure_sqlite_once,
)

def time_function(func, *args, **kwargs):
    """Time a function call and return result and elapsed time."""
    start = time.time()
    result = func(*args, **kwargs)
    elapsed = time.time() - start
    return result, elapsed

if __name__ == "__main__":
    print("Setting up database...")
    configure_sqlite_once()
    ensure_indexes_once()
    
    print("\nFinding seed songs...")
    song1 = find_song_in_db("Kendrick Lamar", "HUMBLE.")
    song2 = find_song_in_db("Eminem", "Lose Yourself")

    seed_songs = [s for s in [song1, song2] if s is not None]
    
    if not seed_songs:
        print("ERROR: No valid seed songs found.")
        exit(1)
    
    print(f"\nSeed songs ({len(seed_songs)}):")
    for s in seed_songs:
        print(f"  • {s['artist']} - {s['title']} (ID: {s['id']})")
    
    seed_ids = [s["id"] for s in seed_songs]
    
    print("\n" + "="*60)
    print("PERFORMANCE TEST")
    print("="*60)
    
    # Test 1: Co-occurrence
    print("\n1. Co-occurrence recommendations (10 songs)...")
    co_rec, co_time = time_function(
        recommend_songs, 
        [{"id": sid} for sid in seed_ids], 
        10
    )
    print(f"   ✓ Completed in {co_time:.2f} seconds")
    print(f"   Found {len(co_rec)} recommendations")
    
    # Test 2: Cosine similarity
    print("\n2. Cosine similarity recommendations (10 songs)...")
    cos_rec, cos_time = time_function(
        recommend_by_playlist_cosine,
        seed_ids,
        10
    )
    print(f"   ✓ Completed in {cos_time:.2f} seconds")
    print(f"   Found {len(cos_rec)} recommendations")
    
    # Test 3: Hybrid
    print("\n3. Hybrid recommendations (10 songs)...")
    hyb_rec, hyb_time = time_function(
        hybrid_recommend,
        seed_ids,
        10
    )
    print(f"   ✓ Completed in {hyb_time:.2f} seconds")
    print(f"   Found {len(hyb_rec)} recommendations")
    
    print("\n" + "="*60)
    print("TOTAL TIME: {:.2f} seconds".format(co_time + cos_time + hyb_time))
    print("="*60)
    
    # Show sample results
    print("\n📊 Sample Hybrid Results:")
    for i, row in enumerate(hyb_rec[:5], 1):
        print(f"  {i}. {row['song']} (score: {row['score']:.3f})")
