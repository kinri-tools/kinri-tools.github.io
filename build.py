"""自動更新ツールサイトのビルダー(複数ページ)。

財務省の国債金利CSVを取得し、翌月の個人向け国債利率の推定値と各種計算機を
静的ページとして public/ に生成する。GitHub Actions で毎日実行すれば完全自動で更新される。

  python build.py            # 取得してビルド
  python build.py --offline  # data/history.csv の最新行だけでビルド(テスト用)
環境変数 SITE_URL (例 https://user.github.io/repo) があれば canonical と sitemap に使う。
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import os
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).parent
OUT = HERE / "public"
HIST = HERE / "data" / "history.csv"
MOF_CSV = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
TAX = 0.20315
SITE_NAME = "金利と利息の計算ツール"
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
# 収益化: ASP/AdSense の承認後に設定する。空なら何も出さない。広告であることを明記すること。
AFFILIATE_HTML = os.environ.get("AFFILIATE_HTML", "")
ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "")  # 例 ca-pub-xxxxxxxx
GSC_VERIFY = os.environ.get("GSC_VERIFY", "")          # Search Console の meta 検証コード


def fetch():
    req = urllib.request.Request(MOF_CSV, headers={"User-Agent": "Mozilla/5.0 (rate-estimator)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("shift_jis", errors="replace")
    rows = list(csv.reader(io.StringIO(raw)))
    header = next(r for r in rows if r and r[0] == "基準日")
    data = [r for r in rows if r and r[0][:1] in ("R", "H") and len(r) > 10 and r[10]]
    last = dict(zip(header, data[-1]))
    return last["基準日"], float(last["3年"]), float(last["5年"]), float(last["10年"])


def estimates(y3, y5, y10):
    return {"v10": max(0.05, round(y10 * 0.66, 2)),
            "f5": max(0.05, round(y5 - 0.05, 2)),
            "f3": max(0.05, round(y3 - 0.03, 2))}


def update_history(day, y3, y5, y10):
    HIST.parent.mkdir(exist_ok=True)
    rows = list(csv.DictReader(HIST.open(encoding="utf-8"))) if HIST.exists() else []
    if not rows or rows[-1]["mof_date"] != day:
        e = estimates(y3, y5, y10)
        rows.append({"mof_date": day, "y3": y3, "y5": y5, "y10": y10,
                     "est_v10": e["v10"], "est_f5": e["f5"], "est_f3": e["f3"]})
        with HIST.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    return rows


JST = dt.timezone(dt.timedelta(hours=9))
# 見た目は style.css(「付箋とメモ用紙」: 紙の地・手書き風の見出し・付箋・日付印)。ページに埋め込んで配信する。
# 変数 --bg --fg --mut --card --line --acc はグラフ(archive.svg_line, gas.py)と holiday.py も使う。
CSS = (HERE / "style.css").read_text(encoding="utf-8")
# 手書き風の見出し用フォント(Klee One 600 の1種類のみ)。本文・数字は端末の標準フォント。
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Klee+One:wght@600&display=swap">')

JS_COMMON = "const TAX=%s;const f=n=>Math.round(n).toLocaleString('ja-JP')+'円';const $=id=>document.getElementById(id);" % TAX


def layout(pages, slug, title, desc, body, js=""):
    root = "../" * slug.count("/")
    jst = dt.datetime.now(JST)
    nav = "".join('<a href="%s%s"%s>%s</a>' % (root, p, ' aria-current="page"' if p == slug else "", html.escape(t))
                  for p, t, _ in pages)
    canon = f'<link rel="canonical" href="{SITE_URL}/{"" if slug == "index.html" else slug}">' if SITE_URL else ""
    adsense = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" '
               'crossorigin="anonymous"></script>') if ADSENSE_CLIENT else ""
    gsc = f'<meta name="google-site-verification" content="{html.escape(GSC_VERIFY)}">' if GSC_VERIFY else ""
    import ads as ad_slots  # 変数名 adsense と衝突させない(以前は module の repr が <head> に出力されていた)
    aff = ad_slots.render(slug) or (f'<h2>PR</h2><div class="card">{AFFILIATE_HTML}</div>' if AFFILIATE_HTML else "")
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebApplication", "name": title,
                     "applicationCategory": "FinanceApplication", "operatingSystem": "Any",
                     "dateModified": jst.date().isoformat()}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{FONTS}
<title>{html.escape(title)} | {SITE_NAME}</title>
<meta name="description" content="{html.escape(desc)}">{canon}{gsc}{adsense}
<link rel="alternate" type="application/atom+xml" title="{'ガソリン価格(全国平均)の週次更新' if slug.startswith('gas/') else '利率予想の変化'}" href="{root}{'gas/feed.xml' if slug.startswith('gas/') else 'feed.xml'}">
<style>{CSS}</style></head><body>
<header><div class="pad"><a class="home" href="{root}index.html">{SITE_NAME}</a><time class="stamp" datetime="{jst:%Y-%m-%d}" title="最終更新日"><small>更新</small> {jst:%m.%d} <small>{jst:%Y}</small></time><nav aria-label="ページ一覧"><b>目次</b>{nav}</nav></div></header>
<main><h1>{html.escape(title)}</h1>
{'<p class="mut">本ページにはプロモーション(広告)が含まれます。広告には「PR」と表示しています。</p>' if aff else ''}
{body}
{aff}
</main>
<footer>このサイトは情報提供のためのもので、特定の金融商品を勧めるものではありません。計算結果は概算です。実際の条件は各金融機関・財務省の公表資料で確認してください。<br>運営者情報・お問い合わせ: <a href="{root}about.html">このサイトについて</a></footer>
<script>{JS_COMMON}{js}</script>
<script type="application/ld+json">{ld}</script>
</body></html>"""


