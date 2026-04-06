"""Slack modal view definitions for the 360 feedback tool."""

from db import get_current_quarter


FEEDBACK_CATEGORIES = [
    ("collaboration", "Collaboration"),
    ("communication", "Communication"),
    ("delivery", "Delivery & Execution"),
    ("technical", "Technical Skills"),
    ("leadership", "Leadership & Influence"),
    ("adaptability", "Adaptability"),
]


def feedback_modal(prefill_user_id: str = None, trigger_id: str = None) -> dict:
    """Modal for submitting feedback about a colleague."""
    quarter = get_current_quarter()

    user_block = {
        "type": "input",
        "block_id": "recipient_block",
        "label": {"type": "plain_text", "text": "Who are you giving feedback about?"},
        "element": {
            "type": "users_select",
            "action_id": "recipient_select",
            "placeholder": {"type": "plain_text", "text": "Select a colleague"},
            **({"initial_user": prefill_user_id} if prefill_user_id else {}),
        },
    }

    return {
        "type": "modal",
        "callback_id": "feedback_submit",
        "title": {"type": "plain_text", "text": "Give Feedback"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": quarter,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{quarter} Feedback* — Only the recipient can see this feedback.",
                },
            },
            {"type": "divider"},
            user_block,
            {
                "type": "input",
                "block_id": "categories_block",
                "label": {"type": "plain_text", "text": "Categories (select all that apply)"},
                "element": {
                    "type": "checkboxes",
                    "action_id": "categories_select",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": label},
                            "value": value,
                        }
                        for value, label in FEEDBACK_CATEGORIES
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "feedback_type_block",
                "label": {"type": "plain_text", "text": "This feedback is primarily…"},
                "element": {
                    "type": "radio_buttons",
                    "action_id": "feedback_type_select",
                    "options": [
                        {"text": {"type": "plain_text", "text": "A strength to keep building on"}, "value": "strength"},
                        {"text": {"type": "plain_text", "text": "An area for growth"}, "value": "growth"},
                        {"text": {"type": "plain_text", "text": "Both"}, "value": "both"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "situation_block",
                "optional": True,
                "label": {"type": "plain_text", "text": "Situation / context (optional)"},
                "hint": {
                    "type": "plain_text",
                    "text": "Briefly describe the project, meeting, or situation this feedback relates to.",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "situation_input",
                    "multiline": False,
                    "placeholder": {"type": "plain_text", "text": "e.g. Q1 planning session, backend migration project"},
                },
            },
            {
                "type": "input",
                "block_id": "content_block",
                "label": {"type": "plain_text", "text": "Your feedback"},
                "hint": {
                    "type": "plain_text",
                    "text": "Be specific and behavioural. What did you observe? What was the impact?",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "content_input",
                    "multiline": True,
                    "min_length": 20,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. During the planning session, Alex proactively flagged a dependency risk that the team had missed…",
                    },
                },
            },
        ],
    }


def self_reflection_modal(current_content: str, quarter: str, prompts: str = None) -> dict:
    """Modal for writing/editing a self-reflection."""
    placeholder = "Write your self-reflection here…"
    if prompts:
        placeholder = prompts  # Slack plain_text max 150 chars, so keep short

    return {
        "type": "modal",
        "callback_id": "reflection_submit",
        "title": {"type": "plain_text", "text": "Self-Reflection"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": quarter,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{quarter} Self-Reflection*\nThis is private — only you can see it.",
                },
            },
            *([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Suggested prompts based on your feedback:*\n{prompts}",
                    },
                },
                {"type": "divider"},
            ] if prompts else []),
            {
                "type": "input",
                "block_id": "reflection_block",
                "label": {"type": "plain_text", "text": "Your reflection"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reflection_input",
                    "multiline": True,
                    "min_length": 0,
                    "initial_value": current_content or "",
                    "placeholder": {"type": "plain_text", "text": placeholder[:150]},
                },
            },
        ],
    }


def add_goal_modal(quarter: str) -> dict:
    """Modal for adding a new goal."""
    return {
        "type": "modal",
        "callback_id": "goal_submit",
        "title": {"type": "plain_text", "text": "Add Goal"},
        "submit": {"type": "plain_text", "text": "Add"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": quarter,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*New goal for {quarter}*",
                },
            },
            {
                "type": "input",
                "block_id": "goal_block",
                "label": {"type": "plain_text", "text": "Goal"},
                "hint": {
                    "type": "plain_text",
                    "text": "Keep it specific and achievable within the quarter.",
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "goal_input",
                    "multiline": False,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Improve cross-team communication by running a weekly sync with design",
                    },
                },
            },
        ],
    }
