from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
from app.config import get_settings
from app.domain.enums import DateRange
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


class HLTVError(RuntimeError):
    """Raised when an HLTV request fails or cannot be parsed"""


@dataclass
class TeamHit:
    id: str
    name: str
    url: str
    logo: str | None = None


@dataclass
class DemoArchive:
    match_id: str
    map_id: str | None
    event: str | None
    match_date: date | None
    dem_paths: list[Path]
    work_dir: Path | None = None  # temp dir to clean up once the match is ingested


def _impersonated_session():
    try:
        from curl_cffi import requests as cffi
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise HLTVError(f"curl-cffi unavailable: {exc}") from exc
    return cffi.Session(impersonate="chrome")


def search_teams(query: str, *, limit: int = 10) -> list[TeamHit]:
    # Look up teams by name via HLTV's JSON search endpoint
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
        raise HLTVError(f"team search failed: {exc}") from exc

    return _parse_team_hits(payload, settings.hltv_base_url)[:limit]


def _parse_team_hits(payload: object, base_url: str) -> list[TeamHit]:
    # HLTV /search returns a list of category objects; pull the teams out
    categories = payload if isinstance(payload, list) else [payload]
    hits: list[TeamHit] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        for team in category.get("teams", []) or []:
            tid = str(team.get("id", "")).strip()
            name = (team.get("name") or "").strip()
            if not tid or not name:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            logo = team.get("logo")
            hits.append(
                TeamHit(
                    id=tid,
                    name=name,
                    url=f"{base_url}/team/{tid}/{slug}",
                    logo=logo if isinstance(logo, str) else None,
                )
            )
    return hits


# The single FlareSolverr browser 500s when overlapping jobs solve at once, so
# gate concurrent solves to ``flaresolverr_concurrency``. Built lazily.
_gate: threading.Semaphore | None = None
_gate_lock = threading.Lock()


def _flaresolverr_gate() -> threading.Semaphore:
    global _gate
    if _gate is None:
        with _gate_lock:
            if _gate is None:
                _gate = threading.Semaphore(max(1, get_settings().flaresolverr_concurrency))
    return _gate


def _flaresolverr_get(url: str, *, attempts: int = 3) -> str:
    # Fetch a Cloudflare-protected page's HTML via FlareSolverr. Its 500s are
    # usually transient, so retry with linear backoff before giving up.
    settings = get_settings()
    if not settings.flaresolverr_url:
        raise HLTVError("FlareSolverr is not configured (set CS2_FLARESOLVERR_URL)")
    import requests

    endpoint = f"{settings.flaresolverr_url.rstrip('/')}/v1"
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": int(settings.request_timeout_s * 1000),
    }
    last_err: Exception | None = None
    with _flaresolverr_gate():
        for attempt in range(attempts):
            try:
                resp = requests.post(endpoint, json=payload, timeout=settings.request_timeout_s + 30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                last_err = exc
            else:
                if data.get("status") == "ok":
                    return data.get("solution", {}).get("response", "")
                last_err = HLTVError(f"FlareSolverr error: {data.get('message', 'unknown')}")
            if attempt + 1 < attempts:
                time.sleep(settings.request_delay_s * (attempt + 1))
    raise HLTVError(f"FlareSolverr request failed after {attempts} attempts: {last_err}")


def map_from_filename(name: str) -> str | None:
    # Derive a CS2 map id from a GOTV .dem filename

    m = re.search(r"-([a-z0-9_]+)\.dem$", name.lower())
    if not m:
        return None
    token = m.group(1)
    if re.fullmatch(r"m\d+", token):  # ``-m2.dem`` with no map name
        return None
    return token if token.startswith("de_") else f"de_{token}"


def _select_dem_members(members: list[str], map_id: str | None) -> list[str]:
    dems = [m for m in members if m.lower().endswith(".dem")]
    if not map_id:
        return dems
    return [m for m in dems if map_from_filename(Path(m).name) == map_id]


def _parse_match_meta(html: str) -> tuple[str | None, date | None]:
    """Pull the event name and match date from an HLTV match page's HTML."""
    event = None
    m = re.search(r'href="/events/\d+/[^"]*"[^>]*>([^<]+)</a>', html)
    if m:
        event = re.sub(r"\s+", " ", m.group(1)).strip() or None

    match_date = None
    d = re.search(r'data-unix="(\d+)"', html)
    if d:
        try:
            match_date = datetime.fromtimestamp(int(d.group(1)) / 1000, tz=timezone.utc).date()
        except (ValueError, OverflowError, OSError):
            pass
    return event, match_date


def _match_involves_team(html: str, team_id: str) -> bool:
    """True if ``team_id`` is one of the two teams on a match page.

    HLTV links both teams as ``/team/{id}/{slug}`` (and ``team={id}`` in stats
    URLs), so requiring the id to appear filters out unrelated matches scraped
    from a featured/other-matches section or a generic homepage fallback.
    """
    return f"/team/{team_id}/" in html or f"team={team_id}" in html


# A result row on a team's results page: the match link plus the match date as
# a unix-ms timestamp. Scoping to ``result-con`` excludes the page's "other
# matches" sidebar (which would leak unrelated teams).
_RESULT_ROW = re.compile(
    r'class="result-con"[^>]*data-zonedgrouping-entry-unix="(\d+)"[^>]*>\s*'
    r'<a href="(/matches/\d+/[a-z0-9-]+)"'
)


def find_match_results(team_id: str, map_id: str | None, date_range: DateRange) -> list[str]:
    # Return result-match URLs for team_id within date_range
    settings = get_settings()
    since = date_range.start_date(date.today())
    # HLTV's ``startDate``/``endDate`` params return a broken (unfiltered) page
    # via FlareSolverr, so fetch the team's results unfiltered and filter the
    # rows by their own timestamp instead.
    url = f"{settings.hltv_base_url}/results?team={team_id}"
    html = _flaresolverr_get(url)
    # If the team's id is absent the request was not served the team's results
    # page (generic homepage / block); scraping it would yield other teams.
    if not _match_involves_team(html, team_id):
        return []
    out: list[str] = []
    for ts, path in _RESULT_ROW.findall(html):
        try:
            match_day = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).date()
        except (ValueError, OverflowError, OSError):
            continue
        if match_day < since:
            continue
        out.append(f"{settings.hltv_base_url}{path}")
    return list(dict.fromkeys(out))  # dedupe, keep newest-first order


