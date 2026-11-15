

# geminiClient = GeminiClient()


import dotenv
import os
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


dotenv.load_dotenv()

router = APIRouter(prefix="/api", tags=["mental-wellness"])

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


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
"""


def analyze_readings(astronaut_id: str, readings: list[dict]):
    if not readings:
        raise HTTPException(400, "No readings supplied")

    prompt = f"""
Analyze the following recent physiological readings for astronaut
{astronaut_id}.

Readings are supplied as JSON:

    {json.dumps(readings, indent=2)}

Provide:
1. A concise summary.
2. Observable patterns or changes.
3. General wellness guidance.
4. Any readings or patterns that may warrant professional attention.
5. An urgency classification.

Do not infer psychological conditions from physiological readings.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=WellnessResponse,
                temperature=0.2,
                max_output_tokens=1200,
            ),
        )

        if response.parsed is not None:
            return response.parsed

        if response.text:
            return WellnessResponse.model_validate_json(response.text)

        raise HTTPException(502, "Gemini returned an empty response")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Wellness analysis failed: {exc}",
        )

@router.post("/astronauts/{astronaut_id}/mental-wellness", response_model=WellnessResponse)
def analyze_wellness(astronaut_id: str, request: WellnessRequest):
    return analyze_readings(astronaut_id, request.readings)

