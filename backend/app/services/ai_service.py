import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in the environment.")

client = genai.Client(api_key=GEMINI_API_KEY)


class AIService:
    """AI service using Google Gemini."""

    def __init__(self):
        self.client = client
        self.model = self.settings.GEMINI_MODEL

    async def generate_summary(self, transcript: str) -> str:
        prompt = f"""
You are an AI meeting assistant.

Analyze the following meeting transcript and create a concise, professional summary.

Include:
- Main topics discussed
- Important decisions
- Key conclusions
- Important context

Transcript:
{transcript}
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        return response.text or "Unable to generate summary."

    async def generate_action_items(self, transcript: str) -> list:
        prompt = f"""
Extract actionable tasks from the following meeting transcript.

Return ONLY a JSON array in this format:

[
    {{
        "description": "Task description",
        "assignee": "Person responsible or Unknown",
        "due_date": "Due date or Unknown"
    }}
]

If there are no action items, return [].

Transcript:
{transcript}
"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )

        return response.text or "[]"