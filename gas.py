"""資源エネルギー庁「石油製品価格調査」(給油所の小売価格・週次)から、ガソリン価格のページを作る。

gas/index.html    : 全国平均(レギュラー・ハイオク・軽油・灯油)の最新値と前週比・前年比、レギュラーの都道府県ランキング、
                    1990年からの推移、年平均の表、燃料代の計算機(2つの都道府県の比較つき)、よくある質問
gas/<県>.html     : 47都道府県それぞれの週次推移(2004年6月〜)、直近26週の表、年平均と全国順位、近隣の県との比較
gas/forecast.html : 次回調査のレギュラー全国平均の予想(減衰トレンド)と、記録した予想の答え合わせ(的中実績)
gas/feed.xml      : 全国平均の週次更新のAtomフィード(feed() が文字列で返す)

データ: 結果ページ(results.html)にある「週次ファイル」(例 261028s5.xlsx、ファイル名=公表日+s5)。
        シートはハイオク/レギュラー/軽油/灯油店頭/灯油配達、B列の調査日はExcelのシリアル値(1900年基準)。
        全国は1990年8月27日から、都道府県は2004年6月14日から(北海道局の列だけは1990年からあるが、
        ほかの県とそろえるため、都道府県のページでは2004年6月14日以降だけを使う)。単位は円/L(灯油は円/18L)、
        消費税込み(2004年3月以前は税抜き)。北海道と沖縄は、調査の地域区分(北海道局・沖縄局)の値。
        年平均と年ごとの順位は、47都道府県すべての値がある調査回だけで計算する(2011年3月の欠けた回を除き、同じ回どうしで比べる)。
取得: ブラウザ風のUser-Agentが必要(既定のUAは403)。短時間に何度もアクセスするとAWS WAFのチャレンジ(HTTP 202)になるため、
      新しい公表があり得る日(最新の調査週の翌週木曜日以降)だけ取得し、ファイル名が前回確かめたものと同じならXLSXは取りにいかない。
      取得・解析・検証のどれかに失敗したら data/gas.csv(前回取得分のキャッシュ)で作り、ページに「取得できなかった」と表示する
      (GitHub Actions では ::warning:: も出す)。成功したらキャッシュを更新する。
      data/gas.csv の最後の行(fuel 列が _seen)は、最後に中身を確かめた週次ファイルの名前(pub 列)。
予想: record_forecast() が data/gas_forecast.csv に「次回調査の予想」を1行追記する(対象日ごとに1行、過去の行は書き換えない)。
出典: 資源エネルギー庁「石油製品価格調査」。公共データ利用規約(第1.0版)に基づき、加工して利用。

    python gas.py           # load() と同じ(新しい公表があり得る日だけ取得)。最新の全国平均を表示する
    python gas.py --force   # 公表日に関係なく取得してキャッシュを更新する(手元のPCから更新したいとき。GAS_FORCE_FETCH=1 でも同じ)
                            # 取得に失敗したときは終了コード 2(CIで取得できるかを確かめる手順にも使える)
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import math
import os
import pathlib
import re
import statistics as st
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "data" / "gas.csv"
FORECAST = HERE / "data" / "gas_forecast.csv"
TOP_URL = "https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/"
RESULTS_URL = TOP_URL + "results.html"
TERMS_URL = "https://www.enecho.meti.go.jp/about/linksto_thissite/"
PDL_URL = "https://www.digital.go.jp/resources/open_data/public_data_license_v1.0"
RECORD_URL = "https://github.com/kinri-tools/kinri-tools.github.io/blob/main/data/gas_forecast.csv"
# 既定の Python UA は 403 になる。ブラウザと同じ形式の UA を送る。
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")
JST = dt.timezone(dt.timedelta(hours=9))
EXCEL_EPOCH = dt.date(1899, 12, 30)  # 1900年基準のシリアル値(1900/3/1以降)
WD = "月火水木金土日"

FUELS = [  # key, シート名, 表示名, 単位
    ("regular", "レギュラー", "レギュラー", "円/L"),
    ("premium", "ハイオク", "ハイオク", "円/L"),
    ("diesel", "軽油", "軽油", "円/L"),
    ("kerosene", "灯油店頭", "灯油 店頭", "円/18L"),
    ("kerosene_dlv", "灯油配達", "灯油 配達", "円/18L"),
]
FUEL = {k: (lab, unit) for k, _, lab, unit in FUELS}

PREFS = [  # slug, 表示名, 週次ファイルの列見出し(空白を除く), 近隣(陸続き。島は海をはさんで最も近い県)
    ("hokkaido", "北海道", "北海道局", ["aomori"]),
    ("aomori", "青森県", "青森", ["hokkaido", "iwate", "akita"]),
    ("iwate", "岩手県", "岩手", ["aomori", "akita", "miyagi"]),
    ("miyagi", "宮城県", "宮城", ["iwate", "akita", "yamagata", "fukushima"]),
    ("akita", "秋田県", "秋田", ["aomori", "iwate", "miyagi", "yamagata"]),
    ("yamagata", "山形県", "山形", ["akita", "miyagi", "fukushima", "niigata"]),
    ("fukushima", "福島県", "福島", ["miyagi", "yamagata", "niigata", "gunma", "tochigi", "ibaraki"]),
    ("ibaraki", "茨城県", "茨城", ["fukushima", "tochigi", "saitama", "chiba"]),
    ("tochigi", "栃木県", "栃木", ["fukushima", "ibaraki", "gunma", "saitama"]),
    ("gunma", "群馬県", "群馬", ["fukushima", "tochigi", "saitama", "nagano", "niigata"]),
    ("saitama", "埼玉県", "埼玉", ["ibaraki", "tochigi", "gunma", "nagano", "yamanashi", "tokyo", "chiba"]),
    ("chiba", "千葉県", "千葉", ["ibaraki", "saitama", "tokyo"]),
    ("tokyo", "東京都", "東京", ["saitama", "chiba", "kanagawa", "yamanashi"]),
    ("kanagawa", "神奈川県", "神奈川", ["tokyo", "yamanashi", "shizuoka"]),
    ("niigata", "新潟県", "新潟", ["yamagata", "fukushima", "gunma", "nagano", "toyama"]),
    ("toyama", "富山県", "富山", ["niigata", "nagano", "gifu", "ishikawa"]),
    ("ishikawa", "石川県", "石川", ["toyama", "gifu", "fukui"]),
    ("fukui", "福井県", "福井", ["ishikawa", "gifu", "shiga", "kyoto"]),
    ("yamanashi", "山梨県", "山梨", ["saitama", "tokyo", "kanagawa", "shizuoka", "nagano"]),
    ("nagano", "長野県", "長野", ["niigata", "gunma", "saitama", "yamanashi", "shizuoka", "aichi", "gifu", "toyama"]),
    ("gifu", "岐阜県", "岐阜", ["toyama", "ishikawa", "fukui", "nagano", "aichi", "mie", "shiga"]),
    ("shizuoka", "静岡県", "静岡", ["kanagawa", "yamanashi", "nagano", "aichi"]),
    ("aichi", "愛知県", "愛知", ["shizuoka", "nagano", "gifu", "mie"]),
    ("mie", "三重県", "三重", ["aichi", "gifu", "shiga", "kyoto", "nara", "wakayama"]),
    ("shiga", "滋賀県", "滋賀", ["fukui", "gifu", "mie", "kyoto"]),
    ("kyoto", "京都府", "京都", ["fukui", "shiga", "mie", "nara", "osaka", "hyogo"]),
    ("osaka", "大阪府", "大阪", ["kyoto", "nara", "wakayama", "hyogo"]),
    ("hyogo", "兵庫県", "兵庫", ["kyoto", "osaka", "okayama", "tottori"]),
    ("nara", "奈良県", "奈良", ["kyoto", "osaka", "mie", "wakayama"]),
    ("wakayama", "和歌山県", "和歌山", ["osaka", "nara", "mie"]),
    ("tottori", "鳥取県", "鳥取", ["hyogo", "okayama", "shimane", "hiroshima"]),
    ("shimane", "島根県", "島根", ["tottori", "hiroshima", "yamaguchi"]),
    ("okayama", "岡山県", "岡山", ["hyogo", "tottori", "hiroshima"]),
    ("hiroshima", "広島県", "広島", ["okayama", "tottori", "shimane", "yamaguchi"]),
    ("yamaguchi", "山口県", "山口", ["shimane", "hiroshima", "fukuoka"]),
    ("tokushima", "徳島県", "徳島", ["kagawa", "ehime", "kochi"]),
    ("kagawa", "香川県", "香川", ["tokushima", "ehime"]),
    ("ehime", "愛媛県", "愛媛", ["kagawa", "tokushima", "kochi"]),
    ("kochi", "高知県", "高知", ["tokushima", "ehime"]),
    ("fukuoka", "福岡県", "福岡", ["yamaguchi", "saga", "kumamoto", "oita"]),
    ("saga", "佐賀県", "佐賀", ["fukuoka", "nagasaki"]),
    ("nagasaki", "長崎県", "長崎", ["saga"]),
    ("kumamoto", "熊本県", "熊本", ["fukuoka", "oita", "miyazaki", "kagoshima"]),
    ("oita", "大分県", "大分", ["fukuoka", "kumamoto", "miyazaki"]),
    ("miyazaki", "宮崎県", "宮崎", ["oita", "kumamoto", "kagoshima"]),
    ("kagoshima", "鹿児島県", "鹿児島", ["kumamoto", "miyazaki", "okinawa"]),
    ("okinawa", "沖縄県", "沖縄局", ["kagoshima"]),
]
SEA = {frozenset(p) for p in (("hokkaido", "aomori"), ("yamaguchi", "fukuoka"), ("kagoshima", "okinawa"))}
NAME = {s: n for s, n, _, _ in PREFS}
NAME["national"] = "全国平均"
AREAS = ["national"] + [s for s, _, _, _ in PREFS]
LABEL2AREA = {lab: s for s, _, lab, _ in PREFS}
LABEL2AREA["全国"] = "national"


# ---------------------------------------------------------------- XLSX(標準ライブラリのみ)
_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_P = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _ref(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, col - 1


def read_xlsx(blob: bytes) -> dict:
    """{シート名: {(行, 列): 値}}(0始まり)。数値は float、文字列は str。ふりがな(rPh)は除く。"""
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_M + "si"):
            parts = [t.text or "" for t in si.findall(_M + "t")]
            parts += [t.text or "" for r in si.findall(_M + "r") for t in r.findall(_M + "t")]
            shared.append("".join(parts))
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(_P + "Relationship")}
    book = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(_M + "sheet"):
        target = rels[sh.get(_R + "id")]
        path = target[1:] if target.startswith("/") else "xl/" + target
        cells = {}
        for c in ET.fromstring(z.read(path)).iter(_M + "c"):
            ref, t, v = c.get("r"), c.get("t"), c.find(_M + "v")
            if not ref:
                continue
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(_M + "t"))
            elif v is None or v.text is None:
                continue
            elif t in ("str", "e", "b"):
                val = v.text
            else:
                try:
                    val = float(v.text)
                except ValueError:
                    val = v.text
            cells[_ref(ref)] = val
        book[sh.get("name")] = cells
    return book


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)  # 半角・全角の空白と改行を除く


def _sheet_series(cells: dict) -> dict:
    """1シート分 -> {調査日: {area or 'tax': 値}}"""
    hdr = [(r, c) for (r, c), v in cells.items() if isinstance(v, str) and _norm(v) == "調査日"]
    if not hdr:
        raise ValueError("見出し『調査日』が見つかりません")
    hrow, dcol = min(hdr)
    cols = {}
    for (r, c), v in cells.items():
        if r != hrow or not isinstance(v, str):
            continue
        k = _norm(v)
        if k in LABEL2AREA:
            cols[c] = LABEL2AREA[k]
        elif "うち" in k and "税" in k:
            cols[c] = "tax"  # うちガソリン税 / うち軽油引取税(円/L)
    missing = set(AREAS) - set(cols.values())
    if missing:
        raise ValueError(f"列が見つかりません: {sorted(missing)}")
    rows = defaultdict(dict)
    for (r, c), v in cells.items():
        if r > hrow:
            rows[r][c] = v
    out = {}
    for r in sorted(rows):
        serial = rows[r].get(dcol)
        if not isinstance(serial, float) or not 30000 < serial < 80000:
            continue
        day = EXCEL_EPOCH + dt.timedelta(days=int(serial))
        out[day] = {a: round(rows[r][c], 2) for c, a in cols.items() if isinstance(rows[r].get(c), float)}
    return out


def parse_weekly(blob: bytes) -> dict:
    """週次ファイル(…s5.xlsx)を data 形式にする。"""
    book = read_xlsx(blob)
    per = {}
    for key, sheet, _, _ in FUELS:
        cells = book.get(sheet)
        if cells is None:
            cells = next((c for n, c in book.items() if _norm(n) == sheet), None)
        if cells is None:
            raise ValueError(f"シート『{sheet}』が見つかりません")
        per[key] = _sheet_series(cells)
    dates = sorted(set().union(*(set(s) for s in per.values())))
    return _assemble(dates, per, {})


def _assemble(dates, per, pub):
    v = {k: {a: [per[k].get(d, {}).get(a) for d in dates] for a in AREAS} for k, *_ in FUELS}
    tax = {k: [per[k].get(d, {}).get("tax") for d in dates] for k, *_ in FUELS}
    return {"dates": dates, "v": v, "tax": tax, "pub": dict(pub), "source": "", "note": "", "url": ""}


# ---------------------------------------------------------------- キャッシュ(data/gas.csv)
def _fmt(x):
    if x is None:
        return ""
    return f"{x:.2f}".rstrip("0").rstrip(".")


SEEN = "_seen"  # data/gas.csv の最後の行の fuel 列。pub 列は、最後に中身を確かめた週次ファイルの名前


def write_cache(data, path=None) -> bool:
    """data/gas.csv を書く(1行=調査日×油種。最後に _seen の行)。内容が同じなら書かない。書いたら True。"""
    path = pathlib.Path(path or CACHE)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "fuel", "pub", "tax"] + AREAS)
    for i, d in enumerate(data["dates"]):
        pub = data["pub"].get(d)
        for k, *_ in FUELS:
            w.writerow([d.isoformat(), k, pub.isoformat() if pub else "", _fmt(data["tax"][k][i])]
                       + [_fmt(data["v"][k][a][i]) for a in AREAS])
    if data.get("seen"):
        w.writerow([data["dates"][-1].isoformat(), SEEN, data["seen"], ""] + [""] * len(AREAS))
    text = buf.getvalue()
    # バイト列で比べる(壊れて UTF-8 として読めない古いファイルでも、例外にせず上書きする)
    if path.exists() and path.read_bytes().replace(b"\r\n", b"\n") == text.encode("utf-8"):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
    return True


def read_cache(path=None):
    """data/gas.csv を読む。読めない行は飛ばして data['bad_rows'] に数える(load() が取得し直して書き直す)。"""
    path = pathlib.Path(path or CACHE)
    if not path.exists():
        return None
    per, pub, seen, bad = {k: {} for k, *_ in FUELS}, {}, "", 0
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            fuel = row.get("fuel")
            if fuel == SEEN:
                seen = (row.get("pub") or "").strip()
                continue
            try:
                if fuel not in per:
                    raise ValueError(f"fuel={fuel!r}")
                d = dt.date.fromisoformat(row["date"])
                vals = {a: float(row[a]) for a in AREAS if row.get(a)}
                if row.get("tax"):
                    vals["tax"] = float(row["tax"])
                if not all(math.isfinite(x) for x in vals.values()):
                    raise ValueError("nan/inf")
                p = dt.date.fromisoformat(row["pub"]) if row.get("pub") else None
            except (KeyError, TypeError, ValueError):
                bad += 1
                continue
            per[fuel][d] = vals
            if p:
                pub[d] = p
    dates = sorted(set().union(*(set(s) for s in per.values())))
    if not dates:
        return None
    data = _assemble(dates, per, pub)
    data.update(seen=seen, bad_rows=bad)
    return data


# ---------------------------------------------------------------- 取得
def _now():
    return dt.datetime.now(JST)


def _http(url, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = getattr(r, "status", None) or r.getcode()
        body = r.read()
    if status != 200 or not body:  # WAFのチャレンジは 202 + 空/JSのページで返る(urllib は例外にしない)
        raise RuntimeError(f"HTTP {status} ({len(body)} bytes) {url}")
    return body


def find_weekly_link(page: str, base: str = RESULTS_URL):
    """結果ページのHTMLから「週次ファイル」(全国・都道府県別の週次XLSX)のURLを探す。"""
    for m in re.finditer(r'<a\s[^>]*?href="([^"]+?\.xlsx)"[^>]*>(.*?)</a>', page, re.S | re.I):
        if "週次" in re.sub(r"<[^>]+>", "", m.group(2)):
            return urllib.parse.urljoin(base, m.group(1))
    m = re.search(r'href="([^"]*\d{6}s5\.xlsx)"', page)
    return urllib.parse.urljoin(base, m.group(1)) if m else None


def pub_from_link(url):
    """ファイル名の先頭6桁(yymmdd)は公表日。読めなければ None。"""
    m = re.search(r"(\d{2})(\d{2})(\d{2})s5\.xlsx$", url or "")
    if not m:
        return None
    try:
        return dt.date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _latest_link():
    page = _http(RESULTS_URL).decode("utf-8", "replace")
    link = find_weekly_link(page, RESULTS_URL)
    if not link:  # 結果ページの場所が変わった場合: 一覧ページから結果ページをたどる
        top = _http(TOP_URL).decode("utf-8", "replace")
        m = re.search(r'href="([^"]*results[^"]*\.html)"', top)
        if m:
            url = urllib.parse.urljoin(TOP_URL, m.group(1))
            link = find_weekly_link(_http(url).decode("utf-8", "replace"), url)
    if not link:
        raise RuntimeError("週次ファイルへのリンクが見つかりません")
    return link


def _monday(d):
    return d - dt.timedelta(days=d.weekday())


def next_check(latest: dt.date) -> dt.date:
    """新しい公表があり得る最初の日(調査は原則月曜、公表は水曜14時。ビルドは朝なので翌週の木曜から)。"""
    return _monday(latest) + dt.timedelta(days=10)


def validate(data, cached=None):
    ds = data["dates"]
    if len(ds) < 500:
        raise ValueError(f"調査日が少なすぎます({len(ds)})")
    nat = data["v"]["regular"]["national"][-1]
    if nat is None or not 50 < nat < 500:
        raise ValueError(f"最新の全国平均が不正です: {nat}")
    n = sum(1 for s, *_ in PREFS if data["v"]["regular"][s][-1] is not None)
    if n < 40:
        raise ValueError(f"最新週の都道府県の値が少なすぎます({n})")
    if cached:
        if ds[-1] < cached["dates"][-1]:
            raise ValueError(f"取得したファイルがキャッシュより古い({ds[-1]} < {cached['dates'][-1]})")
        if len(ds) < len(cached["dates"]) - 5:
            raise ValueError("取得したファイルの行数がキャッシュより大きく少ない")


def _warn(msg):
    """ログに出す。GitHub Actions では実行結果の画面にも注意(::warning::)として出す。"""
    print(f"gas: {msg}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::warning::gas.py " + msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))


def load(force=None, today=None):
    """最新データ。新しい公表があり得る日だけ取得し、失敗したら data/gas.csv を使う(data['note'] に理由)。
    成功したらキャッシュを更新。キャッシュに読めない行があれば、日付に関係なく取得して書き直す。"""
    if force is None:
        force = os.environ.get("GAS_FORCE_FETCH") == "1"
    today = today or _now().date()
    try:
        cached = read_cache()
    except Exception as ex:  # 壊れたキャッシュでガソリンのページ全体を落とさない: キャッシュなしとして取得する
        _warn(f"data/gas.csv を読めないため、取得し直します: {ex!r}")
        cached = None
    if cached and cached.get("bad_rows"):
        _warn(f"data/gas.csv に読めない行が{cached['bad_rows']}行あるため、取得し直します")
        force = True
    if cached and not force and today < next_check(cached["dates"][-1]):
        cached["source"] = "cache"
        return cached
    try:
        link = _latest_link()
        name = link.rsplit("/", 1)[-1]
        pub = pub_from_link(link)
        known = max(cached["pub"].values(), default=None) if cached else None
        if cached and not cached.get("bad_rows") and (name == cached.get("seen") or (pub and known and pub <= known)):
            cached.update(source="cache", url=link)  # 前回確かめたファイルと同じ(まだ新しい公表がない)
            return cached
        data = parse_weekly(_http(link, timeout=120))
        validate(data, cached)
        data["pub"] = dict(cached["pub"]) if cached else {}
        last = data["dates"][-1]
        if pub and last <= pub <= last + dt.timedelta(days=10):
            data["pub"].setdefault(last, pub)
        data["seen"] = name  # 同じファイル(差し替えで名前だけ変わった場合も)を次から取りにいかない
        write_cache(data)
        data.update(source="network", url=link)
        return data
    except Exception as ex:  # ネットワーク・WAF・形式変更のどれでも、キャッシュがあればそれで続ける
        if not cached:
            raise RuntimeError(f"ガソリン価格を取得できず、キャッシュ(data/gas.csv)もありません: {ex!r}") from ex
        _warn(f"取得に失敗したため data/gas.csv を使います: {ex!r}")
        cached.update(source="cache", note=f"{type(ex).__name__}: {ex}")
        return cached


# ---------------------------------------------------------------- 表示と計算の部品
def _jd(d, wd=True):
    return f"{d.year}年{d.month}月{d.day}日" + (f"({WD[d.weekday()]})" if wd else "")


def _iso_jd(s):
    """'2026-10-31' -> '2026年10月31日'(読めなければそのまま、エスケープして返す)。"""
    try:
        return _jd(dt.date.fromisoformat(s), False)
    except (TypeError, ValueError):
        return html.escape(str(s))


def _p(v, unit="円/L"):
    if v is None:
        return "-"
    return f"{v:,.0f}円" if unit == "円/18L" else f"{v:.1f}円"


def _d(x, unit="円/L"):
    if x is None:
        return "-"
    if unit == "円/18L":
        return "±0円" if abs(x) < 0.5 else f"{x:+,.0f}円"
    return "±0.0円" if abs(x) < 0.05 else f"{x:+.1f}円"


def _vs(ds, k):
    """k 回目の調査と前回の調査の差の呼び方。間隔が8日以内なら『前週比』、休みの週をはさんだら『前回比』。"""
    return "前週比" if k > 0 and (ds[k] - ds[k - 1]).days <= 8 else "前回比"


def _series(data, fuel, area):
    return [(d, x) for d, x in zip(data["dates"], data["v"][fuel][area]) if x is not None]


def _ago(dates, i, days=364):
    """dates[i] の days 日前に最も近い調査日の添字(7日以内になければ None)。"""
    target = dates[i] - dt.timedelta(days=days)
    j = min(range(len(dates)), key=lambda k: abs((dates[k] - target).days))
    return j if abs((dates[j] - target).days) <= 7 else None


def _diff(series, i, j):
    if j is None or j < 0 or series[i] is None or series[j] is None:
        return None
    return series[i] - series[j]


def _gap(data, fuel, area, i):
    a, n = data["v"][fuel][area][i], data["v"][fuel]["national"][i]
    return None if a is None or n is None else a - n


def _ranks(data, fuel, i):
    """i 回目の調査の都道府県の順位(安いほうから。同じ値は同順位)。"""
    vals = {s: data["v"][fuel][s][i] for s, *_ in PREFS if data["v"][fuel][s][i] is not None}
    return {s: 1 + sum(1 for y in vals.values() if y < x - 1e-9) for s, x in vals.items()}


def _yearly(points):
    by = defaultdict(list)
    for d, x in points:
        by[d.year].append((d, x))
    return dict(sorted(by.items()))


# ---------------------------------------------------------------- 予想(減衰トレンド)
PHI = 0.5
MODEL = "damped-trend-0.5"
FC_COLS = ["target_date", "forecast", "made_on", "model", "base_date", "base_value"]
DIRNAME = {1: "上昇", -1: "下落", 0: "横ばい"}


def _r1(x):
    """0.1単位に丸める(0.05は0から遠いほうへ)。"""
    return math.copysign(math.floor(abs(x) * 10 + 0.5 + 1e-9) / 10, x)


def predict(values):
    """次回 = 最新 + 0.5 ×(最新 − 前回)。変化分は0.1円単位に丸める。"""
    last, prev = values[-1], values[-2]
    return round(last + _r1(PHI * (last - prev)), 1)


def _dir(x):
    return 0 if abs(x) < 0.05 else (1 if x > 0 else -1)


def next_target(base: dt.date) -> dt.date:
    """次回調査の予定日(翌週の月曜)。祝日などでずれても『base の次の調査』を実績として採点する。"""
    return _monday(base) + dt.timedelta(days=7)


def read_forecasts(path=None):
    path = pathlib.Path(path or FORECAST)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("target_date")]


def record_forecast(data, today=None, path=None) -> None:
    """次回調査のレギュラー全国平均の予想を data/gas_forecast.csv に追記する。
    対象日ごとに1行だけ(2回目以降は何もしない)。対象の調査日になったら記録しない(事後の予想を作らない)。
    過去の行は書き換えない(追記のみ)。"""
    path = pathlib.Path(path or FORECAST)
    pts = _series(data, "regular", "national")
    if len(pts) < 3:
        return
    base_d, base_v = pts[-1]
    target = next_target(base_d)
    today = today or _now().date()
    if today >= target:
        return
    if any(r["target_date"] == target.isoformat() for r in read_forecasts(path)):
        return
    fc = predict([x for _, x in pts])
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        if not new and not path.read_bytes().endswith(b"\n"):
            fh.write("\n")
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(FC_COLS)
        w.writerow([target.isoformat(), f"{fc:.1f}", today.isoformat(), MODEL, base_d.isoformat(), f"{base_v:.1f}"])


def score_forecasts(data, rows):
    """記録した予想と実績(base_date の次の調査)を突き合わせる。
    記録日が対象の調査日(または実際の調査日)より前でない行は、事前の予想と確かめられないので除く。"""
    pts = _series(data, "regular", "national")
    out = []
    for r in rows:
        try:
            target = dt.date.fromisoformat(r["target_date"])
            fc = float(r["forecast"])
            made = dt.date.fromisoformat(r["made_on"])
            base = dt.date.fromisoformat(r["base_date"]) if r.get("base_date") else None
        except (KeyError, TypeError, ValueError):
            continue
        after = [(d, x) for d, x in pts if (d > base if base else d >= target)]
        if made >= target or (after and made >= after[0][0]):
            continue
        if base and r.get("base_value"):
            base_v = float(r["base_value"])
        else:
            before = [x for d, x in pts if d < (after[0][0] if after else target)]
            base_v = before[-1] if before else None
        item = {"target": target, "forecast": fc, "made_on": r.get("made_on", ""), "base_v": base_v,
                "actual_d": None, "actual": None}
        if after:
            item["actual_d"], item["actual"] = after[0]
            item["err"] = fc - item["actual"]
            if base_v is not None:
                item["hit"] = _dir(fc - base_v) == _dir(item["actual"] - base_v)
        out.append(item)
    return out


def backtest(points, since=None, last_n=None):
    """過去の値に同じ式を当てはめた検証(参考)。(回数, この方法のMAE, 前回と同じ値のMAE, 向きの的中率)"""
    idx = [k for k in range(2, len(points)) if since is None or points[k][0] >= since]
    if last_n:
        idx = idx[-last_n:]
    if not idx:
        return None
    vals = [x for _, x in points]
    e_m = e_n = hits = 0.0
    for k in idx:
        fc, a = predict(vals[:k]), vals[k]
        e_m += abs(fc - a)
        e_n += abs(vals[k - 1] - a)
        hits += _dir(fc - vals[k - 1]) == _dir(a - vals[k - 1])
    n = len(idx)
    return n, e_m / n, e_n / n, hits / n


# ---------------------------------------------------------------- グラフ
# 文字の大きさは viewBox の単位で指定するため、画面が狭いと縮む。画面の幅に合わせて単位を大きくし、
# 幅360pxのスマートフォンでも約11px、パソコン(本文の幅728px)では約13pxで表示されるようにする。
CHART_CSS = ("<style>.gch{font-size:13px}@media (max-width:600px){.gch{font-size:19px}}"
             "@media (max-width:420px){.gch{font-size:24px}}</style>")


def svg_chart(series, names=(), aria="推移", w=720, h=260, label_fmt=str, nlab=5):
    """series: [[(x, 値 or None), ...], ...](どれも同じ x の並び)。1本目を実線、2本目を点線で描く。
    names を渡すと凡例を付ける。色は build.CSS のテーマ変数(--acc, --mut, --line)。"""
    labs = [x for x, _ in series[0]]
    vals = [v for s in series for _, v in s if v is not None]
    if len(labs) < 2 or not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + 0.1
    left, right, top, bottom = 82, 14, (46 if names else 18), 46
    xs = [left + k * (w - left - right) / (len(labs) - 1) for k in range(len(labs))]

    def y(v):
        return top + (hi - v) * (h - top - bottom) / (hi - lo)

    def pts(s):
        return " ".join(f"{xs[k]:.1f},{y(v):.1f}" for k, (_, v) in enumerate(s) if v is not None)
    ticks = "".join(f'<text x="{left - 10}" y="{y(t):.1f}" text-anchor="end" dominant-baseline="middle">{t:.1f}</text>'
                    for t in (hi, (hi + lo) / 2, lo))
    m = min(nlab, len(labs))
    pos = sorted({round(j * (len(labs) - 1) / (m - 1)) for j in range(m)})
    xl = "".join(f'<text x="{xs[k]:.1f}" y="{h - 10}" text-anchor="'
                 + ("start" if k == 0 else "end" if k == len(labs) - 1 else "middle")
                 + f'">{html.escape(label_fmt(labs[k]))}</text>' for k in pos)
    styles = [('stroke="var(--acc)" stroke-width="2"', ""), ('stroke="var(--mut)" stroke-width="1.5"', ' stroke-dasharray="5 4"')]
    lines = "".join(f'<polyline fill="none" {sty}{dash} vector-effect="non-scaling-stroke" points="{pts(s)}"/>'
                    for s, (sty, dash) in reversed(list(zip(series, styles))))
    legend, x0 = "", left
    for name, (sty, dash) in zip(names, styles):
        legend += (f'<line x1="{x0}" y1="18" x2="{x0 + 28}" y2="18" {sty}{dash} vector-effect="non-scaling-stroke"/>'
                   f'<text x="{x0 + 36}" y="18" dominant-baseline="middle">{html.escape(name)}</text>')
        x0 += 36 + 26 * len(name) + 30  # 全角1字 = 1em(最大24単位)として、次の凡例と重ならない位置
    return (f'<svg class="gch" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(aria)}のグラフ" '
            f'style="width:100%;height:auto;fill:var(--mut)">{CHART_CSS}'
            f'<line x1="{left}" y1="{h - bottom}" x2="{w - right}" y2="{h - bottom}" stroke="var(--line)"/>'
            f"{legend}{lines}{ticks}{xl}</svg>")


# ---------------------------------------------------------------- ページ
def _source(today):
    return ('<p class="mut">出典: 「石油製品価格調査」(資源エネルギー庁)'
            f'(<a href="{RESULTS_URL}">資源エネルギー庁ウェブサイトの調査結果のページ</a>)を加工して作成'
            f"({_jd(today, False)}に利用)。資源エネルギー庁ウェブサイトの<a href=\"{TERMS_URL}\">利用規約</a>に従い、"
            f'<a href="{PDL_URL}">公共データ利用規約(第1.0版)</a>のもとで利用しています。'
            "平均・差・順位・予想などは当サイトが計算したもので、資源エネルギー庁が作成したものではありません。</p>")


def _asof(data, today):
    last = data["dates"][-1]
    pub = data["pub"].get(last)
    s = f"調査日 {_jd(last)}" + (f"・資源エネルギー庁の公表 {_jd(pub)}" if pub else "")
    s += "。新しい公表(原則として毎週水曜日14時)は、翌朝以降の自動更新で反映します。"
    check = f'<a href="{RESULTS_URL}">資源エネルギー庁のページ</a>で最新の値を確認してください。'
    if data.get("note"):  # 取得するはずの日に、取得・解析・検証のどれかに失敗した
        s += (f"<br><b>※{_jd(today, False)}の自動更新では、資源エネルギー庁のサイトから最新のファイルを取得できませんでした。</b>"
              f"表示しているのは{_jd(last, False)}の調査までの値です。{check}")
    elif (today - last).days > 18:
        s += f"<br><b>※最新の公表値をまだ取得できていない可能性があります。</b>{check}"
    return f'<p class="mut">{s}</p>'


def _ctx(data, today):
    ds = data["dates"]
    n = len(ds)
    i = n - 1
    reg = data["v"]["regular"]
    cnt = [sum(1 for s, *_ in PREFS if reg[s][k] is not None) for k in range(n)]
    # 都道府県別の調査の始まり(2004年6月14日)。北海道局の列だけは1990年からあるが(2004年3月以前は税抜き)、
    # ほかの都道府県とそろえて、都道府県のページではここから後だけを使う。
    pref_start = next(k for k in range(n) if cnt[k] >= 40)
    # 年平均・年ごとの順位は、47都道府県すべての値がある調査回だけで計算する(どの都道府県も同じ回どうしで比べる)。
    full = [k for k in range(pref_start, n) if cnt[k] == len(PREFS) and reg["national"][k] is not None]
    fs = set(full)
    skipped = [ds[k] for k in range(pref_start, n) if k not in fs]  # 例: 2011年3月14日・22日(震災で値が欠けた回)
    yearly = {s: _yearly([(ds[k], reg[s][k]) for k in full]) for s in AREAS}
    yrank = {}
    for yr in yearly["national"]:
        means = {s: st.mean(x for _, x in yearly[s][yr]) for s, *_ in PREFS}
        yrank[yr] = {s: 1 + sum(1 for v in means.values() if v < m - 1e-9) for s, m in means.items()}
    # 年ごとの全国平均が、トップページ(全調査回の平均)と表示上ちがう年
    nat_all = defaultdict(list)
    for d, x in _series(data, "regular", "national"):
        nat_all[d.year].append(x)
    nat_diff = [yr for yr, p in yearly["national"].items()
                if f"{st.mean(nat_all[yr]):.1f}" != f"{st.mean(x for _, x in p):.1f}"]
    ranks = {k: _ranks(data, "regular", k) for k in range(max(pref_start, n - 60), n)}
    return {"data": data, "today": today, "ds": ds, "i": i, "ago": _ago(ds, i), "ranks": ranks,
            "pref_start": pref_start, "full": full, "skipped": skipped, "nat_diff": nat_diff,
            "yearly": yearly, "yrank": yrank, "fc_rows": read_forecasts()}


def _fuel_card(data, fuel, i, j):
    lab, unit = FUEL[fuel]
    s = data["v"][fuel]["national"]
    return (f'<div class="card"><div class="mut">{lab}({unit})</div><div class="big">{_p(s[i], unit)}</div>'
            f'<div class="mut">{_vs(data["dates"], i)} {_d(_diff(s, i, i - 1), unit)} / 1年前比 {_d(_diff(s, i, j), unit)}</div></div>')


def _tax_note(data, fuel):
    """週次ファイルの『うちガソリン税』『うち軽油引取税』列: (最新値, (変わった調査日, 前の値) or None)。"""
    t = [(d, x) for d, x in zip(data["dates"], data["tax"][fuel]) if x is not None]
    if not t:
        return None
    cur = t[-1][1]
    k = len(t) - 1
    while k > 0 and abs(t[k - 1][1] - cur) < 1e-9:
        k -= 1
    return cur, ((t[k][0], t[k - 1][1]) if k > 0 else None)


def _index_page(c, fc):
    data, today, ds, i, j = c["data"], c["today"], c["ds"], c["i"], c["ago"]
    last = ds[i]
    vs = _vs(ds, i)
    reg = data["v"]["regular"]
    nat = reg["national"]
    rk = c["ranks"][i]
    order = sorted(rk, key=lambda s: (reg[s][i], AREAS.index(s)))
    cheap, dear = order[0], order[-1]
    cards = "".join(_fuel_card(data, k, i, j) for k, *_ in FUELS)
    rows = "".join(
        f'<tr><td>{rk[s]}</td><td><a href="{s}.html">{NAME[s]}</a></td><td>{_p(reg[s][i])}</td>'
        f'<td>{_d(_gap(data, "regular", s, i))}</td><td>{_d(_diff(reg[s], i, i - 1))}</td>'
        f'<td>{_p(data["v"]["premium"][s][i])}</td><td>{_p(data["v"]["diesel"][s][i])}</td>'
        f'<td>{_p(data["v"]["kerosene"][s][i], "円/18L")}</td></tr>' for s in order)
    # 燃料代の計算機(灯油は除く)
    gp = {k: {a: data["v"][k][a][i] for a in AREAS if data["v"][k][a][i] is not None} for k in ("regular", "premium", "diesel")}
    opts = "".join(f'<option value="{a}">{NAME[a]}</option>' for a in AREAS)
    opts_b = opts.replace('<option value="tokyo">', '<option value="tokyo" selected>')
    # 推移
    natp = _series(data, "regular", "national")
    wk = natp[-52:]
    monthly = defaultdict(list)
    for d, x in natp:
        monthly[(d.year, d.month)].append(x)
    mser = [(str(y), st.mean(v)) for (y, _), v in sorted(monthly.items())]
    # 年ごとの全国平均
    ytr = []
    for yr in sorted({d.year for d in ds}, reverse=True):
        cells = []
        for k, *_ in FUELS[:4]:
            v = [x for d, x in zip(ds, data["v"][k]["national"]) if d.year == yr and x is not None]
            cells.append(_p(st.mean(v), FUEL[k][1]) if v else "-")
        note = ("(8月〜・税抜き)" if yr == ds[0].year else "(4月から税込み)" if yr == 2004 else "(税抜き)" if yr < 2004
                else f"({last.month}月まで)" if yr == last.year else "")
        ytr.append(f"<tr><td>{yr}年{note}</td>" + "".join(f"<td>{x}</td>" for x in cells)
                   + f"<td>{sum(1 for d in ds if d.year == yr)}</td></tr>")
    # よくある質問の材料(すべてデータから)
    prem = data["v"]["premium"]["national"]
    gaps = [p - r for p, r in list(zip(prem, nat))[-52:] if p is not None and r is not None]
    tg, td = _tax_note(data, "regular"), _tax_note(data, "diesel")
    tax_txt = ""
    if tg:
        tax_txt += f"レギュラーとハイオクには、1リットルあたりガソリン税 {tg[0]:.1f}円が含まれます"
        if tg[1]:
            tax_txt += f"(調査の表では{_jd(tg[1][0], False)}の調査から{tg[0]:.1f}円、それまでは{tg[1][1]:.1f}円)"
        tax_txt += "。"
    if td:
        tax_txt += f"軽油には、1リットルあたり軽油引取税 {td[0]:.1f}円が含まれます"
        if td[1]:
            tax_txt += f"({_jd(td[1][0], False)}の調査から{td[0]:.1f}円、それまでは{td[1][1]:.1f}円)"
        tax_txt += "。"
    recent = [k for k in range(max(c["pref_start"], i - 51), i + 1)]
    cheap_cnt = sum(1 for k in recent if c["ranks"].get(k, {}).get(cheap) == 1)
    if fc and fc["state"] == "open":
        fc_txt = (f'次回調査({_jd(fc["target"])}の週)のレギュラー全国平均は <b>{fc["value"]:.1f}円</b> と予想しています'
                  f'(最新値から{_d(fc["value"] - nat[i])})。')
    elif fc:
        fc_txt = (f'{_jd(fc["target"])}の週の調査のレギュラー全国平均は <b>{fc["value"]:.1f}円</b> と予想しています'
                  f'({_iso_jd(fc["made_on"])}に記録。調査結果の公表を待って答え合わせをします)。')
    else:
        fc_txt = ""
    prev_txt = f"前回の調査({_jd(ds[i - 1], False)})" if i > 0 else "前回の調査"
    body = (_asof(data, today) +
            f"<p>資源エネルギー庁の「石油製品価格調査」によると、{_jd(last)}調査のレギュラーガソリンの全国平均は1リットルあたり"
            f"<b>{_p(nat[i])}</b>です({vs} {_d(_diff(nat, i, i - 1))}、1年前比 {_d(_diff(nat, i, j))})。"
            f"都道府県別では{NAME[cheap]}の{_p(reg[cheap][i])}が最も安く、{NAME[dear]}の{_p(reg[dear][i])}が最も高く、"
            f"その差は{reg[dear][i] - reg[cheap][i]:.1f}円です。"
            + (f"(この回の調査の表には{len(rk)}都道府県の値しかありません。)" if len(rk) < len(PREFS) else "") + "</p>"
            f'<h2>全国平均({_jd(last, False)}調査)</h2><div class="cards">{cards}</div>'
            f'<p class="mut">{vs}は{prev_txt}との差、1年前比は{_jd(ds[j], False) + "の調査" if j is not None else "1年前の調査"}との差です。'
            "灯油は18リットルあたりの価格で、給油所の店頭で買う場合(店頭)と配達の場合(配達)の2種類です。</p>"
            "<h2>都道府県別のレギュラー価格(安い順)</h2>"
            f'<div class="wrap"><table><thead><tr><th>順位</th><th>都道府県</th><th>レギュラー</th><th>全国との差</th><th>{vs}</th>'
            f"<th>ハイオク</th><th>軽油</th><th>灯油店頭(18L)</th></tr></thead><tbody>{rows}</tbody></table></div>"
            '<p class="mut">都道府県名を選ぶと、2004年からの推移・全国順位の変化・近隣の県との比較を表示します。'
            "北海道と沖縄は、調査の地域区分(北海道局・沖縄局)の値です。</p>"
            "<h2>燃料代の計算(2つの都道府県を比べる)</h2>"
            '<label for="gf">燃料</label><select id="gf"><option value="regular">レギュラー</option>'
            '<option value="premium">ハイオク</option><option value="diesel">軽油</option></select>'
            f'<label for="ga">都道府県A</label><select id="ga">{opts}</select>'
            '<label for="pa">Aの価格(円/L、書きかえられます)</label><input id="pa" type="number" step="0.1">'
            f'<label for="gb">都道府県B(比べる相手)</label><select id="gb">{opts_b}</select>'
            '<label for="pb">Bの価格(円/L)</label><input id="pb" type="number" step="0.1">'
            '<label for="km1">1回の走行距離(km)</label><input id="km1" type="number" min="0" value="30">'
            '<label for="kmm">1か月の走行距離(km)</label><input id="kmm" type="number" min="0" value="500">'
            '<label for="eco">燃費(km/L)</label><input id="eco" type="number" min="1" step="0.1" value="15">'
            '<div class="out" id="gr"></div>'
            f'<p class="mut">価格は{_jd(last, False)}の調査の平均です(都道府県や燃料を選び直すと入れ直します)。'
            "実際の燃費は運転のしかたや季節で変わります。</p>"
            f"<h2>レギュラー全国平均の推移(直近{len(wk)}回の調査)</h2>"
            + svg_chart([wk], aria=f"レギュラー全国平均(直近{len(wk)}回の調査)の推移", label_fmt=lambda d: f"{d.month}/{d.day}") +
            f"<h2>{ds[0].year}年からの推移(レギュラー全国平均の月平均)</h2>"
            + svg_chart([mser], aria=f"{ds[0].year}年からのレギュラー全国平均(月平均)の推移", label_fmt=lambda s: s, nlab=6) +
            '<p class="mut">2004年3月以前の価格は消費税抜きです(資源エネルギー庁の注記)。2004年4月の調査から消費税込みのため、'
            "その前後の差には、税の表示方法の違いも含まれます。</p>"
            '<h2 id="yearly">年ごとの全国平均</h2>'
            '<div class="wrap"><table><thead><tr><th>年</th><th>レギュラー</th><th>ハイオク</th><th>軽油</th><th>灯油店頭(18L)</th>'
            f'<th>調査回数</th></tr></thead><tbody>{"".join(ytr)}</tbody></table></div>'
            f'<h2>来週の予想と更新のお知らせ</h2><p>{fc_txt}<a href="forecast.html">予想の方法と的中実績</a>を公開しています。'
            '毎週の全国平均の更新は、<a href="feed.xml">ガソリン価格の更新フィード(Atom)</a>をフィードリーダーに登録すると届きます。</p>'
            "<h2>よくある質問</h2>"
            "<p><b>価格はいつ更新されますか?</b> 資源エネルギー庁は原則として毎週月曜日に調査し、水曜日14時に公表しています。"
            "祝日のある週は、調査日や公表日がずれたり、調査が休みになったりします。"
            "このサイトは毎日自動で更新しており、新しい公表は翌朝以降に反映します。</p>"
            f"<p><b>いちばん安い都道府県はどこですか?</b> {_jd(last, False)}の調査では{NAME[cheap]}({_p(reg[cheap][i])})です。"
            f"{NAME[cheap]}は直近{len(recent)}回の調査のうち{cheap_cnt}回で最も安くなっています。"
            f"最も高いのは{NAME[dear]}({_p(reg[dear][i])})です。</p>"
            f"<p><b>ハイオクとレギュラーの差はどのくらいですか?</b> {_jd(last, False)}の調査の全国平均で{prem[i] - nat[i]:.1f}円です。"
            f"直近{len(gaps)}回の調査の平均は{st.mean(gaps):.1f}円でした。</p>"
            + (f"<p><b>価格に税金はいくら含まれていますか?</b> 価格は消費税込みです。{tax_txt}</p>" if tax_txt else "") +
            "<p><b>近くのガソリンスタンドの価格と違うのはなぜですか?</b> この調査は、対象となった給油所の現金価格(消費税込み)の平均です。"
            "同じ都道府県でも店によって価格は違い、会員価格やカード払いの価格とも異なることがあります。</p>"
            + _source(today))
    js = ("const GP=" + json.dumps(gp, separators=(",", ":")) + ";"
          "function setp(){const u=$('gf').value;$('pa').value=GP[u][$('ga').value]??'';$('pb').value=GP[u][$('gb').value]??'';calc();}"
          "function calc(){const k1=+$('km1').value||0,km=+$('kmm').value||0,e=+$('eco').value||0,pa=+$('pa').value||0,pb=+$('pb').value||0;"
          "if(e<=0){$('gr').textContent='燃費を入力してください';return;}"
          "if(pa<=0&&pb<=0){$('gr').textContent='価格を入力してください';return;}"
          # 価格が空欄(またはその週の値がない)の側は 0円 と出さずに『価格が未入力』とし、差は両方あるときだけ出す
          "const A=$('ga').selectedOptions[0].text,B=$('gb').selectedOptions[0].text,l1=k1/e,lm=km/e,d=lm*(pa-pb),"
          "c=(l,p)=>p>0?f(l*p):'(価格が未入力)',nA=A===B?'A':A,nB=A===B?'B':B;"
          "$('gr').innerHTML=`1回(${k1}km・約${l1.toFixed(1)}L): ${A} <b>${c(l1,pa)}</b> / ${B} ${c(l1,pb)}<br>"
          "1か月(${km}km・約${lm.toFixed(1)}L): ${A} <b>${c(lm,pa)}</b> / ${B} ${c(lm,pb)}<br>"
          "1年: ${A} <b>${c(lm*12,pa)}</b> / ${B} ${c(lm*12,pb)}`"
          "+(pa>0&&pb>0?'<br>'+(Math.abs(d*12)<0.5?'AとBの差: ありません'"
          ":`${d<0?nA:nB}のほうが、1か月 ${f(Math.abs(d))}、1年 ${f(Math.abs(d*12))} 安くなります`):'');}"
          "['gf','ga','gb'].forEach(i=>$(i).addEventListener('change',setp));"
          "['km1','kmm','eco','pa','pb'].forEach(i=>$(i).addEventListener('input',calc));setp();")
    title = "ガソリン価格の全国平均と都道府県ランキング(毎週更新)"
    desc = (f"{_jd(last, False)}調査のレギュラーガソリン全国平均は{_p(nat[i])}/L({vs}{_d(_diff(nat, i, i - 1))})。"
            f"最安は{NAME[cheap]}{_p(reg[cheap][i])}、最高は{NAME[dear]}{_p(reg[dear][i])}。"
            "47都道府県ランキング、ハイオク・軽油・灯油、1990年からの推移、燃料代の計算機。")
    return title, desc, body, js


def _pref_page(c, s, pos):
    data, today, ds, i, j = c["data"], c["today"], c["ds"], c["i"], c["ago"]
    name, nb = PREFS[pos][1], PREFS[pos][3]
    reg = data["v"]["regular"]
    nat = reg["national"]
    last = ds[i]
    v = reg[s][i]
    rk = c["ranks"][i]
    gap = _gap(data, "regular", s, i)
    cards = []
    for k, *_ in FUELS[:4]:
        lab, unit = FUEL[k]
        r = _ranks(data, k, i).get(s)
        cards.append(f'<div class="card"><div class="mut">{lab}({unit})</div><div class="big">{_p(data["v"][k][s][i], unit)}</div>'
                     f'<div class="mut">全国との差 {_d(_gap(data, k, s, i), unit)}' + (f" / 安い順 {r}位" if r else "") + "</div></div>")
    # 直近2年のグラフ(点線は全国平均)
    k0 = max(c["pref_start"], i - 103)
    chart = svg_chart([[(ds[k], reg[s][k]) for k in range(k0, i + 1)], [(ds[k], nat[k]) for k in range(k0, i + 1)]],
                      names=(name, "全国平均"), aria=f"{name}と全国平均のレギュラー価格の推移",
                      label_fmt=lambda d: f"{d.year}/{d.month}")
    # 直近26回
    trs = "".join(
        f"<tr><td>{_jd(ds[k], False)}</td><td>{_p(reg[s][k])}</td><td>{_d(_diff(reg[s], k, k - 1))}</td>"
        f"<td>{_p(nat[k])}</td><td>{_d(_gap(data, 'regular', s, k))}</td><td>{c['ranks'].get(k, {}).get(s, '-')}</td></tr>"
        for k in range(i, max(c["pref_start"], i - 26), -1))
    r52 = [c["ranks"][k][s] for k in range(max(c["pref_start"], i - 51), i + 1) if s in c["ranks"].get(k, {})]
    p52 = [(ds[k], reg[s][k]) for k in range(max(0, i - 51), i + 1) if reg[s][k] is not None]
    # 近隣
    nbrows = []
    for t in [s] + nb:
        x = reg[t][i]
        label = f"<b>{NAME[t]}</b>" if t == s else f'<a href="{t}.html">{NAME[t]}</a>'
        diff = "-" if t == s or x is None or v is None else _d(x - v)
        nbrows.append(f"<tr><td>{label}</td><td>{_p(x)}</td><td>{diff}</td><td>{_p(data['v']['diesel'][t][i])}</td>"
                      f"<td>{_p(data['v']['kerosene'][t][i], '円/18L')}</td></tr>")
    nbv = sorted((reg[t][i], AREAS.index(t), t) for t in nb if reg[t][i] is not None)
    nb_txt = ""
    if nbv and v is not None:
        if len(nbv) == 1:
            x, _, t = nbv[0]
            nb_txt = f"{NAME[t]}は{_p(x)}で、{name}" + (f"より{abs(x - v):.1f}円{'高く' if x > v else '安く'}なっています。"
                                                       if abs(x - v) >= 0.05 else "と同じです。")
        else:
            cheaper = sum(1 for x, _, _ in nbv if x < v - 1e-9)
            if cheaper == 0:
                head = f"比べた近隣の{len(nbv)}都道府県のうち、{name}より安いところはありません。"
            elif cheaper == len(nbv):
                head = f"比べた近隣の{len(nbv)}都道府県は、どこも{name}より安くなっています。"
            else:
                head = f"比べた近隣の{len(nbv)}都道府県のうち、{name}より安いのは{cheaper}か所です。"
            nb_txt = (head + f"近隣で最も安いのは{NAME[nbv[0][2]]}の{_p(nbv[0][0])}、"
                      f"最も高いのは{NAME[nbv[-1][2]]}の{_p(nbv[-1][0])}です。")
    sea = any(frozenset((s, t)) in SEA for t in nb)
    prem_gap = None if data["v"]["premium"][s][i] is None or v is None else data["v"]["premium"][s][i] - v
    # 年平均と全国順位: 47都道府県すべての値がある調査回だけで計算する(全国平均・最安値・最高値も同じ回で)
    ys = c["yearly"][s]
    natd = c["yearly"]["national"]
    p0 = ds[c["pref_start"]]  # 都道府県別の調査の始まり(2004年6月14日)
    first_year = p0.year
    ytr, yr_rank = [], {}
    for yr in sorted(ys, reverse=True):
        pts = ys[yr]
        m = st.mean(x for _, x in pts)
        nm = st.mean(x for _, x in natd[yr])
        rr = c["yrank"].get(yr, {}).get(s)
        if rr:
            yr_rank[yr] = rr
        part = (f"({pts[0][0].month}月〜)" if yr == min(ys) and pts[0][0].month > 1
                else f"({pts[-1][0].month}月まで)" if yr == last.year else "")
        ytr.append(f"<tr><td>{yr}年{part}</td><td>{m:.1f}円</td><td>{_p(nm)}</td><td>{_d(m - nm)}</td>"
                   f"<td>{str(rr) + '位' if rr else '-'}</td><td>{min(x for _, x in pts):.1f}円</td>"
                   f"<td>{max(x for _, x in pts):.1f}円</td></tr>")
    own = _series(data, "regular", s)
    allp = [(d, x) for d, x in own if d >= p0]  # 北海道局の2004年5月以前(税抜きを含む)は使わない
    hi_all, lo_all = max(allp, key=lambda t: t[1]), min(allp, key=lambda t: t[1])
    sk = c["skipped"]
    ynote = ("年平均・全国平均・順位・最安値・最高値は、47都道府県すべての値がある調査回だけで計算しています"
             "(どの都道府県も同じ回どうしで比べるため)。"
             + (f"値が欠けているため除いた調査回: {'、'.join(_jd(d, False) for d in sk[:6])}"
                + (f"など{len(sk)}回" if len(sk) > 6 else "") + "。" if sk else "")
             + (f"全国平均の列は表と同じ調査回の平均のため、{'・'.join(f'{y}年' for y in c['nat_diff'])}は"
                '<a href="index.html#yearly">年ごとの全国平均</a>(その年のすべての調査回の平均)と異なります。'
                if c["nat_diff"] else ""))
    if own and own[0][0] < p0:
        ynote += (f"{name}(調査の地域区分「{PREFS[pos][2]}」)の値は{_jd(own[0][0], False)}の調査からありますが、"
                  f"2004年3月以前は消費税抜きの価格のため、このページではほかの都道府県とそろえて{_jd(p0, False)}以降の値を使っています。")
    if gap is None:
        gap_txt = ""
    elif abs(gap) < 0.05:
        gap_txt = f"全国平均({_p(nat[i])})と同じで、"
    else:
        gap_txt = f"全国平均({_p(nat[i])})より{abs(gap):.1f}円{'高く' if gap > 0 else '安く'}、"
    r_now = rk.get(s)
    r_note = "(最も安い)" if r_now == 1 else "(最も高い)" if r_now == len(rk) else ""
    if v is None:  # 2011年3月のように、その回の表に値がない場合
        lead = (f"<p>{_jd(last)}の調査の表には、{name}の値がありません。"
                f"直近の値は{_jd(allp[-1][0], False)}の調査の1リットルあたり<b>{_p(allp[-1][1])}</b>です。</p>")
    else:
        lead = (f"<p>{name}のレギュラーガソリンの平均価格は、{_jd(last)}の調査で1リットルあたり<b>{_p(v)}</b>です。"
                f"{gap_txt}47都道府県のうち安いほうから{r_now or '-'}番目{r_note}です"
                f"({_vs(ds, i)} {_d(_diff(reg[s], i, i - 1))}、1年前比 {_d(_diff(reg[s], i, j))})。</p>")
    s52 = ""
    if p52 and r52:
        hi52, lo52 = max(p52, key=lambda t: t[1]), min(p52, key=lambda t: t[1])
        s52 = (f"<p>直近{len(p52)}回の調査で最も高かったのは{_jd(hi52[0], False)}の{_p(hi52[1])}、"
               f"最も安かったのは{_jd(lo52[0], False)}の{_p(lo52[1])}です。この間の全国順位は、安いほうから{min(r52)}位〜{max(r52)}位でした。</p>")
    srank = ""
    if yr_rank:
        lo_r, hi_r = min(yr_rank.values()), max(yr_rank.values())

        def years(r):
            ys_ = sorted((y for y, x in yr_rank.items() if x == r), reverse=True)
            return "・".join(f"{y}年" for y in ys_[:3]) + (f"など{len(ys_)}回" if len(ys_) > 3 else "")
        if lo_r == hi_r:
            srank = f"{first_year}年以降、年平均の全国順位(安い順)は毎年{lo_r}位です。"
        else:
            srank = (f"{first_year}年以降の年平均の全国順位(安い順)は{lo_r}位〜{hi_r}位で、"
                     f"{lo_r}位だったのは{years(lo_r)}、{hi_r}位だったのは{years(hi_r)}です。")
    prev_s, next_s = PREFS[pos - 1][0], PREFS[(pos + 1) % len(PREFS)][0]
    bureau = PREFS[pos][2]
    body = (_asof(data, today) + lead +
            f'<div class="cards">{"".join(cards)}</div>'
            '<p class="mut">順位は47都道府県の中で安いほうから数えたものです(同じ価格は同じ順位)。灯油は店頭価格で、18リットルあたりです。'
            + (f"この地域の値は、調査の地域区分「{bureau}」の値です。" if bureau.endswith("局") else "") + "</p>"
            + (f"<p>{name}のハイオクとレギュラーの差は{prem_gap:.1f}円です(全国平均では"
               f"{data['v']['premium']['national'][i] - nat[i]:.1f}円)。</p>" if prem_gap is not None else "") +
            f"<h2>レギュラー価格の推移(直近{i - k0 + 1}回の調査)</h2>" + chart + s52 +
            "<h2>直近26回の調査</h2>"
            f'<div class="wrap"><table><thead><tr><th>調査日</th><th>{name}</th><th>前週比</th><th>全国平均</th><th>全国との差</th>'
            f'<th>安い順</th></tr></thead><tbody>{trs}</tbody></table></div>'
            '<p class="mut">前週比は前回の調査との差です(祝日などで調査が休みの週があります)。</p>'
            f"<h2>近隣の都道府県との比較({_jd(last, False)}の調査)</h2>"
            f'<div class="wrap"><table><thead><tr><th>都道府県</th><th>レギュラー</th><th>{name}との差</th><th>軽油</th><th>灯油店頭(18L)</th>'
            f"</tr></thead><tbody>{''.join(nbrows)}</tbody></table></div>"
            + (f"<p>{nb_txt}</p>" if nb_txt else "")
            + ('<p class="mut">陸続きの県のほか、北海道と青森県、山口県と福岡県、鹿児島県と沖縄県は、海をはさんだ近隣として比べています。</p>'
               if sea else "") +
            f"<h2>年平均と全国順位({first_year}年〜)</h2>"
            '<div class="wrap"><table><thead><tr><th>年</th><th>年平均</th><th>全国平均</th><th>全国との差</th><th>安い順</th>'
            f'<th>最安値</th><th>最高値</th></tr></thead><tbody>{"".join(ytr)}</tbody></table></div>'
            f'<p class="mut">{ynote}</p>'
            f"<p>{srank}{_jd(allp[0][0], False)}以降の最高値は{_jd(hi_all[0], False)}の{_p(hi_all[1])}、"
            f"最安値は{_jd(lo_all[0], False)}の{_p(lo_all[1])}です。</p>"
            f'<p class="mut">前後の都道府県: <a href="{prev_s}.html">{NAME[prev_s]}</a> / <a href="{next_s}.html">{NAME[next_s]}</a> / '
            '<a href="index.html">全国平均と都道府県ランキング</a> / <a href="forecast.html">来週の全国平均の予想</a> / '
            '<a href="feed.xml">更新フィード</a></p>'
            + _source(today))
    title = f"{name}のガソリン価格の推移と全国順位(レギュラー・軽油・灯油)"
    desc = (f"{name}のレギュラーガソリンは{_jd(allp[-1][0], False)}調査で{_p(allp[-1][1])}/L"
            + (f"(全国平均との差{_d(gap)}、安い順で{rk.get(s, '-')}位)" if gap is not None else "") +
            f"。{first_year}年からの週次推移、年平均と全国順位、近隣の県との比較。")
    return title, desc, body, ""


def _forecast_page(c, fc):
    data, today = c["data"], c["today"]
    pts = _series(data, "regular", "national")
    last_d, last_v = pts[-1]
    scored = score_forecasts(data, c["fc_rows"])
    done = [x for x in scored if x["actual"] is not None]
    when_pub = "原則として水曜日14時。祝日のある週は木曜日など"
    if fc:
        pending = fc["state"] == "pending"
        head = (f"{_jd(fc['target'])}の週の調査の予想(答え合わせ待ち)" if pending
                else f"次回の調査({_jd(fc['target'])}の週)の予想")
        nxt = (f'<div class="cards"><div class="card"><div class="mut">{head}</div>'
               f'<div class="big">{fc["value"]:.1f}円</div><div class="mut">最新({_jd(last_d, False)}の調査)の{last_v:.1f}円から'
               f'{_d(fc["value"] - last_v)}({DIRNAME[_dir(fc["value"] - last_v)]})</div></div></div>')
        rec = (f"この予想は{_iso_jd(fc['made_on'])}に記録しました" if fc["made_on"]
               else "この予想はまだ記録していません(次の自動更新で記録します)")
        if pending:
            nxt += (f"<p>{rec}。{_jd(fc['target'], False)}の週の調査結果の公表({when_pub})を待っています。"
                    "調査が休みになった週は、その次の調査と比べます。公表後の自動更新で、答え合わせをこのページに載せます。</p>")
        else:
            nxt += f"<p>{rec}。答え合わせは、次回の調査結果が公表されたあと({when_pub})の自動更新で、このページに載せます。</p>"
    else:  # 対象の調査日を過ぎたが、その回の予想を記録していない(記録は調査日より前にしか作らない)
        nxt = (f"<p>{_jd(next_target(last_d), False)}の週の調査の予想は記録していません。"
               "次の予想は、次回の調査結果の公表後、その値を取り込んだときに記録します。</p>")
    if done:
        mae = st.mean(abs(x["err"]) for x in done)
        hits = [x["hit"] for x in done if "hit" in x]
        summary = (f"これまでの答え合わせ{len(done)}件で、予想と実績の差(絶対値)の平均は{mae:.2f}円、最大は"
                   f"{max(abs(x['err']) for x in done):.1f}円です。"
                   + (f"上昇・下落・横ばいの向きは{len(hits)}件中{sum(hits)}件({sum(hits) / len(hits):.0%})で当たりました。" if hits else ""))
    else:
        summary = "実績はまだありません。最初の答え合わせは、次回の調査結果の公表後に載せます。"

    def dname(x):
        return DIRNAME[_dir(x)]
    trs = []
    for x in sorted(scored, key=lambda t: t["target"], reverse=True):
        bv = x["base_v"]
        if x["actual"] is None:
            trs.append(f"<tr><td>{_jd(x['target'], False)}の週</td><td>{x['forecast']:.1f}円</td><td>答え合わせ待ち</td><td>-</td>"
                       f"<td>{dname(x['forecast'] - bv) if bv is not None else '-'}</td><td>-</td><td>{_iso_jd(x['made_on'])}</td></tr>")
        else:
            ad = x["actual_d"]
            when = _jd(ad, False) + ("" if ad == x["target"] else "(予定から調査日がずれた回)")
            trs.append(f"<tr><td>{when}</td><td>{x['forecast']:.1f}円</td><td>{x['actual']:.1f}円</td><td>{x['err']:+.1f}円</td>"
                       f"<td>{dname(x['forecast'] - bv) if bv is not None else '-'}</td>"
                       f"<td>{dname(x['actual'] - bv) if bv is not None else '-'}</td><td>{_iso_jd(x['made_on'])}</td></tr>")
    table = ('<div class="wrap"><table><thead><tr><th>対象の調査</th><th>予想</th><th>実績</th><th>差</th><th>予想の向き</th>'
             f'<th>実際の向き</th><th>記録日</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>' if trs else "")
    bt = []
    for lab, kw in ((f"2016年1月〜{_jd(last_d, False)}", {"since": dt.date(2016, 1, 1)}), ("直近52回の調査", {"last_n": 52})):
        r = backtest(pts, **kw)
        if r:
            bt.append(f"<tr><td>{lab}</td><td>{r[0]}回</td><td>{r[1]:.2f}円</td><td>{r[2]:.2f}円</td><td>{r[3]:.0%}</td></tr>")
    wk = pts[-26:]
    body = (_asof(data, today) +
            "<p>資源エネルギー庁の「石油製品価格調査」のレギュラーガソリン全国平均について、次回の調査の値を毎週予想して記録し、"
            "公表されたら答え合わせをします。外れた結果もそのまま載せます。</p>"
            "<h2>次回の予想</h2>" + nxt +
            "<h2>予想の方法</h2>"
            "<p>予想 = 最新の全国平均 + 0.5 ×(最新の全国平均 − 前回の全国平均)。変化分は0.1円単位に丸めます(0.05円は0から遠いほうへ)。"
            "直近1回の値動きが、次の1週間にも半分だけ続くと考える単純な方法(減衰トレンド)で、過去の全国平均の数字だけを使います。</p>"
            "<p><b>限界:</b> 原油価格・為替・補助金・税制の変更などは考えていません。補助金や税率が変わる週は大きく外れます。"
            "あくまで目安で、給油の時期を決める根拠になるものではありません。</p>"
            "<h2>的中実績(記録した予想の答え合わせ)</h2>"
            f"<p><b>{summary}</b></p>{table}"
            f'<p class="mut">予想は、対象の調査日より前に記録したものだけを載せています。記録は全件を <a href="{RECORD_URL}">GitHub</a> '
            "で公開しています(変更履歴つき)。祝日などで調査が休みになった週は、その次の調査と比べます。"
            "向きは前回の調査からの変化で、0.1円未満は横ばいとしています。</p>"
            "<h2>過去のデータでの検証(参考)</h2>"
            '<div class="wrap"><table><thead><tr><th>期間</th><th>回数</th><th>この方法の平均誤差</th><th>前回と同じ値とした場合</th>'
            f'<th>向きの的中率</th></tr></thead><tbody>{"".join(bt)}</tbody></table></div>'
            '<p class="mut">過去の全国平均に同じ式を当てはめた計算で、事前に記録した予想ではありません。'
            "「前回と同じ値とした場合」は、何も予想しないときの比べる基準です。</p>"
            f"<h2>全国平均の最近の推移(直近{len(wk)}回の調査)</h2>"
            + svg_chart([wk], aria=f"レギュラー全国平均(直近{len(wk)}回の調査)の推移", label_fmt=lambda d: f"{d.month}/{d.day}") +
            '<p><a href="index.html">全国平均と都道府県ランキング</a> / <a href="feed.xml">更新フィード(Atom)</a></p>'
            + _source(today))
    title = "来週のレギュラーガソリン全国平均の予想と的中実績"
    desc = ((f"次回調査({_jd(fc['target'], False)}の週)のレギュラー全国平均の予想は{fc['value']:.1f}円/L"
             + ("(答え合わせ待ち)" if fc["state"] == "pending" else "") + "。" if fc else "")
            + "毎週の予想を記録し、公表値との答え合わせをすべて公開。予想の方法と限界も説明します。")
    return title, desc, body, ""


def _next_forecast(c):
    """次回調査の予想 {'target', 'value', 'made_on', 'state'}、なければ None。
    state='open'   : 対象の調査日の前。記録済みならその値、未記録なら計算値(made_on='')。
    state='pending': 対象の調査日を過ぎ、公表と答え合わせを待っている(記録した予想があるときだけ)。"""
    pts = _series(c["data"], "regular", "national")
    target = next_target(pts[-1][0])
    rec = None
    for r in c["fc_rows"]:
        if r.get("target_date") == target.isoformat():
            try:
                rec = {"target": target, "value": float(r["forecast"]), "made_on": r.get("made_on") or ""}
            except (KeyError, TypeError, ValueError):
                rec = None
            break
    if c["today"] >= target:
        return dict(rec, state="pending") if rec else None
    if rec:
        return dict(rec, state="open")
    return {"target": target, "value": predict([x for _, x in pts]), "made_on": "", "state": "open"}


def pages(data, today=None):
    """{slug: (title, desc, body, js)}: gas/index.html、gas/<県>.html(47)、gas/forecast.html。"""
    today = today or _now().date()
    c = _ctx(data, today)
    fc = _next_forecast(c)
    out = {"gas/index.html": _index_page(c, fc)}
    for pos, (s, *_) in enumerate(PREFS):
        out[f"gas/{s}.html"] = _pref_page(c, s, pos)
    out["gas/forecast.html"] = _forecast_page(c, fc)
    return out


def feed(data, site_url: str, n=20) -> str:
    """全国平均の週次更新(直近 n 回の調査)の Atom フィード。gas/feed.xml として保存する。
    updated は公表日の14時。公表日が分からない古い回は、調査日の2日後の14時(月曜の調査なら水曜日、
    祝日で火曜にずれた調査なら木曜日。資源エネルギー庁の公表予定と同じ並び)。"""
    site_url = site_url.rstrip("/")
    ds = data["dates"]
    nat = {k: data["v"][k]["national"] for k, *_ in FUELS}
    idx = [k for k in range(len(ds)) if nat["regular"][k] is not None][-n:]
    items, stamps = [], []
    for k in reversed(idx):
        d = ds[k]
        pub = data["pub"].get(d) or (d + dt.timedelta(days=2))
        stamp = f"{pub.isoformat()}T14:00:00+09:00"
        stamps.append(stamp)
        vs = _vs(ds, k)
        parts = [f"{FUEL[f][0]}{'(18L)' if FUEL[f][1] == '円/18L' else ''} {_p(nat[f][k], FUEL[f][1])}"
                 f"({vs} {_d(_diff(nat[f], k, k - 1), FUEL[f][1])})" for f in ("premium", "diesel", "kerosene")]
        rk = _ranks(data, "regular", k)
        extra = ""
        if rk:
            order = sorted(rk, key=lambda s: (data["v"]["regular"][s][k], AREAS.index(s)))
            extra = (f"。最も安いのは{NAME[order[0]]} {_p(data['v']['regular'][order[0]][k])}、"
                     f"最も高いのは{NAME[order[-1]]} {_p(data['v']['regular'][order[-1]][k])}")
        title = f"{_jd(d, False)}調査 レギュラー全国平均 {_p(nat['regular'][k])}({vs} {_d(_diff(nat['regular'], k, k - 1))})"
        summary = (title + "。" + "、".join(parts) + extra
                   + (f"。前回の調査は{_jd(ds[k - 1], False)}です" if vs == "前回比" and k > 0 else "")
                   + "。出典: 資源エネルギー庁「石油製品価格調査」を加工して作成")
        items.append(f"<entry><title>{html.escape(title)}</title><id>tag:kinri-tools,{d.isoformat()}:gas</id>"
                     f"<updated>{stamp}</updated><link href=\"{site_url}/gas/index.html\"/>"
                     f"<summary>{html.escape(summary)}</summary></entry>")
    updated = max(stamps) if stamps else f"{_now().date().isoformat()}T09:00:00+09:00"
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f"<title>ガソリン価格(全国平均)の週次更新</title><id>{site_url}/gas/feed.xml</id>"
            f"<link href=\"{site_url}/gas/index.html\"/><link rel=\"self\" href=\"{site_url}/gas/feed.xml\"/>"
            f"<updated>{updated}</updated><author><name>kinri-tools</name></author>"
            + "".join(items) + "</feed>")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = load(force=True if "--force" in sys.argv else None)
    print(d["source"], d["dates"][-1], "公表", d["pub"].get(d["dates"][-1]), d.get("url") or "-",
          {k: d["v"][k]["national"][-1] for k, *_ in FUELS}, d.get("note", ""))
    sys.exit(2 if d.get("note") else 0)  # 取得に失敗してキャッシュを使ったとき
