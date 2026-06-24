#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimaBackground - Traits Patching Script
该脚本调用本地 LM Studio 模型，对已有的 background_data.json 数据进行增量打补丁。
它将读取每条背景的 tags，并基于最新的 23 个 Traits 特征库，重新提炼出更细致的多重 Traits 属性。
"""

import json
import time
import requests
import re
from pathlib import Path

# ================= 配置与常量 =================
LM_STUDIO_API = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "gemma4-12b-qat-uncensored-hauhaucs-balanced@q4_k_m"

# 最新扩展后的 23 个 Traits 列表
ALLOWED_TRAITS = [
    "indoor", "outdoor", "day", "night", "water", "snowy", "greenery", "neon", "sunlight",
    "street", "classroom", "home", "japanese", "ruins", "cyber", "sky", "stars", "sea",
    "forest", "flower", "sunset", "rainy", "cozy"
]

SYSTEM_PROMPT = f"""你是一个专业的 AI 绘画 Prompt 特征提取专家。
我会给你一个背景名称和相关的英文 Prompt，你需要分析它们，并从预设的特征列表中挑选出【所有符合该背景特征的词】，允许同时挑选多个特征。

【挑选原则】：
- 如果出现樱花/红叶/草地/野花等：选 "flower" 和 "greenery"。
- 如果是林间、竹林、树木：选 "forest" 和 "greenery"。
- 如果是海滩、波浪、沙滩：选 "sea" 和 "water" 和 "outdoor"。
- 如果是小溪、河流、湖泊、雨水、泳池：选 "water"。
- 如果是街道、小巷、商店、城市：选 "street" 和 "outdoor"。
- 如果是学校、课桌、走廊：选 "classroom"。
- 如果是卧室、客厅、书房：选 "home" 和 "indoor"。
- 如果是黄昏、日落、晚霞：选 "sunset" 和 "day"。
- 如果是星空、银河、极光、夜晚：选 "stars" 和 "night"。
- 如果是雨天、雨丝、积水：选 "rainy" 和 "water"。
- 如果是雪景、冰块、冬天：选 "snowy"。
- 如果是温馨的卧室、咖啡馆、暖炉火：选 "cozy"。

可选的特征 (Traits) 列表如下，你只能从中进行多选，不要输出任何不在列表中的词：
{json.dumps(ALLOWED_TRAITS, ensure_ascii=False)}

【输出格式要求】：
你必须且只能返回一个 JSON 数组，不带任何解释。格式如下：
[
  "特征1",
  "特征2",
  "特征3"
]
"""

def clean_json_string(text):
    text = text.strip()
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_general = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
    if match_general:
        return match_general.group(1).strip()
    return text

def extract_traits_with_llm(name_zh, tags):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"背景名称：{name_zh}\n提示词：{tags}"}
        ],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(LM_STUDIO_API, json=payload, timeout=40)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            cleaned = clean_json_string(content)
            traits = json.loads(cleaned)
            if isinstance(traits, list):
                # 过滤出合法的 trait
                return [t for t in traits if t in ALLOWED_TRAITS]
        else:
            print(f"  [API Error] HTTP {response.status_code}")
    except Exception as e:
        print(f"  [Error] 提取失败: {e}")
    return None

def main():
    scripts_dir = Path(__file__).resolve().parent
    db_path = scripts_dir.parent / "background_data.json"
    
    if not db_path.is_file():
        print(f"未找到数据库文件：{db_path}")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print(f"成功载入数据库，共有 {len(data)} 条背景数据。")
    print("开始使用大模型重新提炼每条数据的 Traits 细分特征...")
    
    success_count = 0
    start_time_all = time.time()
    
    # 逐条给非重复的背景打补丁
    for idx, item in enumerate(data):
        if item.get("duplicate"):
            continue
            
        name_zh = item.get("name_zh", "")
        tags = item.get("tags", "")
        old_traits = item.get("traits", [])
        
        print(f"[{idx+1}/{len(data)}] 正在处理场景: {name_zh}...")
        start_time = time.time()
        
        new_traits = extract_traits_with_llm(name_zh, tags)
        
        if new_traits is not None:
            # 更新 traits
            item["traits"] = new_traits
            success_count += 1
            print(f"  └─ 成功! 旧特征: {old_traits} => 新多重特征: {new_traits} | 耗时: {time.time() - start_time:.2f}s")
            
            # 实时写回文件防崩
            try:
                with open(db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  [Warning] 写入数据库失败: {e}")
        else:
            print("  └─ 失败，保持原特征不变。")
            
        time.sleep(0.3)

    print(f"\n全部打补丁完成！成功为 {success_count} 条背景更新了细分特征。")
    print(f"总耗时: {time.time() - start_time_all:.2f}s")

if __name__ == "__main__":
    main()
