import os
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime
from logger import logger, LOG_CATEGORIES
from app.agents.json_processor import JSONProcessor

class AIAgent:
    """
    AI Agent 基类
    提供API调用、配置管理、错误处理等通用功能
    """

    def __init__(self):
        api_key = None
        api_base = None
        vision_model = None
        grading_model = None
        analysis_model = None

        try:
            from app.models import Setting
            from app import db

            try:
                setting_records = Setting.query.all()
                settings = {record.key: record.value for record in setting_records}

                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AIAgent初始化-从数据库加载设置',
                          settings_keys=list(settings.keys()))

                api_key = settings.get('api_key')
                api_base = settings.get('api_base')
                vision_model = settings.get('model_vision')
                grading_model = settings.get('model_grading')
                analysis_model = settings.get('model_analysis')

                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AIAgent初始化-从数据库获取的值',
                          api_key_exists=bool(api_key),
                          api_base=api_base,
                          vision_model=vision_model)
            except Exception as e:
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AIAgent初始化-查询数据库失败', error=str(e))
        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AIAgent初始化-导入模块失败', error=str(e))

        api_key = api_key or os.getenv('AI_API_KEY')
        api_base = api_base or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
        vision_model = vision_model or os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro')
        grading_model = grading_model or os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini')
        analysis_model = analysis_model or os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AIAgent初始化-最终配置',
                  api_key_prefix=api_key[:10] if api_key else None,
                  api_base=api_base,
                  vision_model=vision_model)

        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base
        )

        self.vision_model = vision_model
        self.grading_model = grading_model
        self.analysis_model = analysis_model

        self.json_processor = JSONProcessor()
        self._load_settings()

    def _get_timestamp(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _sanitize_messages_for_log(self, messages):
        """
        清理日志中的消息，避免打印巨大的Base64图片字符串
        """
        try:
            log_messages = []
            for msg in messages:
                msg_copy = msg.copy()
                if isinstance(msg_copy.get('content'), list):
                    content_list = []
                    for item in msg_copy['content']:
                        item_copy = item.copy()
                        if item_copy.get('type') == 'image_url':
                            item_copy['image_url'] = {'url': '[IMAGE_BASE64_DATA_HIDDEN]'}
                        content_list.append(item_copy)
                    msg_copy['content'] = content_list
                log_messages.append(msg_copy)
            return log_messages
        except Exception:
            return "Messages handling error during logging"

    def call_api(self, messages, model=None, response_format=None):
        """
        调用AI API的统一方法
        """
        self._load_settings()

        model = model or self.grading_model

        try:
            safe_log_messages = self._sanitize_messages_for_log(messages)
            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'AI API 调用开始',
                      model=model, messages=safe_log_messages)

            has_image = any('image_url' in part
                          for msg in messages
                          for part in msg.get('content', [])
                          if isinstance(part, dict))

            params = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4000 if has_image else 2000,
                "stream": False
            }

            if response_format:
                params["response_format"] = response_format
            elif has_image and "gpt-4" in model:
                params["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**params)

            content = response.choices[0].message.content
            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'AI API 调用完成',
                      model=model, content=content[:500] if content else 'Empty')

            return content

        except Exception as e:
            error_msg = f"API Error: {str(e)}"
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AI API 调用失败', error=str(e))

            has_image_check = False
            try:
                has_image_check = any('image_url' in part
                                    for msg in messages
                                    for part in msg.get('content', [])
                                    if isinstance(part, dict))
            except:
                pass

            if has_image_check:
                return json.dumps({
                    "is_exam_paper": False,
                    "items": [],
                    "error": error_msg
                })
            return error_msg

    def _load_settings(self):
        """加载最新的设置"""
        try:
            from app.models import Setting
            from app import db

            try:
                setting_records = Setting.query.all()
                settings = {record.key: record.value for record in setting_records}

                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '从数据库加载设置',
                          settings_keys=list(settings.keys()))

                api_key = settings.get('api_key')
                if api_key and api_key.strip():
                    self.client.api_key = api_key

                api_base = settings.get('api_base')
                if api_base and api_base.strip():
                    self.client.base_url = api_base

                if 'model_vision' in settings and settings['model_vision']:
                    self.vision_model = settings['model_vision']
                if 'model_grading' in settings and settings['model_grading']:
                    self.grading_model = settings['model_grading']
                if 'model_analysis' in settings and settings['model_analysis']:
                    self.analysis_model = settings['model_analysis']

            except Exception as e:
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '查询数据库失败', error=str(e))

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '加载设置失败', error=str(e))
            pass

    def encode_image(self, image_path):
        """将图片文件编码为base64字符串"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


class VisionAgent(AIAgent):
    """
    试卷识别Agent
    负责从试卷图片中提取题目信息
    """

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
        """
        分析试卷图片，提取题目信息

        Args:
            image_path: 图片文件路径
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 包含is_exam_paper和items的字典
        """
        try:
            if not os.path.exists(image_path):
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片文件不存在', image_path=image_path)
                return self.json_processor.create_error_response(
                    "FILE_NOT_FOUND",
                    "图片文件不存在",
                    image_path=image_path
                )

            base64_image = self.encode_image(image_path)
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '图片编码成功', image_path=image_path)

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

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], '视觉模型API调用开始',
                      model=self.vision_model)
            result = self.call_api(messages, model=self.vision_model)
            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], '视觉模型API调用完成',
                      model=self.vision_model, raw_result=result[:200] if result else 'Empty')

            if isinstance(result, str) and 'error' in result.lower():
                error_data = self.json_processor.parse_json(result, default={})
                if error_data.get('error'):
                    return error_data

            validated_result = self.json_processor.validate_and_normalize_vision_result(result)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '图片识别成功',
                      is_exam_paper=validated_result.get('is_exam_paper'),
                      item_count=len(validated_result.get('items', [])))

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片识别过程失败', error=str(e))
            return self.json_processor.create_error_response(
                "VISION_ERROR",
                "图片识别过程失败",
                str(e)
            )

    def analyze_multiple(self, image_paths: list, custom_prompt=None):
        """
        批量分析多张试卷图片

        Args:
            image_paths: 图片文件路径列表
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 合并后的题目列表
        """
        all_items = []
        processed_count = 0

        for image_path in image_paths:
            result = self.analyze(image_path, custom_prompt)

            if result.get('is_exam_paper') and result.get('items'):
                all_items.extend(result.get('items', []))
                processed_count += 1

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '批量图片识别完成',
                  total_images=len(image_paths),
                  processed=processed_count,
                  total_items=len(all_items))

        return {
            "is_exam_paper": len(all_items) > 0,
            "items": all_items,
            "processed_count": processed_count,
            "total_images": len(image_paths)
        }


class MetadataAgent(AIAgent):
    """
    元数据分析Agent
    负责从题目文本中提取知识点和难度
    """

    DEFAULT_PROMPT = """你是一个教育专家，擅长分析题目并提取知识点和难度。

