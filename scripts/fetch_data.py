#!/usr/bin/env python3
"""Fetch and merge prompt data from source repositories."""

import gzip
import json
import os
import re
import sys
import time
import hashlib
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = BASE_DIR / "images"
SYNC_STATE_FILE = DATA_DIR / "sync_state.json"
OUTPUT_FILE = DATA_DIR / "prompts.json"

EVO_REPO = "https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts.git"
EVO_CACHE = CACHE_DIR / "evolinkai"
GPT2_JSON_URL = "https://raw.githubusercontent.com/gpt-image2/awesome-gptimage2-prompts/main/prompts.json"
GPT2_CACHE = CACHE_DIR / "gpt-image2-prompts.json"

CATEGORY_MAP = {
    "ecommerce": "ecommerce",
    "ad-creative": "ad-creative",
    "portrait": "portrait",
    "poster": "poster",
    "character": "character",
    "ui": "ui",
    "comparison": "comparison",
}

CATEGORY_LABELS = {
    "ecommerce": {"en": "E-commerce", "zh": "电商产品"},
    "ad-creative": {"en": "Ad Creative", "zh": "广告创意"},
    "portrait": {"en": "Portrait & Photography", "zh": "人像摄影"},
    "poster": {"en": "Poster & Design", "zh": "海报设计"},
    "character": {"en": "Character Design", "zh": "角色设计"},
    "ui": {"en": "UI & Social Media", "zh": "UI界面"},
    "comparison": {"en": "Comparison & Fun", "zh": "对比与趣味"},
}

GPT2_CATEGORY_TAGS = {
    "social-media": "ui",
    "product-marketing": "ad-creative",
    "profile-avatar": "portrait",
    "poster": "poster",
    "infographic": "comparison",
    "ecommerce": "ecommerce",
    "game-asset": "character",
    "comic": "character",
    "youtube-thumbnail": "ad-creative",
    "app-web-design": "ui",
    "typography": "poster",
    "photography": "portrait",
    "illustration": "character",
    "branding": "ad-creative",
    "character-design": "character",
    "ui-ux": "ui",
    "product-shot": "ecommerce",
}


def log(msg):
    print(f"  {msg}")


def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


# ---- EvoLinkAI source ----

def clone_or_pull_evo():
    if (EVO_CACHE / ".git").exists():
        log("Pulling latest EvoLinkAI...")
        stdout, stderr, rc = run("git pull --depth=1 origin main", cwd=EVO_CACHE)
        if rc != 0:
            log(f"git pull failed (will shallow clone fresh): {stderr}")
            run(f"rm -rf {EVO_CACHE}")
    if not (EVO_CACHE / ".git").exists():
        log("Shallow cloning EvoLinkAI repo...")
        stdout, stderr, rc = run(
            f"git clone --depth=1 {EVO_REPO} {EVO_CACHE}"
        )
        if rc != 0:
            log(f"Clone failed: {stderr}")
            return False
    return True


def get_evo_commit():
    stdout, _, _ = run("git rev-parse HEAD", cwd=EVO_CACHE)
    return stdout


def git_diff_files(old_commit):
    """Return list of changed files between old_commit and HEAD."""
    stdout, _, rc = run(
        f"git diff --name-only {old_commit} HEAD -- cases/ images/", cwd=EVO_CACHE
    )
    if rc != 0:
        return []
    return [f for f in stdout.split("\n") if f]


