"""360 Feedback Slack Bot — main entry point.

Run with:  python app.py
Requires:  SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY in .env
"""

import logging
import os
import re
import threading
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import db
import ai
import modals
import home_tab as home
from weekly_nudge import start_scheduler, _iso_week

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = App(token=os.environ["SLACK_BOT_TOKEN"])

db.init_db()


# ── Helpers ──────────────────────────────────────────────────────────────────

# Simple in-process caches to avoid repeated API calls for the same IDs.
_user_internal_cache: dict[str, bool] = {}
_channel_internal_cache: dict[str, bool] = {}


def _is_internal_user(client, user_id: str) -> bool:
    """Return True only if the user belongs to this workspace.

    Rejects:
    - External/Slack Connect users  (is_stranger=True)
    - Bot users                     (is_bot=True)
    - Deleted accounts              (deleted=True)
    """
    if user_id in _user_internal_cache:
        return _user_internal_cache[user_id]
    try:
        info = client.users_info(user=user_id)
        u = info["user"]
        result = (
            not u.get("is_stranger", False)
            and not u.get("is_bot", False)
            and not u.get("deleted", False)
        )
    except Exception:
        result = False
    _user_internal_cache[user_id] = result
    return result


def _is_internal_channel(client, channel_id: str) -> bool:
    """Return True only if the channel is not shared with an external workspace."""
    if not channel_id:
        return True  # DMs / app_home have no channel; allow them
    if channel_id in _channel_internal_cache:
        return _channel_internal_cache[channel_id]
    try:
        info = client.conversations_info(channel=channel_id)
        ch = info["channel"]
        # is_ext_shared — shared via Slack Connect with another org
        result = not ch.get("is_ext_shared", False)
    except Exception:
        result = True  # Fail open for channel lookup errors (e.g. DMs)
    _channel_internal_cache[channel_id] = result
    return result


def _refresh_home(user_id: str, client) -> None:
    """Re-render the Home tab for a user."""
    view = home.build_home_view(user_id, client)
    client.views_publish(user_id=user_id, view=view)


def _get_display_name(client, user_id: str) -> str:
    info = client.users_info(user=user_id)
    profile = info["user"].get("profile", {})
    return profile.get("display_name") or info["user"].get("real_name", user_id)


def _ensure_user(client, user_id: str) -> str:
    """Register user if not seen before. Returns display name."""
    name = _get_display_name(client, user_id)
    db.upsert_user(user_id, name)
    return name


# ── Home tab ─────────────────────────────────────────────────────────────────

@app.event("app_home_opened")
def handle_home_opened(event, client, logger):
    user_id = event["user"]
    try:
        _refresh_home(user_id, client)
    except Exception as e:
        logger.error("Error building home tab for %s: %s", user_id, e)


# ── /feedback slash command ───────────────────────────────────────────────────

@app.command("/feedback")
def handle_feedback_command(ack, command, client):
    ack()
    user_id = command["user_id"]
    _ensure_user(client, user_id)

    # Check if a user was passed: /feedback @username
    prefill = None
    text = command.get("text", "").strip()
    match = re.match(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", text)
    if match:
        candidate = match.group(1)
        if _is_internal_user(client, candidate):
            prefill = candidate
        else:
            client.chat_postMessage(
                channel=user_id,
                text=":warning: That user is external to this workspace — feedback can only be given about internal team members.",
            )
            return

    client.views_open(
        trigger_id=command["trigger_id"],
        view=modals.feedback_modal(prefill_user_id=prefill),
    )


# ── Open feedback modal from Home tab button ─────────────────────────────────

@app.action("open_feedback_modal")
def open_feedback_modal(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    _ensure_user(client, user_id)
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modals.feedback_modal(),
    )


# ── Open feedback modal from nudge DM ────────────────────────────────────────

@app.action("nudge_give_feedback")
def nudge_give_feedback(ack, body, client):
    ack()
    peer_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]
    _ensure_user(client, user_id)
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modals.feedback_modal(prefill_user_id=peer_id),
    )


@app.action("nudge_dismiss")
def nudge_dismiss(ack):
    ack()
    # Nothing to do — just dismiss the interactive message


# ── Feedback modal submission ─────────────────────────────────────────────────

