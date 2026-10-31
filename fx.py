"""為替(ECB参照レート, Frankfurter API経由, キー不要)の実験群ページを生成する。

ページ: fx/index.html(主要通貨・換算計算機), fx/<code>.html(通貨別の長期推移), fx/usd/<year>.html(ドル円の年別)
データの出典表示: 欧州中央銀行(ECB)の参照レート。日本の金融機関の店頭レート(TTM等)とは異なる。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import statistics as st
import urllib.request
from collections import defaultdict

from archive import svg_line

API = "https://api.frankfurter.dev/v1"
CUR = [("USD", "米ドル"), ("EUR", "ユーロ"), ("GBP", "英ポンド"), ("AUD", "豪ドル"),
       ("CAD", "カナダドル"), ("CHF", "スイスフラン"), ("CNY", "人民元"), ("KRW", "韓国ウォン")]
NOTE = ('<p class="mut">出典: 欧州中央銀行(ECB)の参照レート(Frankfurter API経由、営業日ごと・日本時間の夜に更新)。'
        "日本の金融機関の店頭レート(TTM・TTS・TTB)や、外貨両替のレートとは異なります。</p>")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kinri-tools)"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def load(start="1999-01-01"):
    """{date: {code: 1外貨あたりの円}}"""
    syms = ",".join(c for c, _ in CUR)
    raw = _get(f"{API}/{start}..?base=JPY&symbols={syms}")["rates"]
    out = {}
    for d, rates in raw.items():
        out[dt.date.fromisoformat(d)] = {c: 1 / v for c, v in rates.items() if v}
    return dict(sorted(out.items()))


def per(code):
    # 韓国ウォンは100ウォンあたりで表示するのが一般的
    return 100 if code == "KRW" else 1


def fmt(v, code):
    return f"{v * per(code):,.2f}"


def _change(data, code, days):
    dates = [d for d in data if code in data[d]]
    last = dates[-1]
    past = [d for d in dates if d <= last - dt.timedelta(days=days)]
    if not past:
        return None
    a, b = data[past[-1]][code], data[last][code]
    return (b - a) / a * 100


def pages(data):
    out = {}
    last_d = max(data)
    latest = data[last_d]
    # ---- fx/index.html ----
    rows = []
    for c, n in CUR:
        if c not in latest:
            continue
        c30, c365 = _change(data, c, 30), _change(data, c, 365)
        unit = "100" if c == "KRW" else "1"
        rows.append(f'<tr><td><a href="{c.lower()}.html">{n}({unit}{c})</a></td><td>{fmt(latest[c], c)}円</td>'
                    f'<td>{c30:+.2f}%</td><td>{c365:+.2f}%</td></tr>')
    opts = "".join(f'<option value="{latest[c]}">{n}({c})</option>' for c, n in CUR if c in latest)
    body = (f"<p>{last_d:%Y年%m月%d日}時点の主要通貨の対円レートです。毎日自動で更新しています。</p>"
            '<div class="wrap"><table><thead><tr><th>通貨</th><th>レート</th><th>30日間の変化</th><th>1年間の変化</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            '<h2>通貨の換算</h2><label for="fa">金額(外貨)</label><input id="fa" type="number" value="100">'
            f'<label for="fc">通貨</label><select id="fc">{opts}</select>'
            '<div class="out" id="fr"></div>'
            '<p class="mut">海外送金や外貨預金では、ここに表示したレートに各社の手数料(為替コスト)が上乗せされます。</p>'
            + NOTE + '<p><a href="usd/index.html">ドル円の年別アーカイブ(1999年〜)</a></p>')
    js = ("function fx(){const a=+$('fa').value||0,r=+$('fc').value;$('fr').innerHTML=`約 <b>${(a*r).toLocaleString('ja-JP',{maximumFractionDigits:0})}円</b>"
          "(手数料を含まない参照レートでの換算)`;}['fa','fc'].forEach(i=>$(i).addEventListener('input',fx));fx();")
    out["fx/index.html"] = (f"今日の為替レート(ドル円・ユーロ円など主要8通貨)と換算",
                            f"{last_d:%Y年%m月%d日}の主要通貨の対円レート。1ドル={latest['USD']:.2f}円。30日・1年の変化率と通貨換算の計算機。",
                            body, js)
    # ---- fx/<code>.html ----
    for c, n in CUR:
        yearly = defaultdict(list)
        for d, r in data.items():
            if c in r:
                yearly[d.year].append(r[c] * per(c))
        ys = sorted(yearly)
        series = [(y, st.mean(yearly[y])) for y in ys]
        allv = [(d, r[c] * per(c)) for d, r in data.items() if c in r]
        hi, lo = max(allv, key=lambda t: t[1]), min(allv, key=lambda t: t[1])
        unit = "100ウォン" if c == "KRW" else f"1{n}"
        link = (lambda y: f'<a href="usd/{y}.html">{y}年</a>') if c == "USD" else (lambda y: f"{y}年")
        trs = "".join(f"<tr><td>{link(y)}</td><td>{st.mean(yearly[y]):,.2f}</td><td>{max(yearly[y]):,.2f}</td>"
                      f"<td>{min(yearly[y]):,.2f}</td></tr>" for y in reversed(ys))
        body = (f"<p>{unit}あたりの円相場を、{ys[0]}年から年ごとにまとめました。直近({max(allv)[0]:%Y-%m-%d})は {allv[-1][1]:,.2f}円です。"
                f"期間中の最高(円安)は {hi[0]:%Y-%m-%d} の {hi[1]:,.2f}円、最低(円高)は {lo[0]:%Y-%m-%d} の {lo[1]:,.2f}円です。</p>"
                f"<h2>年平均の推移</h2>" + svg_line(series, label_fmt=str) +
                '<h2>年ごとの平均・最高・最低(円)</h2><div class="wrap"><table><thead><tr><th>年</th><th>平均</th><th>最高</th><th>最低</th></tr></thead>'
                f"<tbody>{trs}</tbody></table></div>" + NOTE + '<p><a href="index.html">主要通貨の一覧</a></p>')
        out[f"fx/{c.lower()}.html"] = (f"{n}/円({c}/JPY)の推移({ys[0]}年〜)と年平均",
                                       f"{n}円相場の長期推移。直近{allv[-1][1]:,.2f}円、過去最高{hi[1]:,.2f}円、最低{lo[1]:,.2f}円。年ごとの平均・最高・最低。",
                                       body, "")
    # ---- fx/usd/<year>.html ----
    byy = defaultdict(list)
    for d, r in data.items():
        if "USD" in r:
            byy[d.year].append((d, r["USD"]))
    years = sorted(byy)
    prev = None
    for y in years:
        s = byy[y]
        avg = st.mean(v for _, v in s)
        hi, lo = max(s, key=lambda t: t[1]), min(s, key=lambda t: t[1])
        first, last = s[0][1], s[-1][1]
        months = defaultdict(list)
        for d, v in s:
            months[d.month].append(v)
        trs = "".join(f"<tr><td>{y}年{m}月</td><td>{st.mean(v):.2f}</td><td>{max(v):.2f}</td><td>{min(v):.2f}</td></tr>"
                      for m, v in sorted(months.items()))
        cmp = (f"前年の平均({prev:.2f}円)と比べて{abs(avg-prev):.2f}円の{'円安' if avg > prev else '円高'}です。" if prev else "")
        prev = avg
        nav = " ".join(f'<a href="{yy}.html">{yy}</a>' for yy in (y - 1, y + 1) if yy in byy)
        endw = "直近" if y == years[-1] else "年末"
        body = (f"<p>{y}年のドル円相場は、年初 {first:.2f}円 から{endw} {last:.2f}円 へ"
                f"{'円安' if last > first else '円高'}方向に {abs(last-first):.2f}円 動きました。"
                f"年平均は {avg:.2f}円、最も円安だったのは {hi[0].month}月{hi[0].day}日の {hi[1]:.2f}円、"
                f"最も円高だったのは {lo[0].month}月{lo[0].day}日の {lo[1]:.2f}円 です。{cmp}</p>"
                f"<h2>{y}年のドル円の推移</h2>" + svg_line(s, label_fmt=lambda d: f"{d.month}/{d.day}") +
                '<h2>月ごとの平均・最高・最低(円)</h2><div class="wrap"><table><thead><tr><th>月</th><th>平均</th><th>最高</th><th>最低</th></tr></thead>'
                f"<tbody>{trs}</tbody></table></div>" + NOTE + f'<p class="mut">前後の年: {nav} / <a href="index.html">年別一覧</a></p>')
        out[f"fx/usd/{y}.html"] = (f"{y}年のドル円相場の推移(月平均・最高値・最安値)",
                                   f"{y}年のドル円は年平均{avg:.2f}円、最高{hi[1]:.2f}円、最低{lo[1]:.2f}円。月ごとの平均・最高・最低とグラフ。",
                                   body, "")
    links = " ".join(f'<a href="{y}.html">{y}</a>' for y in reversed(years))
    out["fx/usd/index.html"] = ("ドル円相場の年別アーカイブ(1999年〜)", "ドル円相場を年ごとにまとめたアーカイブ。",
                                f"<p>年を選ぶと、その年のドル円の推移と月ごとの平均・最高・最低を表示します。</p><p>{links}</p>" + NOTE, "")
    return out


def big_moves(data, threshold=1.0):
    """ドル円が前営業日比で threshold% 以上動いた日(フィード用)。"""
    ds = [d for d in data if "USD" in data[d]]
    res = []
    for a, b in zip(ds, ds[1:]):
        ch = (data[b]["USD"] - data[a]["USD"]) / data[a]["USD"] * 100
        if abs(ch) >= threshold:
            res.append((b, data[b]["USD"], ch))
    return res
