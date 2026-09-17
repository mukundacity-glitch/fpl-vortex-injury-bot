import json
import os
import re
import urllib.request
from pathlib import Path
from datetime import datetime, timezone


FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

STATE_FILE = Path("data/injury_state.json")
X_DRAFT_FILE = Path("data/x_drafts.json")


STATUS_TEXT = {
    "a": "Available",
    "d": "Doubt",
    "i": "Injured",
    "s": "Suspended",
    "u": "Unavailable",
}


POSITION_TEXT = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


EVENT_STYLES = {
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
}


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FPL-Vortex-Injury-Bot/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def send_discord_embed(embed):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL secret is missing"
        )

    payload = json.dumps(
        {
            "username": "FPL Vortex Injury News",
            "embeds": [embed],
            "allowed_mentions": {
                "parse": []
            },
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

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discord returned HTTP {response.status}"
            )


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def save_x_draft(player_id, draft):
    X_DRAFT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    existing = {}

    if X_DRAFT_FILE.exists():
        try:
            existing = json.loads(
                X_DRAFT_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            existing = {}

    existing[str(player_id)] = draft

    X_DRAFT_FILE.write_text(
        json.dumps(
            existing,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def clean_text(text):
    text = (text or "").strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def get_player_image(photo):
    if not photo:
        return None

    photo_id = str(photo)

    if photo_id.endswith(".jpg"):
        photo_id = photo_id[:-4]

    photo_id = photo_id.strip()

    if not photo_id.isdigit():
        return None

    return (
        "https://resources.premierleague.com/"
        "premierleague/photos/players/250x250/"
        f"p{photo_id}.png"
    )


def get_team_logo(team_code):
    if not team_code:
        return None

    return (
        "https://resources.premierleague.com/"
        f"premierleague/badges/t{team_code}.png"
    )


def get_position(element_type):
    return POSITION_TEXT.get(
        element_type,
        "Unknown"
    )


def get_status(status):
    return STATUS_TEXT.get(
        status,
        status or "Unknown"
    )


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

    return "AVAILABILITY UPDATE"


def get_style(event_type):
    return EVENT_STYLES.get(
        event_type,
        {
            "icon": "🚨",
            "color": 0x3498DB,
        }
    )


def format_price(now_cost):
    try:
        return f"£{now_cost / 10:.1f}m"
    except Exception:
        return "£0.0m"


def format_ownership(value):
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def get_fdr_label(fdr):
    if fdr is None:
        return "N/A"

    try:
        fdr = int(fdr)
    except Exception:
        return "N/A"

    return f"{fdr}/5"


def get_next_fixture(
    player_team_id,
    fixtures,
    teams_by_id
):
    future = []

    for fixture in fixtures:

        if fixture.get("finished"):
            continue

        home = fixture.get("team_h")
        away = fixture.get("team_a")

        if (
            home != player_team_id
            and away != player_team_id
        ):
            continue

        if fixture.get("event") is None:
            continue

        if home == player_team_id:
            opponent_id = away
            opponent_name = teams_by_id.get(
                opponent_id,
                {}
            ).get(
                "short_name",
                "UNK"
            )

            difficulty = fixture.get(
                "team_h_difficulty"
            )

            home_away = "H"

        else:
            opponent_id = home
            opponent_name = teams_by_id.get(
                opponent_id,
                {}
            ).get(
                "short_name",
                "UNK"
            )

            difficulty = fixture.get(
                "team_a_difficulty"
            )

            home_away = "A"

        future.append(
            {
                "event": fixture.get("event"),
                "opponent": opponent_name,
                "difficulty": difficulty,
                "home_away": home_away,
                "kickoff": fixture.get(
                    "kickoff_time"
                ),
            }
        )

    future.sort(
        key=lambda item: (
            item.get("event") or 999
        )
    )

    return future[0] if future else None


def create_description(
    player,
    event_type
):
    name = player["name"]
    team = player["team"]
    chance = player["chance_next"]
    status = get_status(
        player["status"]
    )

    news = clean_text(
        player["news"]
    )

    ownership = player["ownership"]

    if chance is None:
        chance_text = "an unreported chance of playing"
    else:
        chance_text = f"a {chance}% chance of playing"

    if news:
        detail = (
            f"The latest FPL note states: "
            f"\"{news}\""
        )
    else:
        detail = (
            "The current FPL feed does not include "
            "an additional injury note."
        )

    impact = ""

    try:
        ownership_value = float(
            ownership
        )

        if ownership_value >= 30:
            impact = (
                " With ownership above 30%, "
                "this is a high-impact availability "
                "update for FPL managers."
            )

        elif ownership_value >= 15:
            impact = (
                " His ownership means the update "
                "could affect a meaningful number "
                "of FPL squads."
            )

    except Exception:
        pass

    return (
        f"{name} of {team} is currently listed as "
        f"{status} with {chance_text} ahead of the "
        f"next Gameweek. {detail}{impact}"
    )


def create_takeaway(
    player,
    fixture
):
    name = player["name"]
    status = player["status"]
    chance = player["chance_next"]
    ownership = player["ownership"]

    try:
        ownership_value = float(
            ownership
        )
    except Exception:
        ownership_value = 0.0

    if status == "i":

        if chance is not None and chance <= 25:
            if ownership_value >= 15:
                return (
                    f"If {name} is in your fantasy team, "
                    "start planning a replacement rather "
                    "than waiting for a last-minute decision. "
                    "His ownership makes the news especially "
                    "relevant."
                )

            return (
                f"If {name} is in your fantasy team, "
                "keep a replacement option ready and "
                "monitor the next confirmed update."
            )

        return (
            f"If {name} is in your fantasy team, "
            "monitor the next official update before "
            "making a transfer decision."
        )

    if status == "d":

        if chance is not None and chance <= 25:
            return (
                f"If {name} is in your fantasy team, "
                "have a backup plan ready. A low chance "
                "of playing makes this a genuine selection "
                "concern."
            )

        return (
            f"If {name} is in your fantasy team, "
            "there's no need to rush on this update. "
            "Monitor the next team or injury report "
            "before making a transfer."
        )

    if status == "a":

        return (
            f"If {name} is in your fantasy team, "
            "the latest status is encouraging. "
            "Continue to monitor minutes and team news "
            "ahead of the Gameweek deadline."
        )

    if status == "s":

        return (
            f"If {name} is in your fantasy team, "
            "check the suspension timeline before "
            "using a transfer. The key question is "
            "when he becomes available again."
        )

    if chance is not None:

        if chance >= 90:
            return (
                f"If {name} is in your fantasy team, "
                "the current availability signal is "
                "strong. Keep monitoring final team news."
            )

        if chance <= 25:
            return (
                f"If {name} is in your fantasy team, "
                "prepare a backup option before the "
                "deadline."
            )

    return (
        f"If {name} is in your fantasy team, "
        "monitor the next confirmed FPL update "
        "before taking action."
    )


def create_expected_return(news, status):
    news_lower = (
        news or ""
    ).lower()

    return_phrases = [
        "expected back",
        "expected to return",
        "return date",
        "return next",
        "back after",
        "back in",
        "weeks",
        "week",
        "days",
    ]

    for phrase in return_phrases:
        if phrase in news_lower:
            return news[:300]

    if status == "a":
        return "Available according to current FPL status."

    return (
        "No specific return date stated in the "
        "current FPL update."
    )


def build_x_post(
    player,
    event_type,
    fixture
):
    status_text = get_status(
        player["status"]
    )

    chance = player["chance_next"]

    if chance is None:
        chance_text = "Unknown"
    else:
        chance_text = f"{chance}%"

    fixture_text = ""

    if fixture:
        fixture_text = (
            f"\n📅 Next: "
            f"{fixture['opponent']} "
            f"({fixture['home_away']})"
            f" • FDR {fixture['difficulty']}/5"
        )

    takeaway = create_takeaway(
        player,
        fixture
    )

    text = (
        f"🚨 {event_type}\n\n"
        f"{player['name']} "
        f"({player['team']})\n"
        f"🏥 Status: {status_text}\n"
        f"⚽ Chance: {chance_text}"
        f"{fixture_text}\n\n"
        f"🎯 FPL Takeaway: "
        f"{takeaway}\n\n"
        "#FPL #FPLNews #FPLInjury"
    )

    return text[:280]


def build_embed(
    player,
    event_type,
    gameweek,
    fixture
):
    style = get_style(
        event_type
    )

    chance = player["chance_next"]

    chance_text = (
        "Unknown"
        if chance is None
        else f"{chance}%"
    )

    ownership = format_ownership(
        player["ownership"]
    )

    price = format_price(
        player["now_cost"]
    )

    description = create_description(
        player,
        event_type
    )

    takeaway = create_takeaway(
        player,
        fixture
    )

    expected_return = create_expected_return(
        player["news"],
        player["status"]
    )

    embed = {
        "title": (
            f"{style['icon']} "
            f"FPL VORTEX • {event_type}"
        ),
        "description": (
            f"**{player['name']}**\n"
            f"{player['team']} • "
            f"{player['position']} • "
            f"{price}\n\n"
            f"{description}"
        ),
        "color": style["color"],
        "fields": [
            {
                "name": "🏥 Status",
                "value": (
                    f"**{get_status(player['status'])}**"
                ),
                "inline": True,
            },
            {
                "name": "⚽ Chance of Playing",
                "value": f"**{chance_text}**",
                "inline": True,
            },
            {
                "name": "📈 Ownership",
                "value": f"**{ownership}**",
                "inline": True,
            },
            {
                "name": "📅 Expected Return",
                "value": expected_return[:1024],
                "inline": False,
            },
            {
                "name": "🎯 FPL Takeaway",
                "value": takeaway[:1024],
                "inline": False,
            },
        ],
        "footer": {
            "text": (
                f"FPL Vortex • GW{gameweek} • "
                "Official FPL data • "
                "#FPL #FPLNews #FPLInjury"
            )
        },
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    if fixture:
        fixture_text = (
            f"GW{fixture['event']} • "
            f"{fixture['home_away']} vs "
            f"{fixture['opponent']} • "
            f"FDR {fixture['difficulty']}/5"
        )

        embed["fields"].append(
            {
                "name": "📆 Next Fixture",
                "value": fixture_text,
                "inline": False,
            }
        )

    player_image = get_player_image(
        player["photo"]
    )

    team_logo = get_team_logo(
        player["team_code"]
    )

    if player_image:
        embed["thumbnail"] = {
            "url": player_image
        }

    if team_logo:
        embed["author"] = {
            "name": (
                f"{player['team']} • "
                f"FPL Vortex Injury News"
            ),
            "icon_url": team_logo,
        }

    return embed


def build_test_embed():
    return {
        "title": (
            "🚨 FPL VORTEX • "
            "INJURY NEWS ENGINE"
        ),
        "description": (
            "**Discord rich embed test successful.**\n\n"
            "The injury engine is ready to monitor "
            "FPL player availability changes."
        ),
        "color": 0x3498DB,
        "fields": [
            {
                "name": "🏥 Monitoring",
                "value": (
                    "Injuries, doubts, suspensions, "
                    "returns and availability changes."
                ),
                "inline": False,
            },
            {
                "name": "📊 Data",
                "value": "Official FPL data",
                "inline": True,
            },
            {
                "name": "📡 Destination",
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


def build_player_record(
    player,
    teams_by_id
):
    chance_next = player.get(
        "chance_of_playing_next_round"
    )

    chance_this = player.get(
        "chance_of_playing_this_round"
    )

    news = clean_text(
        player.get("news")
    )

    status = player.get(
        "status"
    ) or "a"

    relevant = (
        status != "a"
        or chance_next is not None
        or chance_this is not None
        or bool(news)
    )

    if not relevant:
        return None

    team = teams_by_id.get(
        player.get("team"),
        {}
    )

    first_name = (
        player.get("first_name")
        or ""
    ).strip()

    second_name = (
        player.get("second_name")
        or ""
    ).strip()

    return {
        "name": (
            f"{first_name} "
            f"{second_name}"
        ).strip(),
        "team": team.get(
            "name",
            "Unknown"
        ),
        "team_short": team.get(
            "short_name",
            "UNK"
        ),
        "team_code": team.get(
            "code"
        ),
        "team_id": player.get(
            "team"
        ),
        "position": get_position(
            player.get("element_type")
        ),
        "now_cost": player.get(
            "now_cost",
            0
        ),
        "ownership": player.get(
            "selected_by_percent",
            "0.0"
        ),
        "chance_next": chance_next,
        "chance_this": chance_this,
        "status": status,
        "news": news,
        "news_added": player.get(
            "news_added"
        ),
        "photo": player.get(
            "photo"
        ),
        "code": player.get(
            "code"
        ),
    }


def main():
    if TEST_MODE:
        send_discord_embed(
            build_test_embed()
        )

        print(
            "Rich Discord test sent successfully."
        )

        return

    print("Fetching FPL data...")

    data = fetch_json(
        FPL_API_URL
    )

    print("Fetching future fixtures...")

    fixtures = fetch_json(
        FPL_FIXTURES_URL
    )

    teams_by_id = {
        team["id"]: team
        for team in data.get(
            "teams",
            []
        )
    }

    current_event = next(
        (
            event
            for event in data.get(
                "events",
                []
            )
            if event.get(
                "is_current"
            )
        ),
        None
    )

    if current_event:
        gameweek = current_event.get(
            "id",
            "?"
        )
    else:
        gameweek = "?"

    previous = load_state()

    current = {}
    changes = []

    for player in data.get(
        "elements",
        []
    ):
        record = build_player_record(
            player,
            teams_by_id
        )

        if record is None:
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
                    player_id,
                    old_record,
                    record
                )
            )

    if not previous:
        save_state(current)

        print(
            "Initial injury baseline created."
        )

        print(
            f"Tracked players: "
            f"{len(current)}"
        )

        return

    for (
        player_id,
        old_record,
        new_record
    ) in changes:

        event_type = get_event_type(
            old_record,
            new_record
        )

        fixture = get_next_fixture(
            new_record["team_id"],
            fixtures,
            teams_by_id
        )

        embed = build_embed(
            new_record,
            event_type,
            gameweek,
            fixture
        )

        send_discord_embed(
            embed
        )

        x_post = build_x_post(
            new_record,
            event_type,
            fixture
        )

        save_x_draft(
            player_id,
            {
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "player": new_record["name"],
                "event_type": event_type,
                "text": x_post,
            }
        )

        print(
            f"Posted Discord alert: "
            f"{new_record['name']} "
            f"• {event_type}"
        )

    save_state(current)

    print(
        "Monitoring complete."
    )

    print(
        f"Changes detected: "
        f"{len(changes)}"
    )


if __name__ == "__main__":
    main()
