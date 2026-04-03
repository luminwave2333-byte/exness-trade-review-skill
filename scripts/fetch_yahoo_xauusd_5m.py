from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def parse_iso_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def chunk_ranges(start: datetime, end: datetime, days_per_chunk: int = 59):
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=days_per_chunk), end)
        yield cur, chunk_end
        cur = chunk_end


def fetch_chunk(symbol: str, start: datetime, end: datetime, interval: str = '5m'):
    params = {
        'period1': int(start.timestamp()),
        'period2': int(end.timestamp()),
        'interval': interval,
        'includePrePost': 'true',
        'events': 'div,splits,capitalGains',
    }
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{urlencode(params)}'
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    result = payload['chart']['result'][0]
    ts = result.get('timestamp') or []
    quote = result['indicators']['quote'][0]
    for i, stamp in enumerate(ts):
        o = quote['open'][i]
        h = quote['high'][i]
        l = quote['low'][i]
        c = quote['close'][i]
        v = quote.get('volume', [None] * len(ts))[i]
        if None in (o, h, l, c):
            continue
        yield {
            'timestamp': datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat().replace('+00:00', 'Z'),
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume': 0 if v is None else v,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='GC=F')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    start = parse_iso_z(args.start)
    end = parse_iso_z(args.end)
    rows = []
    seen = set()
    for chunk_start, chunk_end in chunk_ranges(start, end):
        for row in fetch_chunk(args.symbol, chunk_start, chunk_end):
            key = row['timestamp']
            if key not in seen:
                seen.add(key)
                rows.append(row)
    rows.sort(key=lambda r: r['timestamp'])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        writer.writeheader()
        writer.writerows(rows)
    print(f'Fetched {len(rows)} bars to {out}')


if __name__ == '__main__':
    main()
