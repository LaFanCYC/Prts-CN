import os
import sys
import json
from app.agents.ai_agents import VisionAgent
from logger import logger, LOG_CATEGORIES

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

def test_vision_agent():
    """测试视觉大模型功能"""
    # 获取测试图片路径
    image_path = "app/static/uploads/6de6476b-37d7-4680-bb91-50f6621659ef.png"
    
    if not os.path.exists(image_path):
        print(f"测试图片不存在: {image_path}")
        return
    
    print(f"测试图片路径: {image_path}")
    print(f"图片大小: {os.path.getsize(image_path)} bytes")
    
    # 创建VisionAgent实例
    vision_agent = VisionAgent()
    print(f"视觉模型: {vision_agent.vision_model}")
    
    # 调用analyze方法
    print("\n调用视觉模型分析图片...")
    result = vision_agent.analyze(image_path)
    
    # 打印结果
    print("\n分析结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 检查结果
    if result.get('is_exam_paper'):
        print(f"\n检测到试卷，包含 {len(result.get('items', []))} 个题目")
    else:
        print("\n未检测到试卷")

if __name__ == "__main__":
    test_vision_agent()
