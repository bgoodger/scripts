"""Weekly nudge scheduler — sends DMs prompting users to leave feedback
after observed interactions during the past week."""

import os
import threading
import time
import logging
from datetime import date, timedelta

import schedule

import db

logger = logging.getLogger(__name__)

NUDGE_DAY = os.environ.get("NUDGE_DAY", "0")   # 0=Monday
NUDGE_TIME = os.environ.get("NUDGE_TIME", "09:00")

_DAY_MAP = {
    "0": "monday", "1": "tuesday", "2": "wednesday",
    "3": "thursday", "4": "friday", "5": "saturday", "6": "sunday",
}


def _iso_week(d: date = None) -> str:
    """Return ISO week string like '2026-W14'."""
    d = d or date.today()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def _last_week() -> str:
    last_monday = date.today() - timedelta(days=date.today().weekday() + 7)
    return _iso_week(last_monday)


def _build_nudge_blocks(peers: list, peer_names: dict) -> list:
    """Build Block Kit blocks for the nudge DM."""
    peer_tags = [f"*{peer_names.get(p, p)}*" for p in peers[:5]]
    peers_str = ", ".join(peer_tags)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":wave: You had notable interactions with {peers_str} last week.\n"
                    "Would you like to leave them some feedback? It only takes a minute and makes a real difference."
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": f":pencil: Feedback for {peer_names.get(p, p)}"},
                    "action_id": "nudge_give_feedback",
                    "value": p,
                    "style": "primary",
                }
                for p in peers[:3]  # Max 3 buttons to keep DM clean
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Maybe later"},
                    "action_id": "nudge_dismiss",
                    "value": "dismiss",
                }
            ],
        },
    ]
    return blocks


def send_weekly_nudges(app) -> None:
    """Main job: find users with un-nudged interactions last week and DM them."""
    week = _last_week()
    logger.info("Running weekly nudge job for week %s", week)

    users = db.get_all_users()
    if not users:
        logger.info("No users in DB yet — skipping nudge run.")
        return

    # Build a name lookup map
    name_map = {u["slack_id"]: u["name"] for u in users}

    sent_count = 0
    for user in users:
        user_id = user["slack_id"]
        peers = db.get_active_peers_for_week(user_id, week, min_interactions=2)

        # Filter out peers who have already been nudged this week
        new_peers = [p for p in peers if not db.nudge_already_sent(user_id, p, week)]
        if not new_peers:
            continue

        try:
            blocks = _build_nudge_blocks(new_peers, name_map)
            app.client.chat_postMessage(
                channel=user_id,  # DM by user_id
                text=f"You worked with {', '.join(name_map.get(p, p) for p in new_peers[:3])} last week — want to leave them feedback?",
                blocks=blocks,
            )
            for peer_id in new_peers:
                db.log_nudge(user_id, peer_id, week)
            sent_count += 1
            logger.info("Nudge sent to %s for peers %s", user_id, new_peers)
        except Exception as exc:
            logger.warning("Failed to nudge %s: %s", user_id, exc)

    logger.info("Weekly nudge job complete — %d DMs sent.", sent_count)


def start_scheduler(app) -> None:
    """Start the background schedule loop. Call in a daemon thread."""
    day_name = _DAY_MAP.get(str(NUDGE_DAY), "monday")
    job_fn = getattr(schedule.every(), day_name)
    job_fn.at(NUDGE_TIME).do(send_weekly_nudges, app=app)

    logger.info("Nudge scheduler started — runs every %s at %s", day_name, NUDGE_TIME)

    while True:
        schedule.run_pending()
        time.sleep(60)
