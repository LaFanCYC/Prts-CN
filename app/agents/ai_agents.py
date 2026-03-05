import os
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime
from logger import logger, LOG_CATEGORIES

class AIAgent:
    def __init__(self):
        # 从环境变量获取配置
        api_key = os.getenv('AI_API_KEY', 'your-api-key-here')
        api_base = os.getenv('AI_API_BASE', 'https://api.openai.com/v1')  # 默认使用OpenAI格式
        
        # 创建OpenAI客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base
        )
        
        # 默认模型设置（兼容OpenAI格式）
        self.vision_model = os.getenv('AI_MODEL_VISION', 'gpt-4o')  # OpenAI视觉模型
        self.grading_model = os.getenv('AI_MODEL_GRADING', 'gpt-3.5-turbo')  # OpenAI基础模型
        self.analysis_model = os.getenv('AI_MODEL_ANALYSIS', 'gpt-4')  # OpenAI高级模型
        
        # 尝试从数据库获取配置（延迟导入避免循环依赖）
        try:
            from app.models import Setting
            from app import db
            
            # 只在应用上下文存在时获取设置
            if db.session.bind:
                setting_records = Setting.query.all()
                for record in setting_records:
                    if record.key == 'api_key' and record.value:
                        self.client.api_key = record.value
                    elif record.key == 'api_base' and record.value:
                        self.client.base_url = record.value
                    elif record.key == 'model_vision' and record.value:
                        self.vision_model = record.value
                    elif record.key == 'model_grading' and record.value:
                        self.grading_model = record.value
                    elif record.key == 'model_analysis' and record.value:
                        self.analysis_model = record.value
        except Exception as e:
            # 如果导入失败或数据库不可用，使用环境变量
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '加载设置失败', error=str(e))
            pass
    
    def _get_timestamp(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def call_api(self, messages, model=None):
        # 每次调用API时重新读取最新设置
        self._load_settings()
        
        model = model or self.grading_model
        try:
            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'AI API 调用开始', model=model, messages=messages)
            
            # 检查消息中是否包含图片
            has_image = any('image_url' in part for msg in messages for part in msg.get('content', []) if isinstance(part, dict))
            
            # 对于包含图片的请求，确保使用正确的API参数
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                # 对于视觉模型，可能需要额外的参数
                max_tokens=2000 if has_image else 1000,
                # 确保API调用支持图片输入
                stream=False
            )
            
            content = response.choices[0].message.content
            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'AI API 调用完成', model=model, content=content)
            
            return content
        except Exception as e:
            error_msg = f"API Error: {str(e)}"
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AI API 调用失败', error=str(e))
            # 返回错误信息，让前端知道API调用失败
            if has_image:
                return '''{
                    "is_exam_paper": false,
                    "items": [],
                    "error": "%s"
                }''' % error_msg
            return error_msg
    
    def _load_settings(self):
        """加载最新的设置"""
        try:
            from app.models import Setting
            from app import db
            
            # 只在应用上下文存在时获取设置
            if db.session.bind:
                setting_records = Setting.query.all()
                # 收集所有设置
                settings = {}
                for record in setting_records:
                    settings[record.key] = record.value
                
                # 如果有API密钥和基础URL，重新创建客户端
                if 'api_key' in settings and 'api_base' in settings:
                    self.client = OpenAI(
                        api_key=settings['api_key'],
                        base_url=settings['api_base']
                    )
                elif 'api_key' in settings:
                    self.client.api_key = settings['api_key']
                elif 'api_base' in settings:
                    self.client.base_url = settings['api_base']
                
                # 更新模型设置
                if 'model_vision' in settings:
                    self.vision_model = settings['model_vision']
                if 'model_grading' in settings:
                    self.grading_model = settings['model_grading']
                if 'model_analysis' in settings:
                    self.analysis_model = settings['model_analysis']
        except Exception as e:
            # 如果导入失败或数据库不可用，使用环境变量
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '加载设置失败', error=str(e))
            pass
    
    def encode_image(self, image_path):
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


