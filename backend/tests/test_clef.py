from __future__ import annotations

import io
import json
import urllib.request

from app.ml import clef
from app.ml.clef import QUESTIONS, ask, clef_state


def test_clef_state_keeps_t_utility_in_time_order_with_callout_names():
    util = [
        {"util_type": "flash", "team": "t", "zone": "dust2_t_ramp", "round_time_s": 30.4},
        {"util_type": "smoke", "team": "ct", "zone": "dust2_a_short", "round_time_s": 5.0},
        {"util_type": "decoy", "team": "t", "zone": "dust2_a_short", "round_time_s": 6.0},
        {"util_type": "smoke", "team": "t", "zone": "dust2_a_short", "round_time_s": 12.0},
        {"util_type": "he", "team": "t", "zone": "not_a_zone", "round_time_s": 40.0},
    ]
    state = clef_state("de_dust2", util)
    assert state["map"] == "Dust II"
    assert state["utility_thrown_by_T_so_far"] == [
        {"type": "smoke", "callout": "A Short", "time_s": 12},
        {"type": "flash", "callout": "T Ramp", "time_s": 30},
        {"type": "he", "callout": "not_a_zone", "time_s": 40},
    ]


def test_ask_posts_state_and_questions_and_returns_answers(monkeypatch):
    sent = {}
    answers = {"site": {"type": "choice", "choice": "A",
                        "probabilities": {"A": 0.9, "B": 0.1}, "confidence": 0.8}}

    def fake_urlopen(req, timeout):
        sent["url"], sent["body"] = req.full_url, json.loads(req.data)
        payload = {"answers": answers, "usage": {"input_tokens": 10}}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    state = clef_state("de_dust2", [])
    out = ask(state, host="http://h:1", model="m")
    assert sent["url"] == "http://h:1/v1/systemone"
    assert sent["body"] == {"model": "m", "state": state, "questions": QUESTIONS}
    assert out == {"answers": answers, "usage": {"input_tokens": 10}}
    assert clef.DEFAULT_MODEL == "clef-2k"
