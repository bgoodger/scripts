"""Slack Home tab view builder for the 360 feedback tool."""

from typing import Optional
import db
import ai


SENTIMENT_EMOJI = {
    "positive": ":large_green_circle:",
    "constructive": ":large_yellow_circle:",
    "mixed": ":large_blue_circle:",
}

FEEDBACK_TYPE_LABEL = {
    "strength": "Strength",
    "growth": "Growth area",
    "both": "Both",
}


def _divider() -> dict:
    return {"type": "divider"}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def _button_action(text: str, action_id: str, value: str = "click", style: str = None) -> dict:
    btn = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": action_id,
        "value": value,
    }
    if style:
        btn["style"] = style
    return btn


def build_home_view(user_id: str, slack_client) -> dict:
    """Build the complete Home tab view for a given user."""
    quarter = db.get_current_quarter()

    # Ensure user is registered
    user_info = slack_client.users_info(user=user_id)
    display_name = (
        user_info["user"].get("profile", {}).get("display_name")
        or user_info["user"].get("real_name", "there")
    )
    db.upsert_user(user_id, display_name)

    feedback_items = db.get_feedback_for_user(user_id, quarter)
    counts = db.get_feedback_count_for_user(user_id, quarter)
    goals = db.get_goals(user_id, quarter)
    reflection = db.get_self_reflection(user_id, quarter)

    # Get or generate AI summary
    summary = db.get_cached_summary(user_id, quarter)
    if summary is None and feedback_items:
        summary = ai.summarize_feedback(feedback_items, display_name, quarter)
        db.save_summary(user_id, quarter, summary)

    blocks = []

    # ── Header ──────────────────────────────────────────────────────────────
    blocks.append(_header(f"My 360 Feedback — {quarter}"))
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Hi *{display_name}* :wave: Here's your feedback dashboard for {quarter}.\n"
                    "Feedback you receive is *anonymous* — sources are never revealed to you."
                ),
            },
            "accessory": _button_action(":arrows_counterclockwise: Refresh summary", "refresh_summary", quarter),
        }
    )
    blocks.append(_divider())

    # ── Stats bar ────────────────────────────────────────────────────────────
    blocks.append(
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Feedback received*\n{counts['total']} responses"},
                {"type": "mrkdwn", "text": f"*From*\n{counts['unique_givers']} colleagues"},
            ],
        }
    )

    # ── AI Summary ───────────────────────────────────────────────────────────
    blocks.append(_header(":bar_chart: Quarter Summary"))

    if summary:
        blocks.append(_section(summary.get("summary", "_No summary available._")))

        if summary.get("themes"):
            theme_lines = []
            for t in summary["themes"]:
                emoji = SENTIMENT_EMOJI.get(t.get("sentiment", "mixed"), ":white_circle:")
                detail = t.get("detail", "")
                theme_lines.append(f"{emoji} *{t['theme']}*  _{detail}_")
            blocks.append(_section("*Recurring themes:*\n" + "\n".join(theme_lines)))

        if summary.get("strengths"):
            s_lines = "\n".join(f":white_check_mark: {s}" for s in summary["strengths"])
            blocks.append(_section(f"*Strengths observed:*\n{s_lines}"))

        if summary.get("growth_areas"):
            g_lines = "\n".join(f":seedling: {g}" for g in summary["growth_areas"])
            blocks.append(_section(f"*Areas for growth:*\n{g_lines}"))
    else:
        blocks.append(
            _section(
                ":speech_balloon: No feedback yet this quarter.\n"
                "Ask colleagues to use `/feedback` and select your name!"
            )
        )

    blocks.append(_divider())

    # ── Recent feedback (anonymised) ─────────────────────────────────────────
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:speech_balloon: Recent Feedback*"},
        }
    )

    if feedback_items:
        for item in feedback_items[:5]:
            cats = ", ".join(item.get("categories") or []) or "General"
            ftype = FEEDBACK_TYPE_LABEL.get(item.get("feedback_type", "both"), "")
            date_str = item.get("created_at", "")[:10]
            blocks.append(
                _section(
                    f"*{cats}* · _{ftype}_ · {date_str}\n>{item['content']}"
                )
            )
    else:
        blocks.append(_section("_No feedback received yet._"))

    blocks.append(_divider())

    # ── Self-Reflection ──────────────────────────────────────────────────────
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:writing_hand: My Self-Reflection*"},
            "accessory": _button_action(
                ":pencil2: Edit reflection",
                "open_reflection_modal",
                quarter,
            ),
        }
    )

    if reflection:
        # Show first 400 chars to keep the home tab clean
        preview = reflection[:400] + ("…" if len(reflection) > 400 else "")
        blocks.append(_section(f">{preview}"))
    else:
        blocks.append(
            _section(
                "_You haven't written a self-reflection yet._\n"
                "Click *Edit reflection* to write one — it's only visible to you."
            )
        )

    blocks.append(_divider())

    # ── Goals ────────────────────────────────────────────────────────────────
    open_goals = [g for g in goals if not g["completed"]]
    done_goals = [g for g in goals if g["completed"]]

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*:dart: My Goals for {quarter}*  _{len(done_goals)}/{len(goals)} complete_",
            },
            "accessory": _button_action(":heavy_plus_sign: Add goal", "open_goal_modal", quarter),
        }
    )

    if goals:
        for goal in open_goals:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f":white_large_square: {goal['content']}"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Mark done"},
                        "action_id": "toggle_goal",
                        "value": str(goal["id"]),
                    },
                }
            )
        for goal in done_goals:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":white_check_mark: ~{goal['content']}~",
                    },
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Undo"},
                        "action_id": "toggle_goal",
                        "value": str(goal["id"]),
                    },
                }
            )
    else:
        blocks.append(_section("_No goals set yet. Click *Add goal* to get started._"))

    blocks.append(_divider())

    # ── Give feedback prompt ─────────────────────────────────────────────────
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":pencil: Give feedback to a colleague"},
                    "action_id": "open_feedback_modal",
                    "value": "home",
                    "style": "primary",
                }
            ],
        }
    )

    return {"type": "home", "blocks": blocks}