class VisionAgent(AIAgent):
    DEFAULT_PROMPT = """你是一个专业的试卷数字化专家。你的任务是：
1. 判定上传的图片是否为试卷页面
2. 如果是试卷，提取所有题目信息，包括题号、题干文本
3. 为每个题目标注在图片中的位置坐标 [x, y, w, h]

请严格按照以下JSON格式返回结果：
{
    "is_exam_paper": true/false,
    "items": [
        {
            "index": "题号，如：1, 2, 3(1)",
            "text": "题干完整文本",
            "answer_area": "作答区域描述",
            "bbox": [x, y, w, h]
        }
    ]
}

注意：只返回JSON，不要包含任何其他文字。"""

    def analyze(self, image_path, custom_prompt=None):
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片文件不存在', image_path=image_path)
                return {
                    "is_exam_paper": False,
                    "items": []
                }
            
            # 编码图片
            base64_image = self.encode_image(image_path)
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '图片编码成功', image_path=image_path)
            
            # 构建消息
            messages = [
                {
                    "role": "system",
                    "content": custom_prompt or self.DEFAULT_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
            
            # 调用API
            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], '视觉模型API调用开始', model=self.vision_model)
            result = self.call_api(messages, model=self.vision_model)
            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], '视觉模型API调用完成', model=self.vision_model)
            
            # 解析结果
            try:
                result_json = json.loads(result)
                # 确保返回的JSON格式正确
                if isinstance(result_json, dict):
                    if "is_exam_paper" not in result_json:
                        result_json["is_exam_paper"] = False
                    if "items" not in result_json:
                        result_json["items"] = []
                    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '图片识别成功', is_exam_paper=result_json.get('is_exam_paper'), item_count=len(result_json.get('items', [])))
                    return result_json
                else:
                    logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片识别结果格式错误', raw_response=result)
                    return {
                        "is_exam_paper": False,
                        "items": []
                    }
            except Exception as e:
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片识别JSON解析失败', error=str(e), raw_response=result)
                return {
                    "is_exam_paper": False,
                    "items": []
                }
        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片识别过程失败', error=str(e))
            return {
                "is_exam_paper": False,
                "items": []
            }


class MetadataAgent(AIAgent):
    DEFAULT_PROMPT = """你是一个教育专家，擅长分析题目并提取知识点和难度。

根据给定的题目文本，请分析并返回以下JSON格式：
{
    "knowledge_tags": ["知识点1", "知识点2"],
    "difficulty": 1-5的整数，1最简单，5最难
}

只返回JSON格式。"""

    def analyze(self, question_text, custom_prompt=None):
        messages = [
            {
                "role": "system",
                "content": custom_prompt or self.DEFAULT_PROMPT
            },
            {
                "role": "user",
                "content": f"题目文本：{question_text}"
            }
        ]
        
        result = self.call_api(messages, model=self.grading_model)
        
        try:
            result_json = json.loads(result)
            return result_json
        except:
            return {
                "knowledge_tags": [],
                "difficulty": 3
            }


class GradingAgent(AIAgent):
    DEFAULT_PROMPT = """你是一位严格公正的阅卷老师。请根据以下信息进行评分：

题目信息：
- 题干：{question_text}
- 满分值：{max_score}分

用户作答：{user_answer}

请返回以下JSON格式的评分结果：
{{
    "standard_answer": "标准答案",
    "user_score": 得分数值（0-{max_score}）,
    "feedback": "详细的扣分理由和点评"
}}

注意：必须严格按照满分值{max_score}进行评分，扣分要有具体理由。只返回JSON格式。"""

    def grade(self, question_text, user_answer, max_score, custom_prompt=None):
        prompt = (custom_prompt or self.DEFAULT_PROMPT).format(
            question_text=question_text,
            max_score=max_score,
            user_answer=user_answer or "未作答"
        )
        
        messages = [
            {"role": "system", "content": prompt}
        ]
        
        result = self.call_api(messages, model=self.grading_model)
        
        try:
            result_json = json.loads(result)
            return result_json
        except:
            return {
                "standard_answer": "无法生成标准答案",
                "user_score": 0,
                "feedback": "评分失败，请检查输入"
            }


class AnalysisAgent(AIAgent):
    DEFAULT_PROMPT = """你是一位专业的教育分析师。请根据以下考试数据生成详细的分析报告：

考试信息：
- 考试名称：{exam_name}
- 考试日期：{exam_date}
- 科目：{subject_name}

题目详情（JSON数组）：
{questions_data}

请生成以下JSON格式的分析报告：
{{
    "summary": "整体情况总结",
    "score_analysis": {{
        "total_score": 总分,
        "user_score": 得分,
        "score_rate": 得分率
    }},
    "strengths": ["优势1", "优势2"],
    "weaknesses": ["薄弱点1", "薄弱点2"],
    "suggestions": ["改进建议1", "改进建议2"]
}}

只返回JSON格式。"""

    def analyze(self, exam_data, custom_prompt=None):
        questions_json = json.dumps(exam_data.get('questions', []), ensure_ascii=False, indent=2)
        
        prompt = (custom_prompt or self.DEFAULT_PROMPT).format(
            exam_name=exam_data.get('name', ''),
            exam_date=exam_data.get('date', ''),
            subject_name=exam_data.get('subject_name', ''),
            questions_data=questions_json
        )
        
        messages = [
            {"role": "system", "content": prompt}
        ]
        
        result = self.call_api(messages, model=self.analysis_model)
        
        try:
            result_json = json.loads(result)
            return result_json
        except:
            return {
                "summary": "分析生成失败",
                "score_analysis": {
                    "total_score": 0,
                    "user_score": 0,
                    "score_rate": 0
                },
                "strengths": [],
                "weaknesses": [],
                "suggestions": []
            }
