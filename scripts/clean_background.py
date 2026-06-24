#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimaBackground - LLM Data Cleaning & Translation Script (Updated)
该脚本读取本地下载的 NovelAI 法典原始数据 (suozhang_raw.json)，
自动过滤出最契合物理背景的场景条目，并调用本地 Ollama 运行的 9B 级模型进行清洗、汉化、提炼。

清洗规则：
  1. 剔除 {}、[]、() 及 NAI 权重标识（如 1.5::...::）；
  2. 剔除人物相关的 tag（如 1girl, solo, clothes 等）；
  3. 剔除画风画质相关修饰词（如 masterpiece, artist, year 2024 等）；
  4. 仅保留纯粹的“物理背景”元素描述；
  5. 自动进行中英文双语翻译，并划分至指定的大分类及 Traits 中。
"""

import os
import json
import time
import requests
import argparse
import re
from pathlib import Path

# ================= 配置与常量 =================
LM_STUDIO_API = "http://localhost:1234/v1/chat/completions"

# 预设的大分类（Categories）
ALLOWED_CATEGORIES = [
    "自然与户外 (Nature & Outdoors)",
    "都市与日常 (Urban & Daily)",
    "幻想与异界 (Fantasy & Sci-Fi)",
    "极简与纯色 (Minimalist & Abstract)"
]

# 预设的 Traits 细分特征列表
ALLOWED_TRAITS = [
    "indoor", "outdoor", "day", "night", "water", "snowy", "greenery", "neon", "sunlight",
    "street", "classroom", "home", "japanese", "ruins", "cyber", "sky", "stars", "sea",
    "forest", "flower", "sunset", "rainy", "cozy"
]

# 排除非物理背景的法典子分类（如单纯人物动作、视角等）
EXCLUDED_SUBCATEGORIES = {
    "表情包/搞怪", 
    "情感动作", 
    "多人互动", 
    "人物形象", 
    "美食有关", 
    "视角与打光", 
    "质量词",
    "战斗华丽"
}

# 9B 模型 System Prompt 强约束规范
SYSTEM_PROMPT = f"""你是一个专业的 AI 绘画 Prompt 数据清洗专家。
我会给你一段原始的 Prompt（可能包含画师名、年份、画质词、人物外貌、衣服、以及各类权重括号）。
你需要将其净化，并严格输出指定的 JSON 格式。

【清洗规则】：
1. 【剔除权重符号】：去除所有花括号 {{}}、方括号 [[]]、圆括号 () 以及类似于 "1.5::...::" 的权重标识。
2. 【剔除人物信息】：去除所有描述人物动作、外貌、衣着的词（例如 1girl, solo, master, cowboy shot, breasts, hair, face, clothes, skirt, standing, looking at viewer 等）。
3. 【剔除风格与画质修饰词】：去除所有关于画质（masterpiece, best quality, absurdres 等）、画师（artist:xxx）、年份（year 2024 等）和渲染风格（illustration, watercolor, 3d, realistic, digital art 等）的词。
4. 【仅保留物理背景】：只保留描述“空间、地形、建筑物、天气、时间、天空、水体、植被、光影、具体场景道具”的英文词汇。
5. 【汉化】：将最终保留的英文 tags 翻译为对应的地道中文标签，且两者的顺序必须严格一一对应。
6. 【分类与特征】：大分类 (categories) 必须且只能从指定列表中选择最贴切的一个。Traits 必须从特征列表中挑选 2-3 个最贴切的。

可选的 categories 列表：
{json.dumps(ALLOWED_CATEGORIES, ensure_ascii=False)}

可选的 traits 列表：
{json.dumps(ALLOWED_TRAITS, ensure_ascii=False)}

