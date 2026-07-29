from __future__ import annotations

from datetime import date

import pytest

from app.hltv import players
from app.hltv.client import HLTVError
from tests.conftest import auth, register_and_login

# Trimmed from a real HLTV player page (donk, 2026-07-29): the markup patterns
# the parsers key on, with the 5 MB of scripts/SVG that surrounds them removed.
OVERVIEW = """
<html><head>
<title>Danil 'donk' Kryshkovets Counter-Strike Statistics | HLTV.org</title>
<meta property="og:image" content="https://img-cdn.hltv.org/playerbodyshot/x.png?bg=3e4c54&amp;w=800">
</head><body>
<script>var junk = "<div class='stats-row'><span>fake</span><span>0</span></div>";</script>
<div class="context-item">
  <span class="context-item-name"><img alt="Russia" src="/img/static/flags/30x20/RU.gif"
   class="context-item-flag flag" title="Russia">donk</span></div>
<div class="player-summary-stat-box compact">
  <div class="player-summary-stat-box-side-rating t-rating">
    <div class="player-summary-stat-box-side-rating-background-wrapper">
      <div class="player-summary-stat-box-side-rating-background"></div> 1.34
      <div class="player-summary-stat-box-side-rating-text">T Rating</div></div></div>
  <div class="player-summary-stat-box-rating-wrapper aboveAverage">
    <div class="player-summary-stat-box-rating-text">Good</div>
    <div class="player-summary-stat-box-rating-data-text">1.32</div>
    <div class="player-summary-stat-box-data-description-text player-summary-stat-box-data-text">
      Rating 2.0 <div class="player-summary-tooltip hiddenTooltip"><b>Rating 2.0</b></div></div></div>
  <div class="player-summary-stat-box-side-rating ct-rating">
    <div class="player-summary-stat-box-side-rating-background-wrapper">
      <div class="player-summary-stat-box-side-rating-background"></div> 1.30
      <div class="player-summary-stat-box-side-rating-text">CT Rating</div></div></div>
  <div class="player-summary-stat-box-right-bottom">
    <div class="player-summary-stat-box-data-wrapper ">
      <div class="player-summary-stat-box-data">-</div>
      <div class="player-summary-stat-box-data-text">Round swing</div>
      <div class="player-summary-stat-box-breakdown-bar"></div></div>
    <div class="player-summary-stat-box-data-wrapper average">
      <div class="player-summary-stat-box-data traditionalData">0.67</div>
      <div class="player-summary-stat-box-data-text traditionalData">DPR</div>
      <div class="player-summary-stat-box-breakdown-bar"></div></div>
    <div class="player-summary-stat-box-data-wrapper aboveAverage">
      <div class="player-summary-stat-box-data traditionalData">75.1<span
        class="player-summary-stat-box-percentage">%</span></div>
      <div class="player-summary-stat-box-data-text traditionalData">KAST</div>
      <div class="player-summary-stat-box-breakdown-bar"></div></div></div></div>
<div class="role-stats-section role-firepower">
  <div class="role-stats-section-title-wrapper stats-side-combined">
    <div class="role-stats-section-title">Firepower</div>
    <div class="row-stats-section-score">99<span class="row-stats-section-score-100">/100</span></div></div>
  <div class="role-stats-section-title-wrapper stats-side-ct hidden">
    <div class="row-stats-section-score">98<span class="row-stats-section-score-100">/100</span></div></div></div>
<div class="role-stats-section role-sniping">
  <div class="role-stats-section-title-wrapper stats-side-combined">
    <div class="role-stats-section-title">Sniping</div>
    <div class="row-stats-section-score">1<span class="row-stats-section-score-100">/100</span></div></div></div>
<div class="statistics"><div class="col stats-rows standard-box">
  <div class="stats-row"><span>Total kills</span><span>15736</span></div>
  <div class="stats-row"><span>Headshot %</span><span>61.0%</span></div>
  <div class="stats-row" title="Data from 2016 onward."><span>Damage / Round</span><span>91.2</span></div>
  <div class="stats-row"><span>Maps played</span><span>763</span></div>
</div></div>
</body></html>
"""