def page_index(ctx):
    e, day = ctx["e"], ctx["day"]
    trs = "".join(f"<tr><td>{html.escape(r['mof_date'])}</td><td>{r['y10']}%</td><td>{r['est_v10']}%</td>"
                  f"<td>{r['est_f5']}%</td><td>{r['est_f3']}%</td></tr>" for r in reversed(ctx["rows"][-60:]))
    body = f"""<p class="mut">最終更新: {ctx['built']}(財務省データの基準日 {day})。毎日自動で更新しています。</p>
<h2>翌月募集の利率の推定値(税引前)</h2>
<div class="cards">
<div class="card"><div class="mut">変動10年</div><div class="big">{e['v10']:.2f}%</div><div class="mut">10年金利 {ctx['y10']}% × 0.66</div></div>
<div class="card"><div class="mut">固定5年</div><div class="big">{e['f5']:.2f}%</div><div class="mut">5年金利 {ctx['y5']}% − 0.05%</div></div>
<div class="card"><div class="mut">固定3年</div><div class="big">{e['f3']:.2f}%</div><div class="mut">3年金利 {ctx['y3']}% − 0.03%</div></div>
</div>
<p class="mut">財務省が公表している計算式に、市場の金利をあてはめた推定値です。実際の利率は、募集開始前に財務省が発表する値で確認してください。下限金利は0.05%です。</p>
<h2>利息計算機(税引後)</h2>
<label for="amt">購入額(円、1万円単位)</label><input id="amt" type="number" min="10000" step="10000" value="1000000">
<label for="type">種類</label><select id="type"><option value="{e['v10']}">変動10年({e['v10']:.2f}%)</option><option value="{e['f5']}">固定5年({e['f5']:.2f}%)</option><option value="{e['f3']}">固定3年({e['f3']:.2f}%)</option></select>
<div class="out" id="res"></div>
<h2>利率の推定値の推移</h2>
<div class="wrap"><table><thead><tr><th>基準日</th><th>10年</th><th>変動10年推定</th><th>固定5年推定</th><th>固定3年推定</th></tr></thead><tbody>{trs}</tbody></table></div>
<h2>よくある質問</h2>
<p><b>変動10年と固定5年、どちらが得?</b> 今後金利が上がると見るなら変動10年(半年ごとに見直し)、今の利率を確定させたいなら固定です。今の推定値では{'固定5年' if e['f5'] > e['v10'] else '変動10年'}のほうが初回の利率が高くなっています。</p>
<p><b>元本割れはする?</b> 個人向け国債は国が元本と利子を支払うので、満期まで持てば額面が戻ります。中途換金した場合も元本は割れませんが、直近2回分の利子相当額が差し引かれます(<a href="chuto.html">中途換金シミュレーター</a>)。</p>"""
    js = """function calc(){const a=+$('amt').value||0,r=+$('type').value/100,y=a*r*(1-TAX);$('res').innerHTML=`1年あたり <b>${f(y)}</b>(半年ごとに ${f(y/2)})<br>月平均 ${f(y/12)} / 1日平均 ${f(y/365)}`;}
['amt','type'].forEach(i=>$(i).addEventListener('input',calc));calc();"""
    return ("個人向け国債の利率予想(毎日更新)と利息計算",
            "財務省の国債金利データから、翌月募集の個人向け国債(変動10年・固定5年・固定3年)の利率を毎日自動で推定します。税引後の利息計算機つき。",
            body, js)


