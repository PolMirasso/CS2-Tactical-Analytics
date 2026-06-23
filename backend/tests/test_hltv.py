from __future__ import annotations

from app.hltv.client import _match_involves_team


def test_match_involves_team_matches_team_link():
    html = '<a href="/team/12591/koi">KOI</a> vs <a href="/team/9999/x">X</a>'
    assert _match_involves_team(html, "12591")
    assert _match_involves_team(html, "9999")


def test_match_involves_team_rejects_other_team():
    # An OG (10503) match must not be accepted when KOI (12591) was requested.
    og = '<a href="/team/10503/og">OG</a> vs <a href="/team/8888/y">Y</a>'
    assert not _match_involves_team(og, "12591")


def test_match_involves_team_accepts_stats_url_form():
    assert _match_involves_team("...?team=12591&map=...", "12591")
