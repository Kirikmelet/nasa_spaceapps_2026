import json
import logging
import os
from typing import Literal

import dotenv
from fastapi import APIRouter, HTTPException
from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    AuthenticationError, OpenAI, PermissionDeniedError,
                    RateLimitError)
from pydantic import BaseModel, Field

dotenv.load_dotenv(override=True)

router = APIRouter(prefix="/api", tags=["mental-wellness"])

DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Created on first use, so a missing key doesn't stop the server from booting."""
    global _client
    if _client is None:
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise HTTPException(503, "DEEPSEEK_API_KEY is not set")
        _client = OpenAI(api_key=key, base_url="https://api.deepseek.com",
                         timeout=90.0, max_retries=2)
    return _client


class WellnessRequest(BaseModel):
    readings: list[dict] = Field(min_length=1, max_length=100)


class WellnessResponse(BaseModel):
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

# JSON mode needs the word "json" in the prompt plus an example of the shape you want.
JSON_FORMAT_HINT = """
Reply with a single JSON object and nothing else, in exactly this shape.

EXAMPLE JSON OUTPUT:
{
  "summary": "string, under 60 words",
  "observations": ["string", "string"],
  "guidance": ["string", "string"],
  "warnings": ["string"],
  "urgency": "normal | attention | urgent (choose exactly one)",
  "data_window": "string, e.g. the time range of the readings"
}
"""


def analyze_readings(astronaut_id: str, readings: list[dict]) -> WellnessResponse:
    if not readings:
        raise HTTPException(400, "No readings supplied")

    prompt = f"""
Analyze the following recent physiological readings for astronaut
{astronaut_id}.

Readings are supplied as JSON:

{json.dumps(readings, separators=(",", ":"))}

Provide a concise summary, observable patterns or changes, general wellness
guidance, any readings that may warrant professional attention, and an
urgency classification.

Do not infer psychological conditions from physiological readings.
"""

    try:
        for attempt in (1, 2):
            completion = get_client().chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION + JSON_FORMAT_HINT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=4096,
                temperature=0.2,
            )
            choice = completion.choices[0]
            if choice.finish_reason == "length":
                raise HTTPException(502, "The AI response was cut off, try again")
            try:
                if not choice.message.content:          # JSON mode can occasionally return nothing
                    raise ValueError("empty response")
                return WellnessResponse.model_validate_json(choice.message.content)
            except ValueError:                          # pydantic's ValidationError is a ValueError
                if attempt == 2:
                    raise
                logging.warning("Bad or empty JSON from the model, retrying once")

    except HTTPException:
        raise
    except RateLimitError:                      # keep before APIStatusError
        raise HTTPException(429, "AI rate limit reached, try again shortly")
    except APITimeoutError:                     # keep before APIConnectionError
        raise HTTPException(504, "The AI took too long to respond")
    except (AuthenticationError, PermissionDeniedError) as exc:
        logging.error("DeepSeek auth/permission error: %s", exc)
        raise HTTPException(502, "AI provider rejected the API key")
    except ValueError:
        logging.exception("Model output didn't match the schema")
        raise HTTPException(502, "The AI returned an unexpected format")
    except APIStatusError as exc:
        logging.error("DeepSeek %s: %s", exc.status_code, exc.response.text)
        if exc.status_code == 402:
            raise HTTPException(502, "AI account has insufficient balance")
        raise HTTPException(502, f"AI provider error ({exc.status_code})")
    except APIConnectionError:
        logging.exception("Could not reach DeepSeek")
        raise HTTPException(502, "AI provider unreachable")
    except Exception:
        logging.exception("Wellness analysis failed")
        raise HTTPException(502, "Wellness analysis failed")


@router.post("/astronauts/{astronaut_id}/mental-wellness", response_model=WellnessResponse)
def analyze_wellness(astronaut_id: str, request: WellnessRequest):
    return analyze_readings(astronaut_id, request.readings)