【输出 JSON 格式要求】：
你的输出必须是且只能是一个合法的 JSON 对象，不包含任何解释性文字或 markdown 标记。格式如下：
{{
  "name": "用简短的英文给这个场景起个名字",
  "name_zh": "用简短的中文给这个场景起个名字",
  "tags": "过滤后只包含物理背景描述的英文 tags（全小写，半角逗号分隔）",
  "tags_zh": "对应的中文翻译标签（半角逗号分隔，顺序需与英文对应）",
  "categories": ["选定的分类"],
  "traits": ["特征1", "特征2"]
}}
"""

def clean_json_string(text):
    text = text.strip()
    # 剥离 markdown json 代码块包裹
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_general = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
    if match_general:
        return match_general.group(1).strip()
    return text

def clean_and_translate_with_llm(model, title, raw_tags):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"场景标题：{title}\n原始提示词：{raw_tags}"}
        ]
    }
    
    try:
        response = requests.post(LM_STUDIO_API, json=payload, timeout=60)
        if response.status_code == 200:
            result_content = response.json()["choices"][0]["message"]["content"]
            cleaned_content = clean_json_string(result_content)
            return json.loads(cleaned_content)
        else:
            print(f"  [API Error] HTTP {response.status_code}")
            try:
                print(f"  [API Response] {response.text}")
            except:
                pass
    except Exception as e:
        print(f"  [Error] 请求本地模型失败: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description="AnimaBackground - Data Cleaning Script")
    parser.add_argument("--model", type=str, default="gemma4-12b-qat-uncensored-hauhaucs-balanced@q4_k_m", help="LM Studio 加载的模型名称")
    parser.add_argument("--raw", type=str, default="suozhang_raw.json", help="原始法典 JSON 文件路径")
    parser.add_argument("--db", type=str, default="background_data.json", help="输出的背景数据库 JSON 文件路径")
    parser.add_argument("--limit", type=int, default=20, help="单次处理的最大条目数 (防过载与测试)")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent
    
    raw_path = scripts_dir / args.raw
    db_path = project_root / args.db

    # 1. 检查原始法典数据是否存在
    if not raw_path.is_file():
        print(f"[Error] 未找到原始法典数据：{raw_path.name}")
        print("请确保已下载并放置 'suozhang_raw.json' 到 scripts 目录下。")
        return

    print(f"正在加载原始法典数据：{raw_path.name}...")
    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"[Error] 无法读取原始法典: {e}")
        return

    # 2. 筛选出符合背景类型的词条
    raw_entries = raw_data.get("entries", [])
    valid_scene_entries = []
    
    for entry in raw_entries:
        path = entry.get("path", [])
        # 必须是“各式场景”分类，且不能含有排除的非物理背景子分类
        if "各式场景" in path and not any(sub in path for sub in EXCLUDED_SUBCATEGORIES):
            # 确保含有提示词
            if entry.get("tags", "").strip():
                valid_scene_entries.append(entry)

    print(f"在原始法典中发现 {len(raw_entries)} 条数据，筛选出物理背景相关词条：{len(valid_scene_entries)} 条。")

    # 3. 读取现有输出数据库 (实现增量处理/断点续传)
    if db_path.is_file():
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)
        except Exception as e:
            print(f"无法读取现有数据库 {db_path.name}，将初始化新数组。原因: {e}")
            db_data = []
    else:
        db_data = []

    # 记录已经转换成功的原始 ID (如 suozhang-0033)，防重复清洗
    processed_original_ids = {item.get("original_id") for item in db_data if item.get("original_id")}
    print(f"本地数据库已存在 {len(db_data)} 条背景数据（包含历史已处理 {len(processed_original_ids)} 条）。")

    # 4. 提取要处理的任务队列
    todo_entries = [e for e in valid_scene_entries if e.get("id") not in processed_original_ids]
    print(f"尚待处理的词条数：{len(todo_entries)} 条。")

    if not todo_entries:
        print("所有筛选出的背景词条都已处理完毕，无需运行。")
        return

    # 限制处理数量
    run_entries = todo_entries[:args.limit]
    print(f"本次运行将处理前 {len(run_entries)} 条（可通过 --limit 参数调整）。")

    processed_count = 0

    # 记录当前数据库已有的所有规范化 tags，用于比对重复
    def get_norm_key(t_str):
        return ",".join(sorted([t.strip().lower() for t in t_str.split(",") if t.strip()]))
    
    seen_tags_keys = {get_norm_key(item.get("tags", "")) for item in db_data if not item.get("duplicate")}

    print("\n--- 开始调用大模型批量清洗背景数据 ---")
    for idx, entry in enumerate(run_entries):
        orig_id = entry.get("id", "")
        title = entry.get("title", "")
        raw_tags = entry.get("tags", "")
        
        print(f"[{idx+1}/{len(run_entries)}] 正在处理：{title} ({orig_id})...")
        start_time = time.time()
        
        result = clean_and_translate_with_llm(args.model, title, raw_tags)
        
        if result:
            new_tags = result.get("tags", "")
            new_key = get_norm_key(new_tags)
            is_duplicate = new_key in seen_tags_keys
            
            # 拼装为前端标准格式
            new_item = {
                "id": f"bg_{int(time.time() * 1000) + idx}",
                "original_id": orig_id, # 记录原 ID 以防二次清洗
                "name": result.get("name", title),
                "name_zh": result.get("name_zh", title),
                "tags": new_tags,
                "tags_zh": result.get("tags_zh", ""),
                "categories": result.get("categories", ["自然与户外 (Nature & Outdoors)"]),
                "traits": result.get("traits", []),
                "folder": "images",
                "preview": "" # 留空给后续跑图程序填充
            }
            
            if is_duplicate:
                new_item["duplicate"] = True
                print(f"  └─ [Duplicate] 与已有背景 tags 重复，标记跳过。")
            else:
                seen_tags_keys.add(new_key)
                print(f"  └─ 成功! 场景: {new_item['name_zh']} | 大类: {new_item['categories']} | 耗时: {time.time() - start_time:.2f}s")
            
            db_data.append(new_item)
            processed_count += 1
            
            # 每成功处理一条，就实时写入一次文件，防止中途异常崩掉丢失进度
            try:
                with open(db_path, "w", encoding="utf-8") as f:
                    json.dump(db_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  [Warning] 实时写入备份失败: {e}")
        else:
            print("  └─ 提炼失败！")
            
        time.sleep(0.5)

    print(f"\n批量处理结束。本次成功清洗并写入 {processed_count} 条数据至 {db_path.name}。")

if __name__ == "__main__":
    main()
