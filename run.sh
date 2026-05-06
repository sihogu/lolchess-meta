#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=== [1/2] 크롤링 시작 ==="
uv run --with requests python3 scraper.py

echo ""
echo "=== [2/2] 사이트 빌드 시작 ==="
uv run --with playwright --with requests python3 build_site.py

echo ""
echo "=== 완료: index.html 생성됨 ==="