def parse_evo_case_md(filepath):
    """Parse a case markdown file and extract individual prompts."""
    try:
        text = Path(filepath).read_text(encoding="utf-8")
    except Exception:
        return []

    results = []
    # Each case starts with "### Case N: Title"
    case_blocks = re.split(r"\n(?=### Case \d+:)", text)

    for block in case_blocks:
        if not block.strip():
            continue

        # Extract case number and title
        header_match = re.match(r"### Case (\d+):\s*(.+)", block)
        if not header_match:
            continue
        case_num = header_match.group(1)
        title = header_match.group(2).strip()

        # Extract source link
        source_link = ""
        source_match = re.search(r'\[(@\w+)\]\((https://x\.com/\S+)\)', block)
        if source_match:
            author_name = source_match.group(1)
            source_link = source_match.group(2)
        else:
            author_name = ""

        # Extract image reference (markdown or HTML img tag)
        image_match = re.search(r'!\[.*?\]\((\./images/\S+)\)', block)
        if not image_match:
            image_match = re.search(r'src="(\./images/\S+)"', block)
        image_path = image_match.group(1) if image_match else ""

        # Extract prompt text (content after image, in code block or directly)
        prompt_text = ""
        # Try code block first
        code_match = re.search(r"```(?:json)?\s*\n(.*?)```", block, re.DOTALL)
        if code_match:
            prompt_text = code_match.group(1).strip()
        else:
            # Find "Prompt:" or "**Prompt:**" section
            prompt_section = re.search(
                r"\*\*Prompt:?\*\*\s*\n+(.*?)(?=\n\n---|\Z)", block, re.DOTALL
            )
            if prompt_section:
                prompt_text = prompt_section.group(1).strip()
            else:
                # Take everything after the image
                img_idx = block.find("output.jpg")
                if img_idx > 0:
                    after_img = block[img_idx:]
                    # Skip past markdown image syntax
                    next_newline = after_img.find("\n")
                    if next_newline > 0:
                        prompt_text = after_img[next_newline:].strip()
                        # Remove links
                        prompt_text = re.sub(r"\[.*?\]\(https?://\S+\)", "", prompt_text)
                        prompt_text = prompt_text.strip()

        if not prompt_text:
            continue

        # Detect language / check if contains Chinese
        has_chinese = bool(re.search(r"[一-鿿]", prompt_text))
        has_chinese_title = bool(re.search(r"[一-鿿]", title))

        # Determine format
        fmt = "json" if prompt_text.strip().startswith("{") else "text"

        # Determine category from filename
        filename = Path(filepath).stem
        category = CATEGORY_MAP.get(filename, "comparison")

        # Build local image path (relative to IMAGES_DIR)
        local_image = ""
        if image_path:
            local_image = image_path.replace("./", "").replace("images/", "", 1)

        # Clean title: remove markdown links, keep text
        clean_title = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', title)
        clean_title = re.sub(r'\s*\(by\s+@\w+\)', '', clean_title)
        clean_title = clean_title.strip()

        # Generate a short description from first line of prompt
        desc = prompt_text.split('\n')[0][:120].strip() if prompt_text else clean_title
        # Remove leading JSON-like markers
        if desc.startswith('{') or desc.startswith('"type"'):
            desc = clean_title

        results.append({
            "id": f"evo_{case_num}",
            "title": clean_title,
            "title_zh": "",
            "description": desc,
            "description_zh": "",
            "category": category,
            "tags": [category],
            "prompt_en": prompt_text if not has_chinese else "",
            "prompt_zh": prompt_text if has_chinese else "",
            "image": local_image,
            "image_url": "",
            "author": {"name": author_name, "link": source_link},
            "source": "evolinkai",
            "format": fmt,
            "source_link": source_link,
        })

    return results


def process_evo_cases(evo_dir, changed_files=None):
    """Process EvoLinkAI case files. Merges English + zh-CN for bilingual data."""
    cases_dir = evo_dir / "cases"
    if not cases_dir.exists():
        log(f"Cases dir not found: {cases_dir}")
        return []

    # Only process main language files
    primary_cats = list(CATEGORY_MAP.keys())

    # Parse English files first
    en_prompts = {}  # key: (category, case_num) -> prompt dict
    for cat in primary_cats:
        en_file = cases_dir / f"{cat}.md"
        if en_file.exists():
            prompts = parse_evo_case_md(en_file)
            for p in prompts:
                key = (p["category"], p["id"])
                p["prompt_zh"] = ""  # Clear - will fill from zh-CN
                en_prompts[key] = p

    # Parse Chinese files and merge
    for cat in primary_cats:
        zh_file = cases_dir / f"{cat}_zh-CN.md"
        if zh_file.exists():
            zh_prompts = parse_evo_case_md(zh_file)
            for p in zh_prompts:
                key = (p["category"], p["id"])
                if key in en_prompts:
                    # Merge: use Chinese text as prompt_zh
                    en_prompts[key]["prompt_zh"] = p["prompt_zh"] or p["prompt_en"]
                else:
                    # Chinese-only entry (unlikely but handle)
                    p["prompt_en"] = ""
                    en_prompts[key] = p

    all_prompts = list(en_prompts.values())
    log(f"  EvoLinkAI: {len(all_prompts)} merged prompts (en+zh)")
    return all_prompts


def copy_evo_images(prompts, evo_dir):
    """Copy referenced EvoLinkAI images to local images/ directory."""
    for p in prompts:
        img_rel = p.get("image", "")
        if not img_rel:
            continue
        # Source: in cloned repo, images are under evo_dir/images/
        src = evo_dir / "images" / img_rel
        # Dest: IMAGES_DIR (which is ./images/)
        dst = IMAGES_DIR / img_rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.write_bytes(src.read_bytes())


