"""
Scrape all deck data from lolchess.gg/meta and /meta?pbe=true.
Data is extracted from NEXT_DATA JSON (no browser needed for most data).
"""
import requests, json, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9"
}

os.makedirs("data", exist_ok=True)


def scrape_meta(pbe=False):
    label = "PBE" if pbe else "메타"
    meta_url = "https://lolchess.gg/meta" + ("?pbe=true" if pbe else "")
    output_file = "data/decks_pbe.json" if pbe else "data/decks.json"

    print(f"\n{'='*50}")
    print(f"Fetching {label} meta page: {meta_url}")
    r = requests.get(meta_url, headers=headers, timeout=30)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
    meta_next = json.loads(match.group(1))
    queries = meta_next['props']['pageProps']['dehydratedState']['queries']

    champ_refs = {c['key']: c for c in queries[0]['state']['data']['champions']}
    trait_refs = {t['key']: t for t in queries[1]['state']['data']['traits']}
    item_refs_list = queries[2]['state']['data']['items']
    item_refs = {i['key']: i for i in item_refs_list}

    guide_data = queries[3]['state']['data']
    all_guide_decks = guide_data['guideDecks']
    print(f"Found {len(all_guide_decks)} guide decks")

    # Fetch augment refs from first guide page
    print("Fetching augment refs from guide page...")
    guide_url_0 = f"https://lolchess.gg/builder/guide/{all_guide_decks[0]['teamBuilderKey']}?type=guide"
    r2 = requests.get(guide_url_0, headers=headers, timeout=30)
    match2 = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r2.text, re.DOTALL)
    guide_next = json.loads(match2.group(1))
    guide_queries = guide_next['props']['pageProps']['dehydratedState']['queries']
    refs = guide_queries[1]['state']['data']['refs']
    aug_refs = {a['key']: a for a in refs['augments']}
    print(f"Loaded {len(aug_refs)} augment refs")

    # PBE includes all decks; regular skips first (유물별 챔피언 요약)
    start_idx = 0 if pbe else 1
    decks = []
    for deck in all_guide_decks[start_idx:]:
        key = deck['teamBuilderKey']
        name = deck['name']
        cost = deck.get('cost', 0)
        tag = deck.get('tag', '')
        slots = deck['data']['slots']
        augments_keys = deck['data'].get('augments', [])

        guide_url = f"https://lolchess.gg/builder/guide/{key}?type=guide"

        board = {}
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

        augments = []
        for aug_key in augments_keys:
            aug = aug_refs.get(aug_key, {})
            augments.append({
                'key': aug_key,
                'name': aug.get('name', aug_key),
                'imageUrl': aug.get('imageUrl', '')
            })

        component_counts = {}
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
            'board': board,
            'augments': augments,
            'items': all_items,
            'champions': champions_E,
        })

    print(f"Processed {len(decks)} decks")

    # Fetch LV.5 champion data (parallel)
    print("Fetching LV.5 champion data from guide pages...")

    def fetch_lv5_champs(deck, champ_refs, headers):
        try:
            r = requests.get(deck['guide_url'], headers=headers, timeout=30)
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
            if not match:
                return deck['key'], []
            data = json.loads(match.group(1))
            queries = data['props']['pageProps']['dehydratedState']['queries']
            lv5 = queries[0]['state']['data'].get('lv5TeamBuilder', {})
            champs = []
            for slot in lv5.get('slots', []):
                champ_key = slot.get('champion')
                if champ_key:
                    champ = champ_refs.get(champ_key, {})
                    champs.append({
                        'key': champ_key,
                        'name': champ.get('name', champ_key),
                        'imageUrl': champ.get('imageUrl', '')
                    })
            return deck['key'], champs
        except Exception as e:
            print(f"  ERROR {deck['key']}: {e}")
            return deck['key'], []

    lv5_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_lv5_champs, d, champ_refs, headers): d['key'] for d in decks}
        done = 0
        for future in as_completed(futures):
            key, champs = future.result()
            lv5_map[key] = champs
            done += 1
            print(f"  [{done}/{len(decks)}] {key}: {len(champs)} champs")

    for deck in decks:
        deck['lv5_champions'] = lv5_map.get(deck['key'], [])

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(decks, f, ensure_ascii=False, indent=2)
    print(f"Saved to {output_file}")

    return decks


decks_regular = scrape_meta(pbe=False)
decks_pbe = scrape_meta(pbe=True)

print(f"\n=== Sample 메타 deck: {decks_regular[0]['name']} ===")
print(f"Guide URL: {decks_regular[0]['guide_url']}")
print(f"\n=== Sample PBE deck: {decks_pbe[0]['name']} ===")
print(f"Guide URL: {decks_pbe[0]['guide_url']}")
