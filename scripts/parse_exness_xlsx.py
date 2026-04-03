from __future__ import annotations

import argparse
import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

NS = {
    'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

HEADER_MAP = {
    '时间': 'time',
    '持仓': 'ticket',
    '交易品种': 'symbol',
    '类型': 'side',
    '交易量': 'volume',
    '价位': 'price',
    '止损': 'sl',
    '止盈': 'tp',
    '手续费': 'commission',
    '库存费': 'swap',
    '盈利': 'profit',
}

OUTPUT_FIELDS = [
    'ticket', 'symbol', 'side', 'volume',
    'open_time', 'open_price', 'sl', 'tp',
    'close_time', 'close_price', 'commission', 'swap', 'profit',
    'holding_seconds', 'price_delta', 'profit_sign',
]


@dataclass
class TradeRow:
    ticket: str
    symbol: str
    side: str
    volume: float
    open_time: str
    open_price: float
    sl: float | None
    tp: float | None
    close_time: str
    close_price: float
    commission: float
    swap: float
    profit: float
    holding_seconds: int
    price_delta: float
    profit_sign: str


class XLSXReader:
    def __init__(self, path: Path):
        self.path = path

    def _shared_strings(self, zf: zipfile.ZipFile) -> list[str]:
        if 'xl/sharedStrings.xml' not in zf.namelist():
            return []
        root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        out: list[str] = []
        for si in root.findall('a:si', NS):
            out.append(''.join((t.text or '') for t in si.iterfind('.//a:t', NS)))
        return out

    def iter_rows(self) -> Iterable[list[str]]:
        with zipfile.ZipFile(self.path) as zf:
            shared = self._shared_strings(zf)
            wb = ET.fromstring(zf.read('xl/workbook.xml'))
            sheets = wb.find('a:sheets', NS)
            rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
            rel_map = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels}
            first_sheet = sheets[0]
            rid = first_sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target = 'xl/' + rel_map[rid]
            root = ET.fromstring(zf.read(target))
            sheet_data = root.find('a:sheetData', NS)
            for row in sheet_data:
                values: list[str] = []
                max_col = 0
                cells = []
                for cell in row.findall('a:c', NS):
                    ref = cell.attrib.get('r', 'A1')
                    col_letters = re.match(r'([A-Z]+)', ref).group(1)
                    col_index = 0
                    for ch in col_letters:
                        col_index = col_index * 26 + (ord(ch) - 64)
                    max_col = max(max_col, col_index)
                    t = cell.attrib.get('t')
                    v = cell.find('a:v', NS)
                    value = v.text if v is not None else ''
                    if t == 's' and value != '':
                        value = shared[int(value)]
                    cells.append((col_index, value))
                values = [''] * max_col
                for idx, value in cells:
                    values[idx - 1] = value
                yield values


def parse_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), '%Y.%m.%d %H:%M:%S').replace(tzinfo=timezone.utc)


def to_float(value: str) -> float | None:
    value = (value or '').strip()
    if value == '':
        return None
    return float(value)


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.startswith('XAUUSD'):
        return 'XAUUSD'
    return symbol


def extract_trades(rows: Iterable[list[str]], symbol_filter: str = 'XAUUSD') -> list[TradeRow]:
    rows = list(rows)
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) >= 13 and row[:13] == ['时间', '持仓', '交易品种', '类型', '交易量', '价位', '止损', '止盈', '时间', '价位', '手续费', '库存费', '盈利']:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError('Could not find trade header row in workbook')

    trades: list[TradeRow] = []
    for row in rows[header_idx + 1:]:
        if not row or not (row[0].strip() if len(row) > 0 else ''):
            continue
        if row[0].strip() in {'委托', '交易', '持仓'}:
            break
        if len(row) < 13:
            continue
        symbol = normalize_symbol(row[2])
        side = row[3].strip().lower()
        if symbol != symbol_filter or side not in {'buy', 'sell'}:
            continue
        # Skip non-closed lifecycle rows like open/fill records that appear in some exports.
        if row[9].strip().lower() == 'filled' or '/' in row[4]:
            continue
        try:
            open_dt = parse_time(row[0])
            close_dt = parse_time(row[8])
            open_price = float(row[5])
            close_price = float(row[9])
            profit = float(row[12])
            volume = float(str(row[4]).split('/')[0].strip())
        except (ValueError, IndexError):
            continue
        price_delta = close_price - open_price if side == 'buy' else open_price - close_price
        trades.append(
            TradeRow(
                ticket=row[1].strip(),
                symbol=symbol,
                side=side,
                volume=volume,
                open_time=open_dt.isoformat().replace('+00:00', 'Z'),
                open_price=open_price,
                sl=to_float(row[6]),
                tp=to_float(row[7]),
                close_time=close_dt.isoformat().replace('+00:00', 'Z'),
                close_price=close_price,
                commission=float(row[10] or 0),
                swap=float(row[11] or 0),
                profit=profit,
                holding_seconds=int((close_dt - open_dt).total_seconds()),
                price_delta=price_delta,
                profit_sign='win' if profit > 0 else 'loss' if profit < 0 else 'flat',
            )
        )
    return trades


def write_csv(trades: list[TradeRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.__dict__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--symbol', default='XAUUSD')
    args = parser.parse_args()

    rows = XLSXReader(Path(args.input)).iter_rows()
    trades = extract_trades(rows, symbol_filter=args.symbol.upper())
    write_csv(trades, Path(args.output))
    print(f'Parsed {len(trades)} trades to {args.output}')


if __name__ == '__main__':
    main()
