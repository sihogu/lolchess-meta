"""
Generate the lolchess meta viewer website from scraped deck data.
Layout per deck row: [board+name] | [augments] | [component items] | [champions]
"""
import json, os, base64
from playwright.sync_api import sync_playwright

os.makedirs("data", exist_ok=True)
os.makedirs("screenshots/boards", exist_ok=True)

# ============================================================
# Load data
# ============================================================
with open("data/decks.json", encoding="utf-8") as f:
    decks = json.load(f)
print(f"Loaded {len(decks)} decks")

# ============================================================
# Take board screenshots for each deck
# ============================================================
print("Taking board screenshots...")

def take_board_screenshots(decks):
    board_imgs = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, deck in enumerate(decks):
            key = deck['key']
            print(f"  [{i+1}/{len(decks)}] {deck['name']}")
            img_path = f"screenshots/boards/{key}.png"
            if os.path.exists(img_path):
                board_imgs[key] = img_path
                continue
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(deck['guide_url'], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(6000)
                # Click Lv.5 tab
                lv5 = page.locator(".TabNavItem", has_text="Lv. 5").first
                if lv5.count() > 0:
                    lv5.click()
                    page.wait_for_timeout(1500)
                board = page.locator(".Board").first
                if board.count() > 0:
                    board.screenshot(path=img_path)
                    board_imgs[key] = img_path
                else:
                    board_imgs[key] = None
                page.close()
            except Exception as e:
                print(f"    ERROR: {e}")
                board_imgs[key] = None
        browser.close()
    return board_imgs

board_imgs = take_board_screenshots(decks)

# ============================================================
# Build base64 image map for board screenshots
# ============================================================
board_b64 = {}
for key, path in board_imgs.items():
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            board_b64[key] = base64.b64encode(f.read()).decode()

# ============================================================
# Generate HTML
# ============================================================
print("Generating HTML...")

def star_html(star):
    if star == 3:
        return '<div class="stars s3">★★★</div>'
    elif star == 2:
        return '<div class="stars s2">★★</div>'
    return ''

def deck_row_html(deck, b64_img):
    key = deck['key']
    name = deck['name']
    guide_url = deck['guide_url']
    board_slots = deck['board']
    augments = deck['augments']
    items = deck['items']
    champions = deck['champions']
    tag = deck.get('tag', '')

    hot_badge = '<span class="hot-badge">HOT</span>' if tag == 'hot' else ''

    # Board column: deck name above, board image below
    if b64_img:
        board_content = f'<img src="data:image/png;base64,{b64_img}" class="board-img" alt="배치 보드">'
    else:
        rows = [[0,1,2,3,4,5,6],[7,8,9,10,11,12,13],[14,15,16,17,18,19,20],[21,22,23,24,25,26,27]]
        board_content = '<div class="mini-board">'
        for row_idx in range(3, -1, -1):
            off = "offset" if row_idx % 2 == 1 else ""
            board_content += f'<div class="board-row {off}">'
            for idx in rows[row_idx]:
                if idx in board_slots:
                    c = board_slots[idx]
                    board_content += f'<div class="hex occ" title="{c["champion_name"]}"><img src="{c["champion_img"]}" loading="lazy"></div>'
                else:
                    board_content += '<div class="hex emp"></div>'
            board_content += '</div>'
        board_content += '</div>'

    col_board = f'''<div class="col-board">
      <div class="deck-name-row">{hot_badge}<a href="{guide_url}" target="_blank" class="deck-name">{name}</a></div>
      {board_content}
    </div>'''

    # Augments column
    col_aug = '<div class="col-aug"><div class="aug-list">'
    for aug in augments:
        col_aug += f'''<div class="aug-row">
          <img src="{aug['imageUrl']}" alt="{aug['name']}" title="{aug['name']}" loading="lazy" class="aug-img">
          <span class="aug-name">{aug['name']}</span>
        </div>'''
    col_aug += '</div></div>'

    # Component items column
    col_items = '<div class="col-items"><div class="comp-list">'
    for item in items:
        cnt = item.get('count', 1)
        badge = f'<span class="item-cnt">x{cnt}</span>' if cnt > 1 else ''
        col_items += f'''<div class="comp-row">
          <div class="comp-icon-wrap">
            <img src="{item['imageUrl']}" alt="{item['name']}" title="{item['name']} x{cnt}" loading="lazy" class="comp-img">
            {badge}
          </div>
          <span class="comp-name">{item['name']}</span>
        </div>'''
    col_items += '</div></div>'

    # Champions column (portrait + star + equipped items)
    col_champs = '<div class="col-champs"><div class="champ-list">'
    for champ in champions:
        items_html = ''
        for it in champ.get('items', []):
            items_html += f'<img src="{it["imageUrl"]}" alt="{it["name"]}" title="{it["name"]}" class="champ-item-img" loading="lazy">'
        col_champs += f'''<div class="champ-card">
          <img src="{champ['imageUrl']}" alt="{champ['name']}" title="{champ['name']}" class="champ-img" loading="lazy">
          {star_html(champ['star'])}
          <div class="champ-items">{items_html}</div>
        </div>'''
    col_champs += '</div></div>'

    # data-champs: LV.5 champion names + full champion names (for search)
    all_champ_names = ' '.join(
        c['name'] for c in deck.get('lv5_champions', []) + champions
    )
    return f'<div class="deck-row" data-champs="{all_champ_names}">{col_board}{col_aug}{col_items}{col_champs}</div>\n'

rows_html = ""
for deck in decks:
    rows_html += deck_row_html(deck, board_b64.get(deck['key']))

# ============================================================
# Full HTML
# ============================================================
html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TFT 추천 메타 덱 | 시즌 17</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  background:#0b0b10;
  color:#ccc;
  font-family:'Malgun Gothic','Apple SD Gothic Neo',Arial,sans-serif;
  font-size:12px;
  min-width:1100px;
}}

