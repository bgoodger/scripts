"""Claude API integration for theme summarization and feedback analysis."""

import json
import os
from typing import Optional

import anthropic

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def summarize_feedback(feedback_items: list, recipient_name: str, quarter: str) -> dict:
    """
    Use Claude to extract themes, strengths, and growth areas from raw feedback.
    Returns a dict with keys: summary, themes, strengths, growth_areas.
    Falls back gracefully if the API call fails.
    """
    if not feedback_items:
        return {
            "summary": f"No feedback received yet for {quarter}. Share your /feedback link with colleagues to get started!",
            "themes": [],
            "strengths": [],
            "growth_areas": [],
        }

    lines = []
    for i, item in enumerate(feedback_items, 1):
        cats = ", ".join(item.get("categories") or []) or "General"
        ftype = item.get("feedback_type", "both")
        situation = item.get("situation") or ""
        content = item.get("content", "")
        lines.append(
            f"Feedback #{i} [{cats} | {ftype}]"
            + (f"\nContext: {situation}" if situation else "")
            + f"\n{content}"
        )

    feedback_block = "\n\n---\n\n".join(lines)

    prompt = f"""You are an executive coach helping {recipient_name} understand their 360-degree performance feedback for {quarter}.

Below is a collection of feedback submitted by their peers, manager, and cross-functional stakeholders (sources are anonymised).

<feedback>
{feedback_block}
</feedback>

Analyse this feedback and return a JSON object with exactly these keys:

- "summary": A 2–3 sentence executive summary highlighting the overall picture. Be specific and constructive.
- "themes": A list of up to 5 objects, each with:
    - "theme": short label (e.g. "Stakeholder communication")
    - "count": approximate number of feedback items referencing this theme
    - "sentiment": "positive" | "constructive" | "mixed"
    - "detail": one sentence describing the pattern
- "strengths": A list of up to 4 concrete strengths observed, as short strings.
- "growth_areas": A list of up to 3 specific, actionable development areas, as short strings.

Return only valid JSON. Do not include markdown fencing."""

    try:
        response = _get_client().messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fencing
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as exc:
        return {
            "summary": f"Could not generate summary at this time ({type(exc).__name__}). Your feedback is safely stored.",
            "themes": [],
            "strengths": [],
            "growth_areas": [],
        }


def suggest_reflection_prompts(feedback_summary: dict, quarter: str) -> str:
    """
    Generate personalised self-reflection prompt questions based on the feedback summary.
    Returns a plain-text string with bullet-point questions.
    """
    if not feedback_summary or not feedback_summary.get("themes"):
        return (
            "• What are you most proud of achieving this quarter?\n"
            "• Where did you fall short of your own expectations, and why?\n"
            "• What one behaviour would have the biggest positive impact if you changed it?\n"
            "• What support or resources do you need next quarter?"
        )

    themes_text = "\n".join(
        f"- {t['theme']} ({t['sentiment']}): {t.get('detail', '')}"
        for t in feedback_summary.get("themes", [])
    )
    growth_text = "\n".join(f"- {g}" for g in feedback_summary.get("growth_areas", []))

    prompt = f"""Based on the following 360 feedback themes for {quarter}:

Themes:
{themes_text}

Growth areas:
{growth_text}

Write 4 personalised, thoughtful self-reflection questions (bullet points only, no preamble).
Each question should encourage honest introspection tied to the specific feedback patterns.
Keep them concise."""

    try:
        response = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return (
            "• What are you most proud of achieving this quarter?\n"
            "• Where did you fall short of your own expectations, and why?\n"
            "• What one behaviour would have the biggest positive impact if you changed it?\n"
            "• What support or resources do you need next quarter?"
        )
