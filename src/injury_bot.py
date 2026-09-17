import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont


FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/?future=1"

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
RUN_MODE = os.environ.get("TEST_MODE", "monitor").lower()

STATE_FILE = Path("data/injury_state.json")
X_DRAFT_FILE = Path("data/x_drafts.json")

WIDTH = 1600

BACKGROUND = (8, 15, 28)
PANEL = (15, 27, 45)
ROW = (18, 32, 52)
BORDER = (38, 57, 79)

WHITE = (242, 246, 250)
MUTED = (157, 174, 192)
PLAYER_COLOR = (79, 190, 255)
BLACK = (8, 10, 12)

CATEGORY_STYLE = {
    "INJURY": {
        "label": "INJURY UPDATE",
        "symbol": "!",
        "header": (220, 55, 55),
    },
    "DOUBT": {
        "label": "FITNESS DOUBT",
        "symbol": "!",
        "header": (236, 184, 45),
    },
    "SUSPENSION": {
        "label": "SUSPENSION UPDATE",
        "symbol": "X",
        "header": (205, 55, 55),
    },
    "AVAILABLE": {
        "label": "AVAILABLE",
        "symbol": "✓",
        "header": (57, 184, 103),
    },
}


POSITION_TEXT = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


STATUS_TEXT = {
    "a": "Available",
    "d": "Doubt",
    "i": "Injured",
    "s": "Suspended",
    "u": "Unavailable",
}


def fetch_json(url):
    response = requests.get(
        url,
        headers={
            "User-Agent": "FPL-Vortex-Injury-Bot/1.0",
            "Accept": "application/json",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def download_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "FPL-Vortex-Injury-Bot/1.0",
            },
            timeout=20,
        )

        response.raise_for_status()

        return Image.open(
            BytesIO(response.content)
        ).convert("RGBA")

    except Exception as exc:
        print(
            f"Image download failed: {exc}"
        )
        return None


def load_font(size, bold=False):
    candidates = []

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size,
            )

    return ImageFont.load_default()


def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        (text or "").strip(),
    )


def get_position(element_type):
    return POSITION_TEXT.get(
        element_type,
        "UNK",
    )


def get_status(status):
    return STATUS_TEXT.get(
        status,
        status or "Unknown",
    )


def format_price(value):
    try:
        return f"£{float(value) / 10:.1f}m"
    except Exception:
        return "£0.0m"


def format_ownership(value):
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "0.0%"


def shorten_news(news, limit=70):
    text = clean_text(news)

    if not text:
        return "No additional update"

    if len(text) <= limit:
        return text

    shortened = text[:limit].rsplit(
        " ",
        1,
    )[0]

    return f"{shortened}..."


def extract_expected_return(news):
    news = clean_text(news)

    if not news:
        return "TBC"

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

        r"\bGW\s*\d+\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            news,
            re.IGNORECASE,
        )

        if match:
            return match.group(0)

    return "TBC"


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


