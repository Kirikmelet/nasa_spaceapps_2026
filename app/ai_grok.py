import json
import logging
import os
from typing import Literal

import dotenv
from fastapi import APIRouter, HTTPException
from groq import (APIConnectionError, APIStatusError, APITimeoutError, Groq,
                  PermissionDeniedError, RateLimitError)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

dotenv.load_dotenv(override=True)   # a stale key exported in your shell would otherwise win

router = APIRouter(prefix="/api", tags=["mental-wellness"])

GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
_client: Groq | None = None


def get_client() -> Groq:
    """Created on first use, so a missing key doesn't stop the server from booting."""
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise HTTPException(503, "GROQ_API_KEY is not set")
        _client = Groq(api_key=key, timeout=60.0, max_retries=3)  # SDK retries 429/5xx with backoff
    return _client


class WellnessRequest(BaseModel):
    readings: list[dict] = Field(min_length=1, max_length=100)


class WellnessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")   # adds additionalProperties:false, which strict mode requires

    summary: str
    observations: list[str]
    guidance: list[str]
    warnings: list[str]
    urgency: Literal["normal", "attention", "urgent"]
    data_window: str


SYSTEM_INSTRUCTION = """
You are a wellness information assistant in an astronaut telemetry
demonstration application.

You receive timestamped physiological readings. Your job is to explain
observable patterns and provide general, conservative wellness guidance.

IMPORTANT SAFETY RULES:

- You are not a doctor and must not diagnose medical or mental health
  conditions.
- Vital signs alone cannot establish someone's emotional or mental state.
- Never claim that a person has anxiety, depression, stress, or another
  psychological condition based only on vital signs.
- Do not invent readings, trends, symptoms, or medical history.
- Distinguish observed data from possible explanations.
- Mention when there is insufficient data to draw a conclusion.
- Do not recommend medication, dosages, or treatment changes.
- Do not tell someone to ignore concerning symptoms.
- If the readings appear potentially concerning, recommend appropriate
  professional assessment without pretending to make a diagnosis.
- If the user reports severe symptoms such as chest pain, severe
  difficulty breathing, fainting, or confusion, advise emergency care.
- Keep guidance practical, calm, and concise.

The application is educational and experimental. Your response is not
a substitute for medical evaluation.

Keep it brief: summary under 60 words, at most 4 items in each list,
each item under 25 words. Never repeat a phrase.
"""


def analyze_readings(astronaut_id: str, readings: list[dict]) -> WellnessResponse:
    if not readings:
        raise HTTPException(400, "No readings supplied")

    prompt = f"""
Analyze the following recent physiological readings for astronaut
{astronaut_id}.

Readings are supplied as JSON:

{json.dumps(readings, separators=(",", ":"))}

Provide:
1. A concise summary.
2. Observable patterns or changes.
3. General wellness guidance.
4. Any readings or patterns that may warrant professional attention.
5. An urgency classification.

Do not infer psychological conditions from physiological readings.
"""

    try:
        completion = get_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "wellness_response",
                    "strict": True,
                    "schema": WellnessResponse.model_json_schema(),
                },
            },
            temperature=0.2,
            max_completion_tokens=4096,   # gpt-oss spends part of this on reasoning
            reasoning_effort="low",       # faster, and fewer tokens burned thinking
        )
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise HTTPException(502, "The AI response was cut off, try again")
        if not choice.message.content:
            raise HTTPException(502, "The model returned an empty response")
        return WellnessResponse.model_validate_json(choice.message.content)

    except HTTPException:
        raise
    except RateLimitError:                      # subclass of APIStatusError, so keep it first
        raise HTTPException(429, "AI rate limit reached, try again shortly")
    except APITimeoutError:                     # subclass of APIConnectionError, so keep it first
        raise HTTPException(504, "The AI took too long to respond")
    except PermissionDeniedError as exc:
        logging.error("Groq 403: %s", exc)
        raise HTTPException(502, "AI provider denied access. Check the API key and model access.")
    except ValidationError:
        logging.exception("Model returned JSON that didn't match the schema")
        raise HTTPException(502, "The AI returned an unexpected format")
    except (APIConnectionError, APIStatusError):
        logging.exception("Groq request failed")
        raise HTTPException(502, "AI provider error")
    except Exception:
        logging.exception("Wellness analysis failed")
        raise HTTPException(502, "Wellness analysis failed")


@router.post("/astronauts/{astronaut_id}/mental-wellness", response_model=WellnessResponse)
def analyze_wellness(astronaut_id: str, request: WellnessRequest):
    return analyze_readings(astronaut_id, request.readings)
