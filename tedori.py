"""手取り計算(会社員・協会けんぽ加入)のページを作る。2026年(令和8年)の制度。

tedori/index.html : 年収(または月給+賞与)・年齢・勤務先の都道府県・家族から手取りを計算する計算機(ブラウザで計算)、
                    同じルールで計算した年収別の手取り早見表、協会けんぽの都道府県別 健康保険料率(令和7→8年度)と保険料の差
データ: 協会けんぽ「令和8年度 都道府県単位保険料率」の表(47都道府県・前年度の率つき)を取得し data/kenpo_rates.csv
        (fy=年度の西暦, pref, rate=%)に保存する。取得・検証に失敗したときはそのキャッシュを使う(ページは壊れない)。
        キャッシュは BOM つきでも読み、形式の違う行は読み飛ばす(件数をログに出す)。
        同じページの年度リンク(サイト共通のメニュー)に令和9年度(r09)以降が現れたら、または RULES_UNTIL を過ぎたら、
        未反映である旨をページに表示し、ビルドのログに GitHub Actions の注釈(::warning::)を出す。RULES_UNTIL の30日前からは
        ページには出さずに注釈だけ出す(運営者向けの予告: FY・RATE_URL・料率と税制の定数を手で更新する必要がある)。

  data = load()                       # 取得(失敗時はキャッシュ)
  pages(data) -> {slug: (title, desc, body, js)}
  calc(params, data["rates"][2026])   # Python版の計算(早見表用)。ページの JS (tdCalc) と同じルール

使っている値と出典(2026-10-31 に一次資料で確認):
[健康保険・介護保険・子ども・子育て支援金] 全国健康保険協会(協会けんぽ)
  - 令和8年度 都道府県単位保険料率(令和8年3月分=4月納付分から。東京都9.85%など47都道府県)、介護保険料率1.62%
    (全国一律、40〜64歳。令和7年度は1.59%)、子ども・子育て支援金率0.23%(全国一律、令和8年4月分=5月納付分から)
    https://www.kyoukaikenpo.or.jp/about/business/insurance_rate/rate_prefectures/r08/  (令和7年度: .../r07/)
  - 令和8年度保険料額表(全都道府県、Excel) https://www.kyoukaikenpo.or.jp/assets/r8ippan3.xlsx :
    標準報酬月額 1〜50級(58,000〜1,390,000円)と報酬月額の区分(下の KENPO_UP / KENPO_STD)、厚生年金は 4(1)〜35(32)級、
    被保険者負担分の端数は「給与から控除する場合 50銭以下切捨て・50銭超切上げ」、
    標準賞与額 = 賞与の1,000円未満切捨て。上限は健康保険・介護保険・子ども・子育て支援金が年度累計573万円、厚生年金が1か月150万円。
  - 支援金率0.23%・令和8年4月分(5月の給与天引き)から・半分は事業主負担: こども家庭庁
    https://www.cfa.go.jp/policies/kodomokosodateshienkinseido
  - 健康保険料と支援金は「一般保険料率と支援金率を合算した率」を標準報酬に掛けて折半し、本人負担分を端数処理する
    (厚生労働省・こども家庭庁「子ども・子育て支援金に関するQ&A」令和8年2月12日。原文PDF
     https://www.mhlw.go.jp/hourei/doc/tsuchi/T260216S0101.pdf は2026-10時点で掲載終了(404)のため、同文を引用した記事
     https://www.kaiketsu-j.com/procedure/20716/ で確認)。Q&Aが挙げるのは一般保険料率と支援金率で、介護保険料率も合算するのは
    当サイトの扱い(協会けんぽの保険料額表は 一般+介護 を1つの率として折半額を示す)。支援金の行は支援金率だけで端数処理した額、
    健康保険の行はその差額とする。項目ごとに端数処理する勤務先とは月1円程度違いうるので、ページの「計算の前提」と出典に明記する。
  - 短時間労働者の賃金要件(月額8.8万円以上)は2026年10月1日に撤廃。残る要件は週20時間以上・従業員51人以上の企業・学生でない等:
    日本年金機構 https://www.nenkin.go.jp/oshirase/taisetu/jigyosho/2026/202610/100104.html (更新日 2026-10-01)
  - 利用条件: 協会けんぽ=著作権あり・出所明示で引用可・改変不可・リンクはトップページに「全国健康保険協会ホームページ」と明示
    (https://www.kyoukaikenpo.or.jp/disclosure/website/)。国税庁・総務省・厚生労働省・兵庫労働局・こども家庭庁=公共データ利用規約
    (第1.0版)(出典と加工した旨を記載)。日本年金機構=原則リンクフリー・転載フリー(https://www.nenkin.go.jp/info/aboutweb/aboutsite.html)。
    法令(e-Gov)=著作権の対象外(著作権法第13条)。
[厚生年金] 18.3%(本人9.15%)、標準報酬月額 88,000〜650,000円(1〜32級、650千円は令和2年9月分から)、標準賞与額は1か月150万円まで
    日本年金機構 https://www.nenkin.go.jp/service/kounen/hokenryo/ryogaku/ryogakuhyo/20200825.html と上記xlsx
[雇用保険] 令和8年度(2026-04-01〜2027-03-31) 一般の事業: 労働者5/1000・事業主8.5/1000(令和7年度は5.5/1000・9/1000)
    厚生労働省 https://www.mhlw.go.jp/content/001692566.pdf (掲載ページ https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000108634.html)
    賃金(賞与を含む、実額)に掛け、本人負担分は 50銭以下切捨て・50銭1厘以上切上げ(賃金から控除する場合):
    https://jsite.mhlw.go.jp/hyogo-roudoukyoku/hourei_seido_tetsuzuki/roudou_hoken/hourei_seido/roudouhoken_about/keisan_houhou.html
[所得税 令和8年分] 令和8年度税制改正後(令和8年12月1日施行、令和8年分から。12月の年末調整で適用) 国税庁
  - 給与所得控除後の給与等の金額: 741,000円未満0、2,191,000円未満は収入−740,000円、2,191,000〜2,192,999円 1,451,000円、
    〜2,195,999円 1,453,000円、〜2,199,999円 1,456,000円、2,200,000〜6,599,999円は4,000円刻み(A=4,000円未満切捨て、
    3,600,000円未満 A×70%−80,000円、以上 A×80%−440,000円)、8,500,000円未満 収入×90%−1,100,000円(1円未満切捨て)、
    以上 収入−1,950,000円  https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/114.pdf
  - 基礎控除(合計所得金額): 489万円以下104万円・655万円以下67万円・2,350万円以下62万円・2,400万円以下48万円・
    2,450万円以下32万円・2,500万円以下16万円・超0  https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/115.pdf
    https://www.nta.go.jp/publication/pamph/gensen/2026kaisei.pdf (改正のあらまし: 改正前95/88/68/63/58万円、最低保障額65→74万円、
    扶養親族等の所得要件58→62万円=給与収入136万円以下)
  - 配偶者控除 38/26/13万円(70歳以上48/32/16万円; 本人の合計所得900万/950万/1,000万円以下)、扶養控除 一般38万円・
    特定(19〜22歳)63万円・老人(70歳以上)48万円・同居老親等58万円、16歳未満は0: 同115.pdf
  - 所得金額調整控除 =(給与収入(1,000万円が上限)−850万円)×10%(1円未満切上げ、23歳未満の扶養親族がいる場合)、
    課税給与所得金額の1,000円未満切捨て、速算表(5〜40%、1,805万円超は年末調整の対象外のため確定申告の速算表 40%/45%)、
    年調年税額 = 算出所得税額×102.1%(復興特別所得税を含む、100円未満切捨て)
    https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/109.pdf
[住民税 令和9年度分(令和8年の所得にかかり、2027年6月〜2028年5月に天引き)] 地方税法(e-Gov 2026-10-16 施行版)・総務省
  - 給与所得は所得税と同じ表(最低保障74万円は令和9・10年度分)、住民税の基礎控除は改正なし(43万円)、扶養親族等の所得要件62万円:
    総務省「個人住民税の基礎控除等について」(令和8年5月29日) https://www.soumu.go.jp/main_content/001075462.pdf
  - 所得割 市町村民税6%・道府県民税4%(標準税率、指定都市以外)、基礎控除43万円(合計所得2,400万円以下; 29万/15万/0)、
    配偶者控除33/22/11万円(70歳以上38/26/13万円)、扶養控除 一般33万・特定45万・老人38万・同居老親等45万円、
    調整控除(人的控除額の差: 基礎5万円・配偶者5/4/2万円(70歳以上10/6/3万円)・扶養 一般5万・特定18万・老人10万・同居老親等13万円。
    合計課税所得200万円以下は min(差の合計, 合計課税所得)、超は max(差の合計−(合計課税所得−200万円), 5万円) に 市3%・県2%)、
    均等割 市町村民税3,000円・道府県民税1,000円(標準税率)、所得割の非課税(総所得金額等が 35万円×(本人+同一生計配偶者+扶養親族)
    +10万円、家族がいれば+32万円 以下)とそのすぐ上の負担調整(所得割の合計を「総所得金額等−その限度額」までに減額し市・県で按分)、
    所得割・均等割の100円未満切捨て:  地方税法 第20条の4の2・第35条・第37条・第38条・第310条・第314条の2・第314条の3・
    第314条の6・附則第3条の3  https://laws.e-gov.go.jp/law/325AC0000000226
  - 均等割の非課税: 合計所得金額が 35万円×(本人+同一生計配偶者+扶養親族)+10万円(家族がいれば+21万円)以下
    (生活保護の1級地の基準。市町村の条例で 2級地・3級地は低い) 地方税法施行令第47条の3 https://laws.e-gov.go.jp/law/325CO0000000245
  - 森林環境税 1,000円(国税、均等割とあわせて徴収): 総務省 https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/150790_18.html
  - 特別徴収の月割: 年税額の12分の1、100円未満の端数は最初の月(6月)に合算(地方税法 第20条の4の2 第6項・第8項、第321条の5)
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import pathlib
import re
import unicodedata
import urllib.request
from decimal import Decimal

HERE = pathlib.Path(__file__).parent
CACHE = HERE / "data" / "kenpo_rates.csv"
RATE_URL = "https://www.kyoukaikenpo.or.jp/about/business/insurance_rate/rate_prefectures/r08/"
KK_TOP = "https://www.kyoukaikenpo.or.jp/"   # 協会けんぽはリンクをトップページにするよう求めている
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
JST = dt.timezone(dt.timedelta(hours=9))
FY = 2026                       # 社会保険料率の年度(令和8年度)。所得税は令和8年分、住民税は令和9年度分
RULES_UNTIL = dt.date(2027, 2, 28)  # 令和9年3月分から協会けんぽの料率が変わりうる。過ぎたら注意を出す
HEADS_UP = RULES_UNTIL - dt.timedelta(days=30)  # この日からビルドのログに運営者向けの予告(::warning::)を出す
VERIFIED = "2026年10月31日"         # 下の値を一次資料で確認した日
PDL_URL = "https://www.digital.go.jp/resources/open_data/public_data_license_v1.0"
SALARY_MIN = 10_000                 # 月給(年収÷12)がこれ未満なら計算しない(万円単位の入力ミスなど)
PART_TIME_LINE = 88_000             # 月給がこれ未満なら、勤務先の社会保険の加入要件についての注意を出す(厚生年金の標準報酬月額の下限)
PREFS = ("北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県", "栃木県", "群馬県", "埼玉県",
         "千葉県", "東京都", "神奈川県", "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県",
         "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県",
         "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県", "熊本県", "大分県",
         "宮崎県", "鹿児島県", "沖縄県")
# 料率は 1万分の1 単位の整数で持つ(浮動小数点の誤差を避ける): 1.62% = 162
KAIGO, SHIEN, KOSEI, KOYO = 162, 23, 1830, 50
KAIGO_PREV, KOYO_PREV = 159, 55
# 健康保険の標準報酬月額(1〜50級)。KENPO_UP[i] は i+1 級の報酬月額の上限(未満)
KENPO_UP = (63000, 73000, 83000, 93000, 101000, 107000, 114000, 122000, 130000, 138000, 146000, 155000, 165000,
            175000, 185000, 195000, 210000, 230000, 250000, 270000, 290000, 310000, 330000, 350000, 370000, 395000,
            425000, 455000, 485000, 515000, 545000, 575000, 605000, 635000, 665000, 695000, 730000, 770000, 810000,
            855000, 905000, 955000, 1005000, 1055000, 1115000, 1175000, 1235000, 1295000, 1355000)
KENPO_STD = (58000, 68000, 78000, 88000, 98000, 104000, 110000, 118000, 126000, 134000, 142000, 150000, 160000,
             170000, 180000, 190000, 200000, 220000, 240000, 260000, 280000, 300000, 320000, 340000, 360000, 380000,
             410000, 440000, 470000, 500000, 530000, 560000, 590000, 620000, 650000, 680000, 710000, 750000, 790000,
             830000, 880000, 930000, 980000, 1030000, 1090000, 1150000, 1210000, 1270000, 1330000, 1390000)
KOSEI_MIN, KOSEI_MAX = 88_000, 650_000          # 厚生年金の標準報酬月額 1級・32級
BONUS_CAP_KENPO, BONUS_CAP_KOSEI = 5_730_000, 1_500_000
# 所得税の速算表(上限, 税率%, 控除額)。1,805万円までは年末調整の表、それ以上は確定申告の表と同じ
IT_TABLE = ((1_950_000, 5, 0), (3_300_000, 10, 97_500), (6_950_000, 20, 427_500), (9_000_000, 23, 636_000),
            (18_000_000, 33, 1_536_000), (40_000_000, 40, 2_796_000), (10 ** 15, 45, 4_796_000))
IT_KISO = ((4_890_000, 1_040_000), (6_550_000, 670_000), (23_500_000, 620_000), (24_000_000, 480_000),
           (24_500_000, 320_000), (25_000_000, 160_000))
JT_KISO = ((24_000_000, 430_000), (24_500_000, 290_000), (25_000_000, 150_000))
# 配偶者: 1=70歳未満, 2=70歳以上。本人の合計所得 900万/950万/1,000万円以下の順
SPOUSE_IT = {1: (380_000, 260_000, 130_000), 2: (480_000, 320_000, 160_000)}
SPOUSE_JT = {1: (330_000, 220_000, 110_000), 2: (380_000, 260_000, 130_000)}
SPOUSE_DIFF = {1: (50_000, 40_000, 20_000), 2: (100_000, 60_000, 30_000)}
# 扶養親族(所得62万円以下・障害者でない): (所得税の扶養控除, 住民税の扶養控除, 調整控除の人的控除額の差, 23歳未満か)
DEP = {"u16": (0, 0, 0, True), "a16": (380_000, 330_000, 50_000, True), "a19": (630_000, 450_000, 180_000, True),
       "a23": (380_000, 330_000, 50_000, False), "r70": (480_000, 380_000, 100_000, False),
       "d70": (580_000, 450_000, 130_000, False)}
DEP_LABEL = {"u16": "16歳未満の子など", "a16": "16〜18歳", "a19": "19〜22歳(特定扶養親族)", "a23": "23〜69歳",
             "r70": "70歳以上(同居の親・祖父母以外)", "d70": "70歳以上の同居の親・祖父母"}


# ---------------------------------------------------------------- データ取得(協会けんぽの料率表)
def _cell(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", html.unescape(re.sub(r"<[^>]+>", "", s))))


def parse(text):
    """協会けんぽ「都道府県単位保険料率」ページの表から {年度(西暦): {都道府県: 料率(1万分の1)}}。
    見出し行の「令和◯年度」の並び順に値を対応させる(令和7年度のページは新→旧、令和8年度のページは旧→新の順)。"""
    years, out = [], {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = [_cell(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)]
        if not cells:
            continue
        ys = [2018 + int(y) for c in cells for y in re.findall(r"令和(\d+)年度", c)]
        if len(ys) >= 2 and cells[0] not in PREFS:
            years = ys
            continue
        if cells[0] in PREFS and years:
            vals = [v for c in cells[1:] for v in re.findall(r"(\d+(?:\.\d+)?)%", c)]
            if len(vals) == len(years):
                for y, v in zip(years, vals):
                    out.setdefault(y, {})[cells[0]] = int(Decimal(v) * 100)
    return out


def latest_fy(text):
    """ページ内の年度別リンク(rate_prefectures/r08 など)から、協会けんぽが公表済みの最新年度(西暦)。"""
    ys = [2018 + int(y) for y in re.findall(r"rate_prefectures/r(\d{2})", text)]
    return max(ys) if ys else None


def _valid(rates):
    cur = rates.get(FY, {})
    return len(cur) == len(PREFS) and all(700 <= v <= 1300 for v in cur.values())


_CACHE_ROW = re.compile(r"(20\d\d),([^,]+),(\d{1,2}\.\d{1,2})")


def _read_cache():
    """data/kenpo_rates.csv → {年度: {都道府県: 料率(1万分の1)}}。手で直したとき(BOMつき・列の過不足・%つきなど)に
    黙って誤った率を使わないよう、「年度,都道府県,率(小数2桁まで)」の3列の行だけを読み、ほかは読み飛ばして件数を出す。"""
    out, bad = {}, 0
    if CACHE.exists():
        with CACHE.open(encoding="utf-8-sig", newline="") as fp:
            for i, r in enumerate(csv.reader(fp)):
                r = [c.strip() for c in r]
                if not any(r) or (i == 0 and r == ["fy", "pref", "rate"]):
                    continue
                m = _CACHE_ROW.fullmatch(",".join(r)) if len(r) == 3 else None
                if m and m.group(2) in PREFS:
                    out.setdefault(int(m.group(1)), {})[m.group(2)] = int(Decimal(m.group(3)) * 100)
                else:
                    bad += 1
        if bad:
            print(f"tedori: {CACHE.name} の {bad} 行は形式が違うため読み飛ばしました")
    return out


def _write_cache(rates):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["fy", "pref", "rate"])
    for y in sorted(rates):
        for p in PREFS:
            if p in rates[y]:
                w.writerow([y, p, f"{rates[y][p] / 100:.2f}"])
    new = buf.getvalue()
    if not CACHE.exists() or CACHE.read_text(encoding="utf-8") != new:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(new, encoding="utf-8")
        return True
    return False


def _fetch(timeout):
    req = urllib.request.Request(RATE_URL, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def load(offline=False, timeout=30):
    """{"rates": {年度: {都道府県: 料率}}, "source": "web"|"cache", "latest_fy": 公表済み最新年度|None}"""
    cached = _read_cache()
    if not offline:
        try:
            text = _fetch(timeout)
            got = parse(text)
            if not _valid(got):
                raise ValueError(f"料率表を読めませんでした: {[(y, len(v)) for y, v in got.items()]}")
            rates = {**cached, **got}
            _write_cache(rates)
            return {"rates": rates, "source": "web", "latest_fy": latest_fy(text)}
        except Exception as ex:  # 取得に失敗してもキャッシュでページを作る
            print(f"tedori: 協会けんぽの料率表を取得できないためキャッシュを使います: {ex!r}")
    if not _valid(cached):
        raise RuntimeError("協会けんぽの料率(data/kenpo_rates.csv)がありません")
    return {"rates": cached, "source": "cache", "latest_fy": None}


# ---------------------------------------------------------------- 計算(ページの JS と同じルール)
def _r50(n, d):
    """n/d 円の本人負担分: 50銭以下切捨て・50銭超切上げ。"""
    q, r = divmod(n, d)
    return q + (1 if 2 * r > d else 0)


def std_monthly(m):
    """報酬月額 → (健康保険の等級, 健康保険の標準報酬月額, 厚生年金の標準報酬月額)"""
    g = 0
    while g < len(KENPO_UP) and m >= KENPO_UP[g]:
        g += 1
    sk = KENPO_STD[g]
    return g + 1, sk, min(max(sk, KOSEI_MIN), KOSEI_MAX)


def kyuyo_shotoku(s):
    """令和8年分の給与所得控除後の給与等の金額(年末調整等のための表と同じ)。"""
    if s < 741_000:
        return 0
    if s < 2_191_000:
        return s - 740_000
    if s < 2_200_000:
        return 1_451_000 if s < 2_193_000 else 1_453_000 if s < 2_196_000 else 1_456_000
    if s < 6_600_000:
        a = s // 4000 * 4000
        return a * 7 // 10 - 80_000 if s < 3_600_000 else a * 8 // 10 - 440_000
    if s < 8_500_000:
        return s * 9 // 10 - 1_100_000
    return s - 1_950_000


def income_tax(a):
    for lim, pct, ded in IT_TABLE:
        if a <= lim:
            return a * pct // 100 - ded
    return 0


def _tier(t):
    return 0 if t <= 9_000_000 else 1 if t <= 9_500_000 else 2 if t <= 10_000_000 else -1


def calc(p, rates):
    """p: mode('annual'|'monthly'), annual, monthly, bonus(1回), bonus_n, age, pref, spouse(0/1/2), u16..d70。
    rates: {都道府県: 健康保険料率(1万分の1)}。金額はすべて円(整数)。"""
    age = int(p.get("age", 30))
    kind = int(p.get("spouse", 0))
    dep = {k: max(0, int(p.get(k, 0))) for k in DEP}
    rk = rates[p.get("pref", "東京都")]
    if p.get("mode", "annual") == "annual":
        gross = max(0, int(p.get("annual", 0)))
        m, bonus, bn = gross // 12, 0, 0
    else:
        m, bonus, bn = (max(0, int(p.get(k, 0))) for k in ("monthly", "bonus", "bonus_n"))
        gross = 12 * m + bonus * bn
    care, pen = 40 <= age < 65, age < 70
    hrate = rk + (KAIGO if care else 0) + SHIEN
    grade, sk, sp = std_monthly(m)
    m_all, m_sh = _r50(sk * hrate, 20000), _r50(sk * SHIEN, 20000)
    m_pen = _r50(sp * KOSEI, 20000) if pen else 0
    m_emp = _r50(m * KOYO, 10000)
    b = {"health": 0, "shien": 0, "pension": 0, "koyo": 0}
    sb, left = bonus // 1000 * 1000, BONUS_CAP_KENPO
    for _ in range(bn):
        s_h = min(sb, left)
        left -= s_h
        t_all, t_sh = _r50(s_h * hrate, 20000), _r50(s_h * SHIEN, 20000)
        b["health"] += t_all - t_sh
        b["shien"] += t_sh
        b["pension"] += _r50(min(sb, BONUS_CAP_KOSEI) * KOSEI, 20000) if pen else 0
        b["koyo"] += _r50(bonus * KOYO, 10000)
    health = 12 * (m_all - m_sh) + b["health"]
    shien = 12 * m_sh + b["shien"]
    pension = 12 * m_pen + b["pension"]
    koyo = 12 * m_emp + b["koyo"]
    si = health + shien + pension + koyo
    # 所得税(令和8年分)
    g = kyuyo_shotoku(gross)
    u23 = any(dep[k] for k, v in DEP.items() if v[3])
    adj = min(-(-(min(gross, 10_000_000) - 8_500_000) // 10), 150_000) if u23 and gross > 8_500_000 else 0
    t = g - adj                                   # 合計所得金額(= 総所得金額等)
    tier = _tier(t)
    it_kiso = next((v for lim, v in IT_KISO if t <= lim), 0)
    it_sp = SPOUSE_IT[kind][tier] if kind and tier >= 0 else 0
    it_dep = sum(DEP[k][0] * n for k, n in dep.items())
    it_taxable = max(0, t - si - it_kiso - it_sp - it_dep) // 1000 * 1000
    it_calc = income_tax(it_taxable)
    it = it_calc * 1021 // 100000 * 100
    # 住民税(令和9年度分)
    fam = (1 if kind else 0) + sum(dep.values())
    lim_k = 350_000 * (fam + 1) + 100_000 + (210_000 if fam else 0)
    lim_s = 350_000 * (fam + 1) + 100_000 + (320_000 if fam else 0)
    jt_kiso = next((v for lim, v in JT_KISO if t <= lim), 0)
    jt_sp = SPOUSE_JT[kind][tier] if kind and tier >= 0 else 0
    jt_dep = sum(DEP[k][1] * n for k, n in dep.items())
    jt_taxable = max(0, t - si - jt_kiso - jt_sp - jt_dep) // 1000 * 1000
    city = pref = kintou = shinrin = 0
    status = "非課税"
    if t > lim_k:
        kintou, shinrin, status = 4000, 1000, "均等割のみ"
        if t > lim_s and jt_taxable > 0:
            city, pref = jt_taxable * 6 // 100, jt_taxable * 4 // 100
            if t <= 25_000_000:
                h = 50_000 + (SPOUSE_DIFF[kind][tier] if kind and tier >= 0 else 0) + sum(DEP[k][2] * n for k, n in dep.items())
                base = min(h, jt_taxable) if jt_taxable <= 2_000_000 else max(h - (jt_taxable - 2_000_000), 50_000)
                city, pref = max(0, city - base * 3 // 100), max(0, pref - base * 2 // 100)
            tot = city + pref
            if tot > 0 and t - tot < lim_s:       # 非課税限度額のすぐ上の負担調整
                city, pref = city * (t - lim_s) // (tot * 100) * 100, pref * (t - lim_s) // (tot * 100) * 100
            else:
                city, pref = city // 100 * 100, pref // 100 * 100
            if city + pref:
                status = "課税"
    jt = city + pref + kintou + shinrin
    jt_mon = 0 if jt <= kintou + shinrin else jt // 1200 * 100
    return {"gross": gross, "m": m, "bonus": bonus, "bonus_n": bn, "grade": grade, "kosei_grade": min(max(grade - 3, 1), 32),
            "std_kenpo": sk, "std_kosei": sp, "care": care,
            "m_health": m_all - m_sh, "m_shien": m_sh, "m_pension": m_pen, "m_koyo": m_emp,
            "b_health": b["health"], "b_shien": b["shien"], "b_pension": b["pension"], "b_koyo": b["koyo"],
            "health": health, "shien": shien, "pension": pension, "koyo": koyo, "si": si,
            "kyuyo": g, "adj": adj, "gokei": t,
            "it_kiso": it_kiso, "it_spouse": it_sp, "it_dep": it_dep, "it_taxable": it_taxable, "it_calc": it_calc, "it": it,
            "jt_kiso": jt_kiso, "jt_spouse": jt_sp, "jt_dep": jt_dep, "jt_taxable": jt_taxable,
            "jt_city": city, "jt_pref": pref, "jt_kintou": kintou, "jt_shinrin": shinrin, "jt": jt, "jt_status": status,
            "jt_june": jt - 11 * jt_mon, "jt_month": jt_mon,
            "net": gross - si - it - jt}


# ---------------------------------------------------------------- ページの JS(tdCalc は calc と同じルール)
JS_CALC = r"""/*TDCALC-START*/
const TD_UP=%(up)s,TD_STD=%(std)s,TD_R=%(rates)s;
const TD_KAIGO=%(kaigo)d,TD_SHIEN=%(shien)d,TD_KOSEI=%(kosei)d,TD_KOYO=%(koyo)d;
const TD_IT=[[1950000,5,0],[3300000,10,97500],[6950000,20,427500],[9000000,23,636000],[18000000,33,1536000],[40000000,40,2796000],[1e15,45,4796000]];
const TD_ITK=[[4890000,1040000],[6550000,670000],[23500000,620000],[24000000,480000],[24500000,320000],[25000000,160000]];
const TD_JTK=[[24000000,430000],[24500000,290000],[25000000,150000]];
const TD_SPI={1:[380000,260000,130000],2:[480000,320000,160000]},TD_SPJ={1:[330000,220000,110000],2:[380000,260000,130000]},TD_SPD={1:[50000,40000,20000],2:[100000,60000,30000]};
const TD_DEP={u16:[0,0,0,1],a16:[380000,330000,50000,1],a19:[630000,450000,180000,1],a23:[380000,330000,50000,0],r70:[480000,380000,100000,0],d70:[580000,450000,130000,0]};
function tdR50(n,d){const q=Math.floor(n/d),r=n-q*d;return q+(2*r>d?1:0);}
function tdStd(m){let g=0;while(g<TD_UP.length&&m>=TD_UP[g])g++;const sk=TD_STD[g];return [g+1,sk,Math.min(Math.max(sk,88000),650000)];}
function tdKyuyo(s){if(s<741000)return 0;if(s<2191000)return s-740000;if(s<2200000)return s<2193000?1451000:s<2196000?1453000:1456000;
if(s<6600000){const a=Math.floor(s/4000)*4000;return s<3600000?a*7/10-80000:a*8/10-440000;}if(s<8500000)return Math.floor(s*9/10)-1100000;return s-1950000;}
function tdIt(a){for(const [l,p,d] of TD_IT)if(a<=l)return a*p/100-d;return 0;}
function tdLook(tb,t){for(const [l,v] of tb)if(t<=l)return v;return 0;}
function tdCalc(p){const toI=v=>Math.max(0,Math.floor(+v||0));
const age=Math.floor(+p.age||0),kind=Math.floor(+p.spouse||0),dep={};let fam=kind?1:0,u23=false;
for(const k in TD_DEP){dep[k]=toI(p[k]);fam+=dep[k];if(TD_DEP[k][3]&&dep[k])u23=true;}
const rk=TD_R[p.pref];let gross,m,bonus=0,bn=0;
if(p.mode==='annual'){gross=toI(p.annual);m=Math.floor(gross/12);}else{m=toI(p.monthly);bonus=toI(p.bonus);bn=toI(p.bonus_n);gross=12*m+bonus*bn;}
const care=age>=40&&age<65,pen=age<70,hrate=rk+(care?TD_KAIGO:0)+TD_SHIEN;
const [grade,sk,sp]=tdStd(m),mAll=tdR50(sk*hrate,20000),mSh=tdR50(sk*TD_SHIEN,20000),mPen=pen?tdR50(sp*TD_KOSEI,20000):0,mEmp=tdR50(m*TD_KOYO,10000);
let bH=0,bS=0,bP=0,bK=0,left=5730000;const sb=Math.floor(bonus/1000)*1000;
for(let i=0;i<bn;i++){const sh=Math.min(sb,left);left-=sh;const tA=tdR50(sh*hrate,20000),tS=tdR50(sh*TD_SHIEN,20000);
bH+=tA-tS;bS+=tS;bP+=pen?tdR50(Math.min(sb,1500000)*TD_KOSEI,20000):0;bK+=tdR50(bonus*TD_KOYO,10000);}
const health=12*(mAll-mSh)+bH,shien=12*mSh+bS,pension=12*mPen+bP,koyo=12*mEmp+bK,si=health+shien+pension+koyo;
const g=tdKyuyo(gross),adj=(u23&&gross>8500000)?Math.min(Math.ceil((Math.min(gross,10000000)-8500000)/10),150000):0,t=g-adj;
const tier=t<=9000000?0:t<=9500000?1:t<=10000000?2:-1;
let depIt=0,depJt=0,depH=0;for(const k in TD_DEP){depIt+=TD_DEP[k][0]*dep[k];depJt+=TD_DEP[k][1]*dep[k];depH+=TD_DEP[k][2]*dep[k];}
const itKiso=tdLook(TD_ITK,t),itSp=(kind&&tier>=0)?TD_SPI[kind][tier]:0,itTaxable=Math.floor(Math.max(0,t-si-itKiso-itSp-depIt)/1000)*1000;
const itCalc=tdIt(itTaxable),it=Math.floor(itCalc*1021/100000)*100;
const limK=350000*(fam+1)+100000+(fam?210000:0),limS=350000*(fam+1)+100000+(fam?320000:0);
const jtKiso=tdLook(TD_JTK,t),jtSp=(kind&&tier>=0)?TD_SPJ[kind][tier]:0,jtTaxable=Math.floor(Math.max(0,t-si-jtKiso-jtSp-depJt)/1000)*1000;
let city=0,pref=0,kintou=0,shinrin=0,status='非課税';
if(t>limK){kintou=4000;shinrin=1000;status='均等割のみ';
if(t>limS&&jtTaxable>0){city=jtTaxable*6/100;pref=jtTaxable*4/100;
if(t<=25000000){const h=50000+((kind&&tier>=0)?TD_SPD[kind][tier]:0)+depH;
const base=jtTaxable<=2000000?Math.min(h,jtTaxable):Math.max(h-(jtTaxable-2000000),50000);
city=Math.max(0,city-base*3/100);pref=Math.max(0,pref-base*2/100);}
const tot=city+pref;
if(tot>0&&t-tot<limS){city=Math.floor(city*(t-limS)/(tot*100))*100;pref=Math.floor(pref*(t-limS)/(tot*100))*100;}
else{city=Math.floor(city/100)*100;pref=Math.floor(pref/100)*100;}
if(city+pref)status='課税';}}
const jt=city+pref+kintou+shinrin,jtMon=jt<=kintou+shinrin?0:Math.floor(jt/1200)*100;
return {gross,m,bonus,bonus_n:bn,grade,kosei_grade:Math.min(Math.max(grade-3,1),32),std_kenpo:sk,std_kosei:sp,care,
m_health:mAll-mSh,m_shien:mSh,m_pension:mPen,m_koyo:mEmp,b_health:bH,b_shien:bS,b_pension:bP,b_koyo:bK,
health,shien,pension,koyo,si,kyuyo:g,adj,gokei:t,it_kiso:itKiso,it_spouse:itSp,it_dep:depIt,it_taxable:itTaxable,it_calc:itCalc,it,
jt_kiso:jtKiso,jt_spouse:jtSp,jt_dep:depJt,jt_taxable:jtTaxable,jt_city:city,jt_pref:pref,jt_kintou:kintou,jt_shinrin:shinrin,jt,jt_status:status,
jt_june:jt-11*jtMon,jt_month:jtMon,net:gross-si-it-jt};}
/*TDCALC-END*/"""

JS_UI = r"""
const tdY=n=>Math.round(n).toLocaleString('ja-JP')+'円';
function tdParams(){const p={mode:$('td_mode').value,annual:$('td_annual').value,monthly:$('td_monthly').value,bonus:$('td_bonus').value,
bonus_n:$('td_bn').value,age:$('td_age').value,pref:$('td_pref').value,spouse:$('td_sp').value};
for(const k in TD_DEP)p[k]=$('td_'+k).value;return p;}
function tdShow(s,d){$('td_sum').innerHTML=s;$('td_res').innerHTML=d||'';}
function tdRun(){const p=tdParams();$('td_a').hidden=p.mode!=='annual';$('td_m').hidden=p.mode==='annual';
const age=Math.floor(+p.age||0);if(age<18||age>74)return tdShow('年齢は18〜74歳(2026年12月31日時点)で入力してください。18歳未満は住民税の非課税の基準が違うため、75歳以上は後期高齢者医療制度に移るため、このページの計算の対象外です。');
const r=tdCalc(p);if(!r.m)return tdShow('年収(または月給)を入力してください。');
if(r.gross>1e9)return tdShow('10億円以下の金額で入力してください。');
if(r.m<TD_MINM||r.net<0)return tdShow('金額は円単位で入力してください(例: 年収400万円なら「4000000」)。月給(年収÷12)が1万円未満のときや、社会保険料などが給与を上回るときは計算できません。');
const bon=r.bonus_n>0,row=(n,y,mo,b)=>`<tr><td>${n}</td><td>${tdY(y)}</td><td>${mo}</td>${bon?`<td>${b}</td>`:''}</tr>`;
const part=r.m<TD_PART?'<p class="mut"><b>ご注意</b>: 月給が8万8千円未満です。パート・アルバイトなど勤務時間の短い人は、週の所定労働時間が20時間以上・従業員51人以上の企業に勤務・学生でない などの要件を満たすときに勤務先の健康保険・厚生年金に加入します(月8.8万円以上という賃金の要件は2026年10月1日に撤廃されました)。加入しない場合は国民健康保険・国民年金や家族の扶養になるため、この試算はあてはまりません。加入する場合も、標準報酬月額には下限(健康保険5万8千円・厚生年金8万8千円)があるため、月給がそれより少なくても下限の額をもとに保険料がかかります。</p>':'';
tdShow(`手取り(年間・試算) <b class="big">${tdY(r.net)}</b><br>額面に対する割合 ${(r.net/r.gross*100).toFixed(1)}% / 1か月あたり平均 ${tdY(Math.floor(r.net/12))}`,
`${part}<div class="wrap"><table><thead><tr><th>項目</th><th>年額</th><th>毎月の給与から</th>${bon?`<th>賞与(年${r.bonus_n}回の合計)から</th>`:''}</tr></thead><tbody>
${row('額面(総支給)',r.gross,tdY(r.m),bon?tdY(r.bonus*r.bonus_n):'')}
${row('健康保険料'+(r.care?'(介護保険料を含む)':''),r.health,tdY(r.m_health),bon?tdY(r.b_health):'')}
${row('子ども・子育て支援金',r.shien,tdY(r.m_shien),bon?tdY(r.b_shien):'')}
${row('厚生年金保険料',r.pension,tdY(r.m_pension),bon?tdY(r.b_pension):'')}
${row('雇用保険料',r.koyo,tdY(r.m_koyo),bon?tdY(r.b_koyo):'')}
${row('社会保険料の合計',r.si,tdY(r.m_health+r.m_shien+r.m_pension+r.m_koyo),bon?tdY(r.b_health+r.b_shien+r.b_pension+r.b_koyo):'')}
${row('所得税(復興特別所得税を含む・令和8年分)',r.it,'毎月源泉徴収('+(r.gross>20000000?'確定申告':'年末調整')+'で精算)',bon?'源泉徴収':'')}
${row('住民税(令和9年度分・'+r.jt_status+')',r.jt,r.jt?`2027年6月 ${tdY(r.jt_june)}、7月〜翌5月 ${tdY(r.jt_month)}`:'0円',bon?'—':'')}
${row('<b>手取り</b>',r.net,'',bon?'':'')}</tbody></table></div>
<p class="mut">標準報酬月額 ${tdY(r.std_kenpo)}(健康保険 ${r.grade}級・厚生年金 ${tdY(r.std_kosei)} ${r.kosei_grade}級)。
給与所得 ${tdY(r.kyuyo)}${r.adj?`(所得金額調整控除 ${tdY(r.adj)} の後 ${tdY(r.gokei)})`:''}。
所得税: 基礎控除 ${tdY(r.it_kiso)}${r.it_spouse?`・配偶者控除 ${tdY(r.it_spouse)}`:''}${r.it_dep?`・扶養控除 ${tdY(r.it_dep)}`:''}・社会保険料控除 ${tdY(r.si)} → 課税所得 ${tdY(r.it_taxable)}、税額 ${tdY(r.it_calc)}×102.1%。
住民税: 基礎控除 ${tdY(r.jt_kiso)}${r.jt_spouse?`・配偶者控除 ${tdY(r.jt_spouse)}`:''}${r.jt_dep?`・扶養控除 ${tdY(r.jt_dep)}`:''} → 課税所得 ${tdY(r.jt_taxable)}、所得割 ${tdY(r.jt_city+r.jt_pref)}(市町村 ${tdY(r.jt_city)}・道府県 ${tdY(r.jt_pref)})、均等割 ${tdY(r.jt_kintou)}、森林環境税 ${tdY(r.jt_shinrin)}。${r.gross>20000000?'年収2,000万円を超える人は年末調整の対象外のため、所得税は確定申告で精算します。':''}</p>`);}
['td_mode','td_annual','td_monthly','td_bonus','td_bn','td_age','td_pref','td_sp'].concat(Object.keys(TD_DEP).map(k=>'td_'+k)).forEach(i=>$(i).addEventListener('input',tdRun));
tdRun();"""


def js_code(rates):
    return (JS_CALC % {"up": json.dumps(list(KENPO_UP)), "std": json.dumps(list(KENPO_STD)),
                       "rates": json.dumps({p: rates[p] for p in PREFS}, ensure_ascii=False),
                       "kaigo": KAIGO, "shien": SHIEN, "kosei": KOSEI, "koyo": KOYO}
            + f"\nconst TD_MINM={SALARY_MIN},TD_PART={PART_TIME_LINE};" + JS_UI)


# ---------------------------------------------------------------- ページ
def _pct(v):
    return f"{v / 100:.2f}%"


def _man(n):
    """6,655,556 → 665万5,556円"""
    hi, lo = divmod(n, 10000)
    return f"{hi:,}万{lo:,}円" if lo else f"{hi:,}万円"


def _edge(limit):
    """給与所得(合計所得金額)が limit 以下になる最大の給与収入。"""
    lo, hi = 0, 10 ** 9
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if kyuyo_shotoku(mid) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _steps(rates):
    """基礎控除の段階(合計所得489万円・655万円)をまたぐと所得税がいくら増えるか(東京都・30歳・扶養なし)。"""
    out = []
    for lim, _ in IT_KISO[:2]:
        s = _edge(lim)
        a, b = (calc({"mode": "annual", "annual": x, "age": 30, "pref": "東京都"}, rates) for x in (s, s + 1))
        out.append((s, lim, a["it_kiso"], b["it_kiso"], b["it"] - a["it"], a["net"] - b["net"]))
    return out


PDL = "公共データ利用規約(第1.0版)により利用。当サイトで加工して計算"
NENKIN_TERMS = "日本年金機構ホームページは原則リンクフリー・転載フリー"
LAW = "法令(著作権の対象外)"
# (名称, URL(なし=None), リンクの文字(None なら名称そのものをリンクにする), 利用条件などの補足)
# リンクの文字は名称にする(長いURLをそのまま表示すると、スマートフォンで折り返せずページが横にはみ出す)。
SOURCES = [
    ("全国健康保険協会(協会けんぽ)「令和8年度 都道府県単位保険料率」「令和8年度保険料額表」", KK_TOP, "全国健康保険協会ホームページ",
     f"都道府県単位保険料率の表は毎日の更新時に取得して計算に使用。介護保険料率・子ども・子育て支援金率・標準報酬月額の等級表・"
     f"端数処理・標準賞与額の上限は{VERIFIED}に確認した値。リンクは同協会の求めによりトップページにしています"),
    ("こども家庭庁「子ども・子育て支援金制度について」", "https://www.cfa.go.jp/policies/kodomokosodateshienkinseido", None, PDL),
    ("厚生労働省・こども家庭庁「子ども・子育て支援金に関するQ&A」(2026年2月12日)", None, None,
     "健康保険料と支援金を合計した率で計算してから本人負担分を端数処理する方法。原文(厚生労働省ウェブサイトのPDF)は掲載が終了しているため、"
     "同じ文を引用した記事で内容を確認しました"),
    ("日本年金機構「保険料額表(令和2年9月分〜)(厚生年金保険と協会けんぽ管掌の健康保険)」",
     "https://www.nenkin.go.jp/service/kounen/hokenryo/ryogaku/ryogakuhyo/20200825.html", None, NENKIN_TERMS + "。当サイトで加工して計算"),
    ("日本年金機構「2026(令和8)年10月に社会保険の短時間労働者に係る賃金要件が撤廃されました」",
     "https://www.nenkin.go.jp/oshirase/taisetu/jigyosho/2026/202610/100104.html", None, "2026年10月1日更新。" + NENKIN_TERMS),
    ("厚生労働省「令和8年度の雇用保険料率について」", "https://www.mhlw.go.jp/content/001692566.pdf", None, PDL),
    ("兵庫労働局「労働保険料の計算方法」(雇用保険料の本人負担分の端数処理)",
     "https://jsite.mhlw.go.jp/hyogo-roudoukyoku/hourei_seido_tetsuzuki/roudou_hoken/hourei_seido/roudouhoken_about/keisan_houhou.html",
     None, PDL),
    ("国税庁「令和8年分 年末調整のしかた」(給与所得控除後の給与等の金額の表・速算表・基礎控除額の表・扶養控除額等の表)",
     "https://www.nta.go.jp/users/gensen/nencho/index/shikata.htm", None, PDL),
    ("国税庁「令和8年4月 源泉所得税の改正のあらまし」", "https://www.nta.go.jp/publication/pamph/gensen/2026kaisei.pdf", None, PDL),
    ("総務省「個人住民税の基礎控除等について」(令和8年5月29日)", "https://www.soumu.go.jp/main_content/001075462.pdf", None, PDL),
    ("総務省「森林環境税及び森林環境譲与税」", "https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/150790_18.html",
     None, PDL),
    ("地方税法(e-Gov法令検索)", "https://laws.e-gov.go.jp/law/325AC0000000226", None, LAW),
    ("地方税法施行令 第47条の3(均等割の非課税の基準、e-Gov法令検索)", "https://laws.e-gov.go.jp/law/325CO0000000245", None, LAW),
]


def _source_li(name, url, link, note):
    n = html.escape(name)
    if url is None:
        s = n
    elif link:
        s = f'{n}(<a href="{html.escape(url)}">{html.escape(link)}</a>)'
    else:
        s = f'<a href="{html.escape(url)}">{n}</a>'
    return f"<li>{s}{'。' + html.escape(note) if note else ''}</li>"


def _quick_rows(rates):
    rows = []
    for man in (150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 900, 1000, 1200, 1500, 2000):
        a = calc({"mode": "annual", "annual": man * 10000, "age": 30, "pref": "東京都"}, rates)
        b = calc({"mode": "annual", "annual": man * 10000, "age": 45, "pref": "東京都"}, rates)
        rows.append(f"<tr><td>{man:,}万円</td><td>{a['si']:,}</td><td>{a['it']:,}</td><td>{a['jt']:,}</td>"
                    f"<td><b>{a['net']:,}</b></td><td>{a['net'] / a['gross'] * 100:.1f}%</td><td>{a['net'] // 12:,}</td>"
                    f"<td>{b['net']:,}</td></tr>")
    return "".join(rows)


def _pref_section(data):
    cur, prev = data["rates"][FY], data["rates"].get(FY - 1, {})
    m400 = 4_000_000 // 12
    _, sk, _ = std_monthly(m400)
    def prem(rk, care):
        return 12 * _r50(sk * (rk + (KAIGO if care else 0) + SHIEN), 20000)
    order = sorted(PREFS, key=lambda p: (-cur[p], PREFS.index(p)))
    trs = []
    for p in order:
        rank = 1 + sum(1 for q in PREFS if cur[q] > cur[p])     # 同じ料率は同じ順位
        d = cur[p] - prev[p] if p in prev else None
        dtxt = "-" if d is None else ("据え置き" if d == 0 else f"{d / 100:+.2f}")
        trs.append(f"<tr><td>{rank}</td><td>{p}</td><td>{_pct(cur[p])}</td><td>{_pct(prev[p]) if p in prev else '-'}</td>"
                   f"<td>{dtxt}</td><td>{prem(cur[p], False):,}</td><td>{prem(cur[p], True):,}</td></tr>")
    hi, lo = order[0], order[-1]
    gap = prem(cur[hi], False) - prem(cur[lo], False)
    summary = ""
    if prev:
        down = [p for p in PREFS if p in prev and cur[p] < prev[p]]
        same = [p for p in PREFS if p in prev and cur[p] == prev[p]]
        up = [p for p in PREFS if p in prev and cur[p] > prev[p]]
        def grp(names):
            unit = "県" if all(n.endswith("県") for n in names) else "都道府県"
            return f"{len(names)}{unit}" + (f"({'・'.join(names)})" if len(names) <= 10 else "")
        parts = [f"{w}が{grp(x)}" for w, x in (("引下げ", down), ("据え置き", same), ("引上げ", up)) if x]
        summary = (f"令和7年度と比べると、{'、'.join(parts)}です。"
                   f"介護保険料率(全国一律)は {KAIGO_PREV / 100:.2f}% から {KAIGO / 100:.2f}% に上がりました。")
    body = (f"<p>協会けんぽの健康保険料率は都道府県(勤務先の事業所の所在地)ごとに違います。令和8年度(2026年3月分から)は"
            f"{hi}の {_pct(cur[hi])} が最も高く、{lo}の {_pct(cur[lo])} が最も低くなっています。年収400万円(月33.3万円・賞与なし)の"
            f"40歳未満の人なら、健康保険料と子ども・子育て支援金の本人負担は{hi}が年 {prem(cur[hi], False):,}円、{lo}が年 "
            f"{prem(cur[lo], False):,}円で、差は年 {gap:,}円です。{summary}</p>"
            '<div class="wrap"><table><thead><tr><th>順位</th><th>都道府県</th><th>令和8年度</th><th>令和7年度</th><th>変化(ポイント)</th>'
            "<th>本人負担 年額(40歳未満)</th><th>本人負担 年額(40〜64歳)</th></tr></thead>"
            f"<tbody>{''.join(trs)}</tbody></table></div>"
            f'<p class="mut">本人負担 年額は、年収400万円・賞与なし(標準報酬月額 {sk:,}円)のときの 健康保険料+子ども・子育て支援金'
            f"(40〜64歳は介護保険料 {KAIGO / 100:.2f}% も含む)の12か月分です。子ども・子育て支援金は2026年4月分からなので、"
            "令和7年度の欄の料率には含まれていません。</p>")
    return body


def _annotate(msg):
    """GitHub Actions の注釈(::warning::)。% と改行はワークフローコマンドの書式に合わせてエスケープする。"""
    print("::warning::tedori: " + msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))


def pages(data, today=None):
    today = today or dt.datetime.now(JST).date()
    rates = data["rates"][FY]
    tokyo = calc({"mode": "annual", "annual": 4_000_000, "age": 30, "pref": "東京都"}, rates)
    steps = _steps(rates)
    warn = []
    if data.get("latest_fy") and data["latest_fy"] > FY:
        warn.append(f"協会けんぽは令和{data['latest_fy'] - 2018}年度の保険料率を公表していますが、このページの計算はまだ令和8年度の料率です。")
    if today > RULES_UNTIL:
        warn.append("このページの計算は2026年(令和8年度・令和8年分)の制度にもとづきます。2027年3月分以降の保険料率や翌年の税制改正は反映していません。")
    warn_html = "".join(f'<div class="card"><b>ご注意</b>: {html.escape(w)}</div>' for w in warn)
    # 運営者向け: GitHub Actions の実行結果に注釈として出る(ページの注意と同じ内容、期限の30日前からは予告)
    for w in warn:
        _annotate(f"{w} tedori.py の FY・RATE_URL・料率と税制の定数を更新してください。")
    if not warn and today >= HEADS_UP:
        _annotate(f"{RULES_UNTIL + dt.timedelta(days=1):%Y-%m-%d} から手取り計算のページに「2026年の制度のまま」の注意が出ます。"
                  "令和9年度の協会けんぽの料率・介護保険料率・子ども・子育て支援金率・雇用保険料率などが公表されたら、"
                  "tedori.py の FY・RATE_URL・定数を更新してください。")
    opts = "".join(f'<option{" selected" if p == "東京都" else ""}>{p}</option>' for p in PREFS)
    dep_inputs = "".join(f'<label for="td_{k}">{DEP_LABEL[k]}の人数</label><input id="td_{k}" type="number" min="0" max="9" value="0">'
                         for k in DEP)
    src = "".join(_source_li(*s) for s in SOURCES)
    body = (warn_html +
            f"<p>会社員(協会けんぽに加入している人)の年収から、社会保険料と税金を引いた手取りを計算します。2026年(令和8年)の制度にあわせて、"
            f"協会けんぽの都道府県別の健康保険料率(令和8年度)、2026年4月分から始まった子ども・子育て支援金、令和8年分の所得税の基礎控除の引上げ"
            f"(最大104万円)、給与所得控除の最低保障額の引上げ(74万円)を反映しています。たとえば東京都・30歳・扶養なし・年収400万円なら、"
            f"手取りは約{(tokyo['net'] + 5000) // 10000:,}万円です(試算。社会保険料 {tokyo['si']:,}円、所得税 {tokyo['it']:,}円、住民税 {tokyo['jt']:,}円)。"
            "計算はすべてこのブラウザの中で行い、入力した金額はどこにも送信しません。</p>"
            "<h2>手取りの計算機</h2>"
            '<label for="td_mode">入力のしかた</label><select id="td_mode"><option value="annual">年収(額面)で入力する</option>'
            '<option value="monthly">月給と賞与で入力する</option></select>'
            '<div id="td_a"><label for="td_annual">年収(額面・円)</label><input id="td_annual" type="number" min="0" step="10000" value="4000000">'
            '<p class="mut">賞与なし・毎月同じ額(年収÷12、1円未満切捨て)として計算します。</p></div>'
            '<div id="td_m" hidden><label for="td_monthly">月給(額面・円。残業代や通勤手当などの手当を含む)</label>'
            '<input id="td_monthly" type="number" min="0" step="1000" value="300000">'
            '<label for="td_bonus">賞与1回あたり(額面・円)</label><input id="td_bonus" type="number" min="0" step="10000" value="600000">'
            '<label for="td_bn">賞与の回数(年)</label><select id="td_bn"><option>0</option><option>1</option><option selected>2</option>'
            "<option>3</option><option>4</option></select></div>"
            '<label for="td_age">年齢(2026年12月31日時点、18〜74歳)</label><input id="td_age" type="number" min="18" max="74" value="30">'
            f'<label for="td_pref">勤務先(事業所)の都道府県</label><select id="td_pref">{opts}</select>'
            '<details><summary>配偶者・扶養している家族を入れる(任意)</summary>'
            '<p class="mut">配偶者・家族の年齢は、いずれも2026年12月31日時点の年齢です(税金の控除はこの日の年齢で決まります)。</p>'
            '<label for="td_sp">配偶者(年収が給与だけで136万円以下=合計所得62万円以下の場合)</label><select id="td_sp">'
            '<option value="0">いない・または配偶者の年収が136万円を超える</option><option value="1">いる(70歳未満)</option>'
            f'<option value="2">いる(70歳以上)</option></select>{dep_inputs}'
            '<p class="mut">家族はいずれも所得が62万円以下(給与だけなら年収136万円以下)で、障害者控除などの対象でないものとして計算します。'
            "配偶者の年収が136万円を超える場合の配偶者特別控除、19〜22歳の家族の年収が136万円を超える場合の特定親族特別控除は含みません。</p>"
            "</details>"
            '<div class="out"><p id="td_sum" role="status" aria-live="polite"></p><div id="td_res"></div></div>'
            "<h2>計算の前提</h2><ul>"
            "<li>勤務先で健康保険(協会けんぽ)と厚生年金に加入し、雇用保険は一般の事業の料率が適用される会社員として計算します。"
            "パート・アルバイトの人は、週の所定労働時間が20時間以上などの要件を満たして勤務先の健康保険・厚生年金に加入している場合に"
            "あてはまります(加入していない人は、国民健康保険・国民年金や家族の扶養になるため、この計算とは違います)。</li>"
            f"<li>社会保険料は令和8年度の料率(健康保険・介護保険は2026年3月分から、子ども・子育て支援金 {SHIEN / 100:.2f}% は4月分から、"
            f"雇用保険 {KOYO / 100:.1f}%(一般の事業)は4月から)が1年間続くものとして12か月分を計算します。"
            "2026年の1〜12月に実際に引かれる額とは、料率が変わる前の月の分だけ違います。</li>"
            "<li>健康保険・厚生年金は、月給を標準報酬月額の等級(健康保険1〜50級、厚生年金1〜32級)にあてはめ、本人負担(半分)を"
            "50銭以下切捨て・50銭超切上げで計算します。健康保険料と子ども・子育て支援金は、厚生労働省・こども家庭庁"
            "「子ども・子育て支援金に関するQ&A」(2026年2月12日)にそって、合計した率で計算してから端数処理します"
            "(40〜64歳は介護保険料率も合計しています)。このQ&Aの原文は掲載が終了しているため、同じ文を引用した記事で内容を確認しました。"
            "表の支援金の行は支援金率だけで計算した額、健康保険料の行はその残りです。保険料ごとに端数処理する勤務先では、"
            "月1円程度違うことがあります。賞与は1,000円未満を切り捨てた標準賞与額に掛けます"
            "(上限: 健康保険は年度の累計573万円、厚生年金は1回150万円)。雇用保険料は賞与を含む賃金の額に料率を掛け、"
            "本人負担の50銭以下を切り捨て、50銭1厘以上を切り上げます。</li>"
            "<li>介護保険料は40〜64歳の人だけにかかります(65歳以上は市区町村に別に納めます)。70歳以上は厚生年金保険料がかかりません。"
            "年齢は2026年12月31日時点の年齢を12か月とも同じように使います。実際には、介護保険料は40歳になる月から65歳になる月の前月まで、"
            "厚生年金保険料は70歳になる月の前月までかかる(月は誕生日の前日で決まります)ため、2026年中に40歳・65歳・70歳になる人は"
            "実際の保険料と違います。</li>"
            "<li>所得税は令和8年分の1年分の税額です。年収2,000万円以下の人は年末調整で、2,000万円を超える人(年末調整の対象外)は"
            "確定申告で精算します。改正後の基礎控除などは2026年12月の年末調整から適用され、11月までの毎月の源泉徴収は改正前の税額表の"
            "ままなので、毎月引かれる額の合計とは一致せず、年末調整(または確定申告)で精算されます。</li>"
            "<li>住民税は前年の所得にもとづいて、翌年6月から1年間(12回)給与から引かれます。この計算の住民税は、2026年の所得にかかる"
            "令和9年度分(2027年6月〜2028年5月)です。2026年6月〜2027年5月に引かれている住民税は2025年の所得にもとづく令和8年度分で、"
            "給与所得控除の最低保障額が65万円(令和9年度分は74万円)など一部のルールが違います。</li>"
            "<li>住民税は標準税率(市区町村民税6%・道府県民税4%、均等割 3,000円+1,000円)と森林環境税1,000円で計算しています。"
            "均等割の非課税の基準は1級地(東京23区など)の金額です。指定都市(税率の配分が8%・2%)や、県・市町村の独自の上乗せ"
            "(超過課税)、2級地・3級地の非課税基準は反映していません。</li>"
            "<li>生命保険料控除・iDeCo・ふるさと納税・医療費控除・住宅ローン控除、ひとり親控除・寡婦控除・障害者控除・勤労学生控除などは"
            "含みません。額面はすべて課税される給与として扱います(非課税の通勤手当は分けていません)。</li>"
            "<li>住民税の欄には森林環境税(国税、年1,000円)を含めています。</li></ul>"
            "<h2>2026年(令和8年)の主な変更点</h2><ul>"
            "<li>所得税の基礎控除: 合計所得金額489万円以下は104万円(改正前は95万〜68万円)、489万円超655万円以下は67万円(同63万円)、"
            "655万円超2,350万円以下は62万円(同58万円)。</li>"
            "<li>給与所得控除の最低保障額: 65万円 → 74万円(令和8・9年分。住民税は令和9・10年度分)。年収220万円未満の人の控除額が増えます(最大9万円)。</li>"
            "<li>扶養親族などの所得の要件: 58万円以下 → 62万円以下(給与だけなら年収123万円以下 → 136万円以下)。</li>"
            f"<li>子ども・子育て支援金の開始: 2026年4月分(5月の給与)から、健康保険料とあわせて標準報酬の {SHIEN / 100:.2f}%(本人負担はその半分)。</li>"
            f"<li>雇用保険料(一般の事業・本人負担): {KOYO_PREV / 10:.1f}/1000 → {KOYO / 10:.0f}/1000(2026年4月から)。</li>"
            f"<li>協会けんぽの介護保険料率: {KAIGO_PREV / 100:.2f}% → {KAIGO / 100:.2f}%(2026年3月分から)。都道府県別の健康保険料率は下の表のとおりです。</li>"
            "<li>パート・アルバイトの社会保険の加入要件: 所定内賃金が月額8.8万円以上という賃金の要件(いわゆる「106万円の壁」)が"
            "2026年10月1日に撤廃されました。週の所定労働時間が20時間以上・従業員51人以上の企業に勤務・学生でない などの要件を満たせば、"
            "月給が8.8万円未満でも原則として勤務先の健康保険・厚生年金に加入します(日本年金機構)。</li></ul>"
            + "<p>所得税の基礎控除は合計所得金額で段階的に決まるため、給与だけの人(所得金額調整控除なし)は次の年収を1円でも超えると"
            "所得税が増え、手取りがほぼ同じ額だけ減ります(東京都・30歳・扶養なしの試算)。" +
            "".join(f"年収{_man(s)}を超えると基礎控除が{k1 // 10000}万円から{k2 // 10000}万円になり、所得税が{d:,}円増えます。"
                    for s, _, k1, k2, d, _n in steps) +
            "住民税の基礎控除(43万円)は変わらないので、住民税にこの段差はありません。また社会保険料も、標準報酬月額の等級が"
            "1つ上がるごとに段階的に増えます。</p>"
            "<h2>年収別の手取り早見表(試算・東京都・扶養なし・賞与なし)</h2>"
            '<div class="wrap"><table><thead><tr><th>年収</th><th>社会保険料</th><th>所得税</th><th>住民税</th><th>手取り</th><th>手取り率</th>'
            "<th>手取り(月平均)</th><th>手取り(40〜64歳)</th></tr></thead>"
            f"<tbody>{_quick_rows(rates)}</tbody></table></div>"
            '<p class="mut">単位は円。40歳未満(30歳)で計算し、最後の列だけ40〜64歳(介護保険料あり)の手取りです。'
            "上の計算機と同じルールで計算しています(手取り(月平均)は年額を12で割り、1円未満を切り捨て)。"
            "年収2,000万円を超える人は確定申告が必要です。</p>"
            "<h2>都道府県別の健康保険料率(協会けんぽ・令和8年度)</h2>" + _pref_section(data) +
            "<h2>出典</h2><ul>" + src + "</ul>"
            f'<p class="mut">料率・税率などの数値は各機関の公表資料によるもので、{VERIFIED}に確認しました'
            "(協会けんぽの都道府県単位保険料率の表は毎日の更新時に取得し、取得できないときは前回取得した表を使います)。"
            f'公共データ利用規約(第1.0版)の内容は<a href="{PDL_URL}">デジタル庁のページ</a>で確認できます。'
            "手取りの額・早見表・順位などは当サイトがそれらをもとに計算した試算で、各機関が作成・公表したものではありません。"
            "実際の金額は給与明細・源泉徴収票・住民税の決定通知書で確認してください。</p>")
    title = "年収から手取りを計算(2026年・会社員・協会けんぽの都道府県別)"
    desc = ("会社員(協会けんぽ)の手取りを、令和8年度の都道府県別の健康保険料率・介護保険料率・子ども・子育て支援金・厚生年金・雇用保険と、"
            "令和8年分の所得税(基礎控除最大104万円)・住民税で計算。年収別の早見表と都道府県別の保険料の差つき。")
    return {"tedori/index.html": (title, desc, body, js_code(rates))}