def build_player_record(
    player,
    teams_by_id,
):
    team = teams_by_id.get(
        player.get("team"),
        {},
    )

    return {
        "name": (
            f"{player.get('first_name', '').strip()} "
            f"{player.get('second_name', '').strip()}"
        ).strip(),

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
            "chance_of_playing_next_round",
        ),

        "chance_this": player.get(
            "chance_of_playing_this_round",
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
    if not record:
        return False

    return (
        record.get("status") != "a"
        or record.get("chance_next") is not None
        or record.get("chance_this") is not None
        or bool(record.get("news"))
    )


def classify_event(
    old_record,
    new_record,
):
    old_status = (
        old_record.get("status", "a")
        if old_record
        else "a"
    )

    new_status = new_record.get(
        "status",
        "a",
    )

    if new_status == "i":
        return "INJURY"

    if new_status == "d":
        return "DOUBT"

    if new_status == "s":
        return "SUSPENSION"

    if new_status == "a":
        if old_status in (
            "i",
            "d",
            "u",
        ):
            return "AVAILABLE"

        if old_record:
            if (
                old_record.get("chance_next")
                != new_record.get("chance_next")
            ):
                return "AVAILABLE"

    if new_record.get("news"):
        return "INJURY"

    return "AVAILABLE"


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

        home = fixture.get("team_h")
        away = fixture.get("team_a")

        if (
            home != player_team_id
            and away != player_team_id
        ):
            continue

        if home == player_team_id:
            opponent = teams_by_id.get(
                away,
                {},
            ).get(
                "short_name",
                "UNK",
            )

            home_away = "H"

            difficulty = fixture.get(
                "team_h_difficulty"
            )

        else:
            opponent = teams_by_id.get(
                home,
                {},
            ).get(
                "short_name",
                "UNK",
            )

            home_away = "A"

            difficulty = fixture.get(
                "team_a_difficulty"
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


def build_short_update(player):
    news = shorten_news(
        player.get("news"),
        60,
    )

    chance = player.get(
        "chance_next"
    )

    chance_text = (
        "?"
        if chance is None
        else f"{chance}%"
    )

    return_text = extract_expected_return(
        player.get("news")
    )

    status = player.get(
        "status"
    )

    if status == "s":
        return (
            f"Suspended • "
            f"Return {return_text}"
        )

    if status == "a":
        if player.get("news"):
            return (
                f"{news} • "
                f"{chance_text} • "
                f"Available"
            )

        return (
            f"Available • "
            f"{chance_text}"
        )

    return (
        f"{news} • "
        f"{chance_text} • "
        f"Return {return_text}"
    )


def build_takeaway(category):
    if category == "INJURY":
        return (
            "If any are in your squad, monitor the next confirmed update before transferring."
        )

    if category == "DOUBT":
        return (
            "If any are in your squad, hold fire and monitor the next team news."
        )

    if category == "SUSPENSION":
        return (
            "Check the suspension timeline before using a transfer."
        )

    return (
        "The latest availability signal is positive, but monitor final team news."
    )


def build_x_post(
    category,
    players,
    fixture_lookup,
):
    style = CATEGORY_STYLE[
        category
    ]

    header = (
        f"{style['symbol']} "
        f"{style['label']}"
    )

    player_bits = []

    for player in players:

        chance = player.get(
            "chance_next"
        )

        chance_text = (
            "?"
            if chance is None
            else f"{chance}%"
        )

        player_bits.append(
            f"{player['name']} "
            f"({chance_text})"
        )

    names = ", ".join(
        player_bits
    )

    takeaway = build_takeaway(
        category
    )

    text = (
        f"{header}\n"
        f"{names}\n"
        f"{takeaway}\n"
        "#FPL #FPLNews #FPLInjury"
    )

    if len(text) <= 275:
        return text

    compact_names = ", ".join(
        player["name"]
        for player in players[:3]
    )

    text = (
        f"{header}\n"
        f"{compact_names}\n"
        f"#FPL #FPLNews #FPLInjury"
    )

    return text[:275]


def create_card(
    category,
    players,
    gameweek,
):
    style = CATEGORY_STYLE[
        category
    ]

    row_height = 128

    header_height = 105

    takeaway_height = 92

    footer_height = 55

    height = (
        header_height
        + len(players) * row_height
        + takeaway_height
        + footer_height
        + 40
    )

    image = Image.new(
        "RGB",
        (WIDTH, height),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(
        image
    )

    # ---------------------------------------------------------
    # FONTS
    # ---------------------------------------------------------

    header_font = load_font(
        48,
        bold=True,
    )

    player_font = load_font(
        31,
        bold=True,
    )

    metadata_font = load_font(
        21,
        bold=False,
    )

    update_font = load_font(
        22,
        bold=False,
    )

    takeaway_font = load_font(
        23,
        bold=True,
    )

    footer_font = load_font(
        19,
        bold=False,
    )

    # ---------------------------------------------------------
    # HEADER
    # ---------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            header_height,
        ),
        fill=style["header"],
    )

    header_text = (
        f"{style['symbol']} "
        f"FPL VORTEX • "
        f"{style['label']}"
    )

    draw.text(
        (
            55,
            31,
        ),
        header_text,
        font=header_font,
        fill=BLACK,
    )

    gw_text = f"GW{gameweek}"

    gw_width = (
        draw.textbbox(
            (0, 0),
            gw_text,
            font=metadata_font,
        )[2]
    )

    draw.text(
        (
            WIDTH - gw_width - 55,
            39,
        ),
        gw_text,
        font=metadata_font,
        fill=BLACK,
    )

    # ---------------------------------------------------------
    # PLAYER ROWS
    # ---------------------------------------------------------

    y = header_height + 15

    for index, player in enumerate(
        players
    ):
        row_top = y

        row_bottom = (
            y + row_height - 10
        )

        draw.rounded_rectangle(
            (
                40,
                row_top,
                WIDTH - 40,
                row_bottom,
            ),
            radius=20,
            fill=ROW,
            outline=BORDER,
            width=2,
        )

        # Player photo.
        player_image = download_image(
            get_player_image(
                player.get("photo")
            )
        )

        image_box = 86

        if player_image:

            player_image.thumbnail(
                (
                    image_box,
                    image_box,
                ),
                Image.Resampling.LANCZOS,
            )

            px = 65

            py = (
                row_top
                + 18
                + (
                    image_box
                    - player_image.height
                ) // 2
            )

            mask = Image.new(
                "L",
                (
                    image_box,
                    image_box,
                ),
                0,
            )

            mask_draw = ImageDraw.Draw(
                mask
            )

            mask_draw.ellipse(
                (
                    0,
                    0,
                    image_box,
                    image_box,
                ),
                fill=255,
            )

            image.paste(
                player_image,
                (
                    px,
                    py,
                ),
                mask,
            )

        else:

            draw.ellipse(
                (
                    65,
                    row_top + 18,
                    65 + image_box,
                    row_top + 18 + image_box,
                ),
                fill=(31, 50, 72),
            )

            initials = (
                player["name"][:1]
                or "F"
            )

            initials_font = load_font(
                38,
                bold=True,
            )

            draw.text(
                (
                    91,
                    row_top + 34,
                ),
                initials,
                font=initials_font,
                fill=PLAYER_COLOR,
            )

        # Text start.
        text_x = 180

        # Player name.
        draw.text(
            (
                text_x,
                row_top + 14,
            ),
            player["name"],
            font=player_font,
            fill=PLAYER_COLOR,
        )

        # Team crest.
        crest = download_image(
            get_team_logo(
                player.get("team_code")
            )
        )

        crest_x = text_x

        crest_y = row_top + 57

        if crest:

            crest.thumbnail(
                (
                    28,
                    28,
                ),
                Image.Resampling.LANCZOS,
            )

            image.paste(
                crest,
                (
                    crest_x,
                    crest_y,
                ),
                crest,
            )

            crest_x += 38

        # Metadata line.
        ownership = format_ownership(
            player.get(
                "ownership",
                "0.0",
            )
        )

        ownership_delta = player.get(
            "ownership_delta"
        )

        if ownership_delta is None:
            ownership_text = (
                f"OWN {ownership}"
            )
        else:
            sign = (
                "+"
                if ownership_delta > 0
                else ""
            )

            ownership_text = (
                f"OWN {ownership} • "
                f"Δ {sign}{ownership_delta:.1f}pp"
            )

        metadata = (
            f"{player['team']} • "
            f"{player['position']} • "
            f"{format_price(player['now_cost'])}"
            f" • "
            f"{ownership_text}"
        )

        draw.text(
            (
                crest_x,
                row_top + 59,
            ),
            metadata,
            font=metadata_font,
            fill=MUTED,
        )

        # Short injury/update line.
        update = build_short_update(
            player
        )

        update_start = text_x

        draw.text(
            (
                update_start,
                row_top + 91,
            ),
            update[:105],
            font=update_font,
            fill=WHITE,
        )

        y += row_height

    # ---------------------------------------------------------
    # TAKEAWAY
    # ---------------------------------------------------------

    takeaway_top = (
        header_height
        + len(players) * row_height
        + 5
    )

    draw.line(
        (
            55,
            takeaway_top,
            WIDTH - 55,
            takeaway_top,
        ),
        fill=BORDER,
        width=2,
    )

    takeaway = build_takeaway(
        category
    )

    draw.text(
        (
            55,
            takeaway_top + 17,
        ),
        "FPL TAKEAWAY",
        font=metadata_font,
        fill=style["header"],
    )

    draw.text(
        (
            245,
            takeaway_top + 17,
        ),
        takeaway[:145],
        font=takeaway_font,
        fill=WHITE,
    )

    # ---------------------------------------------------------
    # FOOTER
    # ---------------------------------------------------------

    footer_y = height - 48

    draw.text(
        (
            55,
            footer_y,
        ),
        (
            f"FPL VORTEX • "
            f"Official FPL data • "
            f"#FPL #FPLNews #FPLInjury"
        ),
        font=footer_font,
        fill=MUTED,
    )

    draw.text(
        (
            WIDTH - 250,
            footer_y,
        ),
        f"{len(players)} PLAYER"
        f"{'' if len(players) == 1 else 'S'}",
        font=footer_font,
        fill=MUTED,
    )

    return image


def send_discord_card(
    card,
    category,
):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL secret is missing"
        )

    buffer = BytesIO()

    card.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    buffer.seek(0)

    payload = {
        "username": "FPL Vortex Injury News",
        "content": (
            f"{CATEGORY_STYLE[category]['symbol']} "
            f"FPL Vortex • "
            f"{CATEGORY_STYLE[category]['label']}"
        ),
        "allowed_mentions": {
            "parse": [],
        },
    }

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        data={
            "payload_json": json.dumps(
                payload
            ),
        },
        files={
            "files[0]": (
                "fpl_vortex_injury.png",
                buffer,
                "image/png",
            ),
        },
        timeout=30,
    )

    response.raise_for_status()