@app.view("feedback_submit")
def handle_feedback_submit(ack, body, view, client):
    ack()

    user_id = body["user"]["id"]
    quarter = view["private_metadata"] or db.get_current_quarter()
    values = view["state"]["values"]

    recipient_id = values["recipient_block"]["recipient_select"]["selected_user"]
    categories = [
        opt["value"]
        for opt in (values["categories_block"]["categories_select"].get("selected_options") or [])
    ]
    feedback_type = (values["feedback_type_block"]["feedback_type_select"].get("selected_option") or {}).get("value", "both")
    situation = (values["situation_block"]["situation_input"].get("value") or "").strip() or None
    content = values["content_block"]["content_input"].get("value", "").strip()

    if not content:
        return  # Shouldn't happen due to min_length, but guard anyway

    if recipient_id == user_id:
        client.chat_postMessage(
            channel=user_id,
            text=":warning: You can't submit feedback about yourself. Use the self-reflection section in your Home tab instead.",
        )
        return

    # Reject feedback targeting external/bot/deleted users
    if not _is_internal_user(client, recipient_id):
        client.chat_postMessage(
            channel=user_id,
            text=":warning: Feedback can only be submitted about internal workspace members.",
        )
        return

    # Ensure both users are registered
    _ensure_user(client, user_id)
    _ensure_user(client, recipient_id)

    db.save_feedback(
        giver_id=user_id,
        recipient_id=recipient_id,
        content=content,
        situation=situation,
        categories=categories,
        feedback_type=feedback_type,
        quarter=quarter,
    )

    # Confirm to the giver
    recipient_name = _get_display_name(client, recipient_id)
    client.chat_postMessage(
        channel=user_id,
        text=f":white_check_mark: Your feedback about *{recipient_name}* has been submitted for {quarter}. Only they can see it. Thank you!",
    )

    logger.info("Feedback submitted by %s for %s in %s", user_id, recipient_id, quarter)


# ── Refresh AI summary ────────────────────────────────────────────────────────

