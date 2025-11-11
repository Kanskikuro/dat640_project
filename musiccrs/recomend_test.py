from db import (
    find_song_in_db,
    recommend_by_playlist_cosine,
    hybrid_recommend,
    recommend_songs,
)

if __name__ == "__main__":
    song1 = find_song_in_db("Kendrick Lamar", "HUMBLE.")
    song2 = find_song_in_db("Eminem", "Lose Yourself")

    # Filter out None results
    seed_songs = [s for s in [song1, song2] if s is not None]

    if not seed_songs:
        print("No valid seed songs found.")
    else:
        print("Seed songs:")
        for s in seed_songs:
            print(f" - {s['artist']} : {s['title']} (id: {s['id']})")
        print("\nGenerating recommendations...\n")
        
        co_rec = recommend_songs([{"id": s["id"]} for s in seed_songs], 10)
        print("co-occurrence recommendation:")
        for row in co_rec:
            print(f" - {row['song']} (score: {row['score']})")

        cos_rec = recommend_by_playlist_cosine([s["id"] for s in seed_songs])
        print("\ncosine similarity recommendation:")
        for row in cos_rec:
            print(f" - {row['song']} (score: {row['score']:.3f})")

        hyb_rec = hybrid_recommend([s["id"] for s in seed_songs])
        print("\nhybrid recommendation:")
        for row in hyb_rec:
            print(f" - {row['song']} (score: {row['score']:.3f})")  




""" recommend_songs
{1382: 'Kendrick Lamar : DNA.',
 1386: 'Future : Mask Off',
 1194: 'Lil Uzi Vert : XO TOUR Llif3',
 3043: 'Post Malone : Congratulations',
 537: 'Travis Scott : goosebumps'}
"""