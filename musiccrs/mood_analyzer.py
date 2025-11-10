# musiccrs/mood_analyzer.py
"""
R7.1: Mood and personality-aware recommendation system.
Uses SamLowe/roberta-base-go_emotions for emotion detection.
"""

from transformers import pipeline
from collections import Counter
import re

class MoodAnalyzer:
    """Analyzes user mood from text using emotion detection."""
    
    def __init__(self):
        """Initialize the emotion detection model."""
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the RoBERTa emotion detection model."""
        try:
            print("🔄 Loading emotion detection model (SamLowe/roberta-base-go_emotions)...")
            self.model = pipeline(
                "text-classification",
                model="SamLowe/roberta-base-go_emotions",
                top_k=None,  # Get all emotion scores
                device=-1  # Use CPU
            )
            print("✅ Emotion detection model loaded!")
        except Exception as e:
            print(f"⚠️ Failed to load emotion model: {e}")
            self.model = None
    
    def analyze_emotion(self, text: str) -> dict:
        """Analyze emotions in user text.
        
        Args:
            text: User input text
            
        Returns:
            dict with:
                - primary_emotion: Top emotion
                - emotions: List of {label, score} dicts
                - music_mood: Mapped music mood
        """
        if not self.model or not text:
            return {
                "primary_emotion": "neutral",
                "emotions": [],
                "music_mood": "neutral"
            }
        
        try:
            # Get emotion predictions
            results = self.model(text)[0]
            
            # Sort by score
            results.sort(key=lambda x: x['score'], reverse=True)
            
            # Get primary emotion
            primary = results[0]['label']
            
            # Map to music mood
            music_mood = self._emotion_to_mood(primary, results)
            
            return {
                "primary_emotion": primary,
                "emotions": results[:5],  # Top 5 emotions
                "music_mood": music_mood
            }
        except Exception as e:
            print(f"⚠️ Emotion analysis failed: {e}")
            return {
                "primary_emotion": "neutral",
                "emotions": [],
                "music_mood": "neutral"
            }
    
    def _emotion_to_mood(self, primary_emotion: str, all_emotions: list) -> str:
        """Map detected emotions to music moods.
        
        Args:
            primary_emotion: Top emotion
            all_emotions: All emotion scores
            
        Returns:
            Music mood keyword
        """
        # Emotion to mood mapping
        mood_map = {
            # Positive emotions
            "joy": "happy",
            "amusement": "fun",
            "excitement": "energetic",
            "admiration": "uplifting",
            "approval": "positive",
            "caring": "warm",
            "gratitude": "grateful",
            "love": "romantic",
            "optimism": "hopeful",
            "pride": "confident",
            "relief": "calm",
            
            # Negative emotions
            "anger": "aggressive",
            "annoyance": "intense",
            "disappointment": "melancholic",
            "disapproval": "dark",
            "disgust": "edgy",
            "embarrassment": "introspective",
            "fear": "anxious",
            "grief": "sad",
            "nervousness": "tense",
            "remorse": "regretful",
            "sadness": "sad",
            
            # Neutral/Mixed
            "confusion": "atmospheric",
            "curiosity": "exploratory",
            "desire": "passionate",
            "realization": "reflective",
            "surprise": "dynamic",
            "neutral": "neutral"
        }
        
        return mood_map.get(primary_emotion, "neutral")
    
    def get_mood_keywords(self, mood_data: dict) -> list:
        """Get search keywords based on detected mood.
        
        Args:
            mood_data: Result from analyze_emotion()
            
        Returns:
            List of keywords for searching
        """
        mood = mood_data.get("music_mood", "neutral")
        primary_emotion = mood_data.get("primary_emotion", "neutral")
        
        # Mood-specific keywords
        keyword_map = {
            "happy": ["upbeat", "cheerful", "joyful", "fun", "positive"],
            "fun": ["party", "dance", "energetic", "upbeat"],
            "energetic": ["upbeat", "fast", "energetic", "powerful"],
            "uplifting": ["inspiring", "motivational", "uplifting", "positive"],
            "romantic": ["love", "romantic", "emotional", "intimate"],
            "sad": ["sad", "melancholic", "emotional", "slow"],
            "melancholic": ["melancholic", "sad", "emotional", "moody"],
            "calm": ["calm", "relaxing", "peaceful", "chill"],
            "aggressive": ["aggressive", "intense", "powerful", "heavy"],
            "intense": ["intense", "powerful", "dramatic", "dark"],
            "dark": ["dark", "moody", "atmospheric", "heavy"],
            "neutral": ["chill", "relaxing", "smooth"]
        }
        
        return keyword_map.get(mood, ["chill", "smooth"])


# Singleton instance
mood_analyzer = MoodAnalyzer()