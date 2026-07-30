from __future__ import annotations

import re
from datetime import date

import pytest

from app.hltv import players
from app.hltv.client import HLTVError
from tests.conftest import auth, register_and_login

# Trimmed from a real HLTV player page (s1mple, 2026-07-30): the markup patterns
# the parser keys on, with the 7 MB of scripts/SVG that surrounds them removed.
PROFILE = """
<html><head><title>Oleksandr 's1mple' Kostyliev's Counter-Strike Player Profile | HLTV.org</title>
</head><body>
<script>var junk = '<div class="player-stat"><b>Fake</b><p>9.99</p></div>';</script>
<div class="playerContainer">
  <div class="player-summary-stat-box-left"><div class="player-summary-stat-box-left-banner-wrapper">
    <div class="role-pills"><span class="role-pill role-pill--awp" title="Main AWPer"></span></div>
    <div class="player-summary-stat-box-left-flag"><img alt="Ukraine" class="flag"></div>
    <a href="/team/12878/bcgame" class="player-summary-stat-box-left-team-logo-wrapper"></a></div>
    <div class="player-summary-stat-box-left-bodyshot-wrapper"><img alt="Image of s1mple"
      class="player-summary-stat-box-left-bodyshot" src="https://img-cdn.hltv.org/x.png?w=400&amp;s=abc"></div>
  </div>
  <div class="playerInfoWrapper"><div class="playerNameWrapper"><div class="playerName">
    <h1 class="playerNickname" itemprop="alternateName">s1mple</h1>
    <div class="playerRealname" itemprop="name"><img alt="Ukraine" class="flag"> Oleksandr Kostyliev</div>
  </div></div>
  <div class="playerInfo">
    <div class="playerInfoRow playerAge"><span class="listLeft">Age</span>
      <span class="listRight"><span itemprop="text">28 years</span></span></div>
    <div class="playerInfoRow playerTeam"><span class="listLeft">Current team</span>
      <span class="listRight text-ellipsis"><img alt="BC.Game"><span>
      <a href="/team/12878/bcgame" itemprop="text">BC.Game</a></span></span></div>
    <div class="playerInfoRow playerPrizeMoney"><span class="listLeft "><span>Prize money</span>
      <span><span class="popup-text"> (?)</span></span></span><span class="listRight">$1,549,315</span></div>
    <div class="playerInfoRow playerTop20 top-grid-box"><span class="listLeft top20ListLeft">Top 20</span>
      <span class="listRight top20ListRight"><a href="/news/1">#4</a><span class="top-20-year">('16)</span>,
      <a href="/news/2">#1</a><span class="top-20-year">('18)</span></span></div>
    <div class="playerInfoRow playerAchievement"><span class="listLeft">Player achievements</span>
      <span class="listRight"><div class="majorSection">
        <div class="majorWinner"><b>1</b> x Major winner</div>
        <div class="majorMVP"><b>1</b> x Major MVP</div></div></span></div>
  </div></div>
</div>
<div class="trophySection"><div class="trophyRow"><a href="/team/9999/decoy" class="trophy"></a></div></div>
<div class="tab-content" id="infoBox"><div class="g-grid stats-matches"><div class="col-6 text-ellipsis">
  <h2 class="standard-headline text-ellipsis">s1mple statistics<span class="stats-window">(Past 3 months
    • 7 maps)</span></h2>
  <div class="playerpage-container playerpage-container-attributes">
    <div class="player-stat"><b>Rating 3.0</b><span class="statsVal">
      <p>0.98</p>
      <div class="statsImgContainer"><img class="statsImg" title="Bottom 40% (34th percentile)"></div>
    </span></div>
    <div class="player-stat"><div class="player-stat-top"><b>Firepower</b><span class="statsVal">
      <p><b>73</b><span class="row-stats-section-score-100">/100</span></p></span></div></div>
    <div class="player-stat"><div class="player-stat-top"><b>Sniping</b><span class="statsVal">
      <p><b>79</b><span class="row-stats-section-score-100">/100</span></p></span></div></div>
  </div>
  <div class="moreButton-container"><a href="/stats/players/7998/s1mple">Complete statistics</a></div>
</div></div></div>
<div class="tab-content hidden" id="teamsBox">
  <h2 class="standard-headline">Team stats for s1mple</h2>
  <div class="highlighted-stats-box">
    <div class="highlighted-stat"><div class="stat">8</div><div class="description">Teams</div></div>
    <div class="highlighted-stat"><div class="stat">367</div>
      <div class="description">Days in current team</div></div>
    <div class="highlighted-stat"><div class="stat">4,243</div>
      <div class="description">Days in teams</div></div>
  </div>
  <div class="section-spacer"></div>
  <table class="table-container team-breakdown"><tbody>
    <tr class="team ">
      <td class="time-period-cell"><span data-unix="1753653600000">Jul 2025</span> - Present</td>
      <td class="team-name-cell"><a href="/team/12878/bcgame">
        <span class="team-name gtSmartphone-only">BC.Game</span></a></td></tr>
    <tr class="team past-team">
      <td class="time-period-cell" data-player-team-period-toggle=""><span data-unix="1732143600000">Nov 2024</span>
        - <span data-unix="1746396000000">May 2025</span></td>
      <td class="team-name-cell"><a href="/team/4608/natus-vincere">
        <span class="team-name gtSmartphone-only">Natus Vincere</span></a></td></tr>
    <tr class="team-detail hidden"><td class="time-period-cell"><span data-unix="1641164400000">Jan 2022</span></td>
      <td><span class="team-name">lineup decoy</span></td></tr>
  </tbody></table>
</div>
<div class="tab-content hidden" id="matchesBox">
  <h2 class="standard-headline">Latest results for s1mple</h2>
  <table class="table-container match-table">
    <thead><tr class="event-header-cell">
      <th colspan="3"><a href="/events/8263/cs-asia">CS Asia Championships 2026 - 13-16th</a></th></tr></thead>
    <tbody>
      <tr class="team-row">
        <td class="date-cell"><span data-unix="1779353853000">21/05/2026</span></td>
        <td class="team-center-cell">
          <div class="team-flex lost"><a href="/team/12878/bcgame" class="team-name team-1">BC.Game</a></div>
          <div class="score-cell"><span class="score lost">0</span>
            <span class="score-divider">:</span><span class="score ">2</span></div>
          <div class="team-flex "><a href="/team/4773/pain" class="team-name team-2">paiN</a></div></td>
        <td class="stats-button-cell"><a href="/stats/matches/127097/bcgame-vs-pain">Stats</a></td></tr>
      <tr class="team-row">
        <td class="date-cell"><span data-unix="1779262232000">20/05/2026</span></td>
        <td class="team-center-cell">
          <div class="team-flex "><a href="/team/12878/bcgame" class="team-name team-1">BC.Game</a></div>
          <div class="score-cell"><span class="score ">2</span>
            <span class="score-divider">:</span><span class="score lost">1</span></div>
          <div class="team-flex lost"><a href="/team/6667/faze" class="team-name team-2">FaZe</a></div></td>
        <td class="stats-button-cell"><a href="/stats/matches/127059/bcgame-vs-faze?foo=1">Stats</a></td></tr>
    </tbody>
  </table>
</div>
</body></html>
"""