/* ── Header ── */
header{{
  background:#111118;
  border-bottom:2px solid #c8924e;
  padding:14px 24px;
  display:flex;
  align-items:center;
  gap:14px;
  position:sticky;
  top:0;
  z-index:100;
}}
header h1{{font-size:18px;color:#c8924e;font-weight:700;letter-spacing:-0.3px}}
header .sub{{color:#666;font-size:12px}}
header .src-link{{margin-left:auto;color:#c8924e;font-size:12px;text-decoration:none}}
header .src-link:hover{{text-decoration:underline}}

/* ── Container ── */
.wrap{{max-width:1560px;margin:0 auto;padding:12px 16px}}

/* ── Deck row ── */
.deck-row{{
  display:grid;
  grid-template-columns:460px 220px 190px auto;
  gap:8px;
  align-items:center;
  background:#13131c;
  border:1px solid #222232;
  border-radius:8px;
  padding:8px 12px;
  margin-bottom:6px;
  transition:border-color 0.15s, background 0.15s;
}}
.deck-row:hover{{border-color:#c8924e55;background:#161620}}

/* ── Board column ── */
.col-board{{display:flex;flex-direction:column;align-items:center;gap:5px}}
.deck-name-row{{
  display:flex;
  align-items:center;
  gap:6px;
  width:100%;
  justify-content:center;
}}
.deck-name{{
  color:#e8c888;
  font-size:13px;
  font-weight:700;
  text-decoration:none;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
  max-width:420px;
}}
.deck-name:hover{{color:#c8924e;text-decoration:underline}}
.hot-badge{{
  background:#ff29fa22;
  color:#ff80ff;
  font-size:9px;
  font-weight:700;
  padding:1px 5px;
  border-radius:3px;
  border:1px solid #ff29fa55;
  letter-spacing:0.5px;
  flex-shrink:0;
}}
.board-img{{
  width:444px;
  height:auto;
  max-height:262px;
  border-radius:6px;
  object-fit:contain;
}}
.mini-board{{display:flex;flex-direction:column;gap:2px}}
.board-row{{display:flex;gap:2px}}
.board-row.offset{{padding-left:15px}}
.hex{{width:26px;height:26px;border-radius:50%;overflow:hidden;flex-shrink:0}}
.hex.emp{{background:#222230;border:1px solid #333345}}
.hex.occ{{border:1px solid #c8924e88}}
.hex img{{width:100%;height:100%;object-fit:cover}}

/* ── Augments column ── */
.col-aug{{padding:2px 0}}
.aug-list{{display:flex;flex-direction:column;gap:6px}}
.aug-row{{display:flex;align-items:center;gap:8px}}
.aug-img{{width:36px;height:36px;border-radius:5px;border:1px solid #3a3a52;flex-shrink:0;object-fit:cover}}
.aug-name{{color:#e2c070;font-size:11px;line-height:1.3;flex:1}}

/* ── Component items column ── */
.col-items{{padding:2px 0}}
.comp-list{{display:flex;flex-direction:column;gap:5px}}
.comp-row{{display:flex;align-items:center;gap:7px}}
.comp-icon-wrap{{position:relative;flex-shrink:0;width:32px;height:32px}}
.comp-img{{width:32px;height:32px;border-radius:4px;border:1px solid #3a3a52;object-fit:cover}}
.item-cnt{{
  position:absolute;
  bottom:-3px;right:-5px;
  background:#111118;
  color:#ffc844;
  font-size:9px;
  font-weight:700;
  line-height:1;
  padding:1px 3px;
  border-radius:3px;
  border:1px solid #333;
}}
.comp-name{{color:#aaa;font-size:11px;line-height:1.3}}

/* ── Champions column ── */
.col-champs{{padding:2px 0}}
.champ-list{{display:flex;flex-wrap:wrap;gap:6px;align-content:flex-start}}
.champ-card{{display:flex;flex-direction:column;align-items:center;gap:1px}}
.champ-img{{width:42px;height:42px;border-radius:4px;border:1px solid #3a3a52;object-fit:cover}}
.stars{{font-size:9px;line-height:1;letter-spacing:-1px}}
.stars.s3{{color:#ffd700}}
.stars.s2{{color:#b0b0b0}}
.champ-items{{display:flex;gap:1px;flex-wrap:wrap;justify-content:center;max-width:42px}}
.champ-item-img{{width:13px;height:13px;border-radius:2px;object-fit:cover;border:1px solid #2a2a3a}}

/* ── Search bar ── */
.search-wrap{{
  padding:10px 16px;
  max-width:1560px;
  margin:0 auto;
}}
.search-box{{
  width:100%;
  background:#1a1a26;
  border:1px solid #333348;
  border-radius:8px;
  padding:10px 16px 10px 40px;
  color:#ddd;
  font-size:14px;
  font-family:inherit;
  outline:none;
  transition:border-color 0.15s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%23666' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;
  background-position:14px center;
}}
.search-box:focus{{border-color:#c8924e}}
.search-box::placeholder{{color:#444}}
.search-count{{
  font-size:11px;
  color:#555;
  text-align:right;
  padding:2px 4px 6px;
}}

/* ── Footer ── */
footer{{
  text-align:center;
  color:#444;
  font-size:11px;
  padding:20px;
  border-top:1px solid #1a1a28;
  margin-top:16px;
}}
</style>
</head>
<body>
<header>
  <h1>TFT 추천 메타 덱</h1>
  <span class="sub">lolchess.gg 기반 · 시즌 17 · v17.2b</span>
  <a class="src-link" href="https://lolchess.gg/meta" target="_blank">원본 사이트 →</a>
</header>

<div class="search-wrap">
  <input type="text" class="search-box" id="champSearch" placeholder="챔피언 이름으로 검색... (예: 아칼리, 킨드레드)" autocomplete="off">
  <div class="search-count" id="searchCount"></div>
</div>

<div class="wrap" id="deckList">
  {rows_html}
</div>

<footer>
  데이터 출처: lolchess.gg &nbsp;|&nbsp; 이미지 © Riot Games
</footer>
<script>
(function() {{
  var input = document.getElementById('champSearch');
  var count = document.getElementById('searchCount');
  var rows = document.querySelectorAll('.deck-row');
  var total = rows.length;

  function filter() {{
    var terms = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var visible = 0;
    rows.forEach(function(row) {{
      var champs = (row.getAttribute('data-champs') || '').toLowerCase();
      var show = terms.length === 0 || terms.every(function(t) {{ return champs.indexOf(t) !== -1; }});
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    count.textContent = terms.length ? (visible + ' / ' + total + '개 덱') : '';
  }}

  input.addEventListener('input', filter);
}})();
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"index.html 생성 완료 ({len(html):,} bytes / {len(html)//1024//1024} MB)")
