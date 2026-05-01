#!/bin/bash
# Start the GPT Image Prompts Gallery
cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

echo "  GPT Image Prompts Gallery"
echo "  Starting server..."

if [ ! -f "data/prompts.json" ]; then
  echo "  No data found. Running initial data fetch..."
  python scripts/fetch_data.py --full
  echo ""
fi

python server.py
