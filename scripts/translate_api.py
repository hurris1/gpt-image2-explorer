#!/usr/bin/env python3
"""
批量翻译 prompts.json — DeepSeek V4 Flash

用法:
  python scripts/translate_api.py batch       # 批量翻译 prompt（5条/请求, 16线程）
  python scripts/translate_api.py retry       # 重试失败条目（单条/请求）
  python scripts/translate_api.py title       # 翻译 title_zh（单条, 轻量快速）

说明:
  batch  - 首次翻译或全量翻译。每 5 条合并为一个 API 请求，16 线程并行。
           适用于 prompt_en 有内容但 prompt_zh 为空或英文的条目。
  retry  - 重试 batch 模式翻译失败的条目。逐条请求，只覆盖含中文的结果。
           筛选条件: prompt_zh 为空或不含中文字符。
  title  - 专门翻译标题。逐条请求，轻量级（标题通常很短）。
           筛选条件: title_zh 为空或不含中文字符，且 title 字段非空。

环境变量（按优先级从高到低）:
  AUTH_TOKEN     DeepSeek API Key（推荐）
  MODEL          模型名称（默认 deepseek-v4-flash）
  BASE_URL       API 地址（默认 https://api.deepseek.com）

  也可以写在项目根目录 .env 文件中。

输出:
  data/prompts.json              翻译后的数据
  data/translation_progress.json 进度文件（支持断点续传）
  data/translation.log           运行日志
  data/translation_verbose.log   模型原始输出日志（含 CN_OK/CN_FAIL 标记）
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ---- 配置 ----
BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / '.env'
if env_path.exists():
    for line in env_path.read_text().split('\n'):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            if key not in os.environ:
                os.environ[key] = val

MODEL = os.environ.get('MODEL', 'deepseek-v4-flash')
BASE_URL = os.environ.get('BASE_URL', 'https://api.deepseek.com')
API_KEY = os.environ.get('AUTH_TOKEN', os.environ.get('DEEPSEEK_API_KEY', ''))

DATA_FILE = BASE_DIR / 'data' / 'prompts.json'
PROGRESS_FILE = BASE_DIR / 'data' / 'translation_progress.json'
LOG_FILE = BASE_DIR / 'data' / 'translation.log'
VERBOSE_LOG = BASE_DIR / 'data' / 'translation_verbose.log'

BATCH_SIZE = 5
MAX_WORKERS = 16
TARGET_TPS_RATIO = 0.6
CHECKPOINT_INTERVAL = 50
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
INITIAL_TPS_CAP = 800

# ---- 全局 ----
client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=REQUEST_TIMEOUT)

SYSTEM_PROMPT_BATCH = (
    "你是一个专业翻译，将英文 Prompt 翻译成中文。\n"
    "规则：\n"
    "1. 忠于原文，不做语序调整和总结\n"
    "2. 保留所有 {argument name=\"...\" default=\"...\"} 占位符\n"
    "3. 专业术语保持一致的翻译\n"
    "4. 只输出翻译结果，不要解释"
)

SYSTEM_PROMPT_SINGLE = (
    "你是一个专业翻译。请将以下英文翻译成中文。\n"
    "规则：\n"
    "1. 忠于原文意义，不增加不减少\n"
    "2. 原样保留所有 {argument name=\"...\" default=\"...\"} 占位符\n"
    "3. 对于 JSON 结构，保留所有 key 名不变，只翻译 value 中的文字内容\n"
    "4. 只输出翻译后的完整内容，不要加任何解释或标记\n"
    "5. 输出直接就是翻译结果，不要加 'Prompt:' 之类的前缀"
)

SYSTEM_PROMPT_TITLE = (
    "你是一个专业翻译。请将以下英文标题翻译成简洁的中文标题。\n"
    "规则：\n"
    "1. 简洁有力，保留原标题的核心信息\n"
    "2. 只输出翻译后的中文标题，不要加引号、前缀或解释\n"
    "3. 控制在 30 字以内"
)

tps_lock = Lock()
tps_samples = []
tokens_this_second = 0
second_start = time.time()
rate_limiter_lock = Lock()
verbose_lock = Lock()

# ---- 工具函数 ----
def log(msg):
    ts = time.strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def vlog(item_id, prompt_len, content_len, has_cn, raw_output):
    marker = "CN_OK" if has_cn else "CN_FAIL"
    with verbose_lock:
        with open(VERBOSE_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{'='*80}\n")
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] id={item_id} in={prompt_len} out={content_len} {marker}\n")
            f.write(f"{'-'*80}\n")
            f.write(raw_output[:2000])
            if len(raw_output) > 2000:
                f.write(f"\n... (截断, 共 {len(raw_output)} 字符)")
            f.write(f"\n{'='*80}\n\n")

def has_chinese(text):
    return bool(re.search(r'[一-鿿]', text))

def record_tps(tokens, elapsed):
    with tps_lock:
        tps_samples.append(tokens / elapsed if elapsed > 0 else 0)
        if len(tps_samples) > 120:
            tps_samples.pop(0)

def current_tps_cap():
    with tps_lock:
        if len(tps_samples) < 10:
            return INITIAL_TPS_CAP
        return max(sorted(tps_samples)[int(len(tps_samples) * 0.7)] * TARGET_TPS_RATIO, 200)

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    return {'translated_ids': [], 'total_tokens_used': 0, 'start_time': time.time()}

def save_progress(progress):
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False), encoding='utf-8')

# ---- 翻译函数 ----
def translate_single(item):
    """单条翻译 prompt"""
    prompt_en = item.get('prompt_en', '')
    for attempt in range(MAX_RETRIES):
        try:
            start = time.time()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_SINGLE},
                    {"role": "user", "content": prompt_en}
                ],
                temperature=0.1,
            )
            elapsed = time.time() - start
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            has_cn = has_chinese(content)
            vlog(item['id'], len(prompt_en), len(content), has_cn, content)

            content = re.sub(r'^Prompt:\s*', '', content.strip())
            desc = content[:100] if len(content) > 100 else content
            desc = desc + '...' if len(content) > 100 else desc

            record_tps(tokens, elapsed)
            return (item['id'], '', content, desc, tokens, elapsed, has_cn)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise

def translate_title(item):
    """单条翻译 title"""
    title_en = item.get('title', '')
    for attempt in range(MAX_RETRIES):
        try:
            start = time.time()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_TITLE},
                    {"role": "user", "content": title_en}
                ],
                temperature=0.1,
                max_tokens=100,
            )
            elapsed = time.time() - start
            content = response.choices[0].message.content.strip()
            tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            has_cn = has_chinese(content)
            vlog(f"{item['id']}_title", len(title_en), len(content), has_cn, content)

            record_tps(tokens, elapsed)
            return (item['id'], content, tokens, elapsed, has_cn)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    raise

def build_batch_prompt(items):
    parts = []
    for i, item in enumerate(items):
        parts.append(f"--- Item {i+1} ---\nTitle: {item.get('title', '')}\nPrompt: {item.get('prompt_en', '')}")
    user_text = "\n\n".join(parts)
    return (
        f"请翻译以下 {len(items)} 个条目。每个条目的输出格式严格按：\n"
        f"--- Item N ---\nTitle: 中文标题\nPrompt: 中文内容\n\n"
        f"{user_text}"
    )

def parse_batch_response(content, items):
    results = []
    blocks = re.split(r'--- Item \d+ ---', content)
    blocks = [b.strip() for b in blocks if b.strip()]
    for i, item in enumerate(items):
        title_zh = ''
        prompt_zh = ''
        if i < len(blocks):
            block = blocks[i]
            m = re.search(r'^Title:\s*(.+?)$', block, re.MULTILINE)
            if m:
                title_zh = m.group(1).strip()
                prompt_text = block[m.end():].strip()
                prompt_text = re.sub(r'^Prompt:\s*', '', prompt_text)
                prompt_zh = prompt_text
            else:
                lines = block.strip().split('\n', 1)
                if len(lines) >= 2:
                    title_zh = lines[0].replace('Title:', '').strip()
                    prompt_zh = lines[1].strip()
                else:
                    prompt_zh = block.strip()
        desc = prompt_zh[:100] if len(prompt_zh) > 100 else prompt_zh
        desc = desc + '...' if len(prompt_zh) > 100 else desc
        results.append({'id': item['id'], 'title_zh': title_zh, 'prompt_zh': prompt_zh, 'description_zh': desc})
    return results

def translate_batch(items):
    for attempt in range(MAX_RETRIES):
        try:
            start = time.time()
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_BATCH},
                    {"role": "user", "content": build_batch_prompt(items)}
                ],
                temperature=0.1,
            )
            elapsed = time.time() - start
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            for item in items:
                vlog(f"{item['id']}(batch)", len(build_batch_prompt(items)), len(content), has_chinese(content), content)
            record_tps(tokens, elapsed)
            return parse_batch_response(content, items), tokens, elapsed
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                log(f"  重试 {attempt+1}/{MAX_RETRIES}: {type(e).__name__}, {2**attempt}s")
                time.sleep(2 ** attempt)
    raise

# ---- 模式：batch ----
def run_batch(data, unique, progress, translated_ids, total_tokens):
    need = [item for item in unique.values()
            if item['id'] not in translated_ids and item.get('prompt_en', '').strip()]
    log(f"  待翻译: {len(need)}")
    if not need:
        log("  全部完成!"); return total_tokens

    batches = [need[i:i + BATCH_SIZE] for i in range(0, len(need), BATCH_SIZE)]
    log(f"  共 {len(batches)} 批, 每批 {BATCH_SIZE} 条\n")

    done_count = 0; last_checkpoint = 0; start_time = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(translate_batch, b): b for b in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                results, tokens, elapsed = future.result()
                for r in results:
                    item = unique.get(r['id'])
                    if item:
                        item['title_zh'] = r['title_zh']
                        item['prompt_zh'] = r['prompt_zh']
                        item['description_zh'] = r['description_zh']
                        translated_ids.add(r['id'])
                total_tokens += tokens; done_count += len(results)
                et = time.time() - start_time
                ips = done_count / et if et > 0 else 0
                eta = (len(need) - done_count) / ips if ips > 0 else 0
                log(f"  [{done_count}/{len(need)} {done_count/len(need)*100:.0f}%] {len(results)}条 {elapsed:.1f}s {tokens}tok | {ips:.1f}条/秒 ETA {eta/60:.0f}分")
                if done_count - last_checkpoint >= CHECKPOINT_INTERVAL:
                    progress['translated_ids'] = list(translated_ids); progress['total_tokens_used'] = total_tokens
                    save_progress(progress)
                    data['items'] = list(unique.values()); data['total'] = len(unique)
                    data['generated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    log(f"  [Checkpoint {done_count}条]"); last_checkpoint = done_count
            except Exception as e:
                log(f"  批次失败: {type(e).__name__}: {e}")

    log(f"  耗时: {(time.time()-start_time)/60:.1f}分")
    return total_tokens

# ---- 模式：retry ----
def run_retry(data, unique, progress, translated_ids, total_tokens):
    failed = [item for item in unique.values()
              if not item.get('prompt_zh','') or not has_chinese(item['prompt_zh'])
              if item.get('prompt_en','').strip()]
    log(f"  prompt_zh 无效: {len(failed)} 条")
    if not failed:
        log("  无需重试!"); return total_tokens

    log(f"  Batch size=1, 逐条翻译\n")
    done_count = 0; last_checkpoint = 0; cn_ok = 0; cn_fail = 0; start_time = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(translate_single, item): item for item in failed}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item_id, title_zh, prompt_zh, desc_zh, tokens, elapsed, has_cn = future.result()
                total_tokens += tokens; done_count += 1
                if has_cn:
                    cn_ok += 1
                    target = unique.get(item_id)
                    if target:
                        target['prompt_zh'] = prompt_zh; target['description_zh'] = desc_zh
                        if title_zh:
                            target['title_zh'] = title_zh
                    translated_ids.add(item_id)
                else:
                    cn_fail += 1

                et = time.time() - start_time
                ips = done_count / et if et > 0 else 0
                eta = (len(failed) - done_count) / ips if ips > 0 else 0
                cn_flag = "OK" if has_cn else "FAIL"
                log(f"  [{done_count}/{len(failed)} {done_count/len(failed)*100:.0f}%] {item_id} {elapsed:.1f}s [{cn_flag}] | {ips:.1f}条/秒 ETA {eta/60:.0f}分 | ok={cn_ok} fail={cn_fail}")
                if done_count - last_checkpoint >= CHECKPOINT_INTERVAL:
                    progress['translated_ids'] = list(translated_ids); progress['total_tokens_used'] = total_tokens
                    save_progress(progress)
                    data['items'] = list(unique.values()); data['total'] = len(unique)
                    data['generated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    log(f"  [Checkpoint {done_count}条]"); last_checkpoint = done_count
            except Exception as e:
                log(f"  失败: {item['id']} {type(e).__name__}: {e}")

    log(f"  耗时: {(time.time()-start_time)/60:.1f}分 | 含中文:{cn_ok} 仍英文:{cn_fail}")
    return total_tokens

# ---- 模式：title ----
def run_title(data, unique, progress, translated_ids, total_tokens):
    need = [item for item in unique.values()
            if not item.get('title_zh','') or not has_chinese(item['title_zh'])
            if item.get('title','').strip()]
    log(f"  title_zh 无效: {len(need)} 条")
    if not need:
        log("  无需翻译!"); return total_tokens

    log(f"  逐条翻译标题\n")
    done_count = 0; last_checkpoint = 0; cn_ok = 0; cn_fail = 0; start_time = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(translate_title, item): item for item in need}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item_id, title_zh, tokens, elapsed, has_cn = future.result()
                total_tokens += tokens; done_count += 1
                if has_cn:
                    cn_ok += 1
                    target = unique.get(item_id)
                    if target:
                        target['title_zh'] = title_zh
                else:
                    cn_fail += 1

                et = time.time() - start_time
                ips = done_count / et if et > 0 else 0
                eta = (len(need) - done_count) / ips if ips > 0 else 0
                cn_flag = "OK" if has_cn else "FAIL"
                log(f"  [{done_count}/{len(need)} {done_count/len(need)*100:.0f}%] {item_id} \"{title_zh[:30]}\" {elapsed:.1f}s [{cn_flag}] | {ips:.1f}条/秒 ETA {eta/60:.0f}分 | ok={cn_ok} fail={cn_fail}")
                if done_count - last_checkpoint >= CHECKPOINT_INTERVAL:
                    progress['translated_ids'] = list(translated_ids); progress['total_tokens_used'] = total_tokens
                    save_progress(progress)
                    data['items'] = list(unique.values()); data['total'] = len(unique)
                    data['generated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    log(f"  [Checkpoint {done_count}条]"); last_checkpoint = done_count
            except Exception as e:
                log(f"  失败: {item['id']} {type(e).__name__}: {e}")

    log(f"  耗时: {(time.time()-start_time)/60:.1f}分 | 含中文:{cn_ok} 仍英文:{cn_fail}")
    return total_tokens

# ---- 入口 ----
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('batch', 'retry', 'title'):
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if VERBOSE_LOG.exists():
        VERBOSE_LOG.unlink()

    mode_names = {'batch': '批量翻译 (5条/请求)', 'retry': '重试失败条目 (单条)', 'title': '翻译标题 (单条)'}
    log("=" * 60)
    log(f"  {mode_names[mode]} — DeepSeek V4 Flash")
    log(f"  Model: {MODEL} | Workers: {MAX_WORKERS}")
    log("=" * 60)

    log("\n[1/4] 加载数据...")
    data = json.loads(DATA_FILE.read_text(encoding='utf-8'))

    unique = {}
    for item in data['items']:
        if item['id'] not in unique:
            unique[item['id']] = item
    log(f"  总条目: {len(unique)}（已去重）")

    progress = load_progress()
    translated_ids = set(progress.get('translated_ids', []))
    total_tokens = progress.get('total_tokens_used', 0)
    log(f"  已标记翻译: {len(translated_ids)} | 已用 Token: {total_tokens:,}")

    log(f"\n[2/4] 开始翻译...")

    runners = {'batch': run_batch, 'retry': run_retry, 'title': run_title}
    total_tokens = runners[mode](data, unique, progress, translated_ids, total_tokens)

    log(f"\n[3/4] 最终保存...")
    progress['translated_ids'] = list(translated_ids)
    progress['total_tokens_used'] = total_tokens
    save_progress(progress)

    data['items'] = list(unique.values())
    data['total'] = len(unique)
    data['generated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    log(f"\n[4/4] 完成!")
    cn = sum(1 for i in unique.values() if i.get('prompt_zh') and has_chinese(i['prompt_zh']))
    en = sum(1 for i in unique.values() if i.get('prompt_zh') and not has_chinese(i['prompt_zh']))
    empty = sum(1 for i in unique.values() if not i.get('prompt_zh', ''))
    tz_cn = sum(1 for i in unique.values() if i.get('title_zh') and has_chinese(i['title_zh']))
    log(f"  prompt_zh: 含中文 {cn}条 | 英文 {en}条 | 为空 {empty}条")
    log(f"  title_zh:  含中文 {tz_cn}条")
    log(f"  累计 Token: {total_tokens:,}")
    log(f"  Verbose 日志: {VERBOSE_LOG}")

if __name__ == '__main__':
    main()