def save_x_draft(
    category,
    players,
    gameweek,
):
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

    drafts[
        f"{datetime.now(timezone.utc).isoformat()}_{category}"
    ] = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "category": category,
        "gameweek": gameweek,
        "players": [
            player["name"]
            for player in players
        ],
        "text": build_x_post(
            category,
            players,
            {},
        ),
    }

    X_DRAFT_FILE.write_text(
        json.dumps(
            drafts,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_preview():
    data = fetch_json(
        FPL_API_URL
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
        if event.get("is_current")
    ),
    None,
)

next_event = next(
    (
        event
        for event in data.get(
            "events",
            []
        )
        if event.get("is_next")
    ),
    None,
)

unfinished_event = next(
    (
        event
        for event in data.get(
            "events",
            []
        )
        if not event.get("finished")
    ),
    None,
)

selected_event = (
    current_event
    or next_event
    or unfinished_event
)

gameweek = (
    selected_event.get(
        "id",
        "?"
    )
    if selected_event
    else "?"
)

    selected = []

    for player in data.get(
        "elements",
        []
    ):

        record = build_player_record(
            player,
            teams_by_id,
        )

        if not is_injury_related(
            record
        ):
            continue

        if record["status"] not in (
            "i",
            "d",
            "s",
            "a",
        ):
            continue

        selected.append(record)

        if len(selected) >= 10:
            break

    if not selected:
        raise RuntimeError(
            "No injury or availability "
            "players found."
        )

    grouped = {}

    for player in selected:

        category = classify_event(
            None,
            player,
        )

        grouped.setdefault(
            category,
            [],
        ).append(player)

    # Preview one category containing
    # multiple players whenever possible.
    category_order = [
        "INJURY",
        "DOUBT",
        "SUSPENSION",
        "AVAILABLE",
    ]

    preview_category = None

    for category in category_order:
        if len(
            grouped.get(
                category,
                [],
            )
        ) >= 2:
            preview_category = category
            break

    if preview_category is None:
        for category in category_order:
            if grouped.get(category):
                preview_category = category
                break

    players = grouped[
        preview_category
    ][:6]

    card = create_card(
        preview_category,
        players,
        gameweek,
    )

    send_discord_card(
        card,
        preview_category,
    )

    save_x_draft(
        preview_category,
        players,
        gameweek,
    )

    print(
        "Grouped graphic preview sent."
    )

    print(
        f"Category: {preview_category}"
    )

    print(
        "Players: "
        + ", ".join(
            player["name"]
            for player in players
        )
    )


def run_monitor():
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
        if event.get("is_current")
    ),
    None,
)

