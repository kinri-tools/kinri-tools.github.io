"""日本銀行 時系列統計データ検索サイトAPI(キー不要、2026-02提供開始)から預金・貸出金利のページを作る。

deposit/index.html : 店頭表示の預金金利(普通・定期の期間別)と、個人向け国債の利率予想との比較
loan/index.html    : 貸出約定平均金利(新規・国内銀行)の長期推移
出典: 日本銀行「預金種類別店頭表示金利の平均年利率等」(IR02)、「貸出約定平均金利」(IR04)
"""
from __future__ import annotations

import json
import statistics as st
import urllib.request
from collections import defaultdict

from archive import svg_line

API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
TAX = 0.20315
DEP = [("DLDR121N", "普通預金"), ("DLDR43TL63MN", "定期 3か月"), ("DLDR43TL66MN", "定期 6か月"),
       ("DLDR43TL61YN", "定期 1年"), ("DLDR43TL62YN", "定期 2年"), ("DLDR43TL63YN", "定期 3年"),
       ("DLDR43TL65YN", "定期 5年"), ("DLDR43TL610YN", "定期 10年")]
LOAN = [("DLLR2CIDBNL1", "総合"), ("DLLR2CIDBNL2", "短期(1年未満)"), ("DLLR2CIDBNL3", "長期(1年以上)")]
SRC = '<p class="mut">出典: 日本銀行 時系列統計データ検索サイト({})。毎日自動で取得しています。</p>'


def fetch(db, codes, start):
    url = f"{API}?format=json&lang=jp&db={db}&code={','.join(codes)}&startDate={start}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (kinri-tools)"})
    j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
    if j.get("STATUS") != 200:
        raise RuntimeError(j.get("MESSAGE"))
    out = {}
    for s in j["RESULTSET"]:
        v = s["VALUES"]
        out[s["SERIES_CODE"]] = [(str(d), x) for d, x in zip(v["SURVEY_DATES"], v["VALUES"]) if x is not None]
    return out


def ym(d):
    return f"{d[:4]}年{int(d[4:6])}月"


def deposit_page(est):
    data = fetch("IR02", [c for c, _ in DEP], "202204")
    last = {c: data[c][-1] for c, _ in DEP if data.get(c)}
    yago = {}
    for c, _ in DEP:
        s = dict(data.get(c, []))
        if c in last:
            d = last[c][0]
            yago[c] = s.get(f"{int(d[:4]) - 1}{d[4:]}")
    latest_d = last["DLDR121N"][0]
    rows = "".join(
        f"<tr><td>{n}</td><td>{last[c][1]:.3f}%</td><td>{'-' if yago.get(c) is None else f'{yago[c]:.3f}%'}</td>"
        f"<td>{last[c][1] * (1 - TAX) * 10000:,.0f}円</td></tr>" for c, n in DEP if c in last)
    t1 = last["DLDR43TL61YN"][1]
    best_k, best_v = max((("固定5年", est["f5"]), ("変動10年", est["v10"]), ("固定3年", est["f3"])), key=lambda t: t[1])
    diff = (best_v - t1) / 100 * 1_000_000 * (1 - TAX)
    series = [(ym(d), v) for d, v in data["DLDR43TL61YN"]]
    body = (f"<p>銀行の店頭に表示されている預金金利の平均です(日本銀行の統計、{ym(latest_d)}時点)。"
            f"普通預金は {last['DLDR121N'][1]:.3f}%、1年定期(300万円未満)は {t1:.3f}% です。</p>"
            "<h2>種類・期間別の預金金利(預入300万円未満)</h2>"
            '<div class="wrap"><table><thead><tr><th>種類</th><th>最新</th><th>1年前</th><th>100万円の税引後利息(1年)</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
            "<h2>個人向け国債と比べると</h2>"
            f"<p>翌月募集の個人向け国債の推定利率は、いちばん高い{best_k}で <b>{best_v:.2f}%</b> です"
            f'(<a href="../index.html">毎日更新の予想</a>)。銀行の1年定期の平均 {t1:.3f}% との差は '
            f"{best_v - t1:.2f}ポイントで、100万円を1年預けると税引後で約 <b>{diff:,.0f}円</b> の差になります。"
            "国債は発行から1年間は換金できない点に注意してください"
            '(<a href="../chuto.html">中途換金のシミュレーション</a>)。</p>'
            "<h2>1年定期の平均金利の推移</h2>" + svg_line(series, label_fmt=lambda s: s.replace("年", "/").replace("月", ""))
            + SRC.format("預金種類別店頭表示金利の平均年利率等") +
            '<p class="mut">個別の銀行の金利は、平均より高いことも低いこともあります。新規口座向けの特別金利は含みません。</p>')
    return ("銀行の預金金利の平均(普通預金・定期預金)と国債との比較",
            f"日本銀行の統計による店頭表示の預金金利の平均({ym(latest_d)})。普通預金{last['DLDR121N'][1]:.3f}%、1年定期{t1:.3f}%。"
            "個人向け国債の利率予想との利息の差も計算。", body, "")


def loan_page():
    data = fetch("IR04", [c for c, _ in LOAN], "199310")
    main = data["DLLR2CIDBNL1"]
    yearly = defaultdict(list)
    for d, v in main:
        yearly[int(d[:4])].append(v)
    series = [(y, st.mean(v)) for y, v in sorted(yearly.items())]
    lastd, lastv = main[-1]
    lo = min(main, key=lambda t: t[1])
    hi = max(main, key=lambda t: t[1])
    latest = "".join(f"<tr><td>{n}</td><td>{data[c][-1][1]:.3f}%</td></tr>" for c, n in LOAN if data.get(c))
    trs = "".join(f"<tr><td>{y}年</td><td>{st.mean(v):.3f}%</td><td>{max(v):.3f}%</td><td>{min(v):.3f}%</td></tr>"
                  for y, v in sorted(yearly.items(), reverse=True))
    body = (f"<p>国内銀行が新しく貸し出したお金の平均金利(貸出約定平均金利・新規・総合)は、{ym(lastd)}時点で "
            f"<b>{lastv:.3f}%</b> です。1993年以降で最も低かったのは {ym(lo[0])} の {lo[1]:.3f}%、"
            f"最も高かったのは {ym(hi[0])} の {hi[1]:.3f}% です。</p>"
            f'<h2>最新({ym(lastd)})</h2><div class="wrap"><table><thead><tr><th>区分</th><th>金利</th></tr></thead><tbody>{latest}</tbody></table></div>'
            "<h2>年平均の推移(新規・総合)</h2>" + svg_line(series, label_fmt=str) +
            '<h2>年ごとの平均・最高・最低</h2><div class="wrap"><table><thead><tr><th>年</th><th>平均</th><th>最高</th><th>最低</th></tr></thead>'
            f"<tbody>{trs}</tbody></table></div>"
            '<p>住宅ローンの返済額は <a href="../loan.html">住宅ローン返済額の計算</a> で試算できます。</p>'
            + SRC.format("貸出約定平均金利"))
    return ("銀行の貸出金利の推移(1993年〜)", f"国内銀行の貸出約定平均金利(新規・総合)は{ym(lastd)}時点で{lastv:.3f}%。1993年以降の推移と年平均。",
            body, "")


def pages(est):
    return {"deposit/index.html": deposit_page(est), "loan/index.html": loan_page()}
