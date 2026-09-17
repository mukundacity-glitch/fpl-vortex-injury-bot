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
LOGO_FILE = Path("logo.png")


WIDTH = 1600

BACKGROUND = (218, 220, 223)
CARD = (235, 236, 238)
ROW = (245, 245, 246)
BORDER = (190, 192, 195)

WHITE = (20, 20, 20)
MUTED = (70, 70, 70)
PLAYER_COLOR = (30, 95, 150)
BLACK = (0, 0, 0)

RED = (222, 55, 55)
YELLOW = (235, 185, 45)
GREEN = (55, 184, 100)

FDR_COLORS = {
    1: (64, 190, 105),
    2: (116, 201, 93),
    3: (235, 194, 55),
    4: (239, 137, 52),
    5: (220, 61, 61),
}


CATEGORY_STYLE = {
    "INJURY": {
        "label": "INJURY UPDATE",
        "symbol": "!",
        "header": RED,
        "hash": "#FPL #FPLNews #FPLInjury",
    },
    "DOUBT": {
        "label": "FITNESS DOUBT",
        "symbol": "!",
        "header": YELLOW,
        "hash": "#FPL #FPLNews #FPLInjury",
    },
    "SUSPENSION": {
        "label": "SUSPENSION UPDATE",
        "symbol": "X",
        "header": RED,
        "hash": "#FPL #FPLNews #FPLSuspension",
    },
    "AVAILABLE": {
        "label": "AVAILABLE",
        "symbol": "✓",
        "header": GREEN,
        "hash": "#FPL #FPLNews",
    },
}


POSITION_TEXT = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


STATUS_TEXT = {
    "a": "AVAILABLE",
    "d": "DOUBT",
    "i": "INJURED",
    "s": "SUSPENDED",
    "u": "UNAVAILABLE",
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
            f"Could not download image: {exc}"
        )

        return None


def load_font(size, bold=False):
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


