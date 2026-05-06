"""
Scrape all deck data from lolchess.gg/meta and guide pages.
Data is extracted from NEXT_DATA JSON (no browser needed for most data).
Board screenshots are taken with playwright for deck A elements.
"""
import requests, json, re, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9"
}

os.makedirs("data", exist_ok=True)

# ============================================================
# 1. Fetch meta page data
# ============================================================
print("Fetching meta page...")
r = requests.get("https://lolchess.gg/meta", headers=headers, timeout=30)
match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
meta_next = json.loads(match.group(1))
queries = meta_next['props']['pageProps']['dehydratedState']['queries']

# Build refs maps
champ_refs = {c['key']: c for c in queries[0]['state']['data']['champions']}
trait_refs = {t['key']: t for t in queries[1]['state']['data']['traits']}
item_refs_list = queries[2]['state']['data']['items']
item_refs = {i['key']: i for i in item_refs_list}

# Get guide decks (all 45)
guide_data = queries[3]['state']['data']
all_guide_decks = guide_data['guideDecks']
print(f"Found {len(all_guide_decks)} guide decks")

# ============================================================
# 2. Fetch augment refs from a single guide page
# ============================================================
print("Fetching augment refs from guide page...")
guide_url_0 = f"https://lolchess.gg/builder/guide/{all_guide_decks[0]['teamBuilderKey']}?type=guide"
r2 = requests.get(guide_url_0, headers=headers, timeout=30)
match2 = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r2.text, re.DOTALL)
guide_next = json.loads(match2.group(1))
guide_queries = guide_next['props']['pageProps']['dehydratedState']['queries']
refs = guide_queries[1]['state']['data']['refs']
aug_refs = {a['key']: a for a in refs['augments']}
print(f"Loaded {len(aug_refs)} augment refs")

# ============================================================
# 3. Process each deck (skip first one: 유물별 챔피언 요약)
# ============================================================
decks = []
for deck in all_guide_decks[1:]:  # skip first deck
    key = deck['teamBuilderKey']
    name = deck['name']
    cost = deck.get('cost', 0)
    tag = deck.get('tag', '')
    slots = deck['data']['slots']
    augments_keys = deck['data'].get('augments', [])

    guide_url = f"https://lolchess.gg/builder/guide/{key}?type=guide"

    # Process board slots
    board = {}  # index -> {champion_key, champion_name, champion_img, star, items}
    for slot in slots:
        idx = slot['index']
        champ_key = slot['champion']
        champ = champ_refs.get(champ_key, {})
        items_data = []
        for item_key in slot.get('items', []):
            item = item_refs.get(item_key, {})
            if item:
                items_data.append({
                    'key': item_key,
                    'name': item.get('name', item_key),
                    'imageUrl': item.get('imageUrl', '')
                })
        board[idx] = {
            'champion_key': champ_key,
            'champion_name': champ.get('name', champ_key),
            'champion_img': champ.get('imageUrl', ''),
            'star': slot.get('star', 1),
            'items': items_data
        }

    # Process augments
    augments = []
    for aug_key in augments_keys:
        aug = aug_refs.get(aug_key, {})
        augments.append({
            'key': aug_key,
            'name': aug.get('name', aug_key),
            'imageUrl': aug.get('imageUrl', '')
        })

    # Collect component (재료) items by decomposing each equipped item
    component_counts = {}  # key -> count
    for slot in slots:
        for item_key in slot.get('items', []):
            item = item_refs.get(item_key, {})
            if not item:
                continue
            comps = item.get('compositions', [])
            if comps:
                for c in comps:
                    component_counts[c] = component_counts.get(c, 0) + 1
            elif item.get('isFromItem'):
                component_counts[item_key] = component_counts.get(item_key, 0) + 1

    # Build sorted component item list (most frequent first)
    all_items = []
    for comp_key, cnt in sorted(component_counts.items(), key=lambda x: -x[1]):
        item = item_refs.get(comp_key, {})
        if item:
            all_items.append({
                'key': comp_key,
                'name': item.get('name', comp_key),
                'imageUrl': item.get('imageUrl', ''),
                'count': cnt
            })

    # Champions in order of their index, with equipped items
    sorted_slots = sorted(slots, key=lambda s: s['index'])
    champions_E = []
    for slot in sorted_slots:
        champ_key = slot['champion']
        champ = champ_refs.get(champ_key, {})
        slot_items = []
        for item_key in slot.get('items', []):
            item = item_refs.get(item_key, {})
            if item:
                slot_items.append({
                    'key': item_key,
                    'name': item.get('name', item_key),
                    'imageUrl': item.get('imageUrl', '')
                })
        champions_E.append({
            'key': champ_key,
            'name': champ.get('name', champ_key),
            'imageUrl': champ.get('imageUrl', ''),
            'star': slot.get('star', 1),
            'items': slot_items
        })

    decks.append({
        'key': key,
        'name': name,
        'cost': cost,
        'tag': tag,
        'guide_url': guide_url,
        'board': board,  # dict: slot_index -> champion data
        'augments': augments,  # list of 3 augments
        'items': all_items,  # all items (D)
        'champions': champions_E,  # champion list (E)
    })

print(f"Processed {len(decks)} decks")

# Save data
with open('data/decks.json', 'w', encoding='utf-8') as f:
    json.dump(decks, f, ensure_ascii=False, indent=2)
print("Saved to data/decks.json")

# Print sample
print(f"\n=== Sample deck: {decks[0]['name']} ===")
print(f"Guide URL: {decks[0]['guide_url']}")
print(f"Augments: {[(a['name'], a['imageUrl'][-40:]) for a in decks[0]['augments']]}")
print(f"Champions (E): {[(c['name'], c['star']) for c in decks[0]['champions']]}")
print(f"Component items: {[(i['name'], i['count']) for i in decks[0]['items']]}")
print(f"Board slots: {list(decks[0]['board'].keys())}")