def page_chuto(ctx):
    e = ctx["e"]
    body = f"""<p>個人向け国債は発行から1年たつと換金できます。そのとき「直近2回分の各利子(税引前)×0.79685」が差し引かれます。いつ換金すれば手取りがいくらになるかを計算します。</p>
<label for="amt">購入額(円)</label><input id="amt" type="number" min="10000" step="10000" value="1000000">
<label for="rate">年利率(%、税引前)</label><input id="rate" type="number" step="0.01" value="{e['v10']}">
<label for="months">保有期間(か月、12以上)</label><input id="months" type="number" min="12" value="24">
<div class="out" id="res"></div>
<p class="mut">利率は全期間で一定と仮定した概算です(変動10年は実際には半年ごとに変わります)。利払いは半年ごととして計算しています。</p>"""
    js = """function calc(){const a=+$('amt').value||0,r=+$('rate').value/100,m=Math.max(12,+$('months').value||12);
const n=Math.floor(m/6),semi=a*r/2,got=semi*n*(1-TAX),pen=semi*Math.min(2,n)*0.79685,net=got-pen;
$('res').innerHTML=`受け取った利子(税引後) ${f(got)}<br>換金時の差し引き額 ${f(pen)}<br>⇒ 元本を除いた実質の手取り <b>${f(net)}</b>(元本 ${f(a)} は全額戻ります)`;}
['amt','rate','months'].forEach(i=>$(i).addEventListener('input',calc));calc();"""
    return ("個人向け国債の中途換金シミュレーター",
            "個人向け国債を途中で換金したときの差し引き額(直近2回分の利子×0.79685)と実質の手取りを計算します。", body, js)


def page_compare(ctx):
    e = ctx["e"]
    body = f"""<p>同じ金額を、個人向け国債と定期預金(または普通預金)に預けた場合の税引後の利息を比べます。</p>
<label for="amt">金額(円)</label><input id="amt" type="number" min="10000" step="10000" value="1000000">
<label for="r1">国債の利率(%)</label><input id="r1" type="number" step="0.01" value="{max(e['v10'], e['f5'], e['f3'])}">
<label for="r2">預金の金利(%)</label><input id="r2" type="number" step="0.01" value="0.40">
<label for="yrs">年数</label><input id="yrs" type="number" min="1" value="5">
<div class="out" id="res"></div>
<h2>選ぶときのポイント</h2>
<ul><li>預金は預金保険により1金融機関あたり元本1,000万円とその利息まで保護されます。国債には上限がありません。</li>
<li>預金はいつでも引き出せますが、国債は発行から1年間は原則として換金できません。</li>
<li>新規口座向けの高金利定期は一度きりのことが多いので、2年目以降の金利も確認しましょう。</li></ul>"""
    js = """function calc(){const a=+$('amt').value||0,y=+$('yrs').value||1,i1=a*$('r1').value/100*(1-TAX)*y,i2=a*$('r2').value/100*(1-TAX)*y;
$('res').innerHTML=`国債 ${f(i1)} / 預金 ${f(i2)}(${y}年・税引後・単利)<br>差は <b>${f(Math.abs(i1-i2))}</b>で、${i1>=i2?'国債':'預金'}が有利です`;}
['amt','r1','r2','yrs'].forEach(i=>$(i).addEventListener('input',calc));calc();"""
    return ("国債と定期預金の利息比較", "個人向け国債と定期預金・普通預金の税引後の利息を比較する計算機です。", body, js)


