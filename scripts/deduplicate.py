import json
from pathlib import Path

# 获取项目根目录下的数据库路径
scripts_dir = Path(__file__).resolve().parent
db_path = scripts_dir.parent / "background_data.json"

if db_path.is_file():
    print(f"正在读取数据库：{db_path.name}...")
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    initial_count = len(data)
    unique_data = []
    seen_tags = set()
    removed_count = 0
    
    for item in data:
        # 格式化 tags 排序作为唯一特征 key
        tags_list = [t.strip().lower() for t in item.get("tags", "").split(",") if t.strip()]
        tags_key = ",".join(sorted(tags_list))
        
        if not tags_key:
            # 如果是空数据，直接过滤
            continue
            
        if tags_key not in seen_tags:
            seen_tags.add(tags_key)
            unique_data.append(item)
        else:
            print(f"  [Remove] 发现重复 tags，已移除：{item.get('name_zh')} (原ID: {item.get('original_id')})")
            removed_count += 1
            
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(unique_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n清理完成！原始数据 {initial_count} 条，移除了 {removed_count} 条重复数据，剩余 {len(unique_data)} 条。")
else:
    print(f"未找到数据库文件：{db_path}")
