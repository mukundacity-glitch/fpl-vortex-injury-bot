import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
RUN_MODE = os.environ.get("TEST_MODE", "monitor").lower()

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
        return json.loads(response.read().decode("utf-8"))


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
                "parse": [],
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
        timeout=30,
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


def save_x_draft(player_id, draft):
    X_DRAFT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    drafts = {}

    if X_DRAFT_FILE.exists():
        try:
            drafts = json.loads(
                X_DRAFT_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            drafts = {}

    drafts[str(player_id)] = draft

    X_DRAFT_FILE.write_text(
        json.dumps(
            drafts,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def clean_text(text):
    text = (text or "").strip()
    return re.sub(r"\s+", " ", text)


def get_status(status):
    return STATUS_TEXT.get(
        status,
        status or "Unknown",
    )


def get_position(element_type):
    return POSITION_TEXT.get(
        element_type,
        "Unknown",
    )


def format_price(now_cost):
    try:
        return f"£{float(now_cost) / 10:.1f}m"
    except Exception:
        return "£0.0m"


def format_ownership(value):
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def get_player_image(photo):
    if not photo:
        return None

    photo_id = str(photo)

    if photo_id.endswith(".jpg"):
        photo_id = photo_id[:-4]

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


def get_style(event_type):
    return EVENT_STYLES.get(
        event_type,
        {
            "icon": "🚨",
            "color": 0x3498DB,
        },
    )


def build_player_record(player, teams_by_id):
    team = teams_by_id.get(
        player.get("team"),
        {},
    )

    first_name = (
        player.get("first_name") or ""
    ).strip()

    second_name = (
        player.get("second_name") or ""
    ).strip()

    return {
        "name": f"{first_name} {second_name}".strip(),
        "team": team.get(
            "name",
            "Unknown",
        ),
        "team_short": team.get(
            "short_name",
            "UNK",
        ),
        "team_code": team.get(
            "code",
        ),
        "team_id": player.get(
            "team",
        ),
        "position": get_position(
            player.get("element_type")
        ),
        "now_cost": player.get(
            "now_cost",
            0,
        ),
        "ownership": player.get(
            "selected_by_percent",
            "0.0",
        ),
        "chance_next": player.get(
            "chance_of_playing_next_round"
        ),
        "chance_this": player.get(
            "chance_of_playing_this_round"
        ),
        "status": player.get(
            "status"
        ) or "a",
        "news": clean_text(
            player.get("news")
        ),
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


def is_injury_related(record):
    return (
        record.get("status") != "a"
        or record.get("chance_next") is not None
        or record.get("chance_this") is not None
        or bool(record.get("news"))
    )


def get_event_type(old, new):
    if old is None:
        if new["status"] == "i":
            return "NEW INJURY"

        if new["status"] == "d":
            return "FITNESS DOUBT"

        if new["status"] == "s":
            return "SUSPENSION UPDATE"

        return "INJURY NEWS UPDATE"

    old_status = old.get("status", "a")
    new_status = new.get("status", "a")

    if old_status != new_status:
        if (
            old_status in ("i", "d", "u")
            and new_status == "a"
        ):
            return "RETURN UPDATE"

        if new_status == "i":
            return "NEW INJURY"

        if new_status == "d":
            return "FITNESS DOUBT"

        if new_status == "s":
            return "SUSPENSION UPDATE"

        return "AVAILABILITY UPDATE"

    if old.get("chance_next") != new.get("chance_next"):
        return "AVAILABILITY UPDATE"

    if old.get("chance_this") != new.get("chance_this"):
        return "AVAILABILITY UPDATE"

    if old.get("news") != new.get("news"):
        return "INJURY NEWS UPDATE"

    return "AVAILABILITY UPDATE"


def get_next_fixture(
    player_team_id,
    fixtures,
    teams_by_id,
):
    candidates = []

    for fixture in fixtures:
        if fixture.get("finished"):
            continue

        event = fixture.get("event")

        if event is None:
            continue

        home_team = fixture.get("team_h")
        away_team = fixture.get("team_a")

        if (
            home_team != player_team_id
            and away_team != player_team_id
        ):
            continue

        if home_team == player_team_id:
            opponent_id = away_team
            home_away = "H"
            difficulty = fixture.get(
                "team_h_difficulty"
            )
        else:
            opponent_id = home_team
            home_away = "A"
            difficulty = fixture.get(
                "team_a_difficulty"
            )

        opponent = teams_by_id.get(
            opponent_id,
            {},
        ).get(
            "short_name",
            "UNK",
        )

        candidates.append(
            {
                "event": event,
                "opponent": opponent,
                "home_away": home_away,
                "difficulty": difficulty,
                "kickoff": fixture.get(
                    "kickoff_time"
                ),
            }
        )

    candidates.sort(
        key=lambda item: (
            item["event"],
            item["kickoff"] or "",
        )
    )

    return (
        candidates[0]
        if candidates
        else None
    )


def extract_expected_return(news):
    news = clean_text(news)

    if not news:
        return "Not specified"

    patterns = [
        r"\b\d{1,2}\s+"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
        r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b",

        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
        r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            news,
            re.IGNORECASE,
        )

        if match:
            return match.group(0)

    gw_match = re.search(
        r"\bGW\s*(\d+)\b",
        news,
        re.IGNORECASE,
    )

    if gw_match:
        return f"GW{gw_match.group(1)}"

    return "Not specified"


def build_takeaway(
    player,
    fixture,
):
    name = player["name"]
    status = player["status"]
    chance = player["chance_next"]

    try:
        chance_value = (
            float(chance)
            if chance is not None
            else None
        )
    except Exception:
        chance_value = None

    if status == "i":
        if (
            chance_value is not None
            and chance_value <= 25
        ):
            return (
                f"If {name} is in your squad, "
                "prepare a replacement and monitor "
                "the next confirmed update."
            )

        return (
            f"If {name} is in your squad, "
            "monitor the next update before "
            "using a transfer."
        )

    if status == "d":
        if (
            chance_value is not None
            and chance_value <= 25
        ):
            return (
                f"If {name} is in your squad, "
                "have a backup ready before the deadline."
            )

        return (
            f"If {name} is in your squad, "
            "hold fire and monitor the next update."
        )

    if status == "s":
        return (
            f"If {name} is in your squad, "
            "check the suspension timeline before "
            "using a transfer."
        )

    if status == "a":
        return (
            f"If {name} is in your squad, "
            "the latest availability signal is positive."
        )

    return (
        f"If {name} is in your squad, "
        "monitor the next confirmed update."
    )


def build_embed(
    player,
    event_type,
    gameweek,
    fixture,
    ownership_delta,
):
    style = get_style(event_type)

    chance = player["chance_next"]

    chance_text = (
        "Unknown"
        if chance is None
        else f"{chance}%"
    )

    if ownership_delta is None:
        ownership_delta_text = "OWN Δ 0.0pp"
    else:
        sign = (
            "+"
            if ownership_delta > 0
            else ""
        )

        ownership_delta_text = (
            f"OWN Δ {sign}"
            f"{ownership_delta:.1f}pp"
        )

    takeaway = build_takeaway(
        player,
        fixture,
    )

    news = (
        player["news"]
        or "No additional update provided."
    )

    expected_return = extract_expected_return(
        player["news"]
    )

    embed = {
        "title": (
            f"{style['icon']} "
            f"FPL VORTEX • {event_type}"
        ),
        "description": (
            f"**{ownership_delta_text}**\n\n"
            f"**{player['name']}**\n"
            f"{player['position']} • "
            f"{format_price(player['now_cost'])}\n\n"
            f"🏥 Status: "
            f"**{get_status(player['status'])}**\n"
            f"⚽ Chance of Playing: "
            f"**{chance_text}**"
        ),
        "color": style["color"],
        "fields": [
            {
                "name": "📰 Update",
                "value": news[:500],
                "inline": False,
            },
            {
                "name": "📅 Expected Return",
                "value": expected_return,
                "inline": True,
            },
            {
                "name": "📈 Ownership",
                "value": format_ownership(
                    player["ownership"]
                ),
                "inline": True,
            },
            {
                "name": "🎯 FPL Takeaway",
                "value": takeaway[:300],
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
        embed["fields"].append(
            {
                "name": "📆 Next Fixture",
                "value": (
                    f"GW{fixture['event']} • "
                    f"{fixture['opponent']} "
                    f"({fixture['home_away']}) • "
                    f"FDR {fixture['difficulty']}/5"
                ),
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
            "name": player["team"],
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
            "**Compact injury-card system connected.**\n\n"
            "Player image, club crest, availability, "
            "ownership, fixture context and FPL takeaway "
            "are ready."
        ),
        "color": 0x3498DB,
        "fields": [
            {
                "name": "🏥 Monitoring",
                "value": (
                    "Injuries, doubts, returns, "
                    "suspensions and availability changes."
                ),
                "inline": False,
            },
            {
                "name": "📊 Source",
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


def build_x_post(
    player,
    event_type,
    fixture,
):
    status = get_status(
        player["status"]
    )

    chance = player["chance_next"]

    chance_text = (
        "?"
        if chance is None
        else f"{chance}%"
    )

    takeaway = build_takeaway(
        player,
        fixture,
    )

    text = (
        f"🚨 {event_type}\n"
        f"{player['name']} | "
        f"{status} | Chance {chance_text}\n"
        f"🎯 {takeaway}\n"
        f"#FPL #FPLNews #FPLInjury"
    )

    if len(text) <= 275:
        return text

    short_takeaway = (
        "Monitor the next confirmed update."
    )

    text = (
        f"🚨 {event_type}\n"
        f"{player['name']} | "
        f"{status} | Chance {chance_text}\n"
        f"🎯 {short_takeaway}\n"
        f"#FPL #FPLNews #FPLInjury"
    )

    return text[:275]


def preview_real_player():
    data = fetch_json(
        FPL_API_URL
    )

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
        None,
    )

    gameweek = (
        current_event.get(
            "id",
            "?"
        )
        if current_event
        else "?"
    )

    preview_record = None

    for player in data.get(
        "elements",
        []
    ):
        record = build_player_record(
            player,
            teams_by_id,
        )

        if is_injury_related(record):
            if (
                record["status"] in (
                    "i",
                    "d",
                    "s",
                )
                or record["news"]
            ):
                preview_record = record
                break

    if preview_record is None:
        raise RuntimeError(
            "No current injury or availability item "
            "was found in the FPL data."
        )

    fixture = get_next_fixture(
        preview_record["team_id"],
        fixtures,
        teams_by_id,
    )

    if preview_record["status"] == "i":
        event_type = "NEW INJURY"
    elif preview_record["status"] == "d":
        event_type = "FITNESS DOUBT"
    elif preview_record["status"] == "s":
        event_type = "SUSPENSION UPDATE"
    else:
        event_type = "INJURY NEWS UPDATE"

    embed = build_embed(
        preview_record,
        event_type,
        gameweek,
        fixture,
        None,
    )

    send_discord_embed(
        embed
    )

    x_post = build_x_post(
        preview_record,
        event_type,
        fixture,
    )

    save_x_draft(
        "preview",
        {
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "player": preview_record["name"],
            "event_type": event_type,
            "text": x_post,
        },
    )

    print(
        "Real FPL preview sent successfully."
    )

    print(
        f"Player: {preview_record['name']}"
    )

    print(
        f"Event: {event_type}"
    )


def run_monitor():
    print(
        "Fetching official FPL data..."
    )

    data = fetch_json(
        FPL_API_URL
    )

    print(
        "Fetching future fixtures..."
    )

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
        None,
    )

    gameweek = (
        current_event.get(
            "id",
            "?"
        )
        if current_event
        else "?"
    )

    current = {}

    for player in data.get(
        "elements",
        []
    ):
        player_id = str(
            player["id"]
        )

        current[player_id] = build_player_record(
            player,
            teams_by_id,
        )

    previous = load_state()

    if not previous:
        save_state(current)

        print(
            "Initial FPL injury baseline created."
        )

        print(
            f"Players tracked: {len(current)}"
        )

        return

    changes = []

    for player_id, new_record in current.items():
        old_record = previous.get(
            player_id
        )

        if old_record is None:
            continue

        if old_record == new_record:
            continue

        old_relevant = is_injury_related(
            old_record
        )

        new_relevant = is_injury_related(
            new_record
        )

        if not old_relevant and not new_relevant:
            continue

        try:
            old_ownership = float(
                old_record.get(
                    "ownership",
                    0,
                )
            )

            new_ownership = float(
                new_record.get(
                    "ownership",
                    0,
                )
            )

            ownership_delta = round(
                new_ownership -
                old_ownership,
                1,
            )
        except Exception:
            ownership_delta = None

        changes.append(
            (
                player_id,
                old_record,
                new_record,
                ownership_delta,
            )
        )

    for (
        player_id,
        old_record,
        new_record,
        ownership_delta,
    ) in changes:

        event_type = get_event_type(
            old_record,
            new_record,
        )

        fixture = get_next_fixture(
            new_record["team_id"],
            fixtures,
            teams_by_id,
        )

        embed = build_embed(
            new_record,
            event_type,
            gameweek,
            fixture,
            ownership_delta,
        )

        send_discord_embed(
            embed
        )

        x_post = build_x_post(
            new_record,
            event_type,
            fixture,
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
            },
        )

        print(
            f"Discord alert sent: "
            f"{new_record['name']} "
            f"| {event_type}"
        )

    save_state(current)

    print(
        "Monitoring complete."
    )

    print(
        f"Injury-related changes: "
        f"{len(changes)}"
    )


def main():
    if RUN_MODE == "test":
        send_discord_embed(
            build_test_embed()
        )

        print(
            "Discord test sent successfully."
        )

        return

    if RUN_MODE == "preview":
        preview_real_player()
        return

    run_monitor()


if __name__ == "__main__":
    main()
