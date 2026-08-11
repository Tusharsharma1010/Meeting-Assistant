from typing import Dict, List, Optional
import asyncio
import json
import logging
from datetime import datetime

from google import genai
from google.genai import types

from ..config.settings import get_settings
from .rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


class EnhancedAIService:
    """AI service for meeting analysis using Google Gemini."""

    def __init__(self):
        # Load application settings
        self.settings = get_settings()

        # Get Gemini API key from settings
        self.api_key = self.settings.GEMINI_API_KEY

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to backend/.env"
            )

        # Initialize Gemini client
        self.client = genai.Client(
            api_key=self.api_key
        )

        # Get Gemini model from settings
        self.model = self.settings.GEMINI_MODEL

        # Rate limiter
        self.rate_limiter = RateLimiter(
            self.settings.RATE_LIMIT_PER_MIN
        )

        # Usage statistics
        self.total_tokens_used = 0
        self.total_cost = 0.0

        logger.info(
            f"EnhancedAIService initialized with model: {self.model}"
        )

    # ============================================================
    # Progressive Summary
    # ============================================================

    async def generate_progressive_summary(
        self,
        recent_transcripts: List[str]
    ) -> Optional[Dict]:
        """Generate all live meeting insights in one Gemini request."""

        if not recent_transcripts:
            logger.info(
                "No recent transcripts available for progressive summary."
            )
            return {
                "summary": "",
                "topics": [],
                "decisions": [],
                "action_items": [],
                "questions": []
            }

        transcript = " ".join(
            text.strip()
            for text in recent_transcripts
            if text and text.strip()
        )

        if not transcript:
            logger.info(
                "Recent transcripts contained no usable text."
            )
            return {
                "summary": "",
                "topics": [],
                "decisions": [],
                "action_items": [],
                "questions": []
            }

        messages = [
            {
                "role": "system",
                "content": """
You are a real-time meeting assistant.

Analyze the recent meeting discussion and generate ALL of the following
in a single response:

1. A concise 2-3 sentence summary.
2. Key topics discussed.
3. Decisions that were made.
4. Action items identified.
5. 3-5 useful follow-up questions.

Rules:
- Only include information supported by the transcript.
- Do not invent names, dates, decisions, or tasks.
- If there are no decisions, return an empty array.
- If there are no action items, return an empty array.
- If there are no clear topics, return an empty array.
- If follow-up questions are not useful yet, return an empty array.
- Action items must contain:
  description, assigned_to, due_date, priority.
- Keep the summary concise.
- Do not use Markdown.

Return ONLY valid JSON with exactly these keys:

{
    "summary": "A concise 2-3 sentence summary of the discussion",
    "topics": ["topic 1", "topic 2"],
    "decisions": ["decision 1", "decision 2"],
    "action_items": [
        {
            "description": "Task description",
            "assigned_to": "Person or null",
            "due_date": "Date or null",
            "priority": "high, medium, low, or null"
        }
    ],
    "questions": [
        "Follow-up question 1",
        "Follow-up question 2"
    ]
}
"""
            },
            {
                "role": "user",
                "content": (
                    "Recent meeting discussion:\n\n"
                    f"{transcript}"
                )
            }
        ]

        try:
            result = await self.process_with_retry(messages)

            if not result:
                logger.warning(
                    "Progressive summary: Gemini returned no response."
                )
                return None

            logger.info(
                "Progressive summary raw Gemini response: %s",
                result
            )

            parsed = self._parse_json(result)

            if not isinstance(parsed, dict):
                logger.error(
                    "Progressive summary: expected a JSON object."
                )
                return None

            # Normalize the response so the frontend always receives
            # the same shape.
            action_items = parsed.get("action_items", [])
            if not isinstance(action_items, list):
                action_items = [action_items] if action_items else []

            questions = parsed.get("questions", [])
            if not isinstance(questions, list):
                questions = [questions] if questions else []

            topics = parsed.get("topics", [])
            if not isinstance(topics, list):
                topics = [topics] if topics else []

            decisions = parsed.get("decisions", [])
            if not isinstance(decisions, list):
                decisions = [decisions] if decisions else []

            return {
                "summary": parsed.get("summary", ""),
                "topics": topics,
                "decisions": decisions,
                "action_items": action_items,
                "questions": questions
            }

        except Exception as e:
            logger.exception(
                "Error generating progressive summary: %s",
                e
            )
            return None

    # ============================================================
    # Follow-up Questions
    # ============================================================

    async def generate_followup_questions(
        self,
        context: str
    ) -> Optional[List[str]]:
        """Generate relevant follow-up questions."""

        messages = [
            {
                "role": "system",
                "content": """
You are an attentive meeting participant.

Based on the discussion context, generate 3-5 insightful follow-up
questions that would help clarify or expand on key points.

Focus on questions that:
- Clarify ambiguous points
- Probe deeper into important topics
- Address potential gaps
- Help with next steps

Return ONLY a valid JSON array of strings.

Example:

[
    "What is the expected deadline for this task?",
    "Who will be responsible for implementation?"
]
"""
            },
            {
                "role": "user",
                "content": f"Discussion context:\n\n{context}"
            }
        ]

        result = await self.process_with_retry(messages)

        if not result:
            return None

        parsed = self._parse_json(result)

        if isinstance(parsed, list):
            return parsed

        return None

    # ============================================================
    # Action Items
    # ============================================================

    async def extract_action_items(
        self,
        transcript: str
    ) -> Optional[List[Dict]]:
        """Extract action items from the transcript."""

        messages = [
            {
                "role": "system",
                "content": """
You are a meeting assistant focusing on action items.

Analyze the transcript and extract actionable tasks.

For each action item include:
- description
- assigned_to
- due_date
- priority

Return ONLY a valid JSON array.

Example:

[
    {
        "description": "Prepare the project report",
        "assigned_to": "Rahul",
        "due_date": "Friday",
        "priority": "high"
    }
]

If there are no action items, return [].
"""
            },
            {
                "role": "user",
                "content": f"Meeting transcript:\n\n{transcript}"
            }
        ]

        result = await self.process_with_retry(messages)

        if not result:
            return None

        parsed = self._parse_json(result)

        if isinstance(parsed, list):
            return parsed

        return None

    # ============================================================
    # Final Meeting Summary
    # ============================================================

    async def generate_final_summary(
        self,
        full_transcript: str
    ) -> Optional[Dict]:
        """Generate a comprehensive final meeting summary."""

        messages = [
            {
                "role": "system",
                "content": """
You are a professional meeting summarizer.

Create a comprehensive meeting summary containing:

1. Executive summary
2. Main discussion points
3. Decisions made
4. Action items
5. Key takeaways
6. Follow-up items

Return valid JSON with exactly these keys:

{
    "executive_summary": "...",
    "discussion_points": [],
    "decisions": [],
    "action_items": [],
    "takeaways": [],
    "followup_items": []
}
"""
            },
            {
                "role": "user",
                "content": (
                    f"Full meeting transcript:\n\n{full_transcript}"
                )
            }
        ]

        result = await self.process_with_retry(messages)

        if not result:
            return None

        parsed = self._parse_json(result)

        if isinstance(parsed, dict):
            return parsed

        return None

    # ============================================================
    # Topic Identification
    # ============================================================

    async def identify_topics(
        self,
        transcript: str
    ) -> Optional[List[Dict]]:
        """Identify the main topics discussed in the meeting."""

        messages = [
            {
                "role": "system",
                "content": """
You are a meeting topic analyzer.

Identify the main topics discussed in the meeting.

For each topic provide:
- topic
- description
- time_spent
- participants

Return ONLY a valid JSON array.

Example:

[
    {
        "topic": "Project Planning",
        "description": "Discussion about project milestones",
        "time_spent": "15 minutes",
        "participants": ["Alice", "Bob"]
    }
]
"""
            },
            {
                "role": "user",
                "content": f"Meeting transcript:\n\n{transcript}"
            }
        ]

        result = await self.process_with_retry(messages)

        if not result:
            return None

        parsed = self._parse_json(result)

        if isinstance(parsed, list):
            return parsed

        return None

    # ============================================================
    # Gemini Request + Retry
    # ============================================================

    async def process_with_retry(
        self,
        messages: List[Dict[str, str]],
        max_retries: int = 3
    ) -> Optional[str]:
        """Send a request to Gemini with retry handling."""

        retries = 0

        while retries < max_retries:
            try:

                # ------------------------------------------------
                # Rate limiting
                # ------------------------------------------------

                if not self.rate_limiter.can_make_request():
                    await asyncio.sleep(2)
                    continue

                # ------------------------------------------------
                # Convert OpenAI-style messages into Gemini prompt
                # ------------------------------------------------

                prompt_parts = []

                for message in messages:
                    role = message.get("role", "user")
                    content = message.get("content", "")

                    if role == "system":
                        prompt_parts.append(
                            f"SYSTEM INSTRUCTIONS:\n{content}"
                        )
                    else:
                        prompt_parts.append(
                            f"USER:\n{content}"
                        )

                prompt = "\n\n".join(prompt_parts)

                # ------------------------------------------------
                # Estimate input tokens
                # ------------------------------------------------

                input_tokens = self._estimate_tokens(prompt)

                if (
                    input_tokens
                    > self.settings.MAX_TOKENS_PER_REQUEST
                ):
                    raise ValueError(
                        f"Input tokens ({input_tokens}) exceed "
                        f"maximum allowed "
                        f"({self.settings.MAX_TOKENS_PER_REQUEST})"
                    )

                # ------------------------------------------------
                # Call Gemini
                # ------------------------------------------------

                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        response_mime_type="application/json",
                    ),
                )

                # ------------------------------------------------
                # Extract response
                # ------------------------------------------------

                content = response.text

                if not content:
                    raise ValueError(
                        "Gemini returned an empty response."
                    )

                # ------------------------------------------------
                # Usage statistics
                # ------------------------------------------------

                output_tokens = self._estimate_tokens(content)

                self.total_tokens_used += (
                    input_tokens + output_tokens
                )

                # Gemini cost calculation is intentionally omitted
                # because pricing can vary by model/account.
                self.total_cost = 0.0

                return content

            except Exception as e:
                error_text = str(e)

                # Do not retry quota/rate-limit errors. Retrying a 429
                # immediately only consumes more requests and makes the
                # quota problem worse.
                if (
                    "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                    or "quota" in error_text.lower()
                    or "rate limit" in error_text.lower()
                ):
                    logger.error(
                        "Gemini quota/rate-limit error. "
                        "Not retrying this request: %s",
                        e
                    )
                    return None

                retries += 1

                logger.error(
                    "Error processing Gemini request "
                    f"(attempt {retries}/{max_retries}): {e}"
                )

                if retries >= max_retries:
                    logger.error("Max retries reached.")
                    return None

                await asyncio.sleep(2 ** retries)

        return None

    # ============================================================
    # JSON Parser
    # ============================================================

    def _parse_json(self, content: str):
        """Safely parse JSON returned by Gemini."""

        try:
            return json.loads(content)

        except json.JSONDecodeError:

            logger.warning(
                "Gemini returned invalid JSON. "
                "Attempting to extract JSON."
            )

            cleaned = content.strip()

            # Handle markdown code fences
            if cleaned.startswith("```"):
                cleaned = cleaned.replace(
                    "```json",
                    ""
                )
                cleaned = cleaned.replace(
                    "```",
                    ""
                )
                cleaned = cleaned.strip()

            try:
                return json.loads(cleaned)

            except json.JSONDecodeError:
                logger.error(
                    "Unable to parse Gemini JSON response."
                )
                return None

    # ============================================================
    # Token Estimation
    # ============================================================

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Simple token estimation for usage statistics."""

        if not text:
            return 0

        # Rough approximation:
        # 1 token ≈ 4 characters
        return max(1, len(text) // 4)

    # ============================================================
    # Usage Statistics
    # ============================================================

    def get_usage_stats(self) -> Dict:
        """Get current usage statistics."""

        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": round(self.total_cost, 4),
            "timestamp": datetime.now().isoformat(),
        }