def page_need(ctx):
    e = ctx["e"]
    body = f"""<p>毎月ほしい利息(税引後)から、必要な元本を逆算します。複数の金利で一度に比べられます。</p>
<label for="goal">毎月ほしい税引後の利息(円)</label><input id="goal" type="number" min="100" step="1000" value="30000">
<div class="wrap"><table><thead><tr><th>運用先</th><th>年利(税引前)</th><th>必要な元本</th></tr></thead><tbody id="tb"></tbody></table></div>
<p class="mut">利子には20.315%が源泉徴収されます。元本が増えない単利で計算しています。</p>"""
    js = f"""const R=[['個人向け国債 固定5年(推定)',{e['f5']}],['個人向け国債 変動10年(推定)',{e['v10']}],['個人向け国債 固定3年(推定)',{e['f3']}],['ネット銀行 普通預金(例)',0.85],['メガバンク 普通預金(例)',0.40]];
function calc(){{const g=+$('goal').value||0;$('tb').innerHTML=R.map(([n,r])=>`<tr><td>${{n}}</td><td>${{r.toFixed(2)}}%</td><td>${{f(g*12/(r/100*(1-TAX)))}}</td></tr>`).join('');}}
$('goal').addEventListener('input',calc);calc();"""
    return ("月◯円の利息に必要な元本の計算", "毎月の利息の目標額から、国債や預金で必要になる元本を逆算します。", body, js)


def page_loan(ctx):
    body = """<p>借入額・金利・期間から、毎月の返済額と総利息を計算します(元利均等返済)。金利が上がった場合と比べられます。</p>
<label for="p">借入額(円)</label><input id="p" type="number" step="100000" value="30000000">
<label for="r">金利(年%)</label><input id="r" type="number" step="0.01" value="0.9">
<label for="y">返済期間(年)</label><input id="y" type="number" value="35">
<label for="up">金利が上がった場合の上昇幅(%)</label><input id="up" type="number" step="0.1" value="1.0">
<div class="out" id="res"></div>
<p class="mut">ボーナス返済なし・金利は全期間一定と仮定した概算です。実際の変動金利型ローンには5年ルールや125%ルールがある場合があります。</p>"""
    js = """const pm=(P,r,n)=>r===0?P/n:P*r/(1-Math.pow(1+r,-n));
function calc(){const P=+$('p').value||0,n=(+$('y').value||1)*12,r=(+$('r').value||0)/1200,r2=r+(+$('up').value||0)/1200;
const a=pm(P,r,n),b=pm(P,r2,n);$('res').innerHTML=`毎月の返済額 <b>${f(a)}</b>(総利息 ${f(a*n-P)})<br>金利が上がった場合 ${f(b)}/月(+${f(b-a)})、総利息 ${f(b*n-P)}`;}
['p','r','y','up'].forEach(i=>$(i).addEventListener('input',calc));calc();"""
    return ("住宅ローン返済額の計算(金利上昇シミュレーション)", "住宅ローンの毎月の返済額と総利息を計算し、金利が上がった場合と比較します。", body, js)


