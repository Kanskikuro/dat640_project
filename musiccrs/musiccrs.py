"""MusicCRS conversational agent."""
import os
import json
import ollama
from dialoguekit.core.annotated_utterance import AnnotatedUtterance
from dialoguekit.core.dialogue_act import DialogueAct
from dialoguekit.core.intent import Intent
from dialoguekit.core.slot_value_annotation import SlotValueAnnotation
from dialoguekit.core.utterance import Utterance
from dialoguekit.participant.agent import Agent
from dialoguekit.participant.participant import DialogueParticipant
from dialoguekit.platforms import FlaskSocketPlatform
from config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_API_KEY, DB_PATH

class MusicCRS(Agent):
    def __init__(self, use_llm: bool = True):
        """Initialize MusicCRS agent."""
        super().__init__(id="MusicCRS")

        if use_llm:
            self._llm = ollama.Client(
                host=OLLAMA_HOST,
                headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
            )
        else:
            self._llm = None

        self._playlist = []  # Stores the current playlist

    # --- playlist functions ---
    
    def add_to_playlist(self, artist_song: str) -> None:
        # TODO waiting for db logic
        
        database = self._load_or_create_db()
        if artist_song not in database:
            print(f"'{artist_song}' not found in database.")
            return
        song = database[artist_song]
        if song in self._playlist:
            print(f"'{song}' is already in the playlist.")
            return
        self._playlist.append(database[artist_song])
        print(f"Added '{song}' to playlist.")
            
    def remove_from_playlist(self, song: str) -> None:
        if song not in self._playlist:
            print(f"Song '{song}' is not in the playlist.")
        self._playlist.remove(song)
        print(f"Removed '{song}' from playlist.")
        
    def view_playlist(self) -> list[str]:
        return self._playlist
    
    def clear_playlist(self) -> None:
        self._playlist.clear()

    # --- Dialogue functions ---

    def welcome(self) -> None:
        """Sends the agent's welcome message."""
        utterance = AnnotatedUtterance(
            "Hello, I'm MusicCRS. What are you in the mood for?",
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def goodbye(self) -> None:
        """Quits the conversation."""
        utterance = AnnotatedUtterance(
            "It was nice talking to you. Bye",
            dialogue_acts=[DialogueAct(intent=self.stop_intent)],
            participant=DialogueParticipant.AGENT,
        )
        self._dialogue_connector.register_agent_utterance(utterance)

    def receive_utterance(self, utterance: Utterance) -> None:
        """Gets called each time there is a new user utterance.

        For now the agent only understands specific command.

        Args:
            utterance: User utterance.
        """
        response = ""
        dialogue_acts = []
        if utterance.text.startswith("/info"):
            response = self._info()
        elif utterance.text.startswith("/ask_llm "):
            prompt = utterance.text[9:]
            response = self._ask_llm(prompt)
        elif utterance.text.startswith("/options"):
            options = [
                "Play some jazz music",
                "Recommend me some pop songs",
                "Create a workout playlist",
            ]
            response = self._options(options)
            dialogue_acts = [
                DialogueAct(
                    intent=_INTENT_OPTIONS,
                    annotations=[
                        SlotValueAnnotation("option", option) for option in options
                    ],
                )
            ]
        elif utterance.text == "/quit":
            self.goodbye()
            return
        else:
            response = "I'm sorry, I don't understand that command."

        self._dialogue_connector.register_agent_utterance(
            AnnotatedUtterance(
                response,
                participant=DialogueParticipant.AGENT,
                dialogue_acts=dialogue_acts,
            )
        )

    # --- Response handlers ---

    def _info(self) -> str:
        """Gives information about the agent."""
        return "I am MusicCRS, a conversational recommender system for music."

    def _ask_llm(self, prompt: str) -> str:
        """Calls a large language model (LLM) with the given prompt.

        Args:
            prompt: Prompt to send to the LLM.

        Returns:
            Response from the LLM.
        """
        if not self._llm:
            return "The agent is not configured to use an LLM"

        llm_response = self._llm.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={
                "stream": False,
                "temperature": 0.7,  # optional: controls randomness
                "max_tokens": 100,  # optional: limits the length of the response
            },
        )

        return f"LLM response: {llm_response['response']}"

    def _options(self, options: list[str]) -> str:
        """Presents options to the user."""
        return (
            "Here are some options:\n<ol>\n"
            + "\n".join([f"<li>{option}</li>" for option in options])
            + "</ol>\n"
        )

    # --- database functions ---
    
    def _load_or_create_db(self):
        # TODO  wait for confirmation email regarding db being folder or a db
        """Load the database, create if not exist."""
        # if not os.path.exists(DB_PATH):
        #     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        #     # Create an empty database
        #     with open(DB_PATH, "w") as f:
        #         json.dump({}, f)
        #     print(f"Created new database at {DB_PATH}")
        #     return {}

        # with open(DB_PATH, "r") as f:
        #     db = json.load(f)
        # print(f"Loaded database with {len(db)} tracks")
        # return db
        ...
if __name__ == "__main__":
    platform = FlaskSocketPlatform(MusicCRS)
    platform.start()
    platform.start()