MATCHES = """
<html><body><table class="stats-table sortable-table stats-matches-table">
<thead><tr><th>Date</th><th>Player team</th><th>Opponent</th><th>Map</th>
<th>K - D</th><th>+/-</th><th>Rating</th></tr></thead>
<tbody>
<tr class="group-2 first">
  <td><a href="/stats/matches/mapstatsid/233697/100-thieves-vs-spirit?contextIds=21167">
    <div class="time" data-unix="1785083700000">26/07/26</div></a></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/7020/spirit" class="inline-block">
    <span><img alt="Russia" class="flag">Spirit</span></a><span> (13)</span></div>
    <div class="smartphone-only"><a href="/stats/teams/7020/spirit"><img alt="Spirit"></a></div></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/8474/100-thieves">
    <span>100 Thieves</span></a><span> (0)</span></div></td>
  <td class="statsCenterText">d2</td><td>20 - 7</td><td>+13</td><td>2.84</td></tr>
<tr class="group-2">
  <td><a href="/stats/matches/mapstatsid/233698/100-thieves-vs-spirit">
    <div class="time" data-unix="1785083700000">26/07/26</div></a></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/7020/spirit"><span>Spirit</span></a></div></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/8474/100-thieves"><span>100 Thieves</span></a></div></td>
  <td class="statsCenterText">mrg</td><td>14 - 15</td><td>-1</td><td>0.86</td></tr>
<tr class="group-1">
  <td><a href="/stats/matches/mapstatsid/233611/faze-vs-spirit">
    <div class="time" data-unix="1784997300000">25/07/26</div></a></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/7020/spirit"><span>Spirit</span></a></div></td>
  <td><div class="gtSmartphone-only"><a href="/stats/teams/6667/faze"><span>FaZe</span></a></div></td>
  <td class="statsCenterText">d2</td><td>18 - 13</td><td>+5</td><td>1.22</td></tr>
</tbody></table></body></html>
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


def test_overview_parses_identity_and_ratings():
    p = players._parse_overview(OVERVIEW, "21167")
    assert (p.nick, p.name, p.country) == ("donk", "Danil Kryshkovets", "Russia")
    assert p.image is not None and p.image.endswith("w=800")  # &amp; unescaped
    assert (p.rating, p.rating_label) == ("1.32", "Rating 2.0")
    assert (p.ct_rating, p.t_rating) == ("1.30", "1.34")


def test_overview_parses_summary_career_and_roles():
    p = players._parse_overview(OVERVIEW, "21167")
    # "Round swing" has no data ("-") and is dropped rather than shown empty.
    assert [(s.label, s.value) for s in p.summary] == [("DPR", "0.67"), ("KAST", "75.1%")]
    career = {s.label: s.value for s in p.career}
    assert career["Total kills"] == "15736" and career["Maps played"] == "763"
    assert "fake" not in career  # the <script> decoy never reaches the parser
    # Only the combined-sides score, not the per-side duplicates.
    assert [(r.role, r.score) for r in p.roles] == [("firepower", 99), ("sniping", 1)]


def test_match_rows_map_hltv_codes_to_our_map_ids():
    rows = players._parse_match_rows(MATCHES)
    assert len(rows) == 3
    first = rows[0]
    assert first.map_id == "de_dust2"
    assert (first.kills, first.deaths, first.plus_minus, first.rating) == (20, 7, 13, 2.84)
    assert (first.team, first.opponent) == ("Spirit", "100 Thieves")
    assert first.match_date == date(2026, 7, 26)
    assert first.url == "/stats/matches/mapstatsid/233697/100-thieves-vs-spirit"
    assert rows[1].plus_minus == -1  # negative +/- keeps its sign


def test_map_breakdown_aggregates_the_match_history():
    rows = players._parse_match_rows(MATCHES)
    stats = players._aggregate_maps(rows)
    assert [s.map_id for s in stats] == ["de_dust2", "de_mirage"]  # most played first
    d2 = stats[0]
    assert (d2.maps_played, d2.kills, d2.deaths, d2.plus_minus) == (2, 38, 20, 18)
    assert d2.rating == 2.03  # mean of 2.84 and 1.22
    assert d2.code == "d2"


def test_unknown_map_code_passes_through():
    html = MATCHES.replace(">d2<", ">zzz<")
    stats = players._aggregate_maps(players._parse_match_rows(html))
    assert {s.map_id for s in stats} == {"zzz", "de_mirage"}


def _stub_fetch(monkeypatch, calls: list[str]) -> None:
    def fake(url: str, *, attempts: int = 3) -> str:
        calls.append(url)
        return MATCHES if "/matches/" in url else OVERVIEW

    monkeypatch.setattr(players, "_flaresolverr_get", fake)


def test_profile_endpoint_serves_and_then_caches(client, monkeypatch):
    token = register_and_login(client, "players@example.com")
    calls: list[str] = []
    _stub_fetch(monkeypatch, calls)

    resp = client.get("/hltv/players/21167", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["nick"] == "donk"
    assert body["team_name"] == "Spirit"  # taken from the most recent match row
    assert body["maps"][0]["map_id"] == "de_dust2"
    assert body["fetched_at"] is not None
    assert len(calls) == 2  # overview + match history

    again = client.get("/hltv/players/21167", headers=auth(token))
    assert again.status_code == 200
    assert again.json()["nick"] == "donk"
    assert len(calls) == 2  # served from the cache

    client.get("/hltv/players/21167?refresh=true", headers=auth(token))
    assert len(calls) == 4


def test_profile_falls_back_to_stale_cache_when_hltv_is_down(client, monkeypatch):
    token = register_and_login(client, "players2@example.com")
    calls: list[str] = []
    _stub_fetch(monkeypatch, calls)
    assert client.get("/hltv/players/21167", headers=auth(token)).status_code == 200

    def boom(url: str, *, attempts: int = 3) -> str:
        raise HLTVError("FlareSolverr is not configured")

    monkeypatch.setattr(players, "_flaresolverr_get", boom)
    resp = client.get("/hltv/players/21167?refresh=true", headers=auth(token))
    assert resp.status_code == 200
    assert resp.json()["nick"] == "donk"


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