def page_about(ctx):
    body = """<p>このサイトは、公的な統計データを使って、金利・利息・物価・ガソリン価格・手取りなどを手軽に確かめられるようにした、個人運営のメモ帳のようなツール集です。データは毎日自動で取得し、ページを作り直しています。</p>
<h2>データの出典</h2><p>各ページの末尾に、出典・取得日・利用条件を記載しています。ランキング・平均・予想・計算結果は、当サイトが公表データをもとに計算したものです。</p>
<ul><li>財務省「国債金利情報」(<a href="https://www.mof.go.jp/jgbs/reference/interest_rate/">財務省のページ</a>)</li>
<li>日本銀行「時系列統計データ検索サイト」(預金・貸出金利)(<a href="https://www.stat-search.boj.or.jp/">日本銀行のページ</a>)</li>
<li>総務省統計局「消費者物価指数」(<a href="https://www.stat.go.jp/data/cpi/">総務省統計局のページ</a>)</li>
<li>欧州中央銀行(ECB)の参照為替レート(Frankfurter API経由)(<a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html">ECBのページ</a>)</li>
<li>資源エネルギー庁「石油製品価格調査」(<a href="https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/">資源エネルギー庁のページ</a>)</li>
<li>内閣府「国民の祝日について」(<a href="https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html">内閣府のページ</a>)</li>
<li>全国健康保険協会(協会けんぽ)・国税庁・総務省・厚生労働省・日本年金機構などの公表資料(手取り計算)</li></ul>
<h2>お問い合わせ</h2><p>誤りのご指摘やご意見は、<a href="https://github.com/kinri-tools/kinri-tools.github.io/issues">GitHubのIssues</a>からお知らせください。データの変更履歴と予想の記録も、同じ場所で公開しています。</p>
<h2>免責事項</h2><p>計算結果は概算であり、正確性を保証するものではありません。金融商品の購入は、ご自身の判断で、各金融機関の資料を確認のうえ行ってください。</p>
<h2>広告について</h2><p>当サイトは、A8.net(株式会社ファンコミュニケーションズ)などのアフィリエイトプログラムを利用しています。広告のリンク先で申し込みや購入があると、当サイトが報酬を受け取ることがあります。広告を含むページでは、ページの上部にその旨を表示し、広告そのものには「PR」と表示しています。掲載は商品の推奨ではありません。</p>
<h2>プライバシーポリシー</h2><p>当サイトは、閲覧者の個人情報を収集していません。アクセス解析ツールも使っていません。広告のリンクや計測用の画像は広告配信事業者(A8.net など)のサーバーから読み込まれ、事業者がCookieを使って成果を計測することがあります。Cookieはブラウザの設定で無効にできます。見出しの文字は Google Fonts から読み込んでいるため、閲覧時に Google のサーバーと通信します。</p>"""
    return ("このサイトについて", "運営方針・データ出典・免責事項・プライバシーポリシー。", body, "")


PAGES = [("index.html", "国債の利率予想", page_index), ("chuto.html", "中途換金", page_chuto),
         ("compare.html", "国債と預金の比較", page_compare), ("need.html", "必要な元本", page_need),
         ("loan.html", "住宅ローン", page_loan), ("about.html", "このサイトについて", page_about)]