SEARCH_PAYLOAD = [
    {
        "players": [
            {
                "id": 21167,
                "nickName": "donk",
                "firstName": "Danil",
                "lastName": "Kryshkovets",
                "flagUrl": "https://www.hltv.org/img/static/flags/30x20/RU.gif",
                "pictureUrl": "https://img-cdn.hltv.org/playerbodyshot/x.png",
                "location": "/player/21167/donk",
                "team": {"name": "Spirit", "location": "/team/7020/spirit"},
                "retired": False,
            },
            {
                "id": 17402,
                "nickName": "bedonka",
                "firstName": "Harry",
                "lastName": "Hayes",
                "location": "/player/17402/bedonka",
                "retired": True,
            },
            {"id": "", "nickName": "broken"},
        ],
        "teams": [{"id": 7020, "name": "Spirit"}],
    }
]


def test_search_hits_carry_identity_and_team():
    hits = players._parse_player_hits(SEARCH_PAYLOAD)
    assert [h.nick for h in hits] == ["donk", "bedonka"]  # the id-less row is dropped
    donk = hits[0]
    assert donk.id == "21167"
    assert donk.name == "Danil Kryshkovets"
    assert donk.country == "RU"
    assert (donk.team_id, donk.team_name) == ("7020", "Spirit")
    assert hits[1].retired and hits[1].team_id is None


def test_profile_parses_identity_and_current_team():
    p = players._parse_profile(PROFILE, "7998")
    assert (p.nick, p.name, p.country) == ("s1mple", "Oleksandr Kostyliev", "Ukraine")
    assert (p.age, p.role) == (28, "Main AWPer")
    assert (p.team_id, p.team_name) == ("12878", "BC.Game")
    assert p.image == "https://img-cdn.hltv.org/x.png?w=400&s=abc"  # &amp; unescaped


def test_profile_parses_the_statistics_box():
    p = players._parse_profile(PROFILE, "7998")
    assert (p.rating_label, p.rating) == ("Rating 3.0", "0.98")
    assert p.rating_note == "Bottom 40% (34th percentile)"
    assert p.stats_window == "Past 3 months • 7 maps"
    assert [(r.role, r.score) for r in p.roles] == [("firepower", 73), ("sniping", 79)]
    assert "fake" not in {r.role for r in p.roles}  # the <script> decoy never reaches the parser


def test_profile_summary_collects_the_career_facts():
    p = players._parse_profile(PROFILE, "7998")
    assert [(s.label, s.value) for s in p.summary] == [
        ("Prize money", "$1,549,315"),
        ("Majors won", "1"),
        ("Major MVPs", "1"),
        ("Top 20 appearances", "2"),
        ("Best Top 20", "#1 ('18)"),
        ("Teams", "8"),
        ("Days in current team", "367"),
    ]


