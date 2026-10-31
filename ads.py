"""広告枠: ads.json の設定に従い、ページの種類ごとに提携済みの広告を出し分ける。

- A8のテキスト広告コードをそのまま html に入れる。rel="sponsored nofollow" を自動で付与(Googleの指針)。
- 必ず「PR」と表示する(ステマ規制)。リスクの高い商品は risk の注意書きを必ず併記する。
- html が空の広告は表示しない(コード未設定のまま公開しても壊れない)。
"""
from __future__ import annotations

import json
import pathlib
import re

CONF = pathlib.Path(__file__).with_name("ads.json")


def _load():
    if not CONF.exists():
        return {"slots": {}, "ads": {}}
    return json.loads(CONF.read_text(encoding="utf-8"))


def _sponsored(code: str) -> str:
    def fix(m):
        tag = m.group(0)
        if "rel=" in tag:
            return re.sub(r'rel="[^"]*"', 'rel="sponsored nofollow"', tag)
        return tag[:-1] + ' rel="sponsored nofollow">'
    return re.sub(r"<a\s[^>]*>", fix, code)


def slot_for(slug: str) -> str:
    if slug.startswith("fx/"):
        return "fx"
    if slug in ("about.html",):
        return "none"
    return "default"


def render(slug: str) -> str:
    conf = _load()
    ids = conf.get("slots", {}).get(slot_for(slug), [])
    blocks = []
    for i in ids:
        ad = conf.get("ads", {}).get(i, {})
        code = (ad.get("html") or "").strip()
        if not code:
            continue
        lead = ad.get("lead", "")
        risk = ad.get("risk", "")
        blocks.append('<div class="card">'
                      + (f"<p>{lead}</p>" if lead else "") + _sponsored(code)
                      + (f'<p class="mut">{risk}</p>' if risk else "") + "</div>")
    if not blocks:
        return ""
    return ('<h2>PR</h2><p class="mut">以下は広告です。リンク先で申し込みや購入があると、当サイトが報酬を受け取ることがあります。'
            "掲載は商品の推奨ではありません。</p>" + "".join(blocks))
