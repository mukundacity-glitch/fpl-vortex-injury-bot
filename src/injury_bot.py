import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime, timezone


FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

STATE_FILE = Path("data/injury_state.json")


def fetch_fpl_data():
    request = urllib.request.Request(
        FPL_API_URL,
        headers={
            "User-Agent": "FPL-Vortex-Injury-Bot/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_discord_embed(embed):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL secret is missing")

    payload = json.dumps(
        {
            "username": "FPL Vortex Injury News",
            "embeds": [embed],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FPL-Vortex-Injury-Bot/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discord returned HTTP {response.status}"
            )


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def get_position(position_id):
    return {
        1: "GK",
        2: "DEF",
        3: "MID",
        4: "FWD",
    }.get(position_id, "Unknown")


def get_status_text(status):
    return {
        "a": "Available",
        "d": "Doubt",
        "i": "Injured",
        "s": "Suspended",
        "u": "Unavailable",
    }.get(status, status or "Unknown")


def get_event_type(old, new):
    if old is None:
        return "NEW INJURY"

    old_status = old.get("status")
    new_status = new.get("status")

    old_chance = old.get("chance_next")
    new_chance = new.get("chance_next")

    old_news = old.get("news", "")
    new_news = new.get("news", "")

    if old_status != new_status:
        if new_status == "a":
            return "RETURN UPDATE"

        if new_status == "i":
            return "NEW INJURY"

        if new_status == "d":
            return "FITNESS DOUBT"

        if new_status == "s":
            return "SUSPENSION UPDATE"

        return "AVAILABILITY UPDATE"

    if old_chance != new_chance:
        return "AVAILABILITY UPDATE"

    if old_news != new_news:
        return "INJURY NEWS UPDATE"

    return "FPL AVAILABILITY UPDATE"


def get_event_style(event_type):
    styles = {
        "NEW INJURY": {
            "icon": "🚨",
            "color": 0xE74C3C,
        },
        "FITNESS DOUBT": {
            "icon": "⚠️",
            "color": 0xF39C12,
        },
        "RETURN UPDATE": {
            "icon": "🟢",
            "color": 0x2ECC71,
        },
        "AVAILABILITY UPDATE": {
            "icon": "🔄",
            "color": 0x3498DB,
        },
        "INJURY NEWS UPDATE": {
            "icon": "📰",
            "color": 0x9B59B6,
        },
        "SUSPENSION UPDATE": {
            "icon": "⛔",
            "color": 0x34495E,
        },
        "FPL AVAILABILITY UPDATE": {
            "icon": "📊",
            "color": 0x1ABC9C,
        },
    }

    return styles.get(
        event_type,
        {
            "icon": "🚨",
            "color": 0x3498DB,
        },
    )


def get_player_photo_url(photo):
    if not photo:
        return None

    photo_name = str(photo)

    if photo_name.endswith(".jpg"):
        photo_id = photo_name[:-4]
    else:
        photo_id = photo_name

    if not photo_id.isdigit():
        return None

    return (
        "https://resources.premierleague.com/"
        "premierleague/photos/players/250x250/"
        f"p{photo_id}.png"
    )


def build_record(player, teams):
    chance_next = player.get(
        "chance_of_playing_next_round"
    )

    chance_this = player.get(
        "chance_of_playing_this_round"
    )

    news = (
        player.get("news") or ""
    ).strip()

    status = player.get("status") or "a"

    relevant = (
        status != "a"
        or chance_next is not None
        or chance_this is not None
        or bool(news)
    )

    if not relevant:
        return None

    first_name = (
        player.get("first_name") or ""
    ).strip()

    second_name = (
        player.get("second_name") or ""
    ).strip()

    return {
        "name": f"{first_name} {second_name}".strip(),
        "team": teams.get(
            player.get("team"),
            "Unknown",
        ),
        "position": get_position(
            player.get("element_type")
        ),
        "price": player.get("now_cost", 0) / 10,
        "ownership": player.get(
            "selected_by_percent",
            "0.0",
        ),
        "chance_next": chance_next,
        "chance_this": chance_this,
        "status": status,
        "news": news,
        "news_added": player.get("news_added"),
        "photo": player.get("photo"),
    }


def build_embed(record, event_type, gameweek):
    style = get_event_style(event_type)

    chance = record.get("chance_next")

    if chance is None:
        chance_text = "Not provided"
    else:
        chance_text = f"{chance}%"

    news_text = (
        record.get("news")
        or "No additional update provided by FPL."
    )

    ownership = record.get(
        "ownership",
        "0.0",
    )

    price = record.get("price", 0)

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d %b %Y • %H:%M UTC"
    )

    embed = {
        "title": (
            f"{style['icon']} "
            f"FPL VORTEX • {event_type}"
        ),
        "description": (
            f"**{record['name']}**\n"
            f"{record['team']} • "
            f"{record['position']} • "
            f"£{price:.1f}m"
        ),
        "color": style["color"],
        "fields": [
            {
                "name": "🏥 Status",
                "value": (
                    f"**{get_status_text(record['status'])}**"
                ),
                "inline": True,
            },
            {
                "name": "⚽ Chance of Playing",
                "value": f"**{chance_text}**",
                "inline": True,
            },
            {
                "name": "📈 FPL Ownership",
                "value": f"**{ownership}%**",
                "inline": True,
            },
            {
                "name": "📰 Latest FPL Update",
                "value": news_text[:1024],
                "inline": False,
            },
            {
                "name": "🎯 Gameweek",
                "value": f"**GW{gameweek}**",
                "inline": True,
            },
        ],
        "footer": {
            "text": (
                "FPL Vortex • "
                "Source: Official FPL data • "
                "#FPL #FPLNews #FPLInjury"
            )
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    photo_url = get_player_photo_url(
        record.get("photo")
    )

    if photo_url:
        embed["thumbnail"] = {
            "url": photo_url
        }

    return embed


def build_test_embed():
    return {
        "title": "🚨 FPL VORTEX • INJURY NEWS ENGINE",
        "description": (
            "**Discord connection confirmed.**\n\n"
            "The FPL Vortex Injury News Engine is ready "
            "to monitor player availability changes."
        ),
        "color": 0x3498DB,
        "fields": [
            {
                "name": "🏥 Monitoring",
                "value": (
                    "Injuries, doubts, suspensions "
                    "and availability changes"
                ),
                "inline": False,
            },
            {
                "name": "📊 Data",
                "value": "Official FPL data",
                "inline": True,
            },
            {
                "name": "📡 Channel",
                "value": "🏥 #fpl-injury-updates",
                "inline": True,
            },
        ],
        "footer": {
            "text": (
                "FPL Vortex • "
                "#FPL #FPLNews #FPLInjury"
            )
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def main():
    if TEST_MODE:
        send_discord_embed(
            build_test_embed()
        )

        print(
            "Discord rich embed test sent successfully."
        )

        return

    data = fetch_fpl_data()

    teams = {
        team["id"]: team["name"]
        for team in data.get("teams", [])
    }

    current_event = next(
        (
            event
            for event in data.get("events", [])
            if event.get("is_current")
        ),
        None,
    )

    if current_event:
        gameweek = current_event.get(
            "id",
            "?",
        )
    else:
        gameweek = "?"

    players = data.get(
        "elements",
        [],
    )

    previous = load_state()

    current = {}
    changes = []

    for player in players:
        record = build_record(
            player,
            teams,
        )

        if not record:
            continue

        player_id = str(
            player["id"]
        )

        current[player_id] = record

        old_record = previous.get(
            player_id
        )

        if old_record is None:
            continue

        if old_record != record:
            changes.append(
                (
                    old_record,
                    record,
                )
            )

    if not previous:
        save_state(current)

        print(
            "Initial baseline created."
        )

        print(
            f"Tracked players: "
            f"{len(current)}"
        )

        return

    for old_record, new_record in changes:
        event_type = get_event_type(
            old_record,
            new_record,
        )

        embed = build_embed(
            new_record,
            event_type,
            gameweek,
        )

        send_discord_embed(
            embed
        )

        print(
            f"Sent: {new_record['name']} "
            f"• {event_type}"
        )

    save_state(current)

    print(
        f"Monitoring complete. "
        f"Changes found: {len(changes)}"
    )


if __name__ == "__main__":
    main()