@app.action("refresh_summary")
def refresh_summary(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    quarter = body["actions"][0]["value"]

    db.invalidate_summary(user_id, quarter)

    feedback_items = db.get_feedback_for_user(user_id, quarter)
    if feedback_items:
        name = _get_display_name(client, user_id)
        summary = ai.summarize_feedback(feedback_items, name, quarter)
        db.save_summary(user_id, quarter, summary)

    _refresh_home(user_id, client)


# ── Self-reflection ───────────────────────────────────────────────────────────

@app.action("open_reflection_modal")
def open_reflection_modal(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    quarter = body["actions"][0]["value"]

    current = db.get_self_reflection(user_id, quarter) or ""

    # Generate personalised prompts if there's feedback
    prompt_text = None
    summary = db.get_cached_summary(user_id, quarter)
    if summary:
        prompt_text = ai.suggest_reflection_prompts(summary, quarter)

    client.views_open(
        trigger_id=body["trigger_id"],
        view=modals.self_reflection_modal(current, quarter, prompt_text),
    )


@app.view("reflection_submit")
def handle_reflection_submit(ack, body, view, client):
    ack()
    user_id = body["user"]["id"]
    quarter = view["private_metadata"] or db.get_current_quarter()
    content = view["state"]["values"]["reflection_block"]["reflection_input"].get("value", "").strip()

    db.upsert_self_reflection(user_id, quarter, content)
    _refresh_home(user_id, client)


# ── Goals ─────────────────────────────────────────────────────────────────────

@app.action("open_goal_modal")
def open_goal_modal(ack, body, client):
    ack()
    quarter = body["actions"][0]["value"]
    client.views_open(
        trigger_id=body["trigger_id"],
        view=modals.add_goal_modal(quarter),
    )


@app.view("goal_submit")
def handle_goal_submit(ack, body, view, client):
    ack()
    user_id = body["user"]["id"]
    quarter = view["private_metadata"] or db.get_current_quarter()
    content = view["state"]["values"]["goal_block"]["goal_input"].get("value", "").strip()

    if content:
        db.add_goal(user_id, quarter, content)
    _refresh_home(user_id, client)


@app.action("toggle_goal")
def toggle_goal(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    goal_id = int(body["actions"][0]["value"])
    db.toggle_goal(goal_id)
    _refresh_home(user_id, client)


# ── Interaction tracking ──────────────────────────────────────────────────────

@app.event("app_mention")
def track_mention_interaction(event, client):
    """When user A mentions user B, record an interaction for nudge purposes.
    Only processes internal users in internal (non-Slack-Connect) channels.
    """
    sender_id = event.get("user")
    text = event.get("text", "")
    channel = event.get("channel")
    week = _iso_week()

    if not sender_id:
        return
    if not _is_internal_user(client, sender_id):
        return
    if not _is_internal_channel(client, channel):
        return

    _ensure_user(client, sender_id)

    mentioned = re.findall(r"<@([A-Z0-9]+)>", text)
    for mentioned_id in mentioned:
        if mentioned_id == sender_id:
            continue
        if not _is_internal_user(client, mentioned_id):
            continue
        _ensure_user(client, mentioned_id)
        db.record_interaction(sender_id, mentioned_id, channel, week)
        db.record_interaction(mentioned_id, sender_id, channel, week)


@app.event("message")
def track_message_interactions(event, client, logger):
    """Track @mentions in internal channel messages for weekly nudge purposes.
    Skips bot messages, edits, deletes, external users, and Slack Connect channels.
    """
    if event.get("bot_id") or event.get("subtype"):
        return

    sender_id = event.get("user")
    text = event.get("text", "")
    channel = event.get("channel")
    week = _iso_week()

    if not sender_id:
        return
    if not _is_internal_user(client, sender_id):
        return
    if not _is_internal_channel(client, channel):
        return

    mentioned = re.findall(r"<@([A-Z0-9]+)>", text)
    if not mentioned:
        return

    for mentioned_id in mentioned:
        if mentioned_id == sender_id:
            continue
        if not _is_internal_user(client, mentioned_id):
            continue
        db.record_interaction(sender_id, mentioned_id, channel, week)
        db.record_interaction(mentioned_id, sender_id, channel, week)


# ── /feedback-admin commands ──────────────────────────────────────────────────

@app.command("/feedback-admin")
def handle_admin_command(ack, command, client):
    """Admin commands. Usage:
      /feedback-admin set-manager @user @manager
      /feedback-admin nudge-now
    """
    ack()
    user_id = command["user_id"]
    text = command.get("text", "").strip()

    parts = text.split()
    if not parts:
        client.chat_postMessage(
            channel=user_id,
            text="Usage:\n• `/feedback-admin set-manager @user @manager`\n• `/feedback-admin nudge-now`",
        )
        return

    subcommand = parts[0].lower()

    if subcommand == "set-manager":
        mentions = re.findall(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", text)
        if len(mentions) < 2:
            client.chat_postMessage(channel=user_id, text=":warning: Usage: `/feedback-admin set-manager @user @manager`")
            return
        target_user, manager = mentions[0], mentions[1]
        if not _is_internal_user(client, target_user) or not _is_internal_user(client, manager):
            client.chat_postMessage(
                channel=user_id,
                text=":warning: Both users must be internal workspace members.",
            )
            return
        _ensure_user(client, target_user)
        _ensure_user(client, manager)
        db.set_manager(target_user, manager)
        target_name = _get_display_name(client, target_user)
        manager_name = _get_display_name(client, manager)
        client.chat_postMessage(
            channel=user_id,
            text=f":white_check_mark: *{manager_name}* is now set as manager for *{target_name}*.",
        )

    elif subcommand == "nudge-now":
        client.chat_postMessage(channel=user_id, text=":hourglass: Running weekly nudges now…")
        threading.Thread(target=send_nudges_async, args=(client, user_id), daemon=True).start()

    else:
        client.chat_postMessage(channel=user_id, text=f":warning: Unknown subcommand: `{subcommand}`")


def send_nudges_async(client, requester_id: str):
    from weekly_nudge import send_weekly_nudges
    try:
        send_weekly_nudges(app)
        client.chat_postMessage(channel=requester_id, text=":white_check_mark: Nudge run complete.")
    except Exception as e:
        client.chat_postMessage(channel=requester_id, text=f":x: Nudge run failed: {e}")


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting 360 Feedback Bot…")

    # Start weekly nudge scheduler in a background daemon thread
    nudge_thread = threading.Thread(
        target=start_scheduler,
        args=(app,),
        daemon=True,
        name="nudge-scheduler",
    )
    nudge_thread.start()

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
