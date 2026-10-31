"""国民の祝日(内閣府 CSV, キー不要)から、祝日一覧・連休・営業日計算のページを作る。

holiday/index.html : 今年と来年の祝日一覧(振替休日・国民の休日を含む)、3連休以上の連休と年末年始の休み、
                     次の祝日まであと何日(閲覧者の日付でJS計算)、営業日の計算機(◯営業日後/前・期間の営業日数)
holiday/<年>.html  : 2026年〜来年のうち公表済みの年の、祝日入りカレンダーと月別の営業日数(土日祝/官公庁/銀行)。
                     一度公開した年のページは翌年以降も残す(リンク切れにしない)。それより前の年のページは作らない。
出典: 内閣府「国民の祝日について」 https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html
      内閣府ホームページ利用規約により公共データ利用規約(第1.0版)が適用される。加工して利用している旨をページに書く。
取得に失敗したときは data/holidays.csv(前回取得分, UTF-8)を使い、取得できたらキャッシュを更新する。
キャッシュの先頭行(# ... modified=CSVの更新日 fetched=取得日)に、そのデータの日付を残す(内容が変わったときだけ書き換える)。
GitHub Actions では update.yml で data/holidays.csv もコミットすること(しないと、取得に失敗した日に古いキャッシュへ戻り、
公表済みの年のページが消える)。

  data = load()                               # 取得(失敗時はキャッシュ)
  pages(data) -> {slug: (title, desc, body, js)}
  pages(data, inline_css=False)               # CSS を build.CSS に移したとき(CSS 定数を build.CSS に足す)
"""
from __future__ import annotations

import bisect
import calendar
import csv
import datetime as dt
import email.utils
import html
import io
import json
import pathlib
import re
import urllib.request

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "data" / "holidays.csv"
CSV_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
PAGE_URL = "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html"
RULE_URL = "https://www.cao.go.jp/notice/rule.html"
PDL_URL = "https://www.digital.go.jp/resources/open_data/public_data_license_v1.0"
LAW = {"shukujitsu": "https://laws.e-gov.go.jp/law/323AC1000000178",   # 国民の祝日に関する法律
       "gyosei": "https://laws.e-gov.go.jp/law/363AC0000000091",       # 行政機関の休日に関する法律
       "ginko": "https://laws.e-gov.go.jp/law/357CO0000000040",        # 銀行法施行令
       "chiho": "https://laws.e-gov.go.jp/law/322AC0000000067"}        # 地方自治法(第4条の2: 自治体の休日は条例で定める)
