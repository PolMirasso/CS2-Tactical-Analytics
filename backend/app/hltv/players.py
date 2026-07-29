from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.config import get_settings
from app.hltv.client import HLTVError, _flaresolverr_get, _impersonated_session

_MAP_CODES = {
    "d2": "de_dust2",
    "mrg": "de_mirage",
    "inf": "de_inferno",
    "nuke": "de_nuke",
    "ovp": "de_overpass",
    "anc": "de_ancient",
    "anb": "de_anubis",
    "trn": "de_train",
    "vtg": "de_vertigo",
    "cch": "de_cache",
    "cbl": "de_cobblestone",
    "tcn": "de_tuscan",
}

_TAGS = re.compile(r"<[^>]+>")
_NOISE = re.compile(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", re.S)
_TITLE = re.compile(r"<title>\s*(.*?)\s*</title>", re.S)
_TITLE_NAME = re.compile(r"^(?P<first>.+?) '(?P<nick>.+?)' (?P<last>.+?) Counter-Strike")


@dataclass
class PlayerHit:
    id: str
    nick: str
    name: str | None = None
    image: str | None = None
    country: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    retired: bool = False


@dataclass
class StatItem:
    label: str
    value: str


@dataclass
class RoleScore:
    role: str
    score: int  # HLTV scores each role 0-100


@dataclass
class MapStat:
    map_id: str 
    code: str
    maps_played: int
    kills: int
    deaths: int
    plus_minus: int
    rating: float | None


@dataclass
class MatchRow:
    match_date: date | None
    team: str | None
    opponent: str | None
    map_id: str
    kills: int | None
    deaths: int | None
    plus_minus: int | None
    rating: float | None
    url: str | None


@dataclass
class PlayerProfile:
    id: str
    nick: str
    name: str | None = None
    country: str | None = None
    image: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    rating: str | None = None
    rating_label: str | None = None
    ct_rating: str | None = None
    t_rating: str | None = None
    summary: list[StatItem] = field(default_factory=list)
    career: list[StatItem] = field(default_factory=list)
    roles: list[RoleScore] = field(default_factory=list)
    maps: list[MapStat] = field(default_factory=list)
    matches: list[MatchRow] = field(default_factory=list)


def _text(fragment: str) -> str:
    return _TAGS.sub("", fragment).replace("&nbsp;", " ").strip()


def _strip_noise(html: str) -> str:
    return _NOISE.sub("", html)


def search_players(query: str, *, limit: int = 10) -> list[PlayerHit]:
    """Look up players by nick via HLTV's JSON search endpoint (same one as teams)"""
    settings = get_settings()
    url = f"{settings.hltv_base_url}/search?term={query}"
    try:
        session = _impersonated_session()
        resp = session.get(url, timeout=settings.request_timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except HLTVError:
        raise
    except Exception as exc:
        raise HLTVError(f"player search failed: {exc}") from exc

    return _parse_player_hits(payload)[:limit]


def _parse_player_hits(payload: object) -> list[PlayerHit]:
    categories = payload if isinstance(payload, list) else [payload]
    hits: list[PlayerHit] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        for player in category.get("players", []) or []:
            if not isinstance(player, dict):
                continue
            pid = str(player.get("id", "")).strip()
            nick = (player.get("nickName") or "").strip()
            if not pid or not nick:
                continue
            first = (player.get("firstName") or "").strip()
            last = (player.get("lastName") or "").strip()
            team = player.get("team") if isinstance(player.get("team"), dict) else {}
            hits.append(
                PlayerHit(
                    id=pid,
                    nick=nick,
                    name=f"{first} {last}".strip() or None,
                    image=player.get("pictureUrl") or None,
                    country=_country_from_flag(player.get("flagUrl")),
                    team_id=_id_from_location(team.get("location")),
                    team_name=(team.get("name") or "").strip() or None,
                    retired=bool(player.get("retired")),
                )
            )
    return hits


def _country_from_flag(flag_url: object) -> str | None:
    if not isinstance(flag_url, str):
        return None
    m = re.search(r"/([A-Za-z]{2,3})\.gif", flag_url)
    return m.group(1).upper() if m else None


def _id_from_location(location: object) -> str | None:
    if not isinstance(location, str):
        return None
    m = re.search(r"/(?:team|player)/(\d+)/", location + "/")
    return m.group(1) if m else None


def fetch_player_profile(player_id: str) -> PlayerProfile:
    """Scrape a player's stats: the overview page plus the match history"""
    base = get_settings().hltv_base_url
    # The URL slug is cosmetic; HLTV resolves the player by id alone.
    overview = _flaresolverr_get(f"{base}/stats/players/{player_id}/-")
    profile = _parse_overview(overview, player_id)
    matches = _flaresolverr_get(f"{base}/stats/players/matches/{player_id}/-")
    _apply_match_history(profile, matches)
    return profile


def _parse_overview(html: str, player_id: str) -> PlayerProfile:
    body = _strip_noise(html)
    profile = PlayerProfile(id=str(player_id), nick=str(player_id))

    title = _TITLE.search(html)
    if title:
        named = _TITLE_NAME.match(_text(title.group(1)))
        if named:
            profile.nick = named.group("nick")
            profile.name = f"{named.group('first')} {named.group('last')}".strip()

    nick = re.search(r'class="context-item-name">(?:<[^>]+>)*\s*([^<]+)', body)
    if nick and nick.group(1).strip():
        profile.nick = nick.group(1).strip()

    flag = re.search(r'<img alt="([^"]*)"[^>]*class="context-item-flag', body)
    if flag:
        profile.country = flag.group(1) or None

    image = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if image:
        profile.image = image.group(1).replace("&amp;", "&")

    rating = re.search(r'player-summary-stat-box-rating-data-text">\s*([^<]+)', body)
    if rating:
        profile.rating = rating.group(1).strip()
    label = re.search(r'player-summary-stat-box-data-description-text[^"]*">\s*([^<]+)', body)
    if label:
        profile.rating_label = label.group(1).strip()

    for value, side in re.findall(
        r'player-summary-stat-box-side-rating-background"></div>\s*([\d.]+)\s*'
        r'<div class="player-summary-stat-box-side-rating-text">\s*([^<]+)',
        body,
    ):
        if side.strip().upper().startswith("CT"):
            profile.ct_rating = value
        elif side.strip().upper().startswith("T"):
            profile.t_rating = value

    profile.summary = _parse_summary_box(body)
    profile.career = [
        StatItem(label=lbl.strip(), value=val.strip())
        for lbl, val in re.findall(
            r'<div class="stats-row"[^>]*><span[^>]*>([^<]+)</span><span[^>]*>([^<]+)</span>',
            body,
        )
    ]
    profile.roles = _parse_roles(body)
    return profile


def _parse_summary_box(body: str) -> list[StatItem]:
    # Each stat is a value div followed by a label div
    items: list[StatItem] = []
    blocks = re.findall(
        r'<div class="player-summary-stat-box-data-wrapper[^"]*">(.*?)'
        r'<div class="player-summary-stat-box-breakdown-bar">',
        body,
        re.S,
    )
    for block in blocks:
        value = re.search(r'player-summary-stat-box-data[^"]*">(.*?)</div>', block, re.S)
        label = re.search(r'player-summary-stat-box-data-text[^"]*">\s*([^<]+)', block, re.S)
        if not value or not label:
            continue
        text = _text(value.group(1))
        if text and text != "-":
            items.append(StatItem(label=label.group(1).strip(), value=text))
    return items


def _parse_roles(body: str) -> list[RoleScore]:
    # One section per role
    roles: list[RoleScore] = []
    sections = list(re.finditer(r'<div class="role-stats-section role-([a-z]+)"', body))
    for i, section in enumerate(sections):
        end = sections[i + 1].start() if i + 1 < len(sections) else len(body)
        score = re.search(r'<div class="row-stats-section-score">(\d+)', body[section.start():end])
        if score:
            roles.append(RoleScore(role=section.group(1), score=int(score.group(1))))
    return roles


def _apply_match_history(profile: PlayerProfile, html: str) -> None:
    rows = _parse_match_rows(html)
    profile.matches = rows
    profile.maps = _aggregate_maps(rows)
    # The most recent match names the player's current team
    for row in rows:
        if row.team:
            profile.team_name = row.team
            break


def _parse_match_rows(html: str) -> list[MatchRow]:
    body = _strip_noise(html)
    start = body.find("stats-matches-table")
    if start < 0:
        return []
    table = body[start:body.find("</table>", start)]
    rows: list[MatchRow] = []
    for raw in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", raw, re.S)
        if len(cells) < 7:
            continue
        code = _text(cells[3]).lower()
        kills, deaths = _split_kd(_text(cells[4]))
        rows.append(
            MatchRow(
                match_date=_row_date(cells[0]),
                team=_row_team(cells[1]),
                opponent=_row_team(cells[2]),
                map_id=_MAP_CODES.get(code, code),
                kills=kills,
                deaths=deaths,
                plus_minus=_to_int(_text(cells[5])),
                rating=_to_float(_text(cells[6])),
                url=_row_url(cells[0]),
            )
        )
    return rows


def _row_date(cell: str) -> date | None:
    # HLTV renders the date client-side from a unix-ms attribute.
    m = re.search(r'data-unix="(\d+)"', cell)
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000).date()
    except (OverflowError, OSError, ValueError):
        return None


def _row_team(cell: str) -> str | None:
    # The cell repeats the team for desktop and mobile
    m = re.search(r'<a href="/stats/teams/\d+/[^"]*"[^>]*>(.*?)</a>', cell, re.S)
    name = _text(m.group(1)) if m else ""
    return name or None


def _row_url(cell: str) -> str | None:
    m = re.search(r'href="(/stats/matches/[^"?]+)', cell)
    return m.group(1) if m else None


def _split_kd(text: str) -> tuple[int | None, int | None]:
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", text)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _to_int(text: str) -> int | None:
    m = re.match(r"\s*([+-]?\d+)", text)
    return int(m.group(1)) if m else None


def _to_float(text: str) -> float | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def _aggregate_maps(rows: list[MatchRow]) -> list[MapStat]:
    agg: dict[str, dict] = {}
    for row in rows:
        if not row.map_id:
            continue
        bucket = agg.setdefault(
            row.map_id,
            {"maps": 0, "kills": 0, "deaths": 0, "plus_minus": 0, "ratings": []},
        )
        bucket["maps"] += 1
        bucket["kills"] += row.kills or 0
        bucket["deaths"] += row.deaths or 0
        bucket["plus_minus"] += row.plus_minus or 0
        if row.rating is not None:
            bucket["ratings"].append(row.rating)

    stats = [
        MapStat(
            map_id=map_id,
            code=next((c for c, m in _MAP_CODES.items() if m == map_id), map_id),
            maps_played=b["maps"],
            kills=b["kills"],
            deaths=b["deaths"],
            plus_minus=b["plus_minus"],
            rating=round(sum(b["ratings"]) / len(b["ratings"]), 2) if b["ratings"] else None,
        )
        for map_id, b in agg.items()
    ]
    return sorted(stats, key=lambda s: s.maps_played, reverse=True)
