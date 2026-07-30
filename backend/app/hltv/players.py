from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.config import get_settings
from app.hltv.client import HLTVError, _flaresolverr_get, _impersonated_session

_TAGS = re.compile(r"<[^>]+>")
_NOISE = re.compile(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", re.S)
_SPACES = re.compile(r"\s+")


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
class TeamSpell:
    team_id: str | None
    team_name: str
    start: date | None
    end: date | None  # None while the player is still on the team


@dataclass
class MatchRow:
    match_date: date | None
    team: str | None
    opponent: str | None
    score: str | None
    won: bool | None
    event: str | None
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
    age: int | None = None
    role: str | None = None  # awper, rifle etc...
    rating: str | None = None
    rating_label: str | None = None
    rating_note: str | None = None  # HLTV's percentile blurb
    stats_window: str | None = None  # the period the rating and roles cover
    summary: list[StatItem] = field(default_factory=list)
    roles: list[RoleScore] = field(default_factory=list)
    teams: list[TeamSpell] = field(default_factory=list)
    matches: list[MatchRow] = field(default_factory=list)


def _text(fragment: str) -> str:
    plain = _TAGS.sub(" ", fragment).replace("&nbsp;", " ").replace("&amp;", "&")
    return _SPACES.sub(" ", plain).strip()


def _section(body: str, start_marker: str, end_marker: str) -> str:
    """The slice between two markers, so a regex only sees the block it belongs to"""
    start = body.find(start_marker)
    if start < 0:
        return ""
    end = body.find(end_marker, start)
    return body[start:end] if end > 0 else body[start:]


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
    """Scrape a player's HLTV profile page"""
    base = get_settings().hltv_base_url
    # The URL slug is cosmetic; HLTV resolves the player by id alone.
    return _parse_profile(_flaresolverr_get(f"{base}/player/{player_id}/-"), player_id)


def _parse_profile(html: str, player_id: str) -> PlayerProfile:
    body = _NOISE.sub("", html)
    profile = PlayerProfile(id=str(player_id), nick=str(player_id))

    nick = re.search(r'class="playerNickname"[^>]*>([^<]+)', body)
    if nick:
        profile.nick = nick.group(1).strip()

    real = re.search(r'class="playerRealname"[^>]*>(.*?)</div>', body, re.S)
    if real:
        profile.name = _text(real.group(1)) or None
        flag = re.search(r'<img alt="([^"]*)"', real.group(1))
        if flag:
            profile.country = flag.group(1) or None

    shot = re.search(r'class="player-summary-stat-box-left-bodyshot"[^>]*\ssrc="([^"]+)"', body)
    if shot:
        profile.image = shot.group(1).replace("&amp;", "&")

    pills = re.findall(r'class="role-pill[^"]*"[^>]*title="([^"]+)"', body)
    profile.role = ", ".join(pills) or None

    info = _section(body, '<div class="playerInfo"', '<div class="trophySection"')
    _apply_info_rows(profile, info)
    _apply_stats_box(profile, body)
    profile.teams = _parse_teams(body)
    profile.matches = _parse_results(body)
    _apply_team_totals(profile, body)
    return profile


def _apply_info_rows(profile: PlayerProfile, info: str) -> None:
    # The fact list next to the bodyshot: one "playerInfoRow player<Name>" per fact
    rows = dict(
        re.findall(
            r'playerInfoRow player(\w+)[^>]*>(.*?)(?=<div class="playerInfoRow|\Z)', info, re.S
        )
    )

    age = re.search(r"(\d+)\s*years", rows.get("Age", ""))
    if age:
        profile.age = int(age.group(1))

    team = re.search(r'href="/team/(\d+)/[^"]*"[^>]*>([^<]+)</a>', rows.get("Team", ""))
    if team:
        profile.team_id, profile.team_name = team.group(1), team.group(2).strip()

    money = re.search(r'class="listRight">\s*(\$[\d,]+)', rows.get("PrizeMoney", ""))
    if money:
        profile.summary.append(StatItem(label="Prize money", value=money.group(1)))

    achievements = rows.get("Achievement", "")
    for css, label in (("majorWinner", "Majors won"), ("majorMVP", "Major MVPs")):
        m = re.search(rf'class="{css}"><b>(\d+)</b>', achievements)
        if m:
            profile.summary.append(StatItem(label=label, value=m.group(1)))

    top20 = re.findall(r'>#(\d+)</a><span class="top-20-year">\(\'(\d+)\)', rows.get("Top20", ""))
    if top20:
        rank, year = min(top20, key=lambda t: int(t[0]))
        profile.summary.append(StatItem(label="Top 20 appearances", value=str(len(top20))))
        profile.summary.append(StatItem(label="Best Top 20", value=f"#{rank} ('{year})"))


def _apply_stats_box(profile: PlayerProfile, body: str) -> None:
    # statistics column: overall rating plus the 0-100 role scores
    box = _section(body, 'class="standard-headline text-ellipsis">', '"moreButton-container"')
    window = re.search(r'class="stats-window">\(([^)]+)\)', box)
    if window:
        profile.stats_window = _text(window.group(1))

    rating = re.search(
        r'<div class="player-stat"><b>([^<]+)</b>.*?<p>\s*([\d.]+)\s*</p>(.*?)</div>', box, re.S
    )
    if rating:
        profile.rating_label = rating.group(1).strip()
        profile.rating = rating.group(2)
        note = re.search(r'class="statsImg" title="([^"]+)"', rating.group(3))
        profile.rating_note = note.group(1) if note else None

    profile.roles = [
        RoleScore(role=name.strip().lower(), score=int(score))
        for name, score in re.findall(
            r'<div class="player-stat-top"><b>([^<]+)</b>.*?<p><b>(\d+)</b>', box, re.S
        )
    ]


def _parse_teams(body: str) -> list[TeamSpell]:
    # team-detail rows expand a spell into lineups
    table = _section(body, 'class="table-container team-breakdown"', "</table>")
    spells: list[TeamSpell] = []
    for row in re.findall(r'<tr class="team(?:\s+past-team)?\s*">(.*?)</tr>', table, re.S):
        name = re.search(r'class="team-name[^"]*">([^<]+)</span>', row)
        if not name:
            continue
        team_id = re.search(r'href="/team/(\d+)/[^"]*"', row)
        period = re.search(r'<td class="time-period-cell"[^>]*>(.*?)</td>', row, re.S)
        dates = _unix_dates(period.group(1) if period else "")
        spells.append(
            TeamSpell(
                team_id=team_id.group(1) if team_id else None,
                team_name=name.group(1).strip(),
                start=dates[0] if dates else None,
                end=dates[1] if len(dates) > 1 else None,
            )
        )
    return spells


def _parse_results(body: str) -> list[MatchRow]:
    # The results table groups rows under an event header row
    table = _section(body, "Latest results for", "</table>")
    rows: list[MatchRow] = []
    event: str | None = None
    for block in re.finditer(
        r'<tr class="event-header-cell">(?P<head>.*?)</tr>|<tr class="team-row">(?P<row>.*?)</tr>',
        table,
        re.S,
    ):
        if block.group("head") is not None:
            event = _text(block.group("head")) or None
            continue
        row = block.group("row")
        # HLTV lists the players own team first
        teams = re.findall(r'class="team-name team-\d">([^<]+)</a>', row)
        raw = re.findall(r'<span class="score(?:\s[^"]*)?">([^<]+)</span>', row)
        scores = [s.strip() for s in raw]
        url = re.search(r'href="(/stats/matches/[^"?]+)', row)
        dates = _unix_dates(row)
        rows.append(
            MatchRow(
                match_date=dates[0] if dates else None,
                team=teams[0].strip() if teams else None,
                opponent=teams[1].strip() if len(teams) > 1 else None,
                score=" - ".join(scores[:2]) if len(scores) > 1 else None,
                won=_won(scores),
                event=event,
                url=url.group(1) if url else None,
            )
        )
    return rows


def _won(scores: list[str]) -> bool | None:
    if len(scores) < 2 or not all(s.isdigit() for s in scores[:2]):
        return None
    ours, theirs = int(scores[0]), int(scores[1])
    return None if ours == theirs else ours > theirs


def _apply_team_totals(profile: PlayerProfile, body: str) -> None:
    box = _section(body, "Team stats for", '<div class="section-spacer">')
    wanted = ("Teams", "Days in current team")
    for value, label in re.findall(
        r'<div class="stat">([^<]*)</div>\s*<div class="description">([^<]*)</div>', box
    ):
        if label.strip() in wanted and value.strip() not in ("", "-"):
            profile.summary.append(StatItem(label=label.strip(), value=value.strip()))


def _unix_dates(fragment: str) -> list[date]:
    # HLTV renders dates client-side
    dates: list[date] = []
    for stamp in re.findall(r'data-unix="(\d+)"', fragment):
        try:
            dates.append(datetime.fromtimestamp(int(stamp) / 1000).date())
        except (OverflowError, OSError, ValueError):
            continue
    return dates
