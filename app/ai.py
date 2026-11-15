# To get insight from data


from google import genai
from typing import BaseModel, Optional

from dotenv import load_dotenv

load_dotenv()


class _InsightCache(BaseModel):
    ts: float
    text: Optional[str]
    at: Optional[float]


_insight_cache: _InsightCache = {"ts": 0.0, "text": None, "at": None}
INSIGHT_COOLDOWN = 30  # seconds


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

    # def query_with_insight(self, query: str,
    #                        insight_cache: _InsightCache) -> str:
    #     now: float = time.time()
    #     error: Optional[str] = None

    #     if insight_cache.text and now - insight_cache.ts < INSIGHT_COOLDOWN:
    #         text, cached = insight_cache.text, True
    #     else:
    #         try:
    #             text = self.query(query)
    #             if not text:
    #                 raise ValueError("Model returned error")
    #             cached = False
    #         except Exception as e:
    #             text, error = None, str(e)
    #     return text
    pass


geminiClient = GeminiClient()
