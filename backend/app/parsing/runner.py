from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from app.config import get_settings
from app.parsing.parser import ParsedDemo, parse_demo

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()


def _pool_instance() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                # "spawn" gives the child a clean interpreter (no inherited sockets/threads).
                ctx = multiprocessing.get_context("spawn")
                _pool = ProcessPoolExecutor(
                    max_workers=max(1, get_settings().parse_workers), mp_context=ctx
                )
    return _pool


def run_parse(path: Path, *, map_hint: str | None, team_hint: str | None) -> ParsedDemo:
    """Parse a demo off the web process so its GIL stays free for serving requests."""
    settings = get_settings()
    # Sample data is trivial to build; only real awpy parses are worth offloading.
    if settings.use_sample_data or not settings.parse_in_subprocess:
        return parse_demo(path, map_hint=map_hint, team_hint=team_hint)
    return _pool_instance().submit(
        parse_demo, path, map_hint=map_hint, team_hint=team_hint
    ).result()