# ---- gpt-image2 source ----

def download_gpt2_json():
    """Download prompts.json from gpt-image2 repo."""
    log("Downloading gpt-image2 prompts.json...")
    try:
        req = urllib.request.Request(GPT2_JSON_URL)
        req.add_header("Accept-Encoding", "gzip")
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            # Handle gzip compression
            if raw[:2] == b'\x1f\x8b':
                data = gzip.decompress(raw)
            else:
                data = raw
            # Cache decompressed version
            GPT2_CACHE.write_bytes(data)
            log(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB ({len(json.loads(data).get('items', []))} items)")
            return json.loads(data)
    except Exception as e:
        log(f"Download failed: {e}")
        if GPT2_CACHE.exists():
            log("Using cached version.")
            return json.loads(GPT2_CACHE.read_text(encoding="utf-8"))
        return None


def get_remote_etag():
    """Get ETag for remote prompts.json."""
    try:
        req = urllib.request.Request(GPT2_JSON_URL, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.headers.get("ETag", "")
    except Exception:
        return ""


def infer_category(item):
    """Infer category from item title, description, and tags."""
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    text = title + " " + desc
    tags = [t.lower() for t in item.get("tags", [])]

    keywords = {
        "ecommerce": ["ecommerce", "e-commerce", "product", "shopping", "shop", "store", "retail"],
        "ad-creative": ["ad", "advertisement", "creative", "branding", "marketing", "campaign", "brand"],
        "portrait": ["portrait", "photography", "photo", "selfie", "headshot", "fashion"],
        "poster": ["poster", "design", "flyer", "banner", "layout"],
        "character": ["character", "anime", "manga", "cartoon", "game", "comic", "illustration"],
        "ui": ["ui", "ux", "interface", "app", "dashboard", "screen", "mockup", "website", "web"],
        "comparison": ["comparison", "fun", "infographic", "info", "chart", "diagram", "graph"],
    }

    # Check tags first
    for tag in tags:
        for cat, kws in keywords.items():
            if any(kw in tag for kw in kws):
                return cat

    # Check title/desc
    for cat, kws in keywords.items():
        if any(kw in text for kw in kws):
            return cat

    return "poster"


def format_prompt_content(content):
    """Format JSON prompt content for display."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return content

    if isinstance(content, dict):
        # Flatten JSON prompt into readable text
        parts = []
        for key, val in content.items():
            if isinstance(val, str):
                parts.append(f"{key}: {val}")
            elif isinstance(val, dict):
                parts.append(f"{key}:")
                for k2, v2 in val.items():
                    if isinstance(v2, str):
                        parts.append(f"  {k2}: {v2}")
                    elif isinstance(v2, list):
                        parts.append(f"  {k2}:")
                        for item in v2:
                            if isinstance(item, dict):
                                parts.append(f"    - {json.dumps(item, ensure_ascii=False)}")
                            else:
                                parts.append(f"    - {item}")
                    elif isinstance(v2, (int, float)):
                        parts.append(f"  {k2}: {v2}")
            elif isinstance(val, list):
                parts.append(f"{key}:")
                for item in val:
                    if isinstance(item, dict):
                        parts.append(f"  - {json.dumps(item, ensure_ascii=False)}")
                    else:
                        parts.append(f"  - {item}")
        return "\n".join(parts)

    return str(content)


def process_gpt2_items(data):
    """Process gpt-image2 items into unified format."""
    items = data.get("items", []) if isinstance(data, dict) else data
    results = []

    for item in items:
        item_id = item.get("id", "")
        title = item.get("title", "")
        description = item.get("description", "")

        # Content
        raw_content = item.get("content", "")
        prompt_en = format_prompt_content(raw_content)

        # Translated content (Chinese)
        raw_translated = item.get("translatedContent", "")
        prompt_zh = format_prompt_content(raw_translated) if raw_translated else ""

        # Media - get thumbnail
        media_urls = item.get("mediaThumbnails", item.get("media", []))
        image_url = media_urls[0] if media_urls else ""

        # Category
        category = infer_category(item)
        tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
        if not tags:
            tags = [category]

        # Author
        author_info = item.get("author", {})
        if isinstance(author_info, dict):
            author = {
                "name": author_info.get("name", ""),
                "link": author_info.get("link", ""),
            }
        else:
            author = {"name": "", "link": ""}

        # Source link
        source_link = item.get("sourceLink", "")
        published_at = item.get("sourcePublishedAt", "")

        # Generate local image filename
        local_image = ""
        if image_url:
            ext = ".jpg"
            if ".png" in image_url:
                ext = ".png"
            elif ".webp" in image_url:
                ext = ".webp"
            local_image = f"gpt2/{item_id}{ext}"

        results.append({
            "id": f"gpt2_{item_id}",
            "title": title,
            "title_zh": "",
            "description": description,
            "description_zh": "",
            "category": category,
            "tags": tags,
            "prompt_en": prompt_en,
            "prompt_zh": prompt_zh,
            "image": local_image,
            "image_url": image_url,
            "author": author,
            "source": "gpt-image2",
            "format": "json",
            "source_link": source_link,
            "published_at": published_at,
        })

    return results


def download_single_image(item):
    """Download a single image. Returns (success, item_id)."""
    image_url = item.get("image_url", "")
    local_path = IMAGES_DIR / item["image"]

    if not image_url or not item["image"]:
        return (False, item.get("id", "?"), "no url")
    if local_path.exists():
        return (True, item.get("id", "?"), "cached")

    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(image_url)
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            local_path.write_bytes(resp.read())
        return (True, item.get("id", "?"), "ok")
    except Exception:
        if local_path.exists():
            local_path.unlink()
        return (False, item.get("id", "?"), "failed")


def download_gpt2_images(items, limit=None):
    """Download thumbnail images for gpt-image2 items concurrently."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    to_download = []
    for item in items:
        if limit and len(to_download) >= limit:
            break
        image_url = item.get("image_url", "")
        local_path = IMAGES_DIR / item["image"]
        if image_url and item["image"] and not local_path.exists():
            to_download.append(item)

    total = len(to_download)
    if total == 0:
        log("  All images already cached.")
        return

    log(f"  Downloading {total} new images (concurrent x8)...")
    downloaded = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_single_image, item): item for item in to_download}
        for future in as_completed(futures):
            success, item_id, status = future.result()
            if success:
                downloaded += 1
            else:
                failed += 1
            if (downloaded + failed) % 100 == 0:
                log(f"  Progress: {downloaded}/{total} downloaded...")

    log(f"  Images: {downloaded} downloaded, {failed} failed, {len(items) - total} cached")


