"""財務省の国債金利(1974年〜)から、年別・年限別のアーカイブページを生成する。

各ページはその年/年限の実データ(月平均表・最高/最低・推移グラフ・前年比)から作るので、
ページごとに内容が異なる(中身の薄い量産ページにしない)。
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import statistics as st
import urllib.request
from collections import defaultdict

ALL_CSV = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
CUR_CSV = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
ERA = {"S": 1925, "H": 1988, "R": 2018}
TAX = 0.20315


def to_date(s: str):
    try:
        y, m, d = s[1:].split(".")
        return dt.date(ERA[s[0]] + int(y), int(m), int(d))
    except (KeyError, ValueError):
        return None


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (rate-archive)"})
    return urllib.request.urlopen(req, timeout=60).read().decode("shift_jis", errors="replace")


def load():
    """{date: {年限: 利回り}} と年限リストを返す。"""
    data, mats = {}, None
    for url in (ALL_CSV, CUR_CSV):
        rows = list(csv.reader(io.StringIO(_get(url))))
        header = next(r for r in rows if r and r[0] == "基準日")
        mats = [h for h in header[1:] if h]
        for r in rows:
            d = to_date(r[0]) if r else None
            if not d:
                continue
            vals = {}
            for m, v in zip(mats, r[1:]):
                try:
                    vals[m] = float(v)
                except ValueError:
                    pass
            if vals:
                data[d] = vals
    return dict(sorted(data.items())), mats


def svg_line(points, w=720, h=220, label_fmt=str):
    """points: [(x_label, value)]。テーマ変数で色づけする単純な折れ線。"""
    if len(points) < 2:
        return ""
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + 0.1
    # 目盛り文字はスマホでは大きく表示する(style.css の .chart: 狭い画面で 22 単位)。
    # 文字が切れないよう、左の余白は目盛りの桁数から決め、上下左右にも余白を取る。
    tick_vals = (hi, (hi + lo) / 2, lo)
    tick_txt = [f"{t:.2f}" for t in tick_vals]
    pad, rpad, top, axis = 13 * max(len(s) for s in tick_txt) + 14, 40, 18, h - 32
    xs = [pad + i * (w - pad - rpad) / (len(points) - 1) for i in range(len(points))]
    yof = lambda v: top + (hi - v) * (axis - 6 - top) / (hi - lo)  # noqa: E731
    pts = " ".join(f"{x:.1f},{yof(v):.1f}" for x, v in zip(xs, vals))
    ticks = "".join(f'<text x="{pad-6}" y="{yof(t)+5:.1f}" text-anchor="end">{s}</text>'
                    for t, s in zip(tick_vals, tick_txt))
    step = max(1, (len(points) - 1) // 4)  # x軸の目盛りは5つ程度(スマホで重ならないように)
    xl = "".join(f'<text x="{xs[i]:.1f}" y="{h-6}" text-anchor="middle">{html.escape(label_fmt(points[i][0]))}</text>'
                 for i in range(0, len(points), step))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="推移グラフ" style="width:100%;height:auto;fill:var(--mut)">'
            f'<line x1="{pad}" y1="{axis}" x2="{w-rpad}" y2="{axis}" stroke="var(--line)"/>'
            f'<polyline fill="none" stroke="var(--acc)" stroke-width="2" points="{pts}"/>{ticks}{xl}</svg>')


def fmt(v):
    return "-" if v is None else f"{v:.3f}%"


def year_pages(data, mats):
    """{slug: (title, desc, body)} を返す。"""
    by_year = defaultdict(list)
    for d, v in data.items():
        by_year[d.year].append((d, v))
    years = sorted(by_year)
    pages = {}
    main_mats = [m for m in ("1年", "2年", "5年", "10年", "20年", "30年") if m in mats]
    prev_avg10 = None
    for y in years:
        rows = by_year[y]
        months = defaultdict(list)
        for d, v in rows:
            months[d.month].append(v)
        mtab = []
        for m in sorted(months):
            avgs = {k: (st.mean(x[k] for x in months[m] if k in x) if any(k in x for x in months[m]) else None)
                    for k in main_mats}
            mtab.append((m, avgs))
        s10 = [(d, v["10年"]) for d, v in rows if "10年" in v]
        key = "10年" if s10 else next(k for k in ("5年", "1年") if any(k in v for _, v in rows))
        series = [(d, v[key]) for d, v in rows if key in v]
        hi_d, hi_v = max(series, key=lambda t: t[1])
        lo_d, lo_v = min(series, key=lambda t: t[1])
        avg = st.mean(v for _, v in series)
        first, last = series[0][1], series[-1][1]
        trend = "上昇" if last - first > 0.05 else "低下" if first - last > 0.05 else "ほぼ横ばい"
        partial = "(年の途中まで)" if y == years[-1] or y == years[0] else ""
        cmp = ""
        if prev_avg10 is not None and key == "10年":
            diff = avg - prev_avg10
            cmp = f"前年の平均({prev_avg10:.3f}%)と比べて{abs(diff):.3f}ポイント{'高く' if diff > 0 else '低く'}なっています。"
        if key == "10年":
            prev_avg10 = avg
        v10 = max(0.05, avg * 0.66) if key == "10年" else None
        sim = ""
        if v10:
            interest = 1_000_000 * v10 / 100 * (1 - TAX)
            sim = (f"<h2>この年の金利水準だと、個人向け国債(変動10年)の利率は?</h2>"
                   f"<p>10年金利の年平均 {avg:.3f}% に、現行の計算式(×0.66、下限0.05%)をあてはめると約<b>{v10:.2f}%</b>です。"
                   f"100万円なら税引後で年 約{interest:,.0f}円の利子になります(現行制度での仮定の計算です)。</p>")
        trs = "".join("<tr><td>" + f"{y}年{m}月" + "</td>" + "".join(f"<td>{fmt(a[k])}</td>" for k in main_mats)
                      + "</tr>" for m, a in mtab)
        nav = " ".join(f'<a href="{yy}.html">{yy}</a>' for yy in (y - 1, y + 1) if yy in by_year)
        body = (f"<p>{y}年{partial}の日本国債の利回り(財務省「国債金利情報」)をまとめました。"
                f"{key}国債の利回りは、{'データ初日' if y == years[0] else '年初'} {first:.3f}% から"
                f"{'直近' if y == years[-1] else '年末'} {last:.3f}% へ{trend}しました。"
                f"年平均は {avg:.3f}%、最高は {hi_d.month}月{hi_d.day}日の {hi_v:.3f}%、"
                f"最低は {lo_d.month}月{lo_d.day}日の {lo_v:.3f}% です。{cmp}</p>"
                f"<h2>{key}国債利回りの推移({y}年)</h2>"
                + svg_line(series, label_fmt=lambda d: f"{d.month}/{d.day}") +
                f"<h2>年限別の月平均利回り</h2><div class=\"wrap\"><table><thead><tr><th>月</th>"
                + "".join(f"<th>{k}</th>" for k in main_mats) + f"</tr></thead><tbody>{trs}</tbody></table></div>"
                + sim + f'<p class="mut">データ日数: {len(rows)}日。前後の年: {nav} / <a href="../archive.html">アーカイブ一覧</a></p>')
        pages[f"y/{y}.html"] = (f"{y}年の国債利回り(10年・5年・30年など)の推移と月平均",
                                f"{y}年の日本国債利回りの推移。10年国債は年平均{avg:.3f}%、最高{hi_v:.3f}%、最低{lo_v:.3f}%。"
                                "年限別の月平均の表とグラフ。", body)
    return pages, years


def maturity_pages(data, mats):
    pages = {}
    for k in mats:
        yearly = defaultdict(list)
        for d, v in data.items():
            if k in v:
                yearly[d.year].append(v[k])
        if not yearly:
            continue
        ys = sorted(yearly)
        series = [(y, st.mean(yearly[y])) for y in ys]
        last_d = max(d for d, v in data.items() if k in v)
        last_v = data[last_d][k]
        allv = [(d, v[k]) for d, v in data.items() if k in v]
        hi_d, hi_v = max(allv, key=lambda t: t[1])
        lo_d, lo_v = min(allv, key=lambda t: t[1])
        trs = "".join(f'<tr><td><a href="../y/{y}.html">{y}年</a></td><td>{a:.3f}%</td>'
                      f'<td>{max(yearly[y]):.3f}%</td><td>{min(yearly[y]):.3f}%</td></tr>' for y, a in reversed(series))
        body = (f"<p>{k}国債の利回りを、データのある{ys[0]}年から毎年の平均でまとめました。"
                f"直近({last_d:%Y年%m月%d日})は {last_v:.3f}% です。"
                f"期間中の最高は {hi_d:%Y年%m月%d日} の {hi_v:.3f}%、最低は {lo_d:%Y年%m月%d日} の {lo_v:.3f}% です。</p>"
                f"<h2>{k}国債利回りの年平均の推移</h2>" + svg_line(series, label_fmt=str) +
                "<h2>年ごとの平均・最高・最低</h2><div class=\"wrap\"><table><thead><tr><th>年</th><th>平均</th>"
                f"<th>最高</th><th>最低</th></tr></thead><tbody>{trs}</tbody></table></div>"
                '<p class="mut"><a href="../archive.html">アーカイブ一覧</a></p>')
        slug = f"m/{k.replace('年', 'y')}.html"
        pages[slug] = (f"{k}国債の利回り推移({ys[0]}年〜)と年平均",
                       f"{k}国債利回りの長期推移。直近{last_v:.3f}%、過去最高{hi_v:.3f}%、過去最低{lo_v:.3f}%。年ごとの平均・最高・最低の表。",
                       body)
    return pages


def hub(years, mat_slugs):
    body = ("<p>財務省「国債金利情報」の全期間データから、年別・年限別にまとめたページの一覧です。毎日自動で更新しています。</p>"
            "<h2>年限別の長期推移</h2><p>" + " / ".join(f'<a href="{s}">{t}</a>' for s, t in mat_slugs) + "</p>"
            "<h2>年別</h2><p>" + " ".join(f'<a href="y/{y}.html">{y}</a>' for y in reversed(years)) + "</p>")
    return ("国債利回りアーカイブ(1974年〜)", "日本国債の利回りを年別・年限別にまとめたアーカイブ。", body)