def build(offline=False):
    fetched = None
    if not offline:
        try:
            fetched = fetch()
        except Exception as ex:  # 財務省の取得に失敗しても、記録済みの最新値でサイト全体を公開する
            print(f"::warning::MOF fetch failed, using data/history.csv: {ex!r}")
    if fetched:
        day, y3, y5, y10 = fetched
        rows = update_history(day, y3, y5, y10)
    else:
        rows = list(csv.DictReader(HIST.open(encoding="utf-8")))
        last = rows[-1]
        day, y3, y5, y10 = last["mof_date"], float(last["y3"]), float(last["y5"]), float(last["y10"])
    ctx = {"day": day, "y3": y3, "y5": y5, "y10": y10, "rows": rows, "e": estimates(y3, y5, y10),
           "built": dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M")}
    OUT.mkdir(exist_ok=True)
    nav = [(p, t, fn) for p, t, fn in PAGES if p != "about.html"] + [("accuracy.html", "予想の的中実績", None), ("archive.html", "金利アーカイブ", None),
                                                                    ("deposit/index.html", "預金金利", None),
                                                                    ("loan/index.html", "貸出金利", None),
                                                                    ("cpi/index.html", "物価", None),
                                                                    ("fx/index.html", "為替", None),
                                                                    ("gas/index.html", "ガソリン価格", None),
                                                                    ("tedori/index.html", "手取り計算", None),
                                                                    ("holiday/index.html", "祝日・営業日", None)]
    for slug, _, fn in PAGES:
        title, desc, body, js = fn(ctx)
        (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
    slugs = [s for s, _, _ in PAGES]
    # 的中実績ページとAtomフィード(時間とともに価値が増す独自データ)
    import track
    t, d_, b_ = track.accuracy_page(rows)
    (OUT / "accuracy.html").write_text(layout(nav, "accuracy.html", t, d_, b_), encoding="utf-8")
    slugs.append("accuracy.html")
    (OUT / "feed.xml").write_text(track.feed(rows, SITE_URL or "https://kinri-tools.github.io"),
                                  encoding="utf-8")
    # 日本銀行API(預金・貸出金利)
    try:
        import boj
        for slug, (title, desc, body, js) in boj.pages(ctx["e"]).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
    except Exception as ex:
        print(f"boj skipped: {ex!r}")
    # 消費者物価指数(総務省)
    try:
        import cpi
        dep1y = None
        try:
            dep1y = boj.fetch("IR02", ["DLDR43TL61YN"], "202601")["DLDR43TL61YN"][-1][1]
        except Exception:
            pass
        for slug, (title, desc, body, js) in cpi.page(ctx["e"], dep1y).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
    except Exception as ex:
        print(f"::warning::cpi skipped: {ex!r}")
    # 為替(ECB参照レート)
    try:
        import fx
        for slug, (title, desc, body, js) in fx.pages(fx.load()).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
    except Exception as ex:  # 為替の取得に失敗しても他のページは公開する
        print(f"::warning::fx skipped: {ex!r}")
    # 金利アーカイブ(実データからページごとに異なる内容を生成)
    try:
        import archive
        data, mats = archive.load()
        ypages, years = archive.year_pages(data, mats)
        mpages = archive.maturity_pages(data, mats)
        extra = {**ypages, **mpages}
        extra["archive.html"] = archive.hub(years, [(s, t.split("の")[0]) for s, (t, _, _) in mpages.items()])
        for slug, (title, desc, body) in extra.items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body), encoding="utf-8")
        slugs += list(extra)
    except Exception as ex:  # アーカイブ取得に失敗してもメインページは公開する
        print(f"::warning::archive skipped: {ex!r}")
    # ガソリン価格(資源エネルギー庁 石油製品価格調査・週次)。予想はページを作る前に記録する
    try:
        import gas
        gdata = gas.load()
        gas.record_forecast(gdata)
        for slug, (title, desc, body, js) in gas.pages(gdata).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
        # フィードはサイトマップに入れない
        (OUT / "gas" / "feed.xml").write_text(gas.feed(gdata, SITE_URL or "https://kinri-tools.github.io"),
                                              encoding="utf-8")
    except Exception as ex:  # 取得もキャッシュもできなくても他のページは公開する
        print(f"::warning::gas skipped: {ex!r}")
    # 手取り計算(協会けんぽの都道府県別の保険料率・2026年の税制)
    try:
        import tedori
        tdata = tedori.load()
        for slug, (title, desc, body, js) in tedori.pages(tdata).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
    except Exception as ex:
        print(f"::warning::tedori skipped: {ex!r}")
    # 祝日・営業日(内閣府「国民の祝日」CSV)
    try:
        import holiday
        hdata = holiday.load()
        for slug, (title, desc, body, js) in holiday.pages(hdata).items():
            (OUT / slug).parent.mkdir(parents=True, exist_ok=True)
            (OUT / slug).write_text(layout(nav, slug, title, desc, body, js), encoding="utf-8")
            slugs.append(slug)
    except Exception as ex:
        print(f"::warning::holiday skipped: {ex!r}")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    if os.environ.get("CUSTOM_DOMAIN"):
        (OUT / "CNAME").write_text(os.environ["CUSTOM_DOMAIN"].strip() + "\n", encoding="utf-8")
    if SITE_URL:
        today = dt.date.today().isoformat()
        urls = "".join(f"<url><loc>{SITE_URL}/{'' if s == 'index.html' else s}</loc><lastmod>{today}</lastmod></url>"
                       for s in slugs)
        (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>'
                                         f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                                         encoding="utf-8")
        (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    print(f"built {len(slugs)} pages -> {OUT}  {day}  {ctx['e']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build(offline="--offline" in sys.argv)
