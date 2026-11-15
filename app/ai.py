# To get insight from data
#
from google import genai

from dotenv import load_dotenv

load_dotenv()



class GeminiClient():
    client: genai.Client
    model: str

    def __init__(self, model: str = "gemini-3.8-flash"):
        self.client = genai.Client()
        self.model = model
        pass

    @property
    def interactions(self) -> genai.interactions:
        return self.client.interactions

    def query(self, query: str) -> str:
        interaction = self.interactions.create(
            model=self.model,
            generation_config={
                "thinking_level": "low"
            },
            input=query
        )
        return interaction.output_text

    pass





geminiClient = GeminiClient()
