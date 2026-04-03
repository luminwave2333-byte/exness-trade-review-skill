from __future__ import annotations

import argparse
import csv
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'scripts'


def run(cmd: list[str]) -> None:
    print('$', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def parse_iso_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def infer_range(trades_csv: Path) -> tuple[str, str]:
    with trades_csv.open('r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    opens = [parse_iso_z(r['open_time']) for r in rows]
    closes = [parse_iso_z(r['close_time']) for r in rows]
    start = min(opens) - timedelta(days=1)
    end = max(closes) + timedelta(days=1)
    return (
        start.isoformat().replace('+00:00', 'Z'),
        end.isoformat().replace('+00:00', 'Z'),
    )


def write_overview(trade_analysis: Path, output: Path) -> None:
    rows = list(csv.DictReader(trade_analysis.open('r', encoding='utf-8')))
    total = len(rows)
    wins = sum(1 for r in rows if float(r['profit']) > 0)
    losses = sum(1 for r in rows if float(r['profit']) < 0)
    rapid_flip_losses = sum(float(r['profit']) for r in rows if r['rapid_flip'] == 'True' and float(r['profit']) < 0)
    rapid_reentry_losses = sum(
        float(r['profit'])
        for r in rows
        if r['seconds_since_prev_trade'] and int(r['seconds_since_prev_trade']) < 120 and float(r['profit']) < 0
    )
    text = f"""XAUUSD Review Overview

Total trades: {total}
Winning trades: {wins}
Losing trades: {losses}
Win rate: {round((wins / total) * 100, 2) if total else 0}%
Rapid flip loss amount: {round(-rapid_flip_losses, 2)}
Rapid re-entry (<120s) loss amount: {round(-rapid_reentry_losses, 2)}

See also:
- summary.txt
- behavior_report.txt
- execution_rules.txt
- risk_windows_report.txt
- pretrade_checklist.txt
"""
    output.write_text(text, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the XAUUSD review pipeline end-to-end.')
    parser.add_argument('--input', required=True, help='Path to Exness XLSX history export')
    parser.add_argument('--run-name', help='Output folder name under runs/. Defaults to timestamp.')
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--market-symbol', default='GC=F', help='Yahoo Finance symbol used as gold proxy')
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_name = args.run_name or timestamp
    run_dir = ROOT / 'runs' / run_name
    raw_dir = run_dir / 'raw'
    processed_dir = run_dir / 'processed'
    reports_dir = run_dir / 'reports'
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input).resolve()
    copied_input = raw_dir / input_path.name
    copied_input.write_bytes(input_path.read_bytes())

    trades_csv = processed_dir / 'trades_clean.csv'
    market_csv = raw_dir / 'xauusd_5m.csv'
    analysis_csv = processed_dir / 'trade_analysis.csv'
    summary_txt = reports_dir / 'summary.txt'
    overview_txt = reports_dir / 'overview.txt'

    run([
        'python', str(SRC / 'parse_exness_xlsx.py'),
        '--input', str(copied_input),
        '--output', str(trades_csv),
        '--symbol', args.symbol,
    ])

    start, end = infer_range(trades_csv)
    run([
        'python', str(SRC / 'fetch_yahoo_xauusd_5m.py'),
        '--symbol', args.market_symbol,
        '--start', start,
        '--end', end,
        '--output', str(market_csv),
    ])

    run([
        'python', str(SRC / 'analyze_xauusd_5m.py'),
        '--trades', str(trades_csv),
        '--market', str(market_csv),
        '--output', str(analysis_csv),
        '--summary', str(summary_txt),
    ])

    # Copy stable reports into the run folder.
    base_reports = ROOT / 'data' / 'reports'
    for name in [
        'behavior_report.txt',
        'execution_rules.txt',
        'risk_windows_report.txt',
        'pretrade_checklist.txt',
    ]:
        src = base_reports / name
        dst = reports_dir / name
        if src.exists():
            dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')

    write_overview(analysis_csv, overview_txt)
    print(f'Run complete: {run_dir}')


if __name__ == '__main__':
    main()
