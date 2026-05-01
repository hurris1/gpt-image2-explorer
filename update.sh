#!/bin/bash
# Incremental update for GPT Image Prompts Gallery
cd "$(dirname "$0")"

echo "========================================="
echo "  GPT Image Prompts — Data Update"
echo "========================================="
echo ""

if [ ! -f "data/prompts.json" ]; then
  echo "No existing data. Run start.sh first to do a full fetch."
  exit 1
fi

OLD_COUNT=$(python3 -c "import json; d=json.load(open('data/prompts.json')); print(d.get('total', 0))")
echo "Current prompts: $OLD_COUNT"
echo "Checking for updates..."
echo ""

python3 scripts/fetch_data.py --update

NEW_COUNT=$(python3 -c "import json; d=json.load(open('data/prompts.json')); print(d.get('total', 0))")
ADDED=$((NEW_COUNT - OLD_COUNT))

echo ""
echo "========================================="
echo "  Update Complete"
echo "  Before: $OLD_COUNT prompts"
echo "  After:  $NEW_COUNT prompts"
if [ $ADDED -gt 0 ]; then
  echo "  New:    +$ADDED"
elif [ $ADDED -eq 0 ]; then
  echo "  No new prompts."
fi
echo "========================================="
echo ""
echo "Refresh your browser to see the updated data."
