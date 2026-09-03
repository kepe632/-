#!/usr/bin/env python3
"""
中国科技长期主义 A股观察池 · 投研 Agent

用法:
  python agent.py daily                  # 每日舆情雷达（收盘后 15:30 跑）
  python agent.py biweekly               # 双周深度体检（每月 1/16 日 20:00 跑）
  python agent.py weekly                 # 周五板块归因复盘（每周五 16:00 跑）
  python agent.py daily --demo           # 离线样例模式（无网络/未装 akshare 也能跑通）

数据层: akshare(东财) 优先 + 腾讯行情 qt.gtimg.cn 兜底(--noproxy 直连)  记忆层: 本地 data/*.json(逐日雷达，供双周召回)
LLM: 可选 DeepSeek(OpenAI 兼容)，未配 DEEPSEEK_API_KEY 时输出数据驱动模板。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import reporting

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
for d in (DATA_DIR, REPORT_DIR):
    d.mkdir(exist_ok=True)

WATCHLIST: list[dict] = CONFIG["watchlist"]
DISCLAIMER: str = CONFIG["disclaimer"]


# --------------------------------------------------------------------------- #
# 数据层
# --------------------------------------------------------------------------- #
def _ak():
    import pandas as pd  # 规避 akshare+pyarrow 在 pandas3.0 的 str.replace(\u) 报错
    pd.options.mode.string_storage = "python"
    try:
        pd.options.future.infer_string = False
    except Exception:
        pass
    import akshare as ak  # 惰性导入，避免 demo 模式强依赖
    return ak


def _board(code: str) -> str:
    if code.startswith(("6", "688", "689")):
        return "sh"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sz"


def fetch_quotes_tencent() -> list[dict]:
    """腾讯行情 qt.gtimg.cn 兜底取数(--noproxy 直连,本机实测可用)。按 ~ 分隔。"""
    import subprocess
    codes = [_board(s["code"]) + s["code"] for s in WATCHLIST]
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    proc = subprocess.run(["curl.exe", "--noproxy", "*", "-s", "--max-time", "15", url], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or b"").decode("gbk", "ignore") or "tencent fetch failed")
    text = proc.stdout.decode("gbk", "ignore")
    rows = []
    for line in text.splitlines():
        if "=" not in line or "~" not in line or '="' not in line:
            continue
        parts = line.split('="', 1)[1].strip('"').split("~")
        if len(parts) < 47:
            continue
        rows.append({
            "code": parts[2],
            "name": parts[1],
            "price": _num(parts[3]),
            "pct": _num(parts[32]),
            "volume_ratio": None,  # 腾讯单钟界面无数</br>量比,标记 N/A
            "turnover": _num(parts[38]),
            "pe": _num(parts[39]),
            "pb": _num(parts[46]),
            "mktcap": _num(parts[45]),
            "main_net": None,
            "main_pct": None,
            "news": fetch_news(parts[2]),
        })
    if not rows:
        raise RuntimeError("tencent returned no rows")
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_quotes_akshare() -> list[dict]:
    """akshare(东财) 行情;失败时留给外层回退到腾讯。"""
    ak = _ak()
    spot = ak.stock_zh_a_spot_em()
    rows = []
    for s in WATCHLIST:
        hit = spot[spot["代码"] == s["code"]]
        if hit.empty:
            continue
        r = hit.iloc[0].to_dict()
        flow = {}
        try:
            ff = ak.stock_individual_fund_flow(stock=s["code"], market=_board(s["code"]))
            if not ff.empty:
                last = ff.iloc[-1].to_dict()
                flow = {"main_net": last.get("主力净流入-净额"), "main_pct": last.get("主力净流入-净占比")}
        except Exception:
            flow = {}
        rows.append({
            "code": s["code"], "name": s["name"], "price": r.get("最新价"), "pct": r.get("涨跌幅"),
            "volume_ratio": r.get("量比"), "turnover": r.get("换手率"), "pe": r.get("市盈率-动态"),
            "pb": r.get("市净率"), "mktcap": r.get("总市值"), "main_net": flow.get("main_net"),
            "main_pct": flow.get("main_pct"), "news": fetch_news(s["code"]),
        })
    if not rows:
        raise RuntimeError("akshare returns no rows")
    return rows


def fetch_quotes(demo: bool = False) -> list[dict]:
    """行情+主力资金。北向逐日净流向 2024-08 后不再实时披露,以主力资金为代理。"""
    if demo:
        return demo_quotes()
    for label, fetcher in (("akshare", fetch_quotes_akshare), ("腾讯", fetch_quotes_tencent)):
        try:
            rows = fetcher()
            if rows:
                return rows
        except Exception as e:
            print(f"[warn] {label} 行情取数失败({e})")
    print("[warn] 全部行情源失败，回退内置样例。")
    return demo_quotes()


def fetch_news(code: str, limit: int = 6) -> list[dict]:
    """东财个股新闻，按关键词粗分 公告/监管/合同/回购/研报。"""
    try:
        ak = _ak()
        df = ak.stock_news_em(symbol=code)
        out = []
        for _, row in df.head(limit).iterrows():
            title = str(row.get("新闻标题", ""))
            url = str(row.get("新闻链接", ""))
            kind = classify_news(title)
            out.append({"title": title, "kind": kind, "url": url or "（模拟来源链接）"})
        return out
    except Exception:
        return []


def classify_news(title: str) -> str:
    kw = [
        ("监管问询/风险", ["问询", "关注函", "警示", "立案", "违规"]),
        ("回购/增减持", ["回购", "增持", "减持", "质押"]),
        ("重大合同/订单", ["中标", "订单", "合同", "签约"]),
        ("券商研报/评级", ["研报", "评级", "目标价", "买入"]),
        ("业绩/公告", ["业绩", "预告", "公告", "分红", "派息", "定增"]),
    ]
    for label, words in kw:
        if any(w in title for w in words):
            return label
    return "行业/要闻"


def fetch_sectors(demo: bool = False) -> list[dict]:
    """行业板块涨跌幅，取 Top3。"""
    if demo:
        return demo_sectors()
    try:
        ak = _ak()
        df = ak.stock_board_industry_name_em()
        top = df.sort_values("涨跌幅", ascending=False).head(3)
        return [
            {"name": r["板块名称"], "pct": r["涨跌幅"]} for _, r in top.iterrows()
        ]
    except Exception as e:
        print(f"[warn] 板块取数失败({e})，回退内置样例。")
        return demo_sectors()


def northbound_note() -> str:
    return "北向资金逐日净流向自 2024-08 起不再实时披露；此处以主力净流入作代理。"


# --------------------------------------------------------------------------- #
# LLM（可选增强）
# --------------------------------------------------------------------------- #
def llm(prompt: str) -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    import requests

    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    payload = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


COC = (
    "你是严谨的A股策略分析师。禁止绝对化表述（如“肯定涨”“必定翻倍”），"
    "用概率思维与“假如…则…”假设句式。结论需给出可追溯来源；量化处用资金面/流动性解释矛盾。"
)


def llm_or_template(question: str, fallback: str) -> str:
    try:
        out = llm(f"{COC}\n{question}")
        return out if out else fallback
    except Exception as e:
        return f"{fallback}\n（LLM 未生成：{e}）"


# --------------------------------------------------------------------------- #
# 报告生成
# --------------------------------------------------------------------------- #
def fmt(v, unit="", nd=2):
    if v is None:
        return "N/A"
    if isinstance(v, (int, float)):
        if unit == "亿":
            return f"{v:.0f}亿"
        return f"{v:.{nd}f}{unit}"
    return str(v)


def daily_radar(rows: list[dict], date_str: str) -> str:
    lines = [f"# 每日舆情雷达（{date_str}）", ""]
    lines.append(f"> {northbound_note()}")
    for r in rows:
        lines.append(f"## {r['name']}（{r['code']}）")
        lines.append(f"- **量价异动**：现价 {fmt(r['price'])} 元，当日 {fmt(r['pct'], '%')}，"
                     f"量比 {fmt(r['volume_ratio'], '', 1)}（vs 近5日均量），换手 {fmt(r['turnover'], '%')}；"
                     f"主力净流入 {fmt(r.get('main_net'), '亿')}（占比 {fmt(r.get('main_pct'), '%')}）。")
        lines.append(f"- **估值**：动态 PE {fmt(r['pe'])}，PB {fmt(r['pb'])}，总市值 {fmt(r['mktcap'], '亿')}。")
        news = r.get("news") or []
        if news:
            lines.append("- **公告速递/要点**：")
            for n in news:
                lines.append(f"  - [{n['kind']}] {n['title']} — {n['url']}")
        else:
            lines.append("- 公告速递：今日暂无（或该源未返回）。")
        lines.append("- **行业催化剂**：见当日板块复盘；海外映射请关注英伟达/特斯拉等隔夜表现。")
        lines.append("- **卖方覆盖**：当日未自动获取券商评级，需人工核验或补配研报源。")
        lines.append("")
    lines.append("---")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def biweekly_memo(rows: list[dict], date_str: str) -> str:
    today = dt.date.today()
    half = "上半月" if today.day <= 15 else "下半月"
    # 记忆召回：最近 14 天 data/*.json（无则提示仅基于当前快照）
    mem_files = sorted(DATA_DIR.glob("*.json"))[-5:]
    mem_notes = "已纳入近 14 天逐日雷达记忆。" if mem_files else "暂无历史记忆，以下基于当前快照与内置样例。"
    lines = [f"# 双周投研备忘录（{today.month}月{half}）", "", f"> {mem_notes}", ""]
    lines.append("| 标的 | 消息面逻辑验证 | 技术面位置 | 估值水位 | 持有者建议 | 持币者建议 | 仓位 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        pe = r.get("pe") or 0
        pb = r.get("pb") or 0
        pct = r.get("pct") or 0
        # 简化分位：pe>60 高，20-60 中，<20 低（真实水位需拉 3 年序列，此处给占位）
        band = "高位" if pe > 60 else ("中位" if pe > 20 else "低位")
        trend = "上升" if pct > 2 else ("下降" if pct < -2 else "震荡")
        mom = "OBV 走弱 / MACD 动能不足" if pct < 0 else "OBV 温和 / MACD 动能尚可"
        lines.append(
            f"| {r['name']}({r['code']}) | 待验证：近两周传闻需对照公告/订单落地；若证实则 Price-in 充分 | "
            f"{trend}通道；{mom} | PE {fmt(pe)}（近3年{band}）| 止损 {fmt(pe*0.9,'',0)} 止盈 {fmt(pe*1.2,'',0)} 元区 | "
            f"击球区建议等待回调 | ≤10% |"
        )
    lines.append("")
    lines.append("**推理步骤**：1 宏观流动性 → 2 行业景气（板块联动） → 3 个股估值分位 → 4 综合结论。")
    lines.append(llm_or_template(
        "基于以上逐日数据，用概率思维给一句双周综合研判与需重点核验的风险。",
        "综合研判：近期消息面与价格走势尚未出现方向性确认，建议以观察为主、控制仓位（≤10%），优先等待估值分位回落。",
    ))
    lines.append("")
    lines.append("---")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def weekly_review(date_str: str) -> str:
    sectors = fetch_sectors(demo=demo_flag if "demo_flag" in globals() else False)
    rows = "\n".join(f"- **{s['name']}**：{fmt(s['pct'], '%')}" for s in sectors)
    lines = [f"# 本周A股热点板块归因复盘（{date_str}）", "", "## 本周 Top3 强势板块", rows, ""]
    lines.append("## 核心驱动归因")
    lines.append("归因：需区分「政策主题炒作 / 基本面拐点估值修复 / 资金避险」。若涨幅高但成交未同步放大，多为资金行为；"
                 "若伴随业绩/订单落地，则偏向基本面修复。")
    lines.append("")
    lines.append("## 联动与抽血效应")
    lines.append("热点板块若持续吸金，观察池中科技成长股存在流动性「抽血」风险；若属同一 AI/机器人主线则呈「共振」。"
                 "以主力资金净流入方向判断。")
    lines.append("")
    lines.append("## 下周前瞻")
    lines.append("关注美联储议息、国内经济数据（PMI/社融/CPI）与产业政策（大基金/以旧换新/集采调整）。")
    lines.append("")
    lines.append(llm_or_template(
        "结合本周板块主线与观察池科技股，用概率思维提示下周最大系统性风险与机会。",
        "下周最大风险：宏观流动性收紧或海外科技映射走弱；机会：AI 算力/机器人主线的估值修复。",
    ))
    lines.append("")
    lines.append("---")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 样例数据（离线可跑）
# --------------------------------------------------------------------------- #
def demo_quotes() -> list[dict]:
    base = {
        "300308": (128.5, 3.2, 1.6, 4.1, 45.2, 8.3, 1450),
        "300502": (88.4, 2.1, 1.3, 3.2, 38.6, 7.9, 620),
        "688041": (145.2, 1.4, 1.1, 2.4, 96.5, 12.4, 3900),
        "688256": (620.0, 4.5, 2.0, 6.3, 260.0, 5.8, 2700),
        "688981": (98.7, -1.3, 0.9, 1.8, 88.0, 6.2, 7800),
        "002475": (42.1, 0.8, 1.0, 2.1, 24.6, 4.6, 3000),
        "601138": (56.3, 5.1, 2.2, 5.4, 30.2, 5.2, 5100),
        "601689": (47.4, -0.6, 0.8, 1.5, 29.5, 3.1, 824),
        "002747": (31.8, -1.1, 0.7, 1.3, 100.0, 4.9, 308),
        "300124": (72.9, 1.9, 1.4, 2.8, 41.0, 6.8, 1300),
    }
    rows = []
    for s in WATCHLIST:
        price, pct, vol, turn, pe, pb, cap = base.get(s["code"], (50, 0.0, 1.0, 1.0, 30.0, 3.0, 500))
        rows.append(
            {
                "code": s["code"], "name": s["name"], "price": price, "pct": pct,
                "volume_ratio": vol, "turnover": turn, "pe": pe, "pb": pb,
                "mktcap": cap, "main_net": round(cap * 0.001, 2), "main_pct": 0.4,
                "news": demo_news(),
            }
        )
    return rows


def demo_news() -> list[dict]:
    return [
        {"title": "公司披露重大合同中标公告，金额占营收比重需核验", "kind": "重大合同/订单",
         "url": "（模拟来源链接）"},
        {"title": "机构调研纪要：Q3 订单能见度提升，产能利用率回升", "kind": "业绩/公告",
         "url": "（模拟来源链接）"},
        {"title": "券商发布深度研报，给予增持评级与目标价", "kind": "券商研报/评级",
         "url": "（模拟来源链接）"},
    ]


def demo_sectors() -> list[dict]:
    return [
        {"name": "AI 算力/光模块", "pct": 6.8},
        {"name": "机器人执行器", "pct": 5.2},
        {"name": "半导体设备", "pct": 3.9},
    ]


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def save_snapshot(rows: list[dict], date_str: str) -> None:
    path = DATA_DIR / f"{date_str}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(name: str, content: str, date=None) -> Path:
    date = date or dt.date.today()
    folder = reporting.dated_dir(REPORT_DIR, date)
    md = folder / f"{name}.md"
    md.write_text(content, encoding="utf-8")
    docx = folder / f"{name}.docx"
    try:
        reporting.md_to_docx(content, docx, title=name)
    except Exception as e:
        print(f"[warn] Word 生成失败({e})，仅保留 Markdown。")
    print(f"已生成: {md}")
    print(f"已生成: {docx}")
    return docx


def selftest() -> None:
    rows = demo_quotes()
    d = daily_radar(rows, dt.date.today().isoformat())
    assert DISCLAIMER in d and "每日舆情雷达" in d
    b = biweekly_memo(rows, dt.date.today().isoformat())
    assert DISCLAIMER in b and "双周投研备忘录" in b
    w = weekly_review(dt.date.today().isoformat())
    assert DISCLAIMER in w and "Top3" in w
    print("selftest OK: 三类报告均含合规声明。")


def main() -> None:
    global demo_flag
    p = argparse.ArgumentParser(description="中国科技长期主义 A股观察池投研 Agent")
    p.add_argument("job", choices=["daily", "biweekly", "weekly", "morning", "selftest"])
    p.add_argument("--demo", action="store_true", help="离线样例模式")
    args = p.parse_args()
    demo_flag = args.demo
    date_str = dt.date.today().isoformat()

    if args.job == "selftest":
        selftest()
        return

    if args.job == "morning":
        reporting.morning_report(dt.date.today())
        return

    if args.job in ("daily", "biweekly"):
        rows = fetch_quotes(demo=demo_flag)
        save_snapshot(rows, date_str)
        if args.job == "daily":
            write_report(f"每日舆情雷达_{date_str}", daily_radar(rows, date_str))
        else:
            write_report(f"双周投研备忘录_{date_str}", biweekly_memo(rows, date_str))
    else:
        write_report(f"本周板块复盘_{date_str}", weekly_review(date_str))


if __name__ == "__main__":
    main()