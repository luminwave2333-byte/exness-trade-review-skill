from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def parse_iso_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def load_csv(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def save_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compute_rsi(closes, period=14):
    rsis = [None] * len(closes)
    if len(closes) <= period:
        return rsis
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rsis[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0)
        loss = max(-delta, 0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        rsis[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return rsis


def entry_zone(rsi):
    if rsi is None:
        return 'unknown'
    if rsi < 30:
        return 'oversold'
    if rsi < 45:
        return 'weak'
    if rsi <= 55:
        return 'neutral'
    if rsi <= 70:
        return 'strong'
    return 'overbought'


def floor_5m(dt: datetime) -> datetime:
    minute = dt.minute - (dt.minute % 5)
    return dt.replace(minute=minute, second=0, microsecond=0)


def note_for_trade(trade, prev_trade):
    notes = []
    rsi = trade['rsi_at_entry']
    if trade['holding_seconds'] < 120:
        notes.append('持仓不到2分钟，明显快于5m计划节奏')
    if trade['seconds_since_prev_trade'] is not None and trade['seconds_since_prev_trade'] < 120:
        notes.append('与上一笔间隔极短，存在反应式追单迹象')
    if trade['rapid_flip']:
        notes.append('上一笔后迅速反手，可能受短时波动和情绪驱动')
    if trade['side'] == 'buy':
        if rsi is not None and rsi > 70:
            notes.append('多单入场时RSI过高，存在追高风险')
        elif rsi is not None and 45 <= rsi <= 65:
            notes.append('多单入场RSI处于中性偏强区，环境不差')
    else:
        if rsi is not None and rsi < 30:
            notes.append('空单入场时RSI过低，存在追空风险')
        elif rsi is not None and 35 <= rsi <= 55:
            notes.append('空单入场RSI处于中性区，需更依赖结构确认')
    if trade['profit'] < 0 and trade['holding_seconds'] < 180:
        notes.append('短时间亏损离场，更像入场时机或情绪问题，不只是方向问题')
    if trade['cluster_size_10m'] >= 3:
        notes.append('10分钟内交易过密，可能已偏离计划执行')
    if not notes:
        notes.append('这笔交易在规则层面暂无明显异常，需要结合更多上下文')
    return '；'.join(notes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trades', required=True)
    parser.add_argument('--market', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--summary', required=True)
    args = parser.parse_args()

    trades = load_csv(Path(args.trades))
    market = load_csv(Path(args.market))
    closes = [float(r['close']) for r in market]
    rsis = compute_rsi(closes, period=14)
    for row, rsi in zip(market, rsis):
        row['rsi14'] = rsi
    market_index = {parse_iso_z(row['timestamp']): row for row in market}
    market_times = sorted(market_index)

    analyzed = []
    prev_open = None
    prev_side = None
    for idx, trade in enumerate(trades):
        open_dt = parse_iso_z(trade['open_time'])
        close_dt = parse_iso_z(trade['close_time'])
        bar_time = floor_5m(open_dt)
        exit_bar_time = floor_5m(close_dt)
        bar = market_index.get(bar_time)
        exit_bar = market_index.get(exit_bar_time)
        if bar is None:
            continue
        start = min(open_dt, close_dt)
        end = max(open_dt, close_dt)
        window = [row for t, row in market_index.items() if start <= t <= end]
        if trade['side'] == 'buy':
            mfe = max(float(r['high']) - float(trade['open_price']) for r in window) if window else 0.0
            mae = max(float(trade['open_price']) - float(r['low']) for r in window) if window else 0.0
        else:
            mfe = max(float(trade['open_price']) - float(r['low']) for r in window) if window else 0.0
            mae = max(float(r['high']) - float(trade['open_price']) for r in window) if window else 0.0
        seconds_since_prev = int((open_dt - prev_open).total_seconds()) if prev_open else None
        cluster_size = sum(1 for other in trades if 0 <= (parse_iso_z(other['open_time']) - open_dt).total_seconds() <= 600)
        item = {
            **trade,
            'holding_seconds': int(trade['holding_seconds']),
            'profit': float(trade['profit']),
            'price_delta': float(trade['price_delta']),
            'rsi_at_entry': None if bar['rsi14'] in ('', None) else round(float(bar['rsi14']), 2),
            'rsi_at_exit': None if exit_bar is None or exit_bar['rsi14'] in ('', None) else round(float(exit_bar['rsi14']), 2),
            'entry_zone': entry_zone(None if bar['rsi14'] in ('', None) else float(bar['rsi14'])),
            'mfe': round(mfe, 3),
            'mae': round(mae, 3),
            'seconds_since_prev_trade': seconds_since_prev,
            'rapid_flip': bool(prev_side and prev_side != trade['side'] and seconds_since_prev is not None and seconds_since_prev < 180),
            'cluster_size_10m': cluster_size,
        }
        item['analysis_note'] = note_for_trade(item, analyzed[-1] if analyzed else None)
        analyzed.append(item)
        prev_open = open_dt
        prev_side = trade['side']

    fieldnames = list(analyzed[0].keys()) if analyzed else []
    save_csv(Path(args.output), analyzed, fieldnames)

    wins = [r for r in analyzed if r['profit'] > 0]
    losses = [r for r in analyzed if r['profit'] < 0]
    rapid = sum(1 for r in analyzed if r['holding_seconds'] < 120)
    flips = sum(1 for r in analyzed if r['rapid_flip'])
    zones = Counter(r['entry_zone'] for r in analyzed)
    summary_lines = [
        'XAUUSD 5m 新手交易复盘摘要',
        '',
        f'总交易数: {len(analyzed)}',
        f'盈利交易: {len(wins)}',
        f'亏损交易: {len(losses)}',
        f'胜率: {round((len(wins) / len(analyzed) * 100), 2) if analyzed else 0}%',
        f'持仓不到2分钟的交易数: {rapid}',
        f'快速反手次数: {flips}',
        f'RSI入场区域分布: {dict(zones)}',
        '',
        '初步结论:',
    ]
    if rapid > len(analyzed) * 0.3:
        summary_lines.append('- 大量交易在2分钟内结束，执行节奏明显快于5m计划，更像波动触发的应激操作。')
    if flips > 0:
        summary_lines.append('- 存在快速反手，说明亏损或波动后容易即时改方向，情绪影响执行的概率较高。')
    if zones.get('overbought', 0) + zones.get('oversold', 0) > len(analyzed) * 0.3:
        summary_lines.append('- 不少交易发生在RSI极端区域，需警惕追涨杀跌。')
    if not wins or len(wins) < len(losses):
        summary_lines.append('- 当前更值得优先修的是交易节奏和行为纪律，而不只是找更复杂的指标。')
    summary_path = Path(args.summary)
    summary_path.write_text('\n'.join(summary_lines), encoding='utf-8')

    reports_dir = summary_path.parent
    behavior_path = reports_dir / 'behavior_report.txt'
    execution_path = reports_dir / 'execution_rules.txt'
    risk_path = reports_dir / 'risk_windows_report.txt'
    checklist_path = reports_dir / 'pretrade_checklist.txt'

    all_loss_amount = -sum(r['profit'] for r in analyzed if r['profit'] < 0)
    rapid_flip = [r for r in analyzed if r['rapid_flip']]
    rapid_flip_loss = -sum(r['profit'] for r in rapid_flip if r['profit'] < 0)
    rapid_reentry = [r for r in analyzed if r['seconds_since_prev_trade'] is not None and r['seconds_since_prev_trade'] < 120]
    rapid_reentry_loss = -sum(r['profit'] for r in rapid_reentry if r['profit'] < 0)
    clustered = [r for r in analyzed if r['cluster_size_10m'] >= 3]
    clustered_loss = -sum(r['profit'] for r in clustered if r['profit'] < 0)
    short_hold = [r for r in analyzed if r['holding_seconds'] < 120]
    short_hold_loss = -sum(r['profit'] for r in short_hold if r['profit'] < 0)

    def pct(a, b):
        return round((a / b) * 100, 2) if b else 0

    behavior_lines = [
        f'XAUUSD 行为模式复盘（基于当前 {len(analyzed)} 笔交易）',
        '',
        '核心观察',
        '- 你的问题不像“完全不会看方向”，更像“在波动里执行被带跑”。',
        '- 5m 是计划周期，但大量实际操作远快于 5m 节奏，说明情绪和即时波动对手的影响非常强。',
        '',
        '关键量化结果',
        '1) 快速反手（rapid flip）',
        '- 定义：与上一笔方向相反，且开仓间隔 < 180 秒。',
        f'- 数量：{len(rapid_flip)} 笔，占总交易 {pct(len(rapid_flip), len(analyzed))}%。',
        f'- 这些亏损合计：{round(rapid_flip_loss, 2)}。',
        f'- 占全部亏损金额：{pct(rapid_flip_loss, all_loss_amount)}%。',
        '',
        '2) 快速再入场（seconds_since_prev_trade < 120）',
        f'- 数量：{len(rapid_reentry)} 笔，占总交易 {pct(len(rapid_reentry), len(analyzed))}%。',
        f'- 这些亏损合计：{round(rapid_reentry_loss, 2)}。',
        f'- 占全部亏损金额：{pct(rapid_reentry_loss, all_loss_amount)}%。',
        '',
        '3) 10 分钟内密集交易（cluster_size_10m >= 3）',
        f'- 数量：{len(clustered)} 笔，占总交易 {pct(len(clustered), len(analyzed))}%。',
        f'- 这些亏损合计：{round(clustered_loss, 2)}。',
        f'- 占全部亏损金额：{pct(clustered_loss, all_loss_amount)}%。',
        '',
        '4) 持仓不到 2 分钟',
        f'- 数量：{len(short_hold)} 笔，占总交易 {pct(len(short_hold), len(analyzed))}%。',
        f'- 这些亏损合计：{round(short_hold_loss, 2)}。',
        f'- 占全部亏损金额：{pct(short_hold_loss, all_loss_amount)}%。',
        '',
        '一句结论',
        f'- 严格快速反手本身约贡献了 {pct(rapid_flip_loss, all_loss_amount)}% 的亏损金额；如果把同类冲动型快速换手一起看，快速再入场相关亏损约占 {pct(rapid_reentry_loss, all_loss_amount)}%。',
    ]
    behavior_path.write_text('\n'.join(behavior_lines), encoding='utf-8')

    execution_lines = [
        'XAUUSD 新手执行约束（自动生成版）',
        '',
        '1) 平仓后冷却 120 秒',
        f'- 因为 2 分钟内再次入场相关亏损已占全部亏损金额 {pct(rapid_reentry_loss, all_loss_amount)}%。',
        '',
        '2) 亏损后至少等待 5 分钟',
        '- 避免进入“马上做回来”的修复模式。',
        '',
        '3) 10 分钟最多 2 笔',
        f'- 因为密集交易相关亏损已占全部亏损金额 {pct(clustered_loss, all_loss_amount)}%。',
        '',
        '4) 反手必须先写理由',
        f'- 因为快速反手相关亏损已占全部亏损金额 {pct(rapid_flip_loss, all_loss_amount)}%。',
        '',
        '一句话总结',
        '- 先修交易节奏，再谈加更多指标。',
    ]
    execution_path.write_text('\n'.join(execution_lines), encoding='utf-8')

    hourly = {}
    for r in analyzed:
        hour = parse_iso_z(r['open_time']).hour
        hourly.setdefault(hour, []).append(r)
    hour_rows = []
    for hour, rs in hourly.items():
        if len(rs) < 20:
            continue
        net = sum(r['profit'] for r in rs)
        hour_rows.append((hour, len(rs), net, net / len(rs), sum(1 for r in rs if r['seconds_since_prev_trade'] is not None and r['seconds_since_prev_trade'] < 120) / len(rs)))
    hour_rows.sort(key=lambda x: x[2])
    risk_lines = ['XAUUSD 风险时段与高危窗口复盘', '', '最危险的小时（UTC）']
    for hour, count, net, avg, rapid_ratio in hour_rows[:5]:
        risk_lines.extend([
            f'- {hour:02d}:00 | 交易数 {count} | 净结果 {round(net, 2)} | 平均每笔 {round(avg, 2)} | 快速再入场占比 {round(rapid_ratio * 100, 2)}%'
        ])
    risk_path.write_text('\n'.join(risk_lines), encoding='utf-8')

    checklist_lines = [
        'XAUUSD 开单前检查清单（自动生成版）',
        '',
        '1) 我是不是刚平仓不到 2 分钟？如果是，不准开。',
        '2) 我上一笔是不是亏损且不到 5 分钟？如果是，不准开。',
        '3) 过去 10 分钟我是不是已经开了 2 笔？如果是，不准开。',
        '4) 这笔是 5m 计划内，还是被刚才那一跳刺激到？如果是后者，不准开。',
        '5) 这笔是不是反手？写不出理由，不准开。',
        '6) 我现在是想按计划做，还是想把刚才亏的钱马上做回来？如果是后者，不准开。',
    ]
    checklist_path.write_text('\n'.join(checklist_lines), encoding='utf-8')

    print(f'Analyzed {len(analyzed)} trades -> {args.output}')
    print(f'Summary -> {args.summary}')


if __name__ == '__main__':
    main()
