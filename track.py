"""時間でしか作れない資産: 予想の記録 → 正式発表との答え合わせ(的中実績) と、変化を知らせるAtomフィード。

data/history.csv : 毎日の推定値(build.py が自動追記)
data/actual.csv  : 財務省の正式発表(募集月ごと)。空欄は未確認。
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib

from archive import to_date

HERE = pathlib.Path(__file__).parent
ACTUAL = HERE / "data" / "actual.csv"
KINDS = [("v10", "変動10年"), ("f5", "固定5年"), ("f3", "固定3年")]


def _hist(rows):
    out = []
    for r in rows:
        d = to_date(r["mof_date"])
        if d:
            out.append((d, {k: float(r[f"est_{k}"]) for k, _ in KINDS}))
    return sorted(out)


def accuracy_page(rows):
    hist = _hist(rows)
    actual = list(csv.DictReader(ACTUAL.open(encoding="utf-8"))) if ACTUAL.exists() else []
    trs, errs = [], []
    for a in sorted(actual, key=lambda x: x["offer_month"], reverse=True):
        y, m = map(int, a["offer_month"].split("-"))
        cutoff = dt.date(y, m, 1)
        before = [h for h in hist if h[0] < cutoff]
        est = before[-1] if before else None
        cells = []
        for k, _ in KINDS:
            act = a.get(k) or ""
            if not act:
                cells.append("<td>未確認</td>")
            elif not est:
                cells.append(f"<td>{float(act):.2f}% / 記録開始前</td>")
            else:
                diff = est[1][k] - float(act)
                errs.append(abs(diff))
                cells.append(f"<td>{float(act):.2f}% / 予想 {est[1][k]:.2f}% ({diff:+.2f})</td>")
        basis = f"{est[0]:%Y-%m-%d}時点の予想" if est else "-"
        trs.append(f"<tr><td>{html.escape(a['offer_month'])}募集 {html.escape(a.get('issue', ''))}</td>{''.join(cells)}"
                   f"<td>{basis}</td></tr>")
    summary = (f"これまでの答え合わせ {len(errs)}件で、予想と実際の差は平均 {sum(errs)/len(errs):.3f}ポイント、"
               f"最大 {max(errs):.2f}ポイントです。" if errs else
               "予想の記録は2026年10月29日に始めたばかりです。最初の答え合わせは、2026年11月募集分の正式発表後に載せます。")
    body = (f"<p>このサイトは毎日、翌月募集の個人向け国債の利率を予想して記録しています。"
            f"財務省の正式発表が出たら、募集月の前月までに出していた最後の予想と比べて、ずれをそのまま公開します。"
            f"都合の悪い結果も消しません。</p><p><b>{summary}</b></p>"
            "<div class=\"wrap\"><table><thead><tr><th>募集</th>"
            + "".join(f"<th>{n}(実際/予想)</th>" for _, n in KINDS)
            + f"<th>比べた予想</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
            f"<p class=\"mut\">予想の記録は全件 <a href=\"https://github.com/kinri-tools/kinri-tools.github.io/blob/main/data/history.csv\">GitHub</a>"
            "で公開しています(変更履歴つき)。後から書き換えられないことを、誰でも確かめられます。</p>"
            '<p>利率予想が変わったときの通知: <a href="feed.xml">フィード(RSS/Atom)</a> をFeedlyなどのフィードリーダーに登録してください。</p>')
    return ("利率予想の答え合わせ(的中実績)", "個人向け国債の利率予想と財務省の正式発表を比べた的中実績。予想の記録は全件公開。", body)


def feed(rows, site_url: str):
    hist = _hist(rows)
    entries, prev = [], None
    for d, e in hist:
        if prev is None or any(abs(e[k] - prev[k]) >= 0.01 for k, _ in KINDS):
            entries.append((d, e, prev))
        prev = e
    items = []
    for d, e, p in reversed(entries[-30:]):
        chg = "" if p is None else " / 前回比 " + " ".join(f"{n}{e[k]-p[k]:+.2f}" for k, n in KINDS)
        title = f"{d:%Y-%m-%d} 翌月の利率予想: " + " ".join(f"{n}{e[k]:.2f}%" for k, n in KINDS)
        items.append(f"<entry><title>{html.escape(title)}</title><id>tag:kinri-tools,{d.isoformat()}</id>"
                     f"<updated>{d.isoformat()}T09:00:00+09:00</updated><link href=\"{site_url}/\"/>"
                     f"<summary>{html.escape(title + chg)}</summary></entry>")
    updated = (entries[-1][0] if entries else dt.date.today()).isoformat()
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f"<title>個人向け国債 利率予想の変化</title><id>{site_url}/feed.xml</id>"
            f"<link href=\"{site_url}/\"/><link rel=\"self\" href=\"{site_url}/feed.xml\"/>"
            f"<updated>{updated}T09:00:00+09:00</updated><author><name>kinri-tools</name></author>"
            + "".join(items) + "</feed>")
