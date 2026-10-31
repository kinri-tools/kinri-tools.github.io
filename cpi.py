"""総務省統計局 消費者物価指数(2025年基準・品目別・月次 CSV, キー不要)から物価ページを作る。

cpi/index.html: 総合の前年比、品目別の値上がり/値下がりランキング、全品目の検索表、
                「物価に負けない金利か」(預金・国債の利率 − 物価上昇率)
出典: 総務省統計局「消費者物価指数」(政府標準利用規約2.0)
"""
from __future__ import annotations

import csv
import html
import io
import json
import urllib.request

URL = "https://www.stat.go.jp/data/cpi/2025/csv/zmi2025aa.csv"
TAX = 0.20315


def load():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (kinri-tools)"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("shift_jis", errors="replace")
    rows = list(csv.reader(io.StringIO(raw)))
    names = rows[0][1:]
    weights = rows[5][1:]
    months = [r for r in rows if r and r[0].isdigit() and len(r[0]) == 6]
    series = {}
    for i, n in enumerate(names):
        s = []
        for r in months:
            v = r[i + 1] if i + 1 < len(r) else ""
            try:
                s.append((r[0], float(v)))
            except ValueError:
                pass
        series[n] = s
    w = {n: (int(x) if x.isdigit() else 0) for n, x in zip(names, weights)}
    return series, w


def yoy(s):
    d = dict(s)
    if not s:
        return None
    m, v = s[-1]
    prev = d.get(f"{int(m[:4]) - 1}{m[4:]}")
    return None if not prev else (m, (v / prev - 1) * 100)


def ym(m):
    return f"{m[:4]}年{int(m[4:])}月"


def page(est, deposit_1y=None):
    series, w = load()
    total = yoy(series["総合"])
    if not total:
        raise RuntimeError("総合の前年比が計算できません")
    m, inf = total
    items = []
    for n, s in series.items():
        y = yoy(s)
        if y and y[0] == m and n != "総合":
            items.append((n, y[1], w.get(n, 0)))
    ranked = [x for x in items if x[2] > 0]
    up = sorted(ranked, key=lambda t: -t[1])[:20]
    down = sorted(ranked, key=lambda t: t[1])[:20]

    def tbl(lst):
        return ('<div class="wrap"><table><thead><tr><th>品目</th><th>前年同月比</th></tr></thead><tbody>'
                + "".join(f"<tr><td>{html.escape(n)}</td><td>{v:+.1f}%</td></tr>" for n, v, _ in lst)
                + "</tbody></table></div>")

    best = max(est.values())
    real = [("個人向け国債(推定・最も高い種類)", best)]
    if deposit_1y is not None:
        real.append(("銀行の1年定期(日銀統計の平均)", deposit_1y))
    rrows = "".join(f"<tr><td>{n}</td><td>{r:.3f}%</td><td>{r * (1 - TAX):.3f}%</td><td>{r * (1 - TAX) - inf:+.2f}%</td>"
                    f"<td>{(r * (1 - TAX) - inf) / 100 * 1_000_000:+,.0f}円</td></tr>" for n, r in real)
    data = json.dumps([[n, round(v, 1)] for n, v, _ in sorted(items, key=lambda t: -t[1])], ensure_ascii=False)
    body = (f"<p>総務省の消費者物価指数(2025年基準)によると、{ym(m)}の物価(総合)は前年同月より <b>{inf:+.1f}%</b> 変化しました。"
            "品目ごとの値上がり・値下がりと、預金や国債の利息が物価上昇に追いつくかをまとめています。毎日自動で最新の公表値を取得しています。</p>"
            "<h2>物価に負けない金利か(100万円を1年)</h2>"
            '<div class="wrap"><table><thead><tr><th>預け先</th><th>金利</th><th>税引後</th><th>物価を引いた実質</th><th>実質の増減</th></tr></thead>'
            f"<tbody>{rrows}</tbody></table></div>"
            '<p class="mut">実質 = 税引後の金利 − 物価上昇率(総合・前年同月比)。単純化した目安です。'
            '<a href="../deposit/index.html">預金金利の詳細</a> / <a href="../index.html">国債の利率予想</a></p>'
            f"<h2>値上がりした品目 上位20({ym(m)}・前年同月比)</h2>" + tbl(up) +
            f"<h2>値下がりした品目 上位20</h2>" + tbl(down) +
            '<h2>全品目を検索</h2><label for="q">品目名</label><input id="q" placeholder="例: 米、電気代、卵">'
            '<div class="wrap"><table><thead><tr><th>品目</th><th>前年同月比</th></tr></thead><tbody id="qt"></tbody></table></div>'
            '<p class="mut">出典: 総務省統計局「消費者物価指数」(2025年基準、全国、月次)。前年同月比は指数から計算しています。</p>')
    js = (f"const IT={data};function q(){{const s=$('q').value.trim();const r=IT.filter(x=>!s||x[0].includes(s)).slice(0,100);"
          "$('qt').innerHTML=r.map(x=>`<tr><td>${x[0]}</td><td>${x[1]>0?'+':''}${x[1].toFixed(1)}%</td></tr>`).join('');}"
          "$('q').addEventListener('input',q);q();")
    return {"cpi/index.html": (f"物価上昇率と品目別の値上がりランキング({ym(m)})",
                               f"{ym(m)}の消費者物価(総合)は前年比{inf:+.1f}%。値上がり・値下がり品目ランキング、全品目検索、預金・国債の実質金利。",
                               body, js)}