def text_width(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    return box[2] - box[0]


def fit_font(
    draw,
    text,
    max_width,
    start_size,
    min_size=16,
    bold=False,
):
    size = start_size

    while size >= min_size:
        font = load_font(
            size,
            bold=bold,
        )

        if text_width(
            draw,
            text,
            font,
        ) <= max_width:
            return font

        size -= 1

    return load_font(
        min_size,
        bold=bold,
    )


def shorten_text(
    text,
    max_chars,
):
    text = clean_text(text)

    if not text:
        return "No update provided"

    if len(text) <= max_chars:
        return text

    trimmed = text[:max_chars].rsplit(
        " ",
        1,
    )[0]

    return f"{trimmed}..."


def get_position(element_type):
    return POSITION_TEXT.get(
        element_type,
        "UNK",
    )


def get_status(status):
    return STATUS_TEXT.get(
        status,
        status or "UNKNOWN",
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


def get_fdr_color(difficulty):
    try:
        value = int(difficulty)
    except Exception:
        value = 3

    return FDR_COLORS.get(
        value,
        FDR_COLORS[3],
    )


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


def is_relevant(record):
    if not record:
        return False

    return (
        record.get("status") != "a"
        or record.get("chance_next") is not None
        or record.get("chance_this") is not None
        or bool(record.get("news"))
    )


def classify_category(
    old_record,
    new_record,
):
    status = new_record.get(
        "status",
        "a",
    )

    if status == "i":
        return "INJURY"

    if status == "d":
        return "DOUBT"

    if status == "s":
        return "SUSPENSION"

    if status == "a":

        if old_record:

            old_status = old_record.get(
                "status",
                "a",
            )

            if old_status in (
                "i",
                "d",
                "u",
            ):
                return "AVAILABLE"

            if (
                old_record.get(
                    "chance_next"
                )
                != new_record.get(
                    "chance_next"
                )
            ):
                return "AVAILABLE"

        return "AVAILABLE"

    return "INJURY"


def get_next_fixture(
    player_team_id,
    fixtures,
    teams_by_id,
):
    options = []

    for fixture in fixtures:

        if fixture.get("finished"):
            continue

        event = fixture.get(
            "event"
        )

        if event is None:
            continue

        home = fixture.get(
            "team_h"
        )

        away = fixture.get(
            "team_a"
        )

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

        options.append(
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

    options.sort(
        key=lambda item: (
            item["event"],
            item["kickoff"] or "",
        )
    )

    return (
        options[0]
        if options
        else None
    )


def build_takeaway(category):
    if category == "INJURY":
        return (
            "Monitor the next confirmed update before making a transfer."
        )

    if category == "DOUBT":
        return (
            "Hold fire and monitor final team news before the deadline."
        )

    if category == "SUSPENSION":
        return (
            "Check the suspension timeline before using a transfer."
        )

    return (
        "Availability is positive, but monitor final team news."
    )


def load_logo():
    if not LOGO_FILE.exists():
        print(
            "logo.png not found. Continuing without logo."
        )

        return None

    try:
        return Image.open(
            LOGO_FILE
        ).convert("RGBA")
    except Exception as exc:
        print(
            f"Could not load logo.png: {exc}"
        )

        return None


def paste_contain(
    base,
    image,
    box,
):
    if image is None:
        return

    x1, y1, x2, y2 = box

    max_width = x2 - x1
    max_height = y2 - y1

    image = image.copy()

    image.thumbnail(
        (
            max_width,
            max_height,
        ),
        Image.Resampling.LANCZOS,
    )

    x = x1 + (
        max_width - image.width
    ) // 2

    y = y1 + (
        max_height - image.height
    ) // 2

    base.alpha_composite(
        image,
        (
            x,
            y,
        ),
    )


def create_card(
    category,
    players,
    gameweek,
):
    style = CATEGORY_STYLE[
        category
    ]

    logo = load_logo()

    header_height = 108
    row_height = 118
    takeaway_height = 82
    footer_height = 48

    height = (
        header_height
        + row_height * len(players)
        + takeaway_height
        + footer_height
        + 24
    )

    canvas = Image.new(
        "RGBA",
        (
            WIDTH,
            height,
        ),
        BACKGROUND + (255,),
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # ---------------------------------------------------------
    # FONTS
    # ---------------------------------------------------------

    header_font = load_font(
        52,
        bold=True,
    )

    gameweek_font = load_font(
        30,
        bold=True,
    )

    player_font = load_font(
        44,
        bold=True,
    )

    meta_font = load_font(
        27,
        bold=True,
    )

    update_font = load_font(
        27,
        bold=False,
    )

    small_font = load_font(
        22,
        bold=False,
    )

    takeaway_font = fit_font(
        draw,
        build_takeaway(
            category
        ),
        1150,
        28,
        min_size=20,
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
        fill=style["header"] + (255,),
    )

    paste_contain(
        canvas,
        logo,
        (
            38,
            10,
            132,
            98,
        ),
    )

    header_text = (
        f"{style['symbol']} "
        f"{style['label']}"
    )

    draw.text(
        (
            148,
            26,
        ),
        header_text,
        font=header_font,
        fill=BLACK,
    )

    gw_text = f"GW{gameweek}"

    gw_width = text_width(
        draw,
        gw_text,
        gameweek_font,
    )

    draw.text(
        (
            WIDTH - gw_width - 45,
            36,
        ),
        gw_text,
        font=gameweek_font,
        fill=BLACK,
    )

    # ---------------------------------------------------------
    # PLAYER ROWS
    # ---------------------------------------------------------

    y = header_height + 10

    for player in players:

        row_top = y

        row_bottom = (
            y
            + row_height
            - 7
        )

        draw.rounded_rectangle(
            (
                32,
                row_top,
                WIDTH - 32,
                row_bottom,
            ),
            radius=18,
            fill=ROW + (255,),
            outline=BORDER + (255,),
            width=2,
        )

        # -----------------------------------------------------
        # PLAYER PHOTO
        # -----------------------------------------------------

        player_image = download_image(
            get_player_image(
                player.get("photo")
            )
        )

        image_box = 96

        if player_image:

            player_image.thumbnail(
                (
                    image_box,
                    image_box,
                ),
                Image.Resampling.LANCZOS,
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

            photo_layer = Image.new(
                "RGBA",
                (
                    image_box,
                    image_box,
                ),
                (0, 0, 0, 0),
            )

            photo_x = (
                image_box
                - player_image.width
            ) // 2

            photo_y = (
                image_box
                - player_image.height
            ) // 2

            photo_layer.alpha_composite(
                player_image,
                (
                    photo_x,
                    photo_y,
                ),
            )

            photo_layer.putalpha(
                mask
            )

            canvas.alpha_composite(
                photo_layer,
                (
                    50,
                    row_top + 10,
                ),
            )

        # -----------------------------------------------------
        # PLAYER INFORMATION
        # -----------------------------------------------------

        text_x = 170

        draw.text(
            (
                text_x,
                row_top + 8,
            ),
            player["name"],
            font=player_font,
            fill=PLAYER_COLOR,
        )

        # -----------------------------------------------------
        # TEAM CREST + TEAM / POSITION / PRICE
        # -----------------------------------------------------

        crest = download_image(
            get_team_logo(
                player.get("team_code")
            )
        )

        crest_x = text_x
        crest_y = row_top + 58
        crest_box = 26

        if crest:

            paste_contain(
                canvas,
                crest,
                (
                    crest_x,
                    crest_y,
                    crest_x + crest_box,
                    crest_y + crest_box,
                ),
            )

            crest_x += 35

        metadata = (
            f"{player['team']} • "
            f"{player['position']} • "
            f"{format_price(player['now_cost'])}"
        )

        draw.text(
            (
                crest_x,
                row_top + 57,
            ),
            metadata,
            font=meta_font,
            fill=BLACK,
        )

        # -----------------------------------------------------
        # OWNERSHIP + CHANGE
        # -----------------------------------------------------

        ownership = format_ownership(
            player.get(
                "ownership",
                "0.0",
            )
        )

        delta = player.get(
            "ownership_delta"
        )

        if delta is None:

            ownership_text = (
                f"OWN {ownership}"
            )

        else:

            sign = (
                "+"
                if delta > 0
                else ""
            )

            ownership_text = (
                f"OWN {ownership} • "
                f"Δ {sign}{delta:.1f}pp"
            )

        ownership_width = text_width(
            draw,
            ownership_text,
            small_font,
        )

        draw.text(
            (
                WIDTH
                - ownership_width
                - 70,
                row_top + 18,
            ),
            ownership_text,
            font=small_font,
            fill=MUTED,
        )

        # -----------------------------------------------------
        # SHORT UPDATE LINE
        # -----------------------------------------------------

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

        if player["status"] == "s":

            update_line = (
                f"SUSPENDED • "
                f"Return {return_text}"
            )

        elif player["status"] == "a":

            update_line = (
                f"AVAILABLE • "
                f"Chance {chance_text}"
            )

        else:

            news = shorten_text(
                player.get("news"),
                48,
            )

            update_line = (
                f"{news} • "
                f"{chance_text} • "
                f"Return {return_text}"
            )

        update_line = shorten_text(
            update_line,
            110,
        )

        update_font_actual = fit_font(
            draw,
            update_line,
            1370,
            27,
            min_size=18,
            bold=False,
        )

        draw.text(
            (
                text_x,
                row_top + 87,
            ),
            update_line,
            font=update_font_actual,
            fill=BLACK,
        )

        # -----------------------------------------------------
        # FDR
        # -----------------------------------------------------

        fixture = player.get(
            "fixture"
        )

        if fixture:

            try:
                fdr = int(
                    fixture.get(
                        "difficulty",
                        3,
                    )
                )
            except Exception:
                fdr = 3

            fdr = max(
                1,
                min(
                    5,
                    fdr,
                ),
            )

            fdr_color = get_fdr_color(
                fdr
            )

            fdr_x = WIDTH - 230

            draw.text(
                (
                    fdr_x,
                    row_top + 56,
                ),
                "FDR",
                font=small_font,
                fill=MUTED,
            )

            circle_x = (
                fdr_x + 58
            )

            draw.ellipse(
                (
                    circle_x,
                    row_top + 59,
                    circle_x + 22,
                    row_top + 81,
                ),
                fill=fdr_color,
            )

            draw.text(
                (
                    circle_x + 32,
                    row_top + 55,
                ),
                f"{fdr}/5",
                font=small_font,
                fill=BLACK,
            )

        y += row_height

    # ---------------------------------------------------------
    # FPL TAKEAWAY
    # ---------------------------------------------------------

    takeaway_y = (
        header_height
        + row_height * len(players)
        + 2
    )

    draw.line(
        (
            45,
            takeaway_y,
            WIDTH - 45,
            takeaway_y,
        ),
        fill=BORDER,
        width=2,
    )

    takeaway_label_font = load_font(
        21,
        bold=True,
    )

    draw.text(
        (
            55,
            takeaway_y + 18,
        ),
        "FPL TAKEAWAY",
        font=takeaway_label_font,
        fill=style["header"],
    )

    draw.text(
        (
            250,
            takeaway_y + 16,
        ),
        build_takeaway(
            category
        ),
        font=takeaway_font,
        fill=BLACK,
    )

    # ---------------------------------------------------------
    # FOOTER
    # ---------------------------------------------------------

    footer_y = (
        height
        - footer_height
        + 9
    )

    footer_font = load_font(
        18,
        bold=False,
    )

    left_footer = "FPL VORTEX"

    right_footer = (
        f"Official FPL Data • "
        f"{style['hash']}"
    )

    draw.text(
        (
            55,
            footer_y,
        ),
        left_footer,
        font=footer_font,
        fill=MUTED,
    )

    right_width = text_width(
        draw,
        right_footer,
        footer_font,
    )

    draw.text(
        (
            WIDTH
            - right_width
            - 55,
            footer_y,
        ),
        right_footer,
        font=footer_font,
        fill=MUTED,
    )

    return canvas.convert(
        "RGB"
    )


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

    style = CATEGORY_STYLE[
        category
    ]

    payload = {
        "username": "FPL Vortex Injury News",
        "content": (
            f"{style['symbol']} "
            f"FPL Vortex • "
            f"{style['label']}"
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


def build_x_post(
    category,
    players,
):
    style = CATEGORY_STYLE[
        category
    ]

    names = ", ".join(
        player["name"]
        for player in players
    )

    chance_values = []

    for player in players:
        chance = player.get(
            "chance_next"
        )

        if chance is not None:
            chance_values.append(
                str(chance)
            )

    chance_text = ""

    if chance_values:
        chance_text = (
            f" | Chance "
            f"{'/'.join(chance_values[:3])}%"
        )

    text = (
        f"{style['symbol']} "
        f"{style['label']}\n"
        f"{names}"
        f"{chance_text}\n"
        f"{build_takeaway(category)}\n"
        f"{style['hash']}"
    )

    if len(text) <= 275:
        return text

    compact_names = ", ".join(
        player["name"]
        for player in players[:3]
    )

    text = (
        f"{style['symbol']} "
        f"{style['label']}\n"
        f"{compact_names}\n"
        f"{style['hash']}"
    )

    return text[:275]


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

    key = (
        f"{datetime.now(timezone.utc).isoformat()}"
        f"_{category}"
    )

    drafts[key] = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "gameweek": gameweek,
        "category": category,
        "players": [
            player["name"]
            for player in players
        ],
        "text": build_x_post(
            category,
            players,
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


def find_preview_players(
    data,
    teams_by_id,
):
    selected = []

    for player in data.get(
        "elements",
        []
    ):

        record = build_player_record(
            player,
            teams_by_id,
        )

        if not is_relevant(
            record
        ):
            continue

        selected.append(
            record
        )

        if len(selected) >= 12:
            break

    return selected


def current_gameweek(data):
    current = next(
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

    if current:
        return current.get(
            "id",
            "?",
        )

    next_event = next(
        (
            event
            for event in data.get(
                "events",
                []
            )
            if event.get(
                "is_next"
            )
        ),
        None,
    )

    if next_event:
        return next_event.get(
            "id",
            "?",
        )

    unfinished = next(
        (
            event
            for event in data.get(
                "events",
                []
            )
            if not event.get(
                "finished"
            )
        ),
        None,
    )

    if unfinished:
        return unfinished.get(
            "id",
            "?",
        )

    return "?"


def run_preview():
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

    gameweek = current_gameweek(
        data
    )

    players = find_preview_players(
        data,
        teams_by_id,
    )

    if not players:
        raise RuntimeError(
            "No current injury or "
            "availability players found."
        )

    for player in players:

        fixture = get_next_fixture(
            player["team_id"],
            fixtures,
            teams_by_id,
        )

        player["fixture"] = fixture
        player["ownership_delta"] = None

    grouped = {}

    for player in players:

        category = classify_category(
            None,
            player,
        )

        grouped.setdefault(
            category,
            [],
        ).append(
            player
        )

    # Prefer a category with multiple players
    # for the preview.
    order = [
        "INJURY",
        "DOUBT",
        "SUSPENSION",
        "AVAILABLE",
    ]

    chosen_category = None

    for category in order:

        if len(
            grouped.get(
                category,
                [],
            )
        ) >= 2:

            chosen_category = category
            break

    if chosen_category is None:

        for category in order:

            if grouped.get(
                category
            ):

                chosen_category = category
                break

    preview_players = grouped[
        chosen_category
    ][:6]

    card = create_card(
        chosen_category,
        preview_players,
        gameweek,
    )

    send_discord_card(
        card,
        chosen_category,
    )

    save_x_draft(
        chosen_category,
        preview_players,
        gameweek,
    )

    print(
        "Graphic preview sent successfully."
    )

    print(
        f"Category: {chosen_category}"
    )

    print(
        "Players: "
        + ", ".join(
            player["name"]
            for player in preview_players
        )
    )


def run_test():
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

        if is_relevant(
            record
        ):
            player = record
            break

    if player is None:
        raise RuntimeError(
            "No player available for test."
        )

    category = classify_category(
        None,
        player,
    )

    card = create_card(
        category,
        [player],
        current_gameweek(
            data
        ),
    )

    send_discord_card(
        card,
        category,
    )

    print(
        "Single-player graphic test sent."
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

    gameweek = current_gameweek(
        data
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

    # First normal run creates the baseline.
    if not previous:

        save_state(
            current
        )

        print(
            "Initial FPL injury baseline created."
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

        old_relevant = is_relevant(
            old_record
        )

        new_relevant = is_relevant(
            new_record
        )

        if (
            not old_relevant
            and not new_relevant
        ):
            continue

        category = classify_category(
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

        fixture = get_next_fixture(
            new_record["team_id"],
            fixtures,
            teams_by_id,
        )

        new_record["fixture"] = fixture

        grouped_changes.setdefault(
            category,
            [],
        ).append(
            new_record
        )

    # One card per category.
    for category, players in grouped_changes.items():

        players.sort(
            key=lambda player: float(
                player.get(
                    "ownership",
                    0,
                ) or 0
            ),
            reverse=True,
        )

        # Discord remains compact while avoiding
        # an extremely tall single card.
        for start in range(
            0,
            len(players),
            8,
        ):

            batch = players[
                start:start + 8
            ]

            card = create_card(
                category,
                batch,
                gameweek,
            )

            send_discord_card(
                card,
                category,
            )

            save_x_draft(
                category,
                batch,
                gameweek,
            )

            print(
                f"Posted {category} card "
                f"with {len(batch)} player(s)."
            )

    save_state(
        current
    )

    print(
        "FPL Vortex injury monitoring complete."
    )

    print(
        f"Categories detected: "
        f"{len(grouped_changes)}"
    )

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
        run_test()
        return

    run_monitor()


if __name__ == "__main__":
    main()
