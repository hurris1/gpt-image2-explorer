#!/bin/bash
# Start the GPT Image Prompts Gallery
cd "$(dirname "$0")"

echo "  GPT Image Prompts Gallery"
echo "  Starting server..."

if [ ! -f "data/prompts.json" ]; then
  echo "  No data found. Running initial data fetch..."
  python3 scripts/fetch_data.py --full
  echo ""
fi

python3 server.py
