#!/usr/bin/env python3
"""Download NSIDC SPL3SMP_E version 6 granules for calendar years 2015--2025.

Requires a NASA Earthdata Login token. Create one at
https://urs.earthdata.nasa.gov/profile/tokens and either save it in the
private ~/.earthdata_token file, set EARTHDATA_TOKEN, or pass it with --token.
The script queries NASA CMR, so it does not rely on an assumed NSIDC directory
layout or filename convention.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAME = "SPL3SMP_E"
# CMR stores NSIDC's public "Version 6" as the three-digit version id 006.
VERSION = "006"
PAGE_SIZE = 2000
DEFAULT_TOKEN_FILE = Path.home() / ".earthdata_token"


def saved_token() -> str | None:
    """Return the token from the private default file, if it exists."""
    try:
        token = DEFAULT_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    if not token:
        return None
    return token


def cmr_entries(year: int) -> Iterator[dict]:
    """Yield all CMR entries for one UTC calendar year."""
    params = {"short_name": SHORT_NAME, "version": VERSION,
              "temporal": f"{year}-01-01T00:00:00Z,{year}-12-31T23:59:59Z",
              "page_size": PAGE_SIZE, "page_num": 1}
    while True:
        request = Request(f"{CMR_GRANULES}?{urlencode(params)}")
        with urlopen(request, timeout=90) as response:
            entries = json.load(response)["feed"].get("entry", [])
        if not entries:
            return
        yield from entries
        if len(entries) < PAGE_SIZE:
            return
        params["page_num"] += 1


def data_url(entry: dict) -> str | None:
    """Pick the HDF5 data link, excluding HTML and service links."""
    for link in entry.get("links", []):
        href = link.get("href", "")
        if href.lower().endswith(".h5") and not link.get("inherited", False):
            return href
    return None


def download(url: str, destination: Path, token: str, retries: int) -> str:
    """Download atomically; return 'downloaded' or 'exists'."""
    if destination.exists() and destination.stat().st_size > 0:
        return "exists"
    temporary = destination.with_suffix(destination.suffix + ".part")
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "SPL3SMP_E-downloader/1.0"}
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=300) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            temporary.replace(destination)
            return "downloaded"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            if attempt == retries:
                raise RuntimeError(f"{url}: {exc}") from exc
            delay = 2 ** attempt
            print(f"  retrying in {delay}s ({exc})", file=sys.stderr)
            time.sleep(delay)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path.cwd() / "SPL3SMP_E_v006",
        help="destination directory (default: ./SPL3SMP_E_v006)",
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--token", default=None, help="Earthdata token (overrides file and environment variable)")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="List files without downloading")
    args = parser.parse_args()
    if not 2015 <= args.start_year <= args.end_year:
        parser.error("years must be ordered and start no earlier than 2015")
    # Explicit option wins, followed by the environment and then the private
    # home-directory file. This keeps the token out of shell history by default.
    args.token = args.token or os.environ.get("EARTHDATA_TOKEN") or saved_token()
    if not args.dry_run and not args.token:
        parser.error("provide --token, set EARTHDATA_TOKEN, or create ~/.earthdata_token (Earthdata Login required)")

    # Dry-run is intentionally read-only, including when the output directory
    # has not been created yet.
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    total = downloaded = existing = skipped = 0
    for year in range(args.start_year, args.end_year + 1):
        year_dir = args.output_dir / str(year)
        if not args.dry_run:
            year_dir.mkdir(exist_ok=True)
        entries = list(cmr_entries(year))
        print(f"{year}: CMR returned {len(entries)} granules")
        for entry in entries:
            url = data_url(entry)
            if not url:
                skipped += 1
                print(f"  skipped (no HDF5 link): {entry.get('title', '<untitled>')}", file=sys.stderr)
                continue
            total += 1
            target = year_dir / Path(url.split("?", 1)[0]).name
            if args.dry_run:
                print(target)
                continue
            result = download(url, target, args.token, args.retries)
            downloaded += result == "downloaded"
            existing += result == "exists"
    print(f"Done: {total} HDF5 granules; downloaded={downloaded}, already present={existing}, skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