根据给定的题目文本，请分析并返回以下JSON格式：
{
    "knowledge_tags": ["知识点1", "知识点2"],
    "difficulty": 1-5的整数，1最简单，5最难
}

只返回JSON格式。"""

    def analyze(self, question_text, custom_prompt=None):
        """
        分析题目文本，提取知识点和难度

        Args:
            question_text: 题干文本
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 包含knowledge_tags和difficulty的字典
        """
        try:
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

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'MetadataAgent API调用开始',
                      model=self.grading_model,
                      question_text=question_text[:100])

            result = self.call_api(messages, model=self.grading_model)

            validated_result = self.json_processor.validate_and_normalize_metadata_result(result)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'MetadataAgent分析完成',
                      knowledge_tags=validated_result.get('knowledge_tags'),
                      difficulty=validated_result.get('difficulty'))

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'MetadataAgent分析失败', error=str(e))
            return {
                "knowledge_tags": [],
                "difficulty": 3
            }

    def analyze_batch(self, questions: list, custom_prompt=None):
        """
        批量分析多个题目

        Args:
            questions: 题目列表
            custom_prompt: 自定义提示词（可选）

        Returns:
            list: 分析结果列表
        """
        results = []
        for question in questions:
            question_text = question.get('question_stem', question.get('text', ''))
            if question_text:
                result = self.analyze(question_text, custom_prompt)
                result['question_number'] = question.get('question_number', '')
                results.append(result)

        return results


class GradingAgent(AIAgent):
    """
    评分Agent
    负责对学生的作答进行评分
    """

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
        """
        对学生作答进行评分

        Args:
            question_text: 题干文本
            user_answer: 学生作答内容
            max_score: 满分值
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 评分结果
        """
        try:
            prompt = (custom_prompt or self.DEFAULT_PROMPT).format(
                question_text=question_text,
                max_score=max_score,
                user_answer=user_answer or "未作答"
            )

            messages = [
                {"role": "system", "content": prompt}
            ]

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'GradingAgent API调用开始',
                      model=self.grading_model,
                      max_score=max_score)

            result = self.call_api(messages, model=self.grading_model)

            validated_result = self.json_processor.validate_and_normalize_grading_result(
                result, max_score=int(max_score) if max_score else 10
            )

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'GradingAgent评分完成',
                      user_score=validated_result.get('earned_score'),
                      max_score=max_score)

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'GradingAgent评分失败', error=str(e))
            return {
                "standard_answer": "无法生成标准答案",
                "user_score": 0,
                "earned_score": 0,
                "feedback": "评分失败，请检查输入"
            }

    def grade_question(self, question_data: dict, custom_prompt=None):
        """
        根据题目数据对象进行评分（支持新格式）

        Args:
            question_data: 题目数据字典，需包含question_stem, student_answer, score
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 评分结果
        """
        question_text = question_data.get('question_stem', '')
        user_answer = question_data.get('student_answer', '')
        max_score = question_data.get('score', '10')

        return self.grade(question_text, user_answer, max_score, custom_prompt)

    def grade_batch(self, questions: list, custom_prompt=None):
        """
        批量评分

        Args:
            questions: 题目列表
            custom_prompt: 自定义提示词（可选）

        Returns:
            list: 评分结果列表
        """
        results = []
        for question in questions:
            result = self.grade_question(question, custom_prompt)
            result['question_number'] = question.get('question_number', '')
            results.append(result)

        return results


class AnalysisAgent(AIAgent):
    """
    分析Agent
    负责生成考试分析报告
    """

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
        """
        分析考试数据，生成分析报告

        Args:
            exam_data: 考试数据字典
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 分析报告
        """
        try:
            questions_json = json.dumps(exam_data.get('questions', []),
                                      ensure_ascii=False, indent=2)

            prompt = (custom_prompt or self.DEFAULT_PROMPT).format(
                exam_name=exam_data.get('name', ''),
                exam_date=exam_data.get('date', ''),
                subject_name=exam_data.get('subject_name', ''),
                questions_data=questions_json
            )

            messages = [
                {"role": "system", "content": prompt}
            ]

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'AnalysisAgent API调用开始',
                      model=self.analysis_model,
                      exam_name=exam_data.get('name', ''),
                      question_count=len(exam_data.get('questions', [])))

            result = self.call_api(messages, model=self.analysis_model)

            validated_result = self.json_processor.validate_and_normalize_analysis_result(result)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AnalysisAgent分析完成',
                      summary=validated_result.get('summary', '')[:100],
                      score_rate=validated_result.get('score_analysis', {}).get('score_rate'))

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AnalysisAgent分析失败', error=str(e))
            return self.json_processor.validate_and_normalize_analysis_result(None)

    def analyze_exam(self, exam_info: dict, questions: list, custom_prompt=None):
        """
        根据考试信息和题目列表生成分析报告（支持新格式）

        Args:
            exam_info: 考试信息字典
            questions: 题目列表（包含得分信息）
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 分析报告
        """
        exam_data = {
            'name': exam_info.get('name', ''),
            'date': exam_info.get('date', ''),
            'subject_name': exam_info.get('subject_name', ''),
            'questions': questions
        }

        return self.analyze(exam_data, custom_prompt)