def iter_team_demo_archives(
        team_id: str,
        map_id: str | None,
        date_range: DateRange,
        *,
        max_matches: int = 100,
        on_total: "Callable[[int], None] | None" = None,
) -> Iterator[DemoArchive]:
    # Yield GOTV demo archives one match at a time, as each is downloaded

    settings = get_settings()
    match_urls = find_match_results(team_id, map_id, date_range)[:max_matches]
    if on_total is not None:
        on_total(len(match_urls))

    for match_url in match_urls:
        time.sleep(settings.request_delay_s)  # be polite to HLTV
        try:
            html = _flaresolverr_get(match_url)
            # Guard against page-scrape leaks (a generic homepage or "other
            # matches" section): only keep matches the requested team plays in.
            if not _match_involves_team(html, team_id):
                continue
            demo_links = re.findall(r'href="(/download/demo/\d+)"', html)
            if not demo_links:
                continue
            id_match = re.search(r"/matches/(\d+)", match_url)
            match_id = id_match.group(1) if id_match else match_url.rstrip("/").split("/")[-1]
            event, match_date = _parse_match_meta(html)
            work_dir, dem_paths = _download_and_extract(
                f"{settings.hltv_base_url}{demo_links[0]}", match_id, map_id
            )
        except HLTVError:
            continue  # skip a failed match, keep going
        if dem_paths:
            yield DemoArchive(
                match_id=match_id,
                map_id=map_id,
                event=event,
                match_date=match_date,
                dem_paths=dem_paths,
                work_dir=work_dir,
            )
        elif work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)


def download_team_demos(
        team_id: str, map_id: str | None, date_range: DateRange, *, max_matches: int = 100
) -> list[DemoArchive]:
    return list(
        iter_team_demo_archives(team_id, map_id, date_range, max_matches=max_matches)
    )


def _download_and_extract(
        demo_url: str, match_id: str, map_id: str | None = None
) -> tuple[Path, list[Path]]:
    settings = get_settings()
    try:
        import rarfile

        session = _impersonated_session()
        resp = session.get(demo_url, timeout=settings.demo_download_timeout_s)
        resp.raise_for_status()
    except Exception as exc:
        raise HLTVError(f"demo download failed: {exc}") from exc

    work = Path(tempfile.mkdtemp(prefix=f"hltv-{match_id}-"))
    archive = work / "demo.rar"
    archive.write_bytes(resp.content)

    try:
        with rarfile.RarFile(archive) as rf:
            members = rf.namelist()
    except Exception as exc:
        raise HLTVError(f"failed to read GOTV archive: {exc}") from exc

    wanted = _select_dem_members(members, map_id)

    out: list[Path] = []
    for member in wanted:
        try:
            subprocess.run(
                ["bsdtar", "-x", "-f", str(archive), "-C", str(work), member],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            raise HLTVError(f"failed to extract GOTV archive: {stderr}") from exc
        out.append(work / member)
    return work, out


def cleanup_archive(archive: DemoArchive) -> None:
    """Delete a match's temp download dir (the ``.rar`` and extracted ``.dem``)."""
    if archive.work_dir is not None:
        shutil.rmtree(archive.work_dir, ignore_errors=True)
