#!/usr/bin/env python3
"""Fetch today's Swedish SE3 electricity prices and save them as CSV.

The default source is the open API at elprisetjustnu.se.  Its public endpoint
uses Nord Pool day-ahead data and does not require an API key.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger("se3-prices")
STOCKHOLM = ZoneInfo("Europe/Stockholm")
DEFAULT_URL_TEMPLATE = (
    "https://www.elprisetjustnu.se/api/v1/prices/{year}/{month:02d}-{day:02d}_SE3.json"
)
CSV_FIELDS = [
    "date",
    "time_start",
    "time_end",
    "SEK_per_kWh",
    "EUR_per_kWh",
    "SEK_per_MWh",
    "EUR_per_MWh",
    "currency",
    "bidding_zone",
    "source",
    "retrieved_at",
]


class PriceFetchError(RuntimeError):
    """Raised when the API response cannot be fetched or understood."""


def fetch_json(url: str, timeout: float, retries: int, backoff: float) -> Any:
    """Fetch JSON with a small bounded retry loop for transient failures."""
    request = Request(url, headers={"User-Agent": "se3-price-fetcher/1.0"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise PriceFetchError(f"API returned HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, PriceFetchError) as exc:
            if attempt == retries:
                raise PriceFetchError(f"Could not fetch {url}: {exc}") from exc
            wait = backoff * (2**attempt)
            LOGGER.warning("Request failed (%s); retrying in %.1f seconds", exc, wait)
            time.sleep(wait)
    raise AssertionError("The retry loop must return or raise")


def parse_prices(payload: Any, *, day: date, source: str, retrieved_at: str) -> list[dict[str, str]]:
    """Validate and normalize the API's quarter-hour records."""
    if not isinstance(payload, list) or not payload:
        raise PriceFetchError("API returned no price records")

    records: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise PriceFetchError("API returned an invalid price record")
        try:
            start = datetime.fromisoformat(str(item["time_start"]))
            end = datetime.fromisoformat(str(item["time_end"]))
            sek = float(item["SEK_per_kWh"])
            eur = float(item["EUR_per_kWh"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceFetchError(f"API returned an incomplete price record: {item}") from exc
        if start.date() != day or end <= start:
            raise PriceFetchError("API returned a record outside the requested local date")

        records.append(
            {
                "date": day.isoformat(),
                "time_start": start.isoformat(),
                "time_end": end.isoformat(),
                "SEK_per_kWh": f"{sek:.5f}",
                "EUR_per_kWh": f"{eur:.5f}",
                "SEK_per_MWh": f"{sek * 1000:.2f}",
                "EUR_per_MWh": f"{eur * 1000:.2f}",
                "currency": "SEK/EUR",
                "bidding_zone": "SE3",
                "source": source,
                "retrieved_at": retrieved_at,
            }
        )
    return records


def write_csv(records: list[dict[str, str]], output: Path, *, overwrite: bool) -> bool:
    """Write atomically, returning False when an existing file is kept."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        LOGGER.info("File already exists; leaving it unchanged: %s", output)
        return False

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=output.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        writer = csv.DictWriter(temporary, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    temporary_path.replace(output)
    LOGGER.info("Saved %d records to %s", len(records), output)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="Date to fetch (YYYY-MM-DD; defaults to today)")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("SE3_DATA_DIR", "data")))
    parser.add_argument("--url-template", default=os.getenv("SE3_URL_TEMPLATE", DEFAULT_URL_TEMPLATE))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("SE3_TIMEOUT", "20")))
    parser.add_argument("--retries", type=int, default=int(os.getenv("SE3_RETRIES", "2")))
    parser.add_argument("--backoff", type=float, default=float(os.getenv("SE3_BACKOFF", "2")))
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing daily CSV")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    day = args.date or datetime.now(STOCKHOLM).date()
    url = args.url_template.format(year=day.year, month=day.month, day=day.day)
    output = args.data_dir / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.isoformat()}.csv"
    try:
        payload = fetch_json(url, args.timeout, args.retries, args.backoff)
        records = parse_prices(
            payload,
            day=day,
            source=url,
            retrieved_at=datetime.now(STOCKHOLM).isoformat(),
        )
        write_csv(records, output, overwrite=args.overwrite)
    except (PriceFetchError, OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
