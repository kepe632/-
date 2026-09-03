#!/usr/bin/env python3
"""报告输出增强：按日期+星期建文件夹、Word(docx) 导出、每日早间市场与行业要闻。"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

DISCLAIMER = "本内容基于公开信息整理，不构成任何投资建议，股市有风险，入市需谨慎。"

REPORTS_ROOT = Path(__file__).resolve().parent / "reports"


def weekday_cn(d: dt.date) -> str:
    return "周" + "一二三四五六日"[(d.weekday())]


def dated_dir(root: Path, date: dt.date) -> Path:
    folder = root / f"{date.isoformat()}_{weekday_cn(date)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _f(v, unit=""):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.2f}{unit}"
    except (TypeError, ValueError):
        return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------ 指数 ------------------------------ #
INDEX_CN = [("上证指数", "sh000001"), ("深证成指", "sz399001"), ("创业板指", "sz399006"), ("沪深300", "sh000300")]
INDEX_GLOBAL = [("恒生指数", "hkHSI"), ("道琼斯", "usDJI"), ("纳斯达克", "usIXIC"), ("标普500", "usINX")]


def fetch_indices(codes):
    """腾讯行情直连(--noproxy)，返回 {code: {price, pct}}。涨跌幅由当前价/昨收计算。"""
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    try:
        proc = subprocess.run(["curl.exe", "--noproxy", "*", "-s", "--max-time", "15", url], capture_output=True)
        if proc.returncode != 0:
            return {}
        text = proc.stdout.decode("gbk", "ignore")
    except Exception:
        return {}
    data = {}
    for line in text.splitlines():
        if "~" not in line or '="' not in line:
            continue
        var, payload = line.split('="', 1)
        key = var.strip()
        if key.startswith("v_"):
            key = key[2:]
        parts = payload.strip('"').split("~")
        if len(parts) < 6:
            continue
        price = _num(parts[3])
        prev = _num(parts[4])
        pct = round((price / prev - 1) * 100, 2) if (price and prev) else None
        data[key] = {"price": price, "pct": pct}
    return data


# ------------------------------ 全球/行业新闻 ------------------------------ #
def _row_val(row, names):
    for n in names:
        if n in row.index:
            v = row[n]
            if v is not None and str(v).strip() not in ("", "nan", "None"):
                return v
    return ""


def _parse_time(s, date_part=""):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    if date_part and re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return dt.datetime.strptime(f"{date_part} {s}", fmt)
            except ValueError:
                continue
    return None


def fetch_global_news(window_hours=36):
    """从东财/财联社/新浪取全球财经快讯，过滤近 window_hours 小时。"""
    import akshare as ak
    import pandas as pd

    pd.options.mode.string_storage = "python"
    pd.options.future.infer_string = False
    cutoff = dt.datetime.now() - dt.timedelta(hours=window_hours)
    sources = [("东财", ak.stock_info_global_em), ("财联社", ak.stock_info_global_cls), ("新浪", ak.stock_info_global_sina)]
    items = []
    for src, fn in sources:
        try:
            df = fn()
        except Exception:
            continue
        for _, row in df.head(200).iterrows():
            title = str(_row_val(row, ["标题"]))
            content = str(_row_val(row, ["摘要", "内容"]))
            url = str(_row_val(row, ["链接", "网址", "来源"]))
            t = _parse_time(_row_val(row, ["发布时间", "时间"]), str(_row_val(row, ["发布日期"])))
            if not title:
                title = content[:60]
            if t and t >= cutoff:
                items.append({"title": title, "summary": content, "url": url, "dt": t, "src": src})
    seen, uniq = set(), []
    for it in items:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        uniq.append(it)
    uniq.sort(key=lambda x: x["dt"] or dt.datetime(1970, 1, 1), reverse=True)
    return uniq


GLOBAL_KW = ["美股", "道指", "纳指", "标普", "美联储", "美债", "美元", "欧元", "欧洲", "英央行", "日经",
             "日本央行", "原油", "黄金", "非农", "CPI", "PCE", "离岸", "VIX", "关税", "贸易", "欧股"]
CHINA_KW = ["央行", "A股", "沪指", "深成", "创业板", "证监会", "国务院", "发改委", "财政部", "国常会",
            "人民币", "北向", "北证", "降准", "降息", "LPR", "专项债", "稳增长", "中概", "两市"]
INDUSTRY_KW = ["半导体", "芯片", "光刻", "AI", "算力", "机器人", "新能源", "光伏", "锂电", "储能", "汽车",
               "智能驾驶", "医药", "创新药", "白酒", "军工", "地产", "银行", "券商", "保险", "消费", "游戏",
               "传媒", "5G", "6G", "液冷", "低空", "固态电池"]


def categorize(item):
    txt = (item.get("title", "") or "") + " " + (item.get("summary", "") or "")
    if re.search(r"\.(SZ|SH|BJ)|(公司公告|回购|减持|增持|中标|中报|年报)", txt):
        return "个股/公司公告"
    for kind, kws in (("国际市场", GLOBAL_KW), ("中国市场", CHINA_KW), ("行业产业", INDUSTRY_KW)):
        if any(k in txt for k in kws):
            return kind
    return "市场要闻"


# ------------------------------ Word 导出 ------------------------------ #
def md_to_docx(md_text, path, title):
    import docxfmt
    docxfmt.build_docx(md_text, path, title)


# ------------------------------ 早间报告 ------------------------------ #
def morning_report(date: dt.date):
    folder = dated_dir(REPORTS_ROOT, date)
    cn = fetch_indices([c for _, c in INDEX_CN])
    gl = fetch_indices([c for _, c in INDEX_GLOBAL])
    news = fetch_global_news(window_hours=36)
    buckets = {"国际市场": [], "中国市场": [], "行业产业": [], "个股/公司公告": [], "市场要闻": []}
    for it in news:
        buckets.setdefault(categorize(it), []).append(it)

    md = [f"# 每日早间市场与行业要闻（{date.isoformat()} {weekday_cn(date)}）", ""]
    md += ["## 一、全球主要指数", "", "| 指数 | 最新 | 涨跌幅 |", "|---|---|---|"]
    for name, code in INDEX_GLOBAL:
        row = gl.get(code, {})
        md.append(f"| {name} | {_f(row.get('price'))} | {_f(row.get('pct'), '%')} |")
    md += ["", "## 二、中国市场（A股主要指数）", "", "| 指数 | 最新 | 涨跌幅 |", "|---|---|---|"]
    for name, code in INDEX_CN:
        row = cn.get(code, {})
        md.append(f"| {name} | {_f(row.get('price'))} | {_f(row.get('pct'), '%')} |")
    md += ["", "## 三、要闻分类", ""]
    for kind in ["国际市场", "中国市场", "行业产业", "个股/公司公告", "市场要闻"]:
        items = buckets.get(kind, [])
        md += [f"### {kind}（{len(items)} 条）", ""]
        for it in items[:40]:
            t = it["dt"].strftime("%m-%d %H:%M") if it["dt"] else "?"
            md.append(f"- **[{t}] {it['title']}**")
            if it.get("summary") and it["summary"] != it["title"]:
                md.append(f"  - {it['summary'][:160]}")
            if it.get("url"):
                md.append(f"  - 来源：{it['url']}")
        md.append("")
    md += ["---", "", DISCLAIMER]

    text = "\n".join(md)
    name = f"每日早间市场与行业要闻_{date.isoformat()}_{weekday_cn(date)}"
    md_path = folder / f"{name}.md"
    md_path.write_text(text, encoding="utf-8")
    docx_path = folder / f"{name}.docx"
    md_to_docx(text, docx_path, title=name)
    print(f"已生成: {md_path}")
    print(f"已生成: {docx_path}")
    return docx_path