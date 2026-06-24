#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AnimaBackground - ComfyUI Automated Image Generation & Association Script
该脚本读取清洗完成的 background_data.json，调用本地 ComfyUI API 批量生成背景预览图。
"""

import os
import json
import time
import argparse
import requests
from pathlib import Path

# ================= 配置与参数 =================
DEFAULT_COMFY_URL = "http://127.0.0.1:8189"

def check_comfy_online(base_url):
    """检查 ComfyUI 是否在线"""
    try:
        # 尝试获取 system_stats 节点来测试连接
        response = requests.get(f"{base_url}/system_stats", timeout=5)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False

def queue_prompt(base_url, prompt_workflow):
    """提交工作流任务到 ComfyUI"""
    payload = {"prompt": prompt_workflow}
    try:
        response = requests.post(f"{base_url}/prompt", json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("prompt_id")
        else:
            print(f"  [API Error] 提交任务失败: HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  [Error] 无法连接到 ComfyUI 提交任务: {e}")
    return None

def get_prompt_history(base_url, prompt_id):
    """查询任务执行历史状态"""
    try:
        response = requests.get(f"{base_url}/history/{prompt_id}", timeout=10)
        if response.status_code == 200:
            history = response.json()
            # 如果返回非空字典且包含 prompt_id，说明已完成
            if history and prompt_id in history:
                return history[prompt_id]
    except Exception as e:
        print(f"  [Warning] 查询历史状态出错: {e}")
    return None

def download_image(base_url, filename, subfolder, image_type, save_path):
    """从 ComfyUI 下载生成的图片并保存到本地"""
    params = {
        "filename": filename,
        "subfolder": subfolder,
        "type": image_type
    }
    try:
        response = requests.get(f"{base_url}/view", params=params, timeout=30)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
        else:
            print(f"  [API Error] 下载图片失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"  [Error] 下载图片出错: {e}")
    return False

def main():
    parser = argparse.ArgumentParser(description="AnimaBackground - ComfyUI Image Generator")
    parser.add_argument("--port", type=int, default=8189, help="ComfyUI 服务的端口号")
    parser.add_argument("--limit", type=int, default=20, help="本次运行最大生成的图片张数")
    parser.add_argument("--force", action="store_true", help="强制重新生成即使 preview 字段已有值")
    args = parser.parse_args()

    comfy_url = f"http://127.0.0.1:{args.port}"
    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent
    
    workflow_path = project_root / "Anima (Copy).json"
    db_path = project_root / "background_data.json"
    images_dir = project_root / "images"

    # 1. 创建本地 images 目录
    images_dir.mkdir(parents=True, exist_ok=True)

    # 2. 检查 ComfyUI 是否在线
    print(f"正在检测 ComfyUI 连接状态 ({comfy_url})...")
    if not check_comfy_online(comfy_url):
        print(f"[Error] 无法连接到 ComfyUI 服务，请确保 ComfyUI 已在端口 {args.port} 启动。")
        return
    print("ComfyUI 服务在线！")

    # 3. 读取工作流模板
    if not workflow_path.is_file():
        print(f"[Error] 未找到工作流文件：{workflow_path}")
        return
    
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow_tpl = json.load(f)

    # 4. 读取背景数据库
    if not db_path.is_file():
        print(f"[Error] 未找到背景数据库：{db_path}")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        db_data = json.load(f)

    # 5. 筛选出待生成的有效条目 (排除 duplicate 的条目，且 preview 为空或强制生成)
    todo_items = []
    for item in db_data:
        if item.get("duplicate"):
            continue
        
        item_id = item.get("id")
        preview_path = item.get("preview", "")
        local_file_exists = (images_dir / f"{item_id}.png").is_file()

        # 如果 preview 字段为空，或者强制重新生成，或者本地图片丢失但 preview 记录了路径
        if not preview_path or args.force or (preview_path and not local_file_exists):
            todo_items.append(item)

    print(f"背景数据库中共有 {len(db_data)} 个条目。")
    print(f"待生成预览图的条目数：{len(todo_items)} 个。")

    if not todo_items:
        print("所有条目均已生成预览图，无需执行。")
        return

    # 限制本次运行的生成数量
    run_items = todo_items[:args.limit]
    print(f"本次运行将处理前 {len(run_items)} 个条目。")

    success_count = 0

    # 6. 循环生成
    for idx, item in enumerate(run_items):
        item_id = item.get("id")
        name_zh = item.get("name_zh")
        tags = item.get("tags", "")

        print(f"\n[{idx+1}/{len(run_items)}] 正在为场景生成预览图：{name_zh} ({item_id})...")
        print(f"  └─ 提示词: {tags}")

        # 拷贝并修改工作流
        workflow = json.loads(json.dumps(workflow_tpl))
        
        # 写入多行字符串输入节点 (ID: "93")
        if "93" in workflow and "inputs" in workflow["93"]:
            workflow["93"]["inputs"]["value"] = tags
        else:
            print("  [Error] 工作流中未找到多行文本输入节点 '93'，请检查工作流结构。")
            continue

        # 写入保存图片节点的 filename_prefix (ID: "23")
        if "23" in workflow and "inputs" in workflow["23"]:
            workflow["23"]["inputs"]["filename_prefix"] = f"bg_{item_id}"
        else:
            print("  [Warning] 工作流中未找到保存图片节点 '23'，将使用默认前缀。")

        # 提交任务
        start_time = time.time()
        prompt_id = queue_prompt(comfy_url, workflow)
        if not prompt_id:
            print("  └─ 任务提交失败，跳过该条目。")
            continue

        print(f"  └─ 任务已提交，Prompt ID: {prompt_id}，正在等待 ComfyUI 渲染...")

        # 轮询状态
        completed = False
        retry_count = 0
        max_retries = 300  # 最大等待 300 秒

        while retry_count < max_retries:
            time.sleep(1)
            history_data = get_prompt_history(comfy_url, prompt_id)
            
            if history_data:
                # 任务完成，提取输出图片信息
                outputs = history_data.get("outputs", {})
                
                # 优先从保存图像节点 "23" 中提取
                save_node_output = outputs.get("23", {})
                images = save_node_output.get("images", [])
                
                # 备用从预览图像节点 "39" 中提取
                if not images:
                    preview_node_output = outputs.get("39", {})
                    images = preview_node_output.get("images", [])

                if images:
                    img_info = images[0]
                    filename = img_info.get("filename")
                    subfolder = img_info.get("subfolder", "")
                    image_type = img_info.get("type", "output")
                    
                    # 确定本地保存路径
                    save_path = images_dir / f"{item_id}.png"
                    
                    print(f"  └─ 渲染完成！正在下载图片 {filename}...")
                    if download_image(comfy_url, filename, subfolder, image_type, save_path):
                        # 更新数据库条目
                        item["preview"] = f"images/{item_id}.png"
                        success_count += 1
                        completed = True
                        print(f"  └─ 成功！图片已保存至 {save_path.name} | 耗时: {time.time() - start_time:.1f}s")
                    else:
                        print("  └─ 下载图片失败。")
                else:
                    print("  └─ 任务已完成，但未在输出节点中找到图像。")
                break
            
            retry_count += 1
            if retry_count % 10 == 0:
                print(f"  └─ 仍在排队/渲染中 ({retry_count}s)...")

        if not completed:
            print("  └─ 任务执行超时或失败。")
            
        # 每次成功生成后，实时写入数据库，防止中途异常崩掉丢失进度
        try:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [Warning] 实时写入数据库备份失败: {e}")

    print(f"\n批量生成结束。本次成功生成并关联了 {success_count} 张背景预览图。")

if __name__ == "__main__":
    main()