def test_profile_parses_the_team_history():
    p = players._parse_profile(PROFILE, "7998")
    assert [(t.team_id, t.team_name) for t in p.teams] == [
        ("12878", "BC.Game"),
        ("4608", "Natus Vincere"),
    ]  # the expandable lineup row is not a spell
    assert (p.teams[0].start, p.teams[0].end) == (date(2025, 7, 28), None)  # None = still there
    assert p.teams[1].end == date(2025, 5, 5)


def test_profile_parses_the_latest_results():
    p = players._parse_profile(PROFILE, "7998")
    assert len(p.matches) == 2
    first = p.matches[0]
    assert (first.team, first.opponent) == ("BC.Game", "paiN")
    assert (first.score, first.won) == ("0 - 2", False)
    assert first.match_date == date(2026, 5, 21)
    assert first.event == "CS Asia Championships 2026 - 13-16th"
    assert first.url == "/stats/matches/127097/bcgame-vs-pain"
    assert p.matches[1].won is True  # the divider is not read as a score
    assert p.matches[1].url == "/stats/matches/127059/bcgame-vs-faze"  # query string dropped


def test_profile_survives_a_page_without_recent_stats():
    # Inactive players get an empty state where the rating and role bars would be
    stripped = re.sub(
        r'<div class="playerpage-container playerpage-container-attributes">.*?'
        r'(?=<div class="moreButton-container">)',
        '<div class="playerpage-container empty-state">No stats from past 3 months</div>',
        PROFILE,
        flags=re.S,
    )
    p = players._parse_profile(stripped, "885")
    assert p.nick == "s1mple" and p.roles == [] and p.rating is None
    assert p.matches  # the results table is independent of the stats box


def _stub_fetch(monkeypatch, calls: list[str]) -> None:
    def fake(url: str, *, attempts: int = 3) -> str:
        calls.append(url)
        return PROFILE

    monkeypatch.setattr(players, "_flaresolverr_get", fake)


def test_profile_endpoint_serves_and_then_caches(client, monkeypatch):
    token = register_and_login(client, "players@example.com")
    calls: list[str] = []
    _stub_fetch(monkeypatch, calls)

    resp = client.get("/hltv/players/7998", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nick"] == "s1mple"
    assert body["team_name"] == "BC.Game"
    assert body["matches"][0]["opponent"] == "paiN"
    assert body["fetched_at"] is not None
    assert calls == ["https://www.hltv.org/player/7998/-"]  # one solve, not one per section

    again = client.get("/hltv/players/7998", headers=auth(token))
    assert again.status_code == 200
    assert again.json()["nick"] == "s1mple"
    assert len(calls) == 1  # served from the cache

    client.get("/hltv/players/7998?refresh=true", headers=auth(token))
    assert len(calls) == 2


def test_profile_refetches_a_cache_row_from_an_older_scrape(client, monkeypatch):
    from app.db import session_scope
    from app.domain.models import HltvPlayer

    token = register_and_login(client, "players5@example.com")
    calls: list[str] = []
    _stub_fetch(monkeypatch, calls)
    assert client.get("/hltv/players/8000", headers=auth(token)).status_code == 200

    with session_scope() as session:
        row = session.get(HltvPlayer, "8000")
        row.payload = row.payload.replace('"payload_version":1', '"payload_version":0')

    assert client.get("/hltv/players/8000", headers=auth(token)).status_code == 200
    assert len(calls) == 2  # the stale shape is scraped again instead of being served


def test_profile_falls_back_to_stale_cache_when_hltv_is_down(client, monkeypatch):
    token = register_and_login(client, "players2@example.com")
    calls: list[str] = []
    _stub_fetch(monkeypatch, calls)
    assert client.get("/hltv/players/7998", headers=auth(token)).status_code == 200

    def boom(url: str, *, attempts: int = 3) -> str:
        raise HLTVError("FlareSolverr is not configured")

    monkeypatch.setattr(players, "_flaresolverr_get", boom)
    resp = client.get("/hltv/players/7998?refresh=true", headers=auth(token))
    assert resp.status_code == 200
    assert resp.json()["nick"] == "s1mple"


def test_profile_without_cache_reports_the_scrape_failure(client, monkeypatch):
    token = register_and_login(client, "players3@example.com")

    def boom(url: str, *, attempts: int = 3) -> str:
        raise HLTVError("FlareSolverr is not configured")

    monkeypatch.setattr(players, "_flaresolverr_get", boom)
    resp = client.get("/hltv/players/99999", headers=auth(token))
    assert resp.status_code == 502
    assert "FlareSolverr" in resp.json()["detail"]


def test_player_search_requires_auth(client):
    assert client.get("/hltv/players/search?term=donk").status_code == 401


@pytest.mark.parametrize("term", ["", "d"])
def test_player_search_rejects_short_terms(client, term):
    token = register_and_login(client, "players4@example.com")
    resp = client.get(f"/hltv/players/search?term={term}", headers=auth(token))
    assert resp.status_code == 422
