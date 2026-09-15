# SE3 electricity price collector

`fetch_se3_prices.py` downloads the day's quarter-hour prices for Swedish bidding
zone **SE3** and writes a CSV file to:

```text
data/YYYY/MM/YYYY-MM-DD.csv
```

The default source is the open `elprisetjustnu.se` API, which publishes Nord
Pool day-ahead prices without requiring an API key. The URL is configurable so
the adapter can be changed if the public endpoint changes.

## Run

Python 3.10 or newer is required. Install the dependencies first. The `tzdata`
package is needed on Windows because it provides the IANA timezone database
used for correct Swedish daylight-saving handling:

```powershell
python -m pip install -r requirements.txt
```

Then run:

```powershell
python fetch_se3_prices.py
```

To fetch a specific date while testing:

```powershell
python fetch_se3_prices.py --date 2026-09-15
```

To backfill an inclusive date range:

```powershell
python fetch_se3_prices.py --start-date 2025-08-01 --end-date 2026-09-15 --overwrite
```

The range command processes each date independently and reports every failed
date. It returns exit code `1` if one or more dates could not be fetched, so a
partial backfill is not mistaken for a complete one. Historical dates may be
unavailable if the public API does not retain them.

The script uses `Europe/Stockholm` to decide today's date. Network requests
have a timeout and bounded exponential backoff retries. Expected API and
connection failures are logged and return exit code `1`, rather than printing a
traceback. Existing daily files are kept by default; use `--overwrite` to
replace one.

## CSV columns

The output includes local interval start/end, price in SEK and EUR per kWh and
per MWh, currency, bidding zone, source URL, and retrieval timestamp. A normal
day has 96 quarter-hour rows; daylight-saving transition days may have a
different number.

## Configuration

Command-line options take precedence over environment defaults:

```text
SE3_DATA_DIR      Output root (default: data)
SE3_URL_TEMPLATE  URL containing {year}, {month}, and {day}
SE3_TIMEOUT      Request timeout in seconds (default: 20)
SE3_RETRIES      Additional attempts after the first request (default: 2)
SE3_BACKOFF      Initial retry delay in seconds (default: 2)
```

## Cron

Run once daily after the day-ahead prices are normally published:

```cron
15 14 * * * cd /path/to/project && /usr/bin/python3 fetch_se3_prices.py >> /var/log/se3-prices.log 2>&1
```

The command is safe to repeat because an existing daily file is not overwritten
unless `--overwrite` is supplied.

## GitHub Actions

The workflow in `.github/workflows/log_prices.yml` runs automatically at
`00:05` in `Europe/Stockholm` and can also be started with **Run workflow** in
the Actions tab. GitHub Actions schedules use UTC, so the workflow listens at
both relevant UTC times and skips the one that is not `00:05` in Stockholm.

The workflow installs the dependencies, runs the collector, and commits new
files below `data/` back to the repository. It uses the built-in
`GITHUB_TOKEN`; no personal access token is required. In the repository's
**Settings → Actions → General**, **Workflow permissions** must allow
**Read and write permissions** for the workflow token.