JST = dt.timezone(dt.timedelta(hours=9))
WD = "月火水木金土日"  # date.weekday(): 0=月
ONE = dt.timedelta(days=1)
FIRST_YEAR_PAGE = 2026
YEAREND = {"gov": ("官公庁", 29), "bank": ("銀行", 31)}  # 12月◯日〜1月3日を休みにする
_DATE = re.compile(r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*$")
_META = re.compile(r"\b(modified|fetched)=(\d{4}-\d{2}-\d{2})\b")


# ---------------------------------------------------------------- データ取得
def parse(text):
    """内閣府CSV(日付,名称)/キャッシュ(date,name)を [(date, 名称)] にする。日付以外の行(見出し)は無視。"""
    out = {}
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 2:
            continue
        m = _DATE.match(r[0])
        name = r[1].strip()
        if m and name:
            out[dt.date(int(m[1]), int(m[2]), int(m[3]))] = name
    return sorted(out.items())


def _valid(rows):
    if len(rows) < 500:
        return False
    years = {d.year for d, _ in rows}
    gan = sum(1 for _, n in rows if n == "元日")  # 文字化けしていれば一致しない
    return gan >= 0.9 * len(years) and max(years) - min(years) + 1 == len(years)


def _decode(raw):
    for enc in ("utf-8-sig", "cp932"):  # 現在はShift_JIS。将来UTF-8に変わっても読めるように
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("cp932", errors="replace")


def _fetch(timeout):
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0 (kinri-tools)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw, lm = r.read(), r.headers.get("Last-Modified")
    mod = None
    if lm:
        try:
            mod = email.utils.parsedate_to_datetime(lm).astimezone(JST).date()
        except (TypeError, ValueError):
            pass
    return _decode(raw), mod


def _read_cache():
    """data/holidays.csv -> ([(date, 名称)], {"modified": date, "fetched": date})。
    先頭のコメント行 '# <URL> modified=YYYY-MM-DD fetched=YYYY-MM-DD' から、そのデータのCSV更新日と取得日を読む。"""
    if not CACHE.exists():
        return [], {}
    text = CACHE.read_text(encoding="utf-8-sig")
    meta = {}
    for line in text.splitlines()[:3]:
        if line.startswith("#"):
            for k, v in _META.findall(line):
                try:
                    meta[k] = dt.date.fromisoformat(v)
                except ValueError:  # 日付が壊れていても、行データは使う
                    pass
    return parse(text), meta


def _write_cache(rows, modified, fetched):
    CACHE.parent.mkdir(exist_ok=True)
    buf = io.StringIO()
    buf.write(f"# {CSV_URL} modified={modified.isoformat() if modified else '-'} fetched={fetched.isoformat()}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "name"])
    w.writerows((d.isoformat(), n) for d, n in rows)
    CACHE.write_text(buf.getvalue(), encoding="utf-8", newline="")


def today_jst():
    return dt.datetime.now(JST).date()


def load(offline=False, timeout=30):
    """{"rows": [(date, 名称)], "source": "live"|"cache", "modified": CSVの更新日|None,
        "checked": 今回確認した日(live のみ)|None, "fetched": そのデータを取得した日|None}"""
    try:
        cached, meta = _read_cache()
    except Exception as ex:  # 壊れたキャッシュ(手作業の編集・マージの失敗など)でも、取得できればページは作る
        print(f"holiday: cache unreadable, ignoring it ({ex!a})")  # !a: コンソールの文字コードに依存しない
        cached, meta = [], {}
    if not offline:
        try:
            text, mod = _fetch(timeout)
            rows = parse(text)
            if not _valid(rows):
                raise ValueError(f"unexpected CSV content ({len(rows)} rows)")
            if _valid(cached) and rows[-1][0] < cached[-1][0]:
                raise ValueError("fetched CSV covers fewer years than the cache")
        except Exception as ex:  # 取得できなくても、前回のデータでページは作る
            print(f"holiday: fetch failed, using cache ({ex!a})")
        else:
            today = today_jst()
            if rows != cached or not meta.get("fetched"):  # 内容が変わったときだけ書く(毎日のコミット差分を出さない)
                try:
                    _write_cache(rows, mod, today)
                    print(f"holiday: updated {CACHE.name} ({len(rows)} rows, {rows[0][0].year}-{rows[-1][0].year});"
                          " commit it so that later fallbacks use this data")
                except OSError as ex:  # 書けなくても、取得できたデータでページは作る
                    print(f"holiday: could not write the cache ({ex!a})")
            return {"rows": rows, "source": "live", "modified": mod, "checked": today, "fetched": today}
    if not _valid(cached):
        raise RuntimeError("holiday: no usable data (fetch failed and data/holidays.csv is missing or broken)")
    return {"rows": cached, "source": "cache", "modified": meta.get("modified"), "checked": None,
            "fetched": meta.get("fetched")}


# ---------------------------------------------------------------- 計算
def kinds(rows):
    """CSVで「休日」の日を祝日法 第3条第2項(振替休日)/第3項(国民の休日)に分ける。{date: (種類, 振替元の日曜日)}"""
    hol = dict(rows)
    out = {}
    for d, n in rows:
        if n != "休日":
            continue
        p = d - ONE
        while p in hol and p.weekday() != 6:
            p -= ONE
        if p in hol and p.weekday() == 6:
            out[d] = ("振替休日", p)
        else:
            a, b = hol.get(d - ONE), hol.get(d + ONE)
            if a and b and a != "休日" and b != "休日":
                out[d] = ("国民の休日", None)
    return out


def labels(rows, kd):
    """表示用の名称。CSVの「休日」には判定した種類をかっこで添える。"""
    return {d: (f"{n}({kd[d][0]})" if d in kd else n) for d, n in rows}


def is_off(d, hol, wk=True, hd=True, ye=""):
    if wk and d.weekday() >= 5:
        return True
    if hd and d in hol:
        return True
    return bool(ye) and ((d.month == 1 and d.day <= 3) or (d.month == 12 and d.day >= YEAREND[ye][1]))


def add_biz(start, n, hol, **o):
    """start から n 営業日後(n<0なら前)。開始日は数えない。(日付, とばした休業日のリスト)"""
    step = ONE if n >= 0 else -ONE
    d, left, skipped = start, abs(n), []
    while left:
        d += step
        if is_off(d, hol, **o):
            skipped.append(d)
        else:
            left -= 1
    return d, skipped


def count_biz(a, b, hol, inclusive=True, **o):
    """a〜b の営業日数。inclusive=False なら開始日を含めない(翌日〜終了日)。b<a なら入れ替える。"""
    if b < a:
        a, b = b, a
    d, c = (a if inclusive else a + ONE), 0
    while d <= b:
        c += not is_off(d, hol, **o)
        d += ONE
    return c


def runs(hol, start, end, min_len=3):
    """start〜end で土日と祝日・休日が min_len 日以上続く期間 [(初日, 最終日)]"""
    out, cur, d = [], [], start
    while d <= end:
        if d.weekday() >= 5 or d in hol:
            cur.append(d)
        else:
            if len(cur) >= min_len:
                out.append((cur[0], cur[-1]))
            cur = []
        d += ONE
    if len(cur) >= min_len:
        out.append((cur[0], cur[-1]))
    return out


def law_newyear(y):
    """y年の年始のうち、祝日法だけで日付が決まる休み: 元日(第2条: 1月1日)と、元日が日曜日のときの1月2日(第3条第2項の振替休日)。
    y年の祝日がまだデータにないとき、前年から続く連休を年末で切らないためにだけ使う(推計はしない)。"""
    d = dt.date(y, 1, 1)
    return {d: "元日", d + ONE: "休日(振替休日)"} if d.weekday() == 6 else {d: "元日"}


def run_around(day, hol, **o):
    if not is_off(day, hol, **o):
        return None
    a = b = day
    while is_off(a - ONE, hol, **o):
        a -= ONE
    while is_off(b + ONE, hol, **o):
        b += ONE
    return a, b


def _furikae_of(d, hol):
    x = d + ONE
    while x in hol and hol[x] != "休日":
        x += ONE
    return x if hol.get(x) == "休日" else None


# ---------------------------------------------------------------- 表示
def _md(d):
    return f"{d.month}月{d.day}日({WD[d.weekday()]})"


def _ymd(d):
    return f"{d.year}年{_md(d)}"


def _short(d):
    return f"{d.month}/{d.day}({WD[d.weekday()]})"


def _span(a, b):
    return f"{_ymd(a)}〜{_md(b) if a.year == b.year else _ymd(b)}"


def _jdate(d):
    return f"{d.year}年{d.month}月{d.day}日"


# ページ本文は <div class="hol"> で囲み、ここの規則はその中だけに効かせる(build.CSS に移してもほかのページに影響しない)。
# 本文のリンク色: build.CSS は nav a しか色を付けないため、ダークモードでブラウザ既定の青(コントラスト1.9:1)になるのを防ぐ。
CSS = (".hol a{color:var(--acc)}.hol .hl th,.hol .hl td{text-align:left}.hol .hl td.d,.hol .nw td{white-space:nowrap}"
       ".hol .cal{font-size:.85rem}.hol .cal th,.hol .cal td{text-align:center;padding:3px 0;border-bottom:0}"
       ".hol .cal td.o{background:var(--line)}.hol .cal td.h{background:var(--line);color:var(--acc);font-weight:700}"
       ".hol .cal caption{text-align:left;font-weight:700;padding-bottom:4px}"
       ".hol fieldset{border:0;margin:0;padding:0;min-width:0}.hol legend{font-weight:700;padding:0}"
       ".hol input[type=checkbox]{width:auto;margin:0 6px 0 0}.hol details{margin-top:8px}")
STYLE = f"<style>{CSS}</style>"


def _wrap(body, inline_css):
    return (STYLE if inline_css else "") + f'<div class="hol">{body}</div>'


def _source(data, today):
    rows = data["rows"]
    mod = f"(CSVの更新日: {_jdate(data['modified'])})" if data.get("modified") else ""
    if data["source"] == "live":
        st = f"{_jdate(data['checked'])}に内閣府のCSVを確認しました{mod}"
    else:
        got = f"{_jdate(data['fetched'])}に取得したデータ" if data.get("fetched") else "前回取得したデータ"
        st = f"{_jdate(today)}の更新では内閣府のCSVを取得できなかったため、{got}{mod}を使っています"
    return (f'<p class="mut">出典: 内閣府「<a href="{PAGE_URL}">国民の祝日について</a>」の'
            f'「<a href="{CSV_URL}">国民の祝日(csv形式)</a>」({rows[0][0].year}年〜{rows[-1][0].year}年分)を加工して作成。{st}。'
            f'利用条件: <a href="{RULE_URL}">内閣府ホームページ利用規約</a>により'
            f'<a href="{PDL_URL}">公共データ利用規約(第1.0版)</a>が適用されます。'
            "曜日、振替休日・国民の休日の区別、連休、営業日数は、このデータをもとに当サイトが計算したものです。"
            "毎日自動で確認し、内閣府の公表内容が変わればこのページにも反映します。</p>")


def _nodata(data, y):
    """y年の祝日がデータにない理由(取得できた日は「内閣府のCSVにまだない」、キャッシュの日は確認できていない)"""
    return (f"{y}年の祝日は内閣府のCSVにまだ載っていないため" if data["source"] == "live"
            else f"{y}年の祝日は取得済みのデータにないため")


def _note(d, n, hol, kd):
    if d in kd:
        k, src = kd[d]
        if k == "振替休日":
            return f"振替休日({_md(src)}の{html.escape(hol[src])}が日曜日のため)"
        return "国民の休日(前日と翌日が祝日のため)"
    if d.weekday() == 6:
        f = _furikae_of(d, hol)
        return f"日曜日と重なるため、{_md(f)}が振替休日" if f else "日曜日と重なる"
    if d.weekday() == 5:
        return "土曜日と重なる(振替休日はありません)"
    return ""


def _wd_counts(ys):
    return (sum(1 for d, _ in ys if d.weekday() < 5), sum(1 for d, _ in ys if d.weekday() == 5),
            sum(1 for d, _ in ys if d.weekday() == 6))


def _year_list(y, rows, hol, kd):
    ys = [(d, n) for d, n in rows if d.year == y]
    trs = "".join(f'<tr><td class="d">{d.month}月{d.day}日</td><td>{WD[d.weekday()]}</td><td>{html.escape(n)}</td>'
                  f"<td>{_note(d, n, hol, kd)}</td></tr>" for d, n in ys)
    n_k = sum(1 for _, n in ys if n == "休日")
    wdn, sat, sun = _wd_counts(ys)
    return (f'<h2 id="y{y}">{y}年の祝日・休日({len(ys)}日)</h2>'
            '<div class="wrap"><table class="hl"><thead><tr><th>日付</th><th>曜日</th><th>名称(内閣府のCSVのとおり)</th>'
            f"<th>備考</th></tr></thead><tbody>{trs}</tbody></table></div>"
            f"<p>{y}年の祝日・休日は{len(ys)}日(国民の祝日{len(ys) - n_k}日、休日{n_k}日)です。"
            f"平日にあたるのは{wdn}日、土曜日は{sat}日、日曜日は{sun}日です。"
            f'<a href="{y}.html">{y}年のカレンダーと月別の営業日数</a></p>')


JS = r"""const HN=__HN__,HY=__HY__,JW='日月火水木金土';
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
function dn(y,m,d){const t=new Date(0);t.setUTCFullYear(y,m-1,d);return Math.round(t.getTime()/864e5);}
function dp(n){const t=new Date(n*864e5);return [t.getUTCFullYear(),t.getUTCMonth()+1,t.getUTCDate(),t.getUTCDay()];}
const H=new Map();
for(const y in HY){const a=HY[y];for(let i=0;i<a.length;i+=2)H.set(dn(+y,Math.floor(a[i]/100),a[i]%100),HN[a[i+1]]);}
const HK=[...H.keys()].sort((a,b)=>a-b),YS=Object.keys(HY).map(Number),Y0=Math.min(...YS),Y1=Math.max(...YS);
const XH=new Set();{const n=dn(Y1+1,1,1);XH.add(n);if(dp(n)[3]===0)XH.add(n+1);}
const fd=n=>{const [y,m,d,w]=dp(n);return `${y}年${m}月${d}日(${JW[w]})`;};
const sd=n=>{const [y,m,d,w]=dp(n);return `${y}/${m}/${d}(${JW[w]})`;};
const md=n=>{const [,m,d,w]=dp(n);return `${m}/${d}(${JW[w]})`;};
const p2=(v,k)=>String(v).padStart(k,'0');
const iso=n=>{const [y,m,d]=dp(n);return `${p2(y,4)}-${p2(m,2)}-${p2(d,2)}`;};
function pd(s){const m=/^\s*(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})\s*$/.exec(s||'');if(!m)return null;
const y=+m[1],mo=+m[2],d=+m[3],n=dn(y,mo,d),c=dp(n);return c[0]===y&&c[1]===mo&&c[2]===d?n:null;}
function why(n,o){const [,m,d,w]=dp(n),r=[];if(o.hd&&H.has(n))r.push(H.get(n));if(o.wk&&(w===0||w===6))r.push(w?'土曜':'日曜');
if(o.ye&&((m===1&&d<=3)||(m===12&&d>=(o.ye==='gov'?29:31))))r.push('年末年始');return r;}
function bizAdd(s,k,o){const st=k<0?-1:1,sk=[];let c=s,left=Math.abs(k),g=0;
while(left>0){c+=st;if(++g>1e6)return null;const r=why(c,o);if(r.length)sk.push([c,r]);else left--;}return {d:c,sk};}
function bizCount(a,b,o,incl){let c=0;const off=[];for(let x=incl?a:a+1;x<=b;x++){const r=why(x,o);if(r.length)off.push([x,r]);else c++;}return {c,off};}
function tally(off,o){const t={wk:0,hd:0,ye:0};for(const [x] of off){const w=dp(x)[3];if(o.wk&&(w===0||w===6))t.wk++;else if(o.hd&&H.has(x))t.hd++;else t.ye++;}return t;}
function cov(a,b,o){if(!o.hd)return '';const ya=dp(Math.min(a,b))[0],yb=dp(Math.max(a,b))[0];if(ya>=Y0&&yb<=Y1)return '';
return `<p class="mut">注意: 祝日のデータは${Y0}年〜${Y1}年の分です。この範囲外の年の祝日は、休みに含めずに計算しています${yb>Y1?`(${Y1+1}年以降の祝日は、内閣府が公表したあと、このページに自動で反映します)`:''}。</p>`;}
function lst(a,label){if(!a.length)return '';const mx=400,li=a.slice(0,mx).map(([x,r])=>`<li>${sd(x)} ${esc(r.join('・'))}</li>`).join('');
return `<details${a.length<=12?' open':''}><summary>${label}(${a.length}日)</summary><ul>${li}</ul>${a.length>mx?`<p class="mut">ほか${a.length-mx}日は省略しました。</p>`:''}</details>`;}
const opt=()=>({wk:$('wk').checked,hd:$('hd').checked,ye:$('ye').value});
function calcA(){const o=opt(),s=pd($('a0').value),k=Math.trunc(+$('an').value||0)*(+$('ad').value||1);
if(s===null){$('ar').innerHTML='開始日を入力してください。';return;}
if(Math.abs(k)>10000){$('ar').innerHTML='営業日数は10000以内で入力してください。';return;}
const r=bizAdd(s,k,o);if(!r){$('ar').innerHTML='計算できませんでした。';return;}
let h;
if(k===0){const w=why(s,o),nx=bizAdd(s,1,o),pv=bizAdd(s,-1,o);
h=`0営業日後は、開始日の <b>${fd(s)}</b> そのものです。`+(w.length?`この日は休業日(${esc(w.join('・'))})です。次の営業日は${fd(nx.d)}、前の営業日は${fd(pv.d)}です。`:'この日は営業日です。');}
else h=`${fd(s)}の${Math.abs(k)}営業日${k>0?'後':'前'}は <b>${fd(r.d)}</b> です。<br><span class="mut">開始日は数えず、${k>0?'翌日から':'前日からさかのぼって'}営業日を${Math.abs(k)}日数えた日です。</span>`+lst(r.sk,'とばした休業日');
$('ar').innerHTML=h+cov(s,r.d,o);}
function calcB(){const o=opt();let a=pd($('b0').value),b=pd($('b1').value),sw='';
if(a===null||b===null){$('br').innerHTML='開始日と終了日を入力してください。';return;}
if(b<a){[a,b]=[b,a];sw='<br><span class="mut">終了日が開始日より前だったため、入れ替えて計算しました。</span>';}
if(b-a>36600){$('br').innerHTML='期間は100年以内で入力してください。';return;}
const incl=$('bm').value==='1',r=bizCount(a,b,o,incl),r2=bizCount(a,b,o,!incl),t=tally(r.off,o),days=b-a+(incl?1:0),ps=[];
if(o.wk)ps.push(`土日 ${t.wk}日`);if(o.hd)ps.push(`${o.wk?'平日の祝日・休日':'祝日・休日'} ${t.hd}日`);
if(o.ye)ps.push(`年末年始${o.wk&&o.hd?'(土日・祝日以外)':o.wk?'(土日以外)':o.hd?'(祝日以外)':''} ${t.ye}日`);
$('br').innerHTML=`${fd(a)}〜${fd(b)}の営業日数は <b>${r.c}日</b> です(${incl?'開始日と終了日を両方含む':'開始日を含めず、翌日から終了日まで'})。`
+`<br>数えた${days}日のうち、休業日は${r.off.length}日${ps.length?`(${ps.join('、')})`:''}です。`
+`<br><span class="mut">${incl?'開始日を含めない':'開始日と終了日を両方含める'}数え方では${r2.c}日です。</span>`+sw+lst(r.off,'期間中の休業日')+cov(a,b,o);}
function calc(){calcA();calcB();}
function today(){const t=new Date();return dn(t.getFullYear(),t.getMonth()+1,t.getDate());}
function nextInfo(td){let i=HK.findIndex(n=>n>=td),pre='';
if(i>=0&&HK[i]===td){pre=`今日は${esc(H.get(td))}です。`;i++;}
if(i<0||i>=HK.length){$('nx').textContent='-';$('nxs').innerHTML=pre+`祝日のデータは${Y1}年までです`;}
else{const n=HK[i];$('nx').textContent=md(n);$('nxs').innerHTML=pre+`${esc(H.get(n))}・あと${n-td}日`;}
const end=Math.min(dn(Y1+1,1,3),td+800);let s=null,best=null;
for(let x=td-7;x<=end+1;x++){const w=dp(x)[3],off=x<=end&&(w===0||w===6||H.has(x)||XH.has(x));
if(off){if(s===null)s=x;}else{if(s!==null&&x-s>=3&&x-1>=td){best=[s,x-1];break;}s=null;}}
if(best){const [a,b]=best;$('nr').textContent=`${md(a)}〜`;$('nrs').innerHTML=`${md(b)}までの${b-a+1}連休・${a<=td?'今日は連休中です':`あと${a-td}日`}`;}
else{$('nr').textContent='-';$('nrs').textContent=`${Y1}年末までに3連休以上はありません`;}
$('asof').textContent=`今日(${fd(td)})の日付で計算しています。`;}
['wk','hd','ye','a0','an','ad','b0','b1','bm'].forEach(i=>['input','change'].forEach(e=>$(i).addEventListener(e,calc)));
(function(){const td=today(),[y,m]=dp(td);$('a0').value=iso(td);$('b0').value=iso(dn(y,m,1));$('b1').value=iso(dn(y,m+1,0));nextInfo(td);calc();})();"""


def _js_data(rows, lab):
    names, idx, years = [], {}, {}
    for d, _ in rows:
        n = lab[d]
        if n not in idx:
            idx[n] = len(names)
            names.append(n)
        years.setdefault(str(d.year), []).extend((d.month * 100 + d.day, idx[n]))

    def enc(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return JS.replace("__HN__", enc(names)).replace("__HY__", enc(years))


def index_page(data, today, page_years, inline_css=True):
    rows = data["rows"]
    hol, kd = dict(rows), kinds(rows)
    lab = labels(rows, kd)
    y0, y1 = rows[0][0].year, rows[-1][0].year
    ty = today.year
    shown = [y for y in (ty, ty + 1) if y0 <= y <= y1]
    # 連休の判定用: データの翌年の元日(と、日曜なら1月2日の振替休日)は祝日法で決まるので、年末から続く連休を切らない
    ext = law_newyear(y1 + 1)
    holx = {**hol, **ext}
    # ---- 次の祝日・次の連休(ビルド日時点。閲覧時にJSが閲覧者の日付で計算し直す) ----
    ds = [d for d, _ in rows]
    i, pre = bisect.bisect_left(ds, today), ""
    if i < len(ds) and ds[i] == today:
        pre, i = f"今日は{html.escape(lab[today])}です。", i + 1
    if i < len(ds):
        nx, nxs = _short(ds[i]), pre + f"{html.escape(lab[ds[i]])}・あと{(ds[i] - today).days}日"
    else:
        nx, nxs = "-", pre + f"祝日のデータは{y1}年までです"
    end = min(dt.date(y1 + 1, 1, 3), today + 800 * ONE)
    nr = next(((a, b) for a, b in runs(holx, today - 7 * ONE, end) if b >= today), None)
    if nr:
        a, b = nr
        nrb, nrs = f"{_short(a)}〜", (f"{_short(b)}までの{(b - a).days + 1}連休・"
                                      + ("今日は連休中です" if a <= today else f"あと{(a - today).days}日"))
    else:
        nrb, nrs = "-", f"{y1}年末までに3連休以上はありません"
    ty_rows = [(d, n) for d, n in rows if d.year == ty]
    wdn, sat, sun = _wd_counts(ty_rows)
    if ty_rows:
        ty_card = f'<div class="big">{len(ty_rows)}日</div><div class="mut">うち平日{wdn}日・土曜{sat}日・日曜{sun}日</div>'
    elif data["source"] == "live":
        ty_card = f'<div class="big">-</div><div class="mut">内閣府のCSVに{ty}年がまだありません</div>'
    else:
        ty_card = f'<div class="big">-</div><div class="mut">取得済みのデータは{y1}年までです</div>'
    cards = ('<div class="cards">'
             f'<div class="card"><div class="mut">次の祝日</div><div class="big" id="nx">{nx}</div><div class="mut" id="nxs">{nxs}</div></div>'
             f'<div class="card"><div class="mut">次の3連休以上</div><div class="big" id="nr">{nrb}</div><div class="mut" id="nrs">{nrs}</div></div>'
             f'<div class="card"><div class="mut">{ty}年の祝日・休日</div>{ty_card}</div></div>'
             f'<p class="mut" id="asof">{_jdate(today)}時点の計算です(ページを開くと、その日の日付で計算し直します)。</p>')
    # ---- 営業日の計算機(初期値の結果もビルド時に計算しておく。JSが動けば閲覧者の日付で置き換わる) ----
    a_n = 5
    a_d, _ = add_biz(today, a_n, hol)
    m0 = today.replace(day=1)
    m1 = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    b_c = count_biz(m0, m1, hol)
    opts_ye = "".join(f'<option value="{k}">12月{v[1]}日〜1月3日({v[0]})</option>' for k, v in YEAREND.items())
    calc_html = (
        '<h2 id="calc">営業日の計算</h2>'
        f"<p>土日・祝日・年末年始を除いた「営業日」で、◯営業日後(前)の日付と、期間中の営業日数を計算します。"
        f"祝日は内閣府の公表データ({y0}年〜{y1}年)を使います。</p>"
        '<div class="card"><fieldset><legend>休みにする日</legend>'
        '<label><input type="checkbox" id="wk" checked>土曜日・日曜日</label>'
        '<label><input type="checkbox" id="hd" checked>祝日・休日(振替休日・国民の休日を含む)</label>'
        f'<label for="ye">年末年始</label><select id="ye"><option value="">休みにしない</option>{opts_ye}</select></fieldset></div>'
        "<h3>◯営業日後・◯営業日前の日付</h3>"
        f'<label for="a0">開始日</label><input id="a0" type="date" value="{today.isoformat()}">'
        f'<label for="an">営業日数</label><input id="an" type="number" step="1" value="{a_n}">'
        '<label for="ad">方向</label><select id="ad"><option value="1">後(先の日付)</option><option value="-1">前(過去の日付)</option></select>'
        f'<div class="out" id="ar" aria-live="polite">{_ymd(today)}の{a_n}営業日後は <b>{_ymd(a_d)}</b> です(土日・祝日を休みとして計算)。</div>'
        '<p class="mut">開始日は数えません。開始日の次の営業日が「1営業日後」です(開始日が休みの日でも同じ)。'
        "0を入れると開始日そのものを表示し、マイナスの数を入れると逆の方向に数えます。</p>"
        "<h3>期間中の営業日数</h3>"
        f'<label for="b0">期間の開始日</label><input id="b0" type="date" value="{m0.isoformat()}">'
        f'<label for="b1">期間の終了日</label><input id="b1" type="date" value="{m1.isoformat()}">'
        '<label for="bm">数え方</label><select id="bm">'
        '<option value="1">開始日と終了日を両方含める</option>'
        '<option value="0">開始日を含めない(翌日〜終了日)</option></select>'
        f'<div class="out" id="br" aria-live="polite">{_ymd(m0)}〜{_ymd(m1)}の営業日数は <b>{b_c}日</b> です(開始日と終了日を両方含む・土日祝を休みとして計算)。</div>'
        '<p class="mut">「両方含める」で月初〜月末を指定すると、その月の営業日数になります。'
        "「開始日を含めない」数え方で数えた日数は、上の「◯営業日後」の計算と一致します"
        "(例: ある日から、その3営業日後の日付までを数えると3日)。終了日が開始日より前のときは、入れ替えて計算します。"
        "会社や金融機関によっては、ここで選べない独自の休業日があります。</p>")
    # ---- 3連休以上・年末年始 ----
    renkyu = ""
    if shown:
        s0, s1 = dt.date(shown[0], 1, 1), dt.date(shown[-1], 12, 31)
        # 終わりは翌年1月3日まで見る(データの翌年は ext の元日だけ。1月4日以降に続く連休は、元日だけでは生じない)
        rr = [(a, b) for a, b in runs(holx, s0 - 7 * ONE, min(s1 + 7 * ONE, dt.date(y1 + 1, 1, 3)))
              if b >= s0 and a <= s1]
        labx = {**lab, **{d: f"{n}※" for d, n in ext.items()}}
        trs = "".join(
            f"<tr><td>{_span(a, b)}</td><td>{(b - a).days + 1}日</td>"
            f"<td>{'・'.join(html.escape(labx[x]) for x in sorted(holx) if a <= x <= b)}</td></tr>" for a, b in rr)
        used = [x for x in sorted(ext) if any(a <= x <= b for a, b in rr)]
        ext_note = ""
        if used:
            ext_note = (f'<p class="mut">※{_nodata(data, y1 + 1)}、祝日法で日付が決まっている{y1 + 1}年1月1日の元日(第2条)'
                        + ("と、元日が日曜日のための1月2日の振替休日(第3条第2項)" if len(used) > 1 else "")
                        + "だけを含めて数えています。</p>")
        ye_items = []
        for y in shown:
            parts = []
            for k, (who, _) in YEAREND.items():
                a, b = run_around(dt.date(y, 12, 31), holx, ye=k)
                parts.append(f"{who}は{_span(a, b)}の{(b - a).days + 1}連休")
            miss = (f"({_nodata(data, y + 1)}、{y + 1}年1月は祝日法で日付が決まっている元日だけを祝日として計算しています)"
                    if y + 1 > y1 else "")
            ye_items.append(f"<li>{y}年から{y + 1}年: {'、'.join(parts)}{miss}</li>")
        yrs = "・".join(f"{y}年" for y in shown)
        renkyu = (f'<h2 id="renkyu">3連休以上の連休({yrs})</h2>'
                  "<p>土日と祝日・休日が3日以上続く期間です(年末年始の休みは含めていません)。</p>"
                  '<div class="wrap"><table class="hl"><thead><tr><th>期間</th><th>日数</th><th>含まれる祝日・休日</th></tr></thead>'
                  f"<tbody>{trs}</tbody></table></div>{ext_note}"
                  f"<h3>年末年始の休み(土日・祝日とつながる連続の休み)</h3><ul>{''.join(ye_items)}</ul>"
                  f'<p class="mut">国の行政機関(官公庁)は<a href="{LAW["gyosei"]}">行政機関の休日に関する法律</a>で12月29日〜1月3日が、'
                  f'銀行は<a href="{LAW["ginko"]}">銀行法施行令</a>第5条で12月31日〜1月3日が休日と定められています。'
                  f'地方自治体の休日は、<a href="{LAW["chiho"]}">地方自治法</a>第4条の2にもとづき各自治体の条例で定められています。'
                  "民間企業の年末年始休暇は会社ごとに異なります。</p>")
    # ---- 祝日一覧 ----
    lists = "".join(_year_list(y, rows, hol, kd) for y in shown)
    if ty + 1 > y1:  # 来年(または今年から)の祝日がデータにない
        ny = f"{y1 + 1}年{'以降' if ty > y1 else ''}"
        if data["source"] != "live":
            msg = (f"{ny}の祝日は、前回取得したデータ({y1}年まで)に含まれていません。{_jdate(today)}の更新では"
                   "内閣府のCSVを取得できなかったため、公表済みかどうかを確認できていません。取得できしだい、このページに自動で追加します。")
        elif ty == y1 and today.month <= 2:  # 内閣府「国民の祝日について」: 翌年分は前年の2月に掲載
            msg = f"{ny}の祝日は、内閣府が{ty}年2月ごろに公表する予定です。公表されたら、このページに自動で追加します。"
        else:
            msg = (f"{ny}の祝日は、{_jdate(data.get('checked') or today)}の時点で内閣府のCSVにまだ載っていません。"
                   "載りしだい、このページに自動で追加します。")
        lists += f"<p>{msg}</p>"
    # ---- きまり ----
    ex = [d for d, (k, _) in kd.items() if k == "国民の休日" and d <= dt.date(ty + 1, 12, 31)]
    ex_txt = f"(例: {_ymd(max(ex))})" if ex else ""
    rule = (f'<h2 id="rule">祝日・休日のきまり</h2><ul>'
            f'<li><b>国民の祝日</b>: <a href="{LAW["shukujitsu"]}">国民の祝日に関する法律</a>(祝日法)第2条で年16日が定められています。'
            "春分の日・秋分の日は日付が法律に書かれておらず、国立天文台が前年2月に官報で公表する春分日・秋分日になります。</li>"
            "<li><b>振替休日</b>(祝日法第3条第2項): 祝日が日曜日に当たるときは、その後の最も近い「祝日でない日」が休日になります。"
            "土曜日に当たる祝日には、振替休日はありません。</li>"
            f"<li><b>国民の休日</b>(同第3項): 前日と翌日がどちらも祝日である平日は休日になります{ex_txt}。</li>"
            "<li><b>年末年始</b>: 1月1日(元日)以外は祝日ではありません。国の行政機関(官公庁)は12月29日〜1月3日、"
            "銀行は12月31日〜1月3日が休日です。地方自治体の年末年始の休日は、各自治体の条例で定められています。</li></ul>"
            '<p class="mut">内閣府のCSVでは、振替休日と国民の休日はどちらも「休日」と書かれています。'
            "このページの「振替休日」「国民の休日」の区別は、祝日法の規定にもとづいて当サイトが判定したものです。</p>")
    ylinks = " / ".join(f'<a href="{y}.html">{y}年</a>' for y in page_years)
    toc = " / ".join([f'<a href="#calc">営業日の計算</a>'] + [f'<a href="#y{y}">{y}年の祝日</a>' for y in shown]
                     + (['<a href="#renkyu">3連休以上</a>'] if shown else []) + ['<a href="#rule">祝日のきまり</a>'])
    body = _wrap(f"<p>内閣府が公表している「国民の祝日」のデータ({y0}年〜{y1}年)から、祝日・振替休日の一覧、"
                 "3連休以上の連休、次の祝日までの日数をまとめ、土日・祝日・年末年始を除いた営業日を計算できるようにしました。</p>"
                 + cards + f"<p>{toc}</p>" + calc_html + lists + renkyu + rule
                 + (f"<h2>年別の祝日カレンダーと月別の営業日数</h2><p>{ylinks}</p>" if page_years else "")
                 + _source(data, today), inline_css)
    yt = "・".join(f"{y}年" for y in shown) or f"{y0}〜{y1}年"
    title = f"{yt}の祝日一覧と営業日計算"
    desc = (f"{yt}の祝日・振替休日の一覧、3連休以上の連休、次の祝日まであと何日かを内閣府の公表データから表示。"
            "土日・祝日・年末年始(官公庁/銀行)を除く営業日の計算機つき。")
    return title, desc, body, _js_data(rows, lab)


def year_page(y, data, page_years, today, inline_css=True):
    rows = data["rows"]
    hol, kd = dict(rows), kinds(rows)
    lab = labels(rows, kd)
    ys = [(d, n) for d, n in rows if d.year == y]
    stats = []
    for m in range(1, 13):
        days = [dt.date(y, m, i) for i in range(1, calendar.monthrange(y, m)[1] + 1)]
        wk = sum(1 for d in days if d.weekday() >= 5)
        hw = sum(1 for d in days if d in hol and d.weekday() < 5)
        stats.append((m, len(days), wk, hw, len(days) - wk - hw,
                      sum(1 for d in days if not is_off(d, hol, ye="gov")),
                      sum(1 for d in days if not is_off(d, hol, ye="bank"))))
    tot = [sum(s[i] for s in stats) for i in range(1, 7)]
    hi, lo = max(s[4] for s in stats), min(s[4] for s in stats)
    hi_m = "・".join(f"{s[0]}月" for s in stats if s[4] == hi)
    lo_m = "・".join(f"{s[0]}月" for s in stats if s[4] == lo)
    cmp = ""
    if any(d.year == y - 1 for d in hol):
        pb = count_biz(dt.date(y - 1, 1, 1), dt.date(y - 1, 12, 31), hol)
        diff = tot[3] - pb
        cmp = (f"前年({y - 1}年)の{pb}日より{abs(diff)}日{'多く' if diff > 0 else '少なく'}なっています。" if diff
               else f"前年({y - 1}年)と同じ日数です。")
    n_k = sum(1 for _, n in ys if n == "休日")
    wdn, sat, sun = _wd_counts(ys)
    trs = "".join(f"<tr><td>{m}月</td><td>{n}日</td><td>{wk}日</td><td>{hw}日</td><td><b>{b}日</b></td><td>{g}日</td><td>{bk}日</td></tr>"
                  for m, n, wk, hw, b, g, bk in stats)
    trs += ("<tr><td><b>年間</b></td>" + "".join(f"<td><b>{v}日</b></td>" for v in tot) + "</tr>")
    head = "".join(f"<th>{c}</th>" for c in ("月", "日数", "土日", "平日の祝日・休日", "営業日", "官公庁", "銀行"))
    cal_cards = []
    for m in range(1, 13):
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(y, m)
        body_rows = []
        for w in weeks:
            tds = []
            for d in w:
                if d.month != m:
                    tds.append("<td></td>")
                elif d in hol:
                    tds.append(f'<td class="h" title="{html.escape(lab[d])}">{d.day}</td>')
                elif d.weekday() >= 5:
                    tds.append(f'<td class="o">{d.day}</td>')
                else:
                    tds.append(f"<td>{d.day}</td>")
            body_rows.append("<tr>" + "".join(tds) + "</tr>")
        names = " / ".join(f"{d.day}日 {html.escape(lab[d])}" for d, _ in ys if d.month == m)
        cal_cards.append(f'<div class="card"><table class="cal"><caption>{m}月(営業日{stats[m - 1][4]}日)</caption>'
                         "<thead><tr>" + "".join(f"<th>{c}</th>" for c in "日月火水木金土") + "</tr></thead>"
                         f"<tbody>{''.join(body_rows)}</tbody></table>"
                         f'<p class="mut">{names or "祝日なし"}</p></div>')
    others = " / ".join(f'<a href="{p}.html">{p}年</a>' for p in page_years if p != y)
    body = _wrap(f"<p>{y}年の祝日・休日は<b>{len(ys)}日</b>です(国民の祝日{len(ys) - n_k}日、休日{n_k}日)。"
                 f"平日にあたるのは{wdn}日、土曜日は{sat}日、日曜日は{sun}日です。"
                 f"土日と祝日・休日を除いた営業日は年間<b>{tot[3]}日</b>で、{cmp}"
                 f"年末年始も休みとすると、官公庁(1月1日〜3日・12月29日〜31日)は{tot[4]}日、銀行(1月1日〜3日・12月31日)は{tot[5]}日です。"
                 f"土日と祝日・休日だけを休みとした場合、月別では{hi_m}の{hi}日が最も多く、{lo_m}の{lo}日が最も少なくなっています。</p>"
                 f"<h2>{y}年の月別の営業日数</h2>"
                 f'<div class="wrap"><table class="nw"><thead><tr>{head}</tr></thead><tbody>{trs}</tbody></table></div>'
                 '<p class="mut">営業日 = 日数 − 土日 − 平日の祝日・休日。「官公庁」は12月29日〜1月3日、「銀行」は12月31日〜1月3日も'
                 "休みとして数えた営業日です。会社ごとの独自の休業日(夏季休暇など)は含みません。</p>"
                 f"<h2>{y}年のカレンダー</h2>"
                 '<p class="mut">網かけは土日と祝日・休日、色つきの太字は祝日・休日です。</p>'
                 f'<div class="cards">{"".join(cal_cards)}</div>'
                 '<p><a href="index.html#calc">営業日の計算機(◯営業日後・期間の営業日数)</a>'
                 + (f' / <a href="index.html#y{y}">{y}年の祝日一覧と振替休日</a>' if y in (today.year, today.year + 1) else "")
                 + (f" / ほかの年: {others}" if others else "") + "</p>"
                 + _source(data, today), inline_css)
    title = f"{y}年の祝日カレンダーと月別の営業日数"
    desc = (f"{y}年の祝日・休日は{len(ys)}日。土日祝を除く営業日は年間{tot[3]}日(月別の最多は{hi_m}の{hi}日)。"
            "官公庁・銀行の年末年始休みを除いた営業日数と、祝日入りの月別カレンダー。")
    return title, desc, body, ""


def pages(data, today=None, inline_css=True):
    """inline_css=False: 本文に <style> を入れない(CSS 定数を build.CSS に足したとき用)"""
    today = today or today_jst()
    rows = data["rows"]
    have = {d.year for d, _ in rows}
    page_years = [y for y in range(FIRST_YEAR_PAGE, today.year + 2) if y in have]
    out = {"holiday/index.html": index_page(data, today, page_years, inline_css)}
    for y in page_years:
        out[f"holiday/{y}.html"] = year_page(y, data, page_years, today, inline_css)
    return out
