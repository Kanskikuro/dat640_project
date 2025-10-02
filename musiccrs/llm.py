# musiccrs/llm.py
import ollama
from config import OLLAMA_HOST, OLLAMA_API_KEY, OLLAMA_MODEL


class LLMClient:
    def __init__(self):
        self.client = ollama.Client(
            host=OLLAMA_HOST,
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
        )

    def ask(self, prompt: str) -> str:
        resp = self.client.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={"stream": False, "temperature": 0.7, "max_tokens": 100},
        )
        return resp["response"]
