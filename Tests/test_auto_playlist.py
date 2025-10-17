#!/usr/bin/env python3
"""Test script for the auto playlist feature (R4.4)."""

import sys
import time
sys.path.insert(0, 'musiccrs')

from db import search_tracks_by_keywords, configure_sqlite_once, ensure_indexes_once

def test_search_performance():
    """Test the database search performance."""
    print("=" * 60)
    print("Testing database search performance...")
    print("=" * 60)
    
    configure_sqlite_once()
    ensure_indexes_once()
    
    test_cases = [
        ["love", "sad"],
        ["energetic", "gym", "workout"],
        ["calm", "relaxing", "sleep"],
        ["rock", "metal"],
        ["jazz", "smooth"]
    ]
    
    for keywords in test_cases:
        start = time.time()
        results = search_tracks_by_keywords(keywords, limit=15)
        elapsed = time.time() - start
        
        print(f"\nKeywords: {keywords}")
        print(f"Found: {len(results)} tracks in {elapsed:.3f}s")
        if results:
            print(f"Sample: {results[0]['artist']} - {results[0]['title']} (popularity: {results[0]['popularity']})")

def test_keyword_extraction():
    """Test keyword extraction from descriptions."""
    print("\n" + "=" * 60)
    print("Testing keyword extraction (no LLM)...")
    print("=" * 60)
    
    test_descriptions = [
        "sad love songs",
        "energetic music for gym session",
        "calm and relaxing music for studying",
        "upbeat party music",
        "emotional ballads"
    ]
    
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as'}
    
    for desc in test_descriptions:
        words = desc.lower().split()
        keywords = [w.strip() for w in words if len(w) > 2 and w not in stop_words]
        
        print(f"\nDescription: '{desc}'")
        print(f"Keywords: {keywords}")

def test_full_workflow():
    """Test the complete auto playlist workflow."""
    print("\n" + "=" * 60)
    print("Testing full auto playlist workflow (no LLM)...")
    print("=" * 60)
    
    configure_sqlite_once()
    ensure_indexes_once()
    
    description = "sad love songs"
    
    print(f"\nDescription: '{description}'")
    
    # Step 1: Extract keywords (simple word splitting)
    start_total = time.time()
    start = time.time()
    
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as'}
    words = description.lower().split()
    keywords = [w.strip() for w in words if len(w) > 2 and w not in stop_words]
    
    elapsed_extraction = time.time() - start
    print(f"1. Keywords extracted: {keywords} ({elapsed_extraction:.3f}s)")
    
    # Step 2: Search database
    start = time.time()
    tracks = search_tracks_by_keywords(keywords, limit=15)
    elapsed_search = time.time() - start
    print(f"2. Found {len(tracks)} tracks ({elapsed_search:.3f}s)")
    
    elapsed_total = time.time() - start_total
    print(f"\nTotal time: {elapsed_total:.3f}s")
    
    if elapsed_total <= 2.0:
        print("✅ Excellent performance (< 2 seconds)")
    elif elapsed_total <= 5.0:
        print("✅ Performance target met (< 5 seconds)")
    else:
        print(f"⚠️  Performance target missed ({elapsed_total:.3f}s > 5.0s)")
    
    # Show sample results
    print("\nSample tracks:")
    for i, track in enumerate(tracks[:5], 1):
        print(f"{i}. {track['artist']} - {track['title']} (popularity: {track['popularity']})")

if __name__ == "__main__":
    test_search_performance()
    test_keyword_extraction()
    test_full_workflow()
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)