next_event = next(
    (
        event
        for event in data.get(
            "events",
            []
        )
        if event.get("is_next")
    ),
    None,
)

unfinished_event = next(
    (
        event
        for event in data.get(
            "events",
            []
        )
        if not event.get("finished")
    ),
    None,
)

selected_event = (
    current_event
    or next_event
    or unfinished_event
)

gameweek = (
    selected_event.get(
        "id",
        "?"
    )
    if selected_event
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

        current[player_id] = (
            build_player_record(
                player,
                teams_by_id,
            )
        )

    previous = load_state()

    if not previous:

        save_state(
            current
        )

        print(
            "Initial injury baseline created."
        )

        print(
            f"Players tracked: "
            f"{len(current)}"
        )

        return

    grouped_changes = {}

    for player_id, new_record in current.items():

        old_record = previous.get(
            player_id
        )

        if old_record == new_record:
            continue

        if not is_injury_related(
            old_record
        ) and not is_injury_related(
            new_record
        ):
            continue

        category = classify_event(
            old_record,
            new_record,
        )

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

        new_record["ownership_delta"] = (
            ownership_delta
        )

        grouped_changes.setdefault(
            category,
            [],
        ).append(
            new_record
        )

    for category, players in grouped_changes.items():

        players.sort(
            key=lambda player: (
                float(
                    player.get(
                        "ownership",
                        0,
                    )
                    or 0
                ),
            ),
            reverse=True,
        )

        # Keep one compact card per category.
        card = create_card(
            category,
            players,
            gameweek,
        )

        send_discord_card(
            card,
            category,
        )

        save_x_draft(
            category,
            players,
            gameweek,
        )

        print(
            f"Posted {category} card "
            f"with {len(players)} player(s)."
        )

    save_state(
        current
    )

    print(
        "FPL Vortex monitoring complete."
    )

    print(
        f"Categories posted: "
        f"{len(grouped_changes)}"
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


def main():

    if RUN_MODE == "preview":
        run_preview()
        return

    if RUN_MODE == "test":
        data = fetch_json(
            FPL_API_URL
        )

        teams_by_id = {
            team["id"]: team
            for team in data.get(
                "teams",
                []
            )
        }

        player = None

        for item in data.get(
            "elements",
            []
        ):
            record = build_player_record(
                item,
                teams_by_id,
            )

            if is_injury_related(
                record
            ):
                player = record
                break

        if player is None:
            raise RuntimeError(
                "No player available for test."
            )

        category = classify_event(
            None,
            player,
        )

        create_test = create_card(
            category,
            [player],
            "TEST",
        )

        send_discord_card(
            create_test,
            category,
        )

        print(
            "Graphic test sent."
        )

        return

    run_monitor()


if __name__ == "__main__":
    main()
