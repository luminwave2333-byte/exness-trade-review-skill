# Exness 交易复盘 Skill

这是一个用于 **Exness / MetaTrader 导出交易历史复盘** 的 OpenClaw Skill，重点面向 **XAUUSD（日内 / 超短线）** 交易行为分析。

它的核心能力包括：
- 解析 Exness 导出的 `.xlsx` 历史报表
- 重建 5 分钟黄金市场上下文
- 计算 RSI 环境参考
- 识别快速重进、快速反手、局部密集交易、反应式短持仓等执行问题
- 自动生成结构化复盘报告

---

## 推荐输入文件

推荐使用 Exness / MetaTrader 客户端通过以下方式导出的文件：

**Toolbox → History → 右键 → Report → Open XML**

也就是 **Open XML 格式的 `.xlsx` 报告文件**。

这是本 skill 最推荐、适配最好的输入格式。

---

## 适合用来做什么

- 每日交易复盘
- 多天交易行为对比
- 分析是否存在情绪化交易
- 识别危险盈利日 / 健康盈利日 / 亏损控制失败日
- 将原始交易记录转成可解释的行为报告

---

## 不适合用来做什么

- Tick 级别经纪商微观报价分析
- 代替真实交易系统回测
- 保证生成可盈利策略

---

## 仓库结构

- `README.md` — English repository overview
- `README_cn.md` — 中文说明
- `SKILL.md` — OpenClaw skill 元信息与使用流程
- `scripts/` — 可运行的分析脚本
- `references/` — 行为解释与交易规则参考

---

## 最常用运行方式

```bash
python scripts/run_review.py --input /path/to/report.xlsx --run-name my-run
```

运行后会在下面生成输出：

```bash
runs/my-run/
```

主要包括：
- `processed/trade_analysis.csv`
- `reports/overview.txt`
- `reports/summary.txt`
- `reports/behavior_report.txt`
- `reports/execution_rules.txt`
- `reports/risk_windows_report.txt`
- `reports/pretrade_checklist.txt`

---

## 最典型的使用场景

### 场景 1：复盘某一天
你导出今天的 Exness 历史报表，然后运行：

```bash
python scripts/run_review.py --input ./ReportHistory.xlsx --run-name 20260402
```

然后查看：
- 今天是否盈利
- 是否存在快速重进
- 是否存在密集交易
- 是否属于健康盈利日还是危险盈利日

### 场景 2：连续多天复盘
你每天导出一个报表，用不同 `run-name` 跑：

```bash
python scripts/run_review.py --input ./ReportHistory_20260401.xlsx --run-name 20260401
python scripts/run_review.py --input ./ReportHistory_20260402.xlsx --run-name 20260402
```

再把几天结果并排对比：
- 哪天更稳定
- 哪天局部情绪化更明显
- 哪天大亏单更多

---

## 最值得关注的指标

这个项目不是让你迷信指标，而是帮助你看清 **行为质量**。

建议优先看：
1. 是否快速重进
2. 是否快速反手
3. 是否 10 分钟内交易过密
4. 是否出现重亏单
5. 只有在这些都控制得还可以时，再看 RSI 与市场环境

---

## 安全提醒

不要把真实账户导出文件或 `runs/` 生成结果直接提交到公开仓库。

本仓库已经通过 `.gitignore` 忽略：
- `runs/`
- `.xlsx`
- `.csv`
- `latest_input.xlsx`

---

## 一句话总结

这个 skill 最适合做的，不是“神化入场信号”，而是把你的 Exness 原始交易记录转成：

**可解释、可复盘、可追踪行为改进的交易分析结果。**