# ---- Merge & Save ----

def merge_prompts(evo_prompts, gpt2_prompts):
    """Merge prompts from both sources, deduplicating by title similarity."""
    all_prompts = evo_prompts + gpt2_prompts

    # Add category labels
    for p in all_prompts:
        cat = p.get("category", "comparison")
        labels = CATEGORY_LABELS.get(cat, {"en": cat, "zh": cat})
        p["category_en"] = labels["en"]
        p["category_zh"] = labels["zh"]

    return all_prompts


def save_prompts(prompts, filepath):
    """Save prompts to JSON file."""
    output = {
        "version": 1,
        "total": len(prompts),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "categories": [
            {"id": k, "en": v["en"], "zh": v["zh"]}
            for k, v in CATEGORY_LABELS.items()
        ],
        "items": prompts,
    }
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Saved {len(prompts)} prompts to {filepath}")


def save_sync_state(evo_commit, gpt2_etag, total):
    """Save sync state for future incremental updates."""
    state = {
        "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_prompts": total,
        "sources": {
            "evolinkai": {
                "last_commit": evo_commit,
                "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "gpt-image2": {
                "last_etag": gpt2_etag,
                "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        },
    }
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Sync state saved (commit={evo_commit[:8]}..., etag={gpt2_etag[:16]}...)")


def load_sync_state():
    """Load previous sync state."""
    if SYNC_STATE_FILE.exists():
        try:
            return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sources": {"evolinkai": {}, "gpt-image2": {}}}


# ---- Main ----

def cmd_full():
    """Full data fetch - clone repos, download everything."""
    log("=== Full data fetch ===")

    # EvoLinkAI
    log("Processing EvoLinkAI source...")
    if not clone_or_pull_evo():
        log("ERROR: Failed to get EvoLinkAI repo")
        return 1
    evo_commit = get_evo_commit()
    log(f"  Commit: {evo_commit[:12]}...")
    evo_prompts = process_evo_cases(EVO_CACHE)
    log(f"  Total EvoLinkAI prompts: {len(evo_prompts)}")
    copy_evo_images(evo_prompts, EVO_CACHE)

    # gpt-image2
    log("Processing gpt-image2 source...")
    gpt2_data = download_gpt2_json()
    if gpt2_data is None:
        log("ERROR: Failed to get gpt-image2 data")
        return 1
    gpt2_etag = get_remote_etag()
    gpt2_prompts = process_gpt2_items(gpt2_data)
    log(f"  Total gpt-image2 prompts: {len(gpt2_prompts)}")
    log(f"  Downloading images (this will take a while)...")
    download_gpt2_images(gpt2_prompts)

    # Merge & Save
    log("Merging and saving...")
    all_prompts = merge_prompts(evo_prompts, gpt2_prompts)
    save_prompts(all_prompts, OUTPUT_FILE)
    save_sync_state(evo_commit, gpt2_etag, len(all_prompts))

    log(f"=== Done! {len(all_prompts)} total prompts ===")
    return 0


def cmd_update():
    """Incremental update - only fetch what changed."""
    log("=== Incremental update ===")

    prev_state = load_sync_state()

    new_evo_prompts = []
    new_gpt2_prompts = []

    # EvoLinkAI update
    log("Checking EvoLinkAI for changes...")
    if not clone_or_pull_evo():
        log("WARNING: EvoLinkAI update failed, skipping.")
    else:
        new_commit = get_evo_commit()
        old_commit = prev_state["sources"].get("evolinkai", {}).get("last_commit", "")
        if new_commit != old_commit and old_commit:
            log(f"  New commits: {old_commit[:8]}... → {new_commit[:8]}...")
            changed = git_diff_files(old_commit)
            log(f"  Changed files: {len(changed)}")
            if changed:
                new_evo_prompts = process_evo_cases(EVO_CACHE, changed_files=changed)
                copy_evo_images(new_evo_prompts, EVO_CACHE)
                log(f"  New/updated EvoLinkAI prompts: {len(new_evo_prompts)}")
        elif new_commit != old_commit:
            log(f"  First sync at commit {new_commit[:8]}...")
        else:
            log("  No changes detected.")

    # gpt-image2 update
    log("Checking gpt-image2 for changes...")
    new_etag = get_remote_etag()
    old_etag = prev_state["sources"].get("gpt-image2", {}).get("last_etag", "")
    if new_etag != old_etag or not old_etag:
        log(f"  New data available (etag changed)")
        gpt2_data = download_gpt2_json()
        if gpt2_data:
            new_gpt2_prompts = process_gpt2_items(gpt2_data)
            # Find truly new items by comparing IDs
            existing_ids = set()
            if OUTPUT_FILE.exists():
                old_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
                existing_ids = {item["id"] for item in old_data.get("items", [])}
            truly_new = [p for p in new_gpt2_prompts if p["id"] not in existing_ids]
            log(f"  New prompts: {len(truly_new)} (total remote: {len(new_gpt2_prompts)})")
            if truly_new:
                log(f"  Downloading new images...")
                download_gpt2_images(truly_new)
            new_gpt2_prompts = truly_new  # Only add new ones
    else:
        log("  No changes detected.")

    # Merge with existing data
    existing_items = []
    if OUTPUT_FILE.exists():
        old_data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        existing_items = old_data.get("items", [])

    # Remove old evo items that were updated, add new ones
    if new_evo_prompts:
        new_evo_ids = {p["id"] for p in new_evo_prompts}
        existing_items = [p for p in existing_items if p["id"] not in new_evo_ids]
        existing_items.extend(new_evo_prompts)

    # Add new gpt2 items
    if new_gpt2_prompts:
        existing_items.extend(new_gpt2_prompts)

    all_prompts = existing_items
    # Ensure category labels and zh fields exist
    for p in all_prompts:
        if "category_en" not in p:
            cat = p.get("category", "comparison")
            labels = CATEGORY_LABELS.get(cat, {"en": cat, "zh": cat})
            p["category_en"] = labels["en"]
            p["category_zh"] = labels["zh"]
        if "title_zh" not in p:
            p["title_zh"] = ""
        if "description_zh" not in p:
            p["description_zh"] = ""

    save_prompts(all_prompts, OUTPUT_FILE)
    new_commit = get_evo_commit() if (EVO_CACHE / ".git").exists() else old_commit
    save_sync_state(new_commit, new_etag or old_etag, len(all_prompts))

    log(f"=== Done! {len(all_prompts)} total prompts ===")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch GPT Image prompt data")
    parser.add_argument(
        "--full", action="store_true", help="Full initial fetch"
    )
    parser.add_argument(
        "--update", action="store_true", help="Incremental update"
    )
    args = parser.parse_args()

    if args.full:
        sys.exit(cmd_full())
    elif args.update:
        sys.exit(cmd_update())
    else:
        parser.print_help()
        print("\nUsage:")
        print("  python3 scripts/fetch_data.py --full     # First time")
        print("  python3 scripts/fetch_data.py --update   # Daily maintenance")
        sys.exit(1)
