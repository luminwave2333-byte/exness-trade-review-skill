---
name: exness-trade-review
description: Analyze Exness-exported XAUUSD trading history with a repeatable review pipeline that parses `.xlsx` history reports, reconstructs 5m market context, computes RSI-based and behavior-based diagnostics, and outputs structured reports about execution quality, rapid re-entry, impulsive trading, and risk patterns. Use when the user wants daily or multi-day Exness trade review, wants a new report analyzed, wants this review pipeline packaged as a reusable skill, or wants help interpreting XAUUSD trading behavior from Exness history exports.
---

# Exness Trade Review

Use this skill to run repeatable XAUUSD trade reviews from Exness history exports.

## Workflow

1. Save the user's Exness history export as a local `.xlsx` file.
2. Run `scripts/run_review.py --input <file> --run-name <label>`.
3. Read the generated reports under `runs/<label>/reports/`.
4. Summarize:
   - net result
   - win/loss counts
   - rapid re-entry / rapid flip / clustered-trading behavior
   - biggest mistakes
   - whether the day looks healthy, dangerous, or mixed
5. If the user asks about rule interpretation, read `references/interpreting-results.md`.
6. If the user asks about RSI or execution rules, read `references/trading-rules.md`.

## What the scripts do

- `scripts/parse_exness_xlsx.py` — parse the Exness workbook into normalized CSV.
- `scripts/fetch_yahoo_xauusd_5m.py` — fetch 5m gold proxy bars from Yahoo Finance (`GC=F`).
- `scripts/analyze_xauusd_5m.py` — compute RSI and execution-behavior diagnostics.
- `scripts/run_review.py` — run the full pipeline and write a self-contained `runs/<label>/` output folder.

## Output files

After a run, inspect:

- `reports/overview.txt`
- `reports/summary.txt`
- `reports/behavior_report.txt`
- `reports/execution_rules.txt`
- `reports/risk_windows_report.txt`
- `reports/pretrade_checklist.txt`
- `processed/trade_analysis.csv`

## Interpretation rules

Prefer behavioral interpretation over indicator worship.

Use this ordering when summarizing:

1. Did the user avoid rapid re-entry and rapid flip behavior?
2. Did the day avoid clustered trading and oversized loss clusters?
3. Did the user keep losses small?
4. Only then discuss RSI and local market context.

## Important limitations

- `GC=F` is a practical proxy for gold market context, not a broker-identical Exness feed.
- This skill is best for execution review, behavior review, and 5m context reconstruction.
- This skill is not a tick-accurate broker microstructure analyzer.

## When to read references

- Read `references/interpreting-results.md` when you need help turning report metrics into coaching language.
- Read `references/trading-rules.md` when the user asks for RSI usage rules, execution discipline rules, or safe beginner-style entry constraints.
