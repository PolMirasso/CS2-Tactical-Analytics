from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from app.config import get_settings
from app.domain.enums import DateRange
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
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


def _flaresolverr_get(url: str) -> str:
    # Fetch a Cloudflare-protected page's HTML via FlareSolverr
    settings = get_settings()
    if not settings.flaresolverr_url:
        raise HLTVError("FlareSolverr is not configured (set CS2_FLARESOLVERR_URL)")
    try:
        import requests

        resp = requests.post(
            f"{settings.flaresolverr_url.rstrip('/')}/v1",
            json={
                "cmd": "request.get",
                "url": url,
                "maxTimeout": int(settings.request_timeout_s * 1000),
            },
            timeout=settings.request_timeout_s + 30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise HLTVError(f"FlareSolverr request failed: {exc}") from exc
    if data.get("status") != "ok":
        raise HLTVError(f"FlareSolverr error: {data.get('message', 'unknown')}")
    return data.get("solution", {}).get("response", "")


def map_from_filename(name: str) -> str | None:
    # Derive a CS2 map id from a GOTV .dem filename

    m = re.search(r"-([a-z0-9_]+)\.dem$", name.lower())
    if not m:
        return None
    token = m.group(1)
    if re.fullmatch(r"m\d+", token):  # ``-m2.dem`` with no map name
        return None
    return token if token.startswith("de_") else f"de_{token}"


def find_match_results(team_id: str, map_id: str | None, date_range: DateRange) -> list[str]:
    # Return result-match URLs for team_id within date_range
    settings = get_settings()
    since = date_range.start_date(date.today())
    url = (
        f"{settings.hltv_base_url}/results?team={team_id}"
        f"&startDate={since.isoformat()}&endDate={date.today().isoformat()}"
    )
    html = _flaresolverr_get(url)
    # Keep the full path including the slug - HLTV serves a generic homepage
    paths = sorted(set(re.findall(r'/matches/\d+/[a-z0-9\-]+', html)))
    return [f"{settings.hltv_base_url}{path}" for path in paths]


def iter_team_demo_archives(
        team_id: str, map_id: str | None, date_range: DateRange, *, max_matches: int = 5
) -> Iterator[DemoArchive]:
    # Yield GOTV demo archives one match at a time, as each is downloaded

    settings = get_settings()
    match_urls = find_match_results(team_id, map_id, date_range)[:max_matches]

    for match_url in match_urls:
        time.sleep(settings.request_delay_s)  # be polite to HLTV
        try:
            html = _flaresolverr_get(match_url)
            demo_links = re.findall(r'href="(/download/demo/\d+)"', html)
            if not demo_links:
                continue
            id_match = re.search(r"/matches/(\d+)", match_url)
            match_id = id_match.group(1) if id_match else match_url.rstrip("/").split("/")[-1]
            work_dir, dem_paths = _download_and_extract(
                f"{settings.hltv_base_url}{demo_links[0]}", match_id
            )
        except HLTVError:
            continue  # skip a failed match, keep going
        if dem_paths:
            yield DemoArchive(
                match_id=match_id,
                map_id=map_id,
                event=None,
                match_date=None,
                dem_paths=dem_paths,
                work_dir=work_dir,
            )


def download_team_demos(
        team_id: str, map_id: str | None, date_range: DateRange, *, max_matches: int = 5
) -> list[DemoArchive]:
    return list(
        iter_team_demo_archives(team_id, map_id, date_range, max_matches=max_matches)
    )


def _download_and_extract(demo_url: str, match_id: str) -> tuple[Path, list[Path]]:
    # Download a GOTV ``.rar`` and extract *every* ``.dem`` member. The archive
    # holds all maps of the series, so we ingest them all rather than discard
    # the ones we already paid to download. Returns (work_dir, dem_paths).

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

    wanted = [m for m in members if m.lower().endswith(".dem")]

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
