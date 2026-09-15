import csv
from datetime import date
from pathlib import Path
from unittest.mock import patch

import fetch_se3_prices


def sample_payload():
    return [
        {
            "SEK_per_kWh": 1.25,
            "EUR_per_kWh": 0.11,
            "time_start": "2026-09-15T00:00:00+02:00",
            "time_end": "2026-09-15T00:15:00+02:00",
        }
    ]


def test_parse_prices_normalizes_units():
    rows = fetch_se3_prices.parse_prices(
        sample_payload(),
        day=date(2026, 9, 15),
        source="test",
        retrieved_at="2026-09-15T12:00:00+02:00",
    )
    assert rows[0]["SEK_per_MWh"] == "1250.00"
    assert rows[0]["EUR_per_MWh"] == "110.00"
    assert rows[0]["bidding_zone"] == "SE3"


def test_write_csv_is_idempotent(tmp_path: Path):
    output = tmp_path / "data" / "2026" / "09" / "2026-09-15.csv"
    rows = fetch_se3_prices.parse_prices(
        sample_payload(),
        day=date(2026, 9, 15),
        source="test",
        retrieved_at="now",
    )
    assert fetch_se3_prices.write_csv(rows, output, overwrite=False)
    assert not fetch_se3_prices.write_csv(rows, output, overwrite=False)
    with output.open(newline="", encoding="utf-8") as file:
        saved = list(csv.DictReader(file))
    assert len(saved) == 1
    assert saved[0]["date"] == "2026-09-15"


def test_invalid_payload_is_rejected():
    try:
        fetch_se3_prices.parse_prices(
            [],
            day=date(2026, 9, 15),
            source="test",
            retrieved_at="now",
        )
    except fetch_se3_prices.PriceFetchError as exc:
        assert "no price records" in str(exc)
    else:
        raise AssertionError("Expected PriceFetchError")


def test_range_fetch_is_inclusive(tmp_path: Path):
    args = fetch_se3_prices.build_parser().parse_args(
        [
            "--start-date",
            "2026-09-14",
            "--end-date",
            "2026-09-15",
            "--data-dir",
            str(tmp_path),
        ]
    )
    with patch.object(fetch_se3_prices, "fetch_day") as fetch_day:
        assert fetch_se3_prices.main(
            [
                "--start-date",
                "2026-09-14",
                "--end-date",
                "2026-09-15",
                "--data-dir",
                str(tmp_path),
            ]
        ) == 0
    assert [call.args[1] for call in fetch_day.call_args_list] == [
        date(2026, 9, 14),
        date(2026, 9, 15),
    ]


def test_invalid_date_range_returns_usage_error():
    assert fetch_se3_prices.main(
        ["--start-date", "2026-09-15", "--end-date", "2026-09-14"]
    ) == 2
