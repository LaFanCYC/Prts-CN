import os
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime
from logger import logger, LOG_CATEGORIES
from app.agents.json_processor import JSONProcessor

def load_prompt_from_file(name):
    """从prompts文件夹中读取提示词文件"""
    prompt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'prompts')
    file_path = os.path.join(prompt_dir, f'{name}.txt')
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], f'读取提示词文件失败: {name}.txt', error=str(e))
    return None

class AIAgent:
    """
    AI Agent 基类
    提供API调用、配置管理、错误处理等通用功能
    """

    def __init__(self, agent_type=None):
        self.agent_type = agent_type
        self._settings = {}

        self.client = OpenAI(
            api_key='',
            base_url='https://ark.cn-beijing.volces.com/api/v3'
        )

        self.vision_model = 'doubao-seed-2.0-pro'
        self.grading_model = 'doubao-seed-2.0-mini'
        self.analysis_model = 'doubao-seed-2.0-pro'
        self.metadata_model = 'doubao-seed-2.0-mini'

        self.json_processor = JSONProcessor()

        self._load_settings()

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], f'{self.__class__.__name__} 初始化完成',
                  agent_type=self.agent_type,
                  api_key_set=bool(self._settings.get('api_key')),
                  api_base=self._settings.get('api_base'),
                  model=self._get_current_model())

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
        注意：不再每次调用都重新加载设置，避免多线程环境下的应用上下文问题
        设置应在Agent初始化时加载
        """
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
                "max_tokens": 40000 if has_image else 20000,
                "stream": False
                
            }

            if response_format:
                params["response_format"] = response_format
            elif has_image and "gpt-4" in model:
                params["response_format"] = {"type": "json_object"}

            if hasattr(self, 'enable_deep_thinking') and self.enable_deep_thinking:
                params["extra_body"] = {"enable_deep_thinking": True}
                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '启用深度思考模式', model=model)

            response = self.client.chat.completions.create(**params)

            if not hasattr(response, 'choices') or len(response.choices) == 0:
                error_msg = "API returned no choices"
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AI API 返回空结果', 
                          model=model, response=str(response))
                return json.dumps({
                    "error": error_msg,
                    "is_exam_paper": False,
                    "items": []
                })

            choice = response.choices[0]
            message = choice.message if hasattr(choice, 'message') else None
            content = message.content if message else None

            if content is None:
                error_msg = "API returned empty content (possibly rate limited)"
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AI API 返回空内容', model=model)
                return json.dumps({
                    "error": error_msg,
                    "is_exam_paper": False,
                    "items": []
                })

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
        """加载最新的设置，支持各Agent独立配置"""
        settings = {}

        try:
            from app.models import Setting
            from app import db

            try:
                setting_records = Setting.query.all()
                settings = {record.key: record.value for record in setting_records}
                self._settings = settings

                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '从数据库加载设置',
                          settings_keys=list(settings.keys()),
                          agent_type=self.agent_type)
            except Exception as e:
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '从数据库加载设置失败，使用环境变量', error=str(e))
        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '无法访问数据库，使用环境变量', error=str(e))

        if self.agent_type == 'vision':
            api_key = settings.get('vision_api_key') or settings.get('api_key') or os.getenv('AI_VISION_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings.get('vision_api_base') or settings.get('api_base') or os.getenv('AI_VISION_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = settings.get('model_vision') or os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro')
            deep_thinking_key = 'vision_deep_thinking'
        elif self.agent_type == 'grading':
            api_key = settings.get('grading_api_key') or settings.get('api_key') or os.getenv('AI_GRADING_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings.get('grading_api_base') or settings.get('api_base') or os.getenv('AI_GRADING_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = settings.get('model_grading') or os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini')
            deep_thinking_key = 'grading_deep_thinking'
        elif self.agent_type == 'analysis':
            api_key = settings.get('analysis_api_key') or settings.get('api_key') or os.getenv('AI_ANALYSIS_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings.get('analysis_api_base') or settings.get('api_base') or os.getenv('AI_ANALYSIS_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = settings.get('model_analysis') or os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')
            deep_thinking_key = 'analysis_deep_thinking'
        elif self.agent_type == 'metadata':
            api_key = settings.get('metadata_api_key') or settings.get('api_key') or os.getenv('AI_METADATA_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings.get('metadata_api_base') or settings.get('api_base') or os.getenv('AI_METADATA_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = settings.get('model_metadata') or os.getenv('AI_MODEL_METADATA', 'doubao-seed-2.0-mini')
            deep_thinking_key = None
        elif self.agent_type == 'subject_analysis':
            api_key = settings.get('subject_analysis_api_key') or settings.get('analysis_api_key') or settings.get('api_key') or os.getenv('AI_SUBJECT_ANALYSIS_API_KEY') or os.getenv('AI_ANALYSIS_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings.get('subject_analysis_api_base') or settings.get('analysis_api_base') or settings.get('api_base') or os.getenv('AI_SUBJECT_ANALYSIS_API_BASE') or os.getenv('AI_ANALYSIS_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = settings.get('model_subject_analysis') or settings.get('model_analysis') or os.getenv('AI_MODEL_SUBJECT_ANALYSIS') or os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')
            deep_thinking_key = 'subject_analysis_deep_thinking'
        else:
            api_key = settings.get('api_key') or os.getenv('AI_API_KEY')
            api_base = settings.get('api_base') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            model = None
            deep_thinking_key = None

        if deep_thinking_key:
            self.enable_deep_thinking = settings.get(deep_thinking_key, 'false').lower() == 'true' or os.getenv(f'AI_{deep_thinking_key.upper()}', 'false').lower() == 'true'
        else:
            self.enable_deep_thinking = False

        if api_key and api_key.strip():
            self.client.api_key = api_key

        if api_base and api_base.strip():
            self.client.base_url = api_base

        if model and model.strip():
            if self.agent_type == 'vision':
                self.vision_model = model
            elif self.agent_type == 'grading':
                self.grading_model = model
            elif self.agent_type == 'analysis':
                self.analysis_model = model
            elif self.agent_type == 'metadata':
                self.metadata_model = model
            elif self.agent_type == 'subject_analysis':
                self.analysis_model = model

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '设置加载完成',
                  agent_type=self.agent_type,
                  api_key_set=bool(api_key),
                  api_base=api_base)

    def _get_current_model(self):
        """获取当前Agent使用的模型"""
        if self.agent_type == 'vision':
            return self.vision_model
        elif self.agent_type == 'grading':
            return self.grading_model
        elif self.agent_type == 'analysis':
            return self.analysis_model
        elif self.agent_type == 'metadata':
            return self.metadata_model
        elif self.agent_type == 'subject_analysis':
            return self.analysis_model
        return None

    def encode_image(self, image_path):
        """将图片文件编码为base64字符串"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


class VisionAgent(AIAgent):
    """
    试卷识别Agent
    负责从试卷图片中提取题目信息
    """

    def __init__(self):
        super().__init__(agent_type='vision')

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

            prompt_content = custom_prompt or self.DEFAULT_PROMPT
            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'VisionAgent 发送题目数据',
                      model=self.vision_model,
                      image_path=image_path,
                      input_prompt=prompt_content[:500] if prompt_content else 'Empty')

            result = self.call_api(messages, model=self.vision_model)

            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'VisionAgent 返回结果',
                      model=self.vision_model,
                      raw_result=result[:1000] if result else 'Empty')

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

    def __init__(self):
        super().__init__(agent_type='metadata')

    DEFAULT_PROMPT = """你是一个教育专家，擅长分析题目并提取知识点。

根据给定的题目文本，请分析并返回以下JSON格式：
{
    "knowledge_tags": ["知识点1", "知识点2"]
}

只返回JSON格式。"""

    def analyze(self, question_text, custom_prompt=None):
        """
        分析题目文本，提取知识点

        Args:
            question_text: 题干文本
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 包含knowledge_tags的字典
        """
        try:
            prompt = custom_prompt or self.DEFAULT_PROMPT
            messages = [
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": f"题目文本：{question_text}"
                }
            ]

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'MetadataAgent 发送题目数据',
                      model=self.metadata_model,
                      input_text=question_text[:200],
                      prompt=prompt[:300] if prompt else 'Empty')

            result = self.call_api(messages, model=self.metadata_model)

            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'MetadataAgent 返回结果',
                      model=self.metadata_model,
                      raw_result=result[:1000] if result else 'Empty')

            validated_result = self.json_processor.validate_and_normalize_metadata_result(result)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'MetadataAgent 分析完成',
                      knowledge_tags=validated_result.get('knowledge_tags'))

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'MetadataAgent分析失败', error=str(e))
            return {
                "knowledge_tags": []
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

    def __init__(self):
        super().__init__(agent_type='grading')

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
            question_data: 题目数据字典，需包含question_stem, student_answer, score等
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 评分结果
        """
        try:
            prompt = custom_prompt or self.DEFAULT_PROMPT

            question_json_str = json.dumps({
                "question_number": question_data.get('question_index', question_data.get('question_number', '')),
                "question_stem": question_data.get('question_stem', question_data.get('ocr_text', '')),
                "student_answer": question_data.get('student_answer', question_data.get('user_answer_text', '')),
                "score": str(question_data.get('score', question_data.get('max_score', 10))),
                "reference_answer": "",
                "analysis": "",
                "knowledge_point": ""
            }, ensure_ascii=False)

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'GradingAgent 发送题目数据',
                      model=self.grading_model,
                      question_number=question_data.get('question_index', ''),
                      input_json=question_json_str,
                      prompt=prompt[:300] if prompt else 'Empty')

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": question_json_str}
            ]

            result = self.call_api(messages, model=self.grading_model)

            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'GradingAgent 返回结果',
                      model=self.grading_model,
                      question_number=question_data.get('question_index', ''),
                      raw_result=result[:1500] if result else 'Empty')

            max_score = int(question_data.get('score', question_data.get('max_score', 10)))
            validated_result = self.json_processor.validate_and_normalize_grading_result(
                result, max_score=max_score
            )

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'GradingAgent 评分完成',
                      question_number=question_data.get('question_index', ''),
                      earned_score=validated_result.get('earned_score'),
                      max_score=max_score,
                      validated_result=validated_result)

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'GradingAgent评分失败', error=str(e))
            return {
                "standard_answer": "无法生成标准答案",
                "user_score": 0,
                "earned_score": 0,
                "feedback": f"评分失败: {str(e)}"
            }

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

    def __init__(self):
        super().__init__(agent_type='analysis')

    DEFAULT_PROMPT = """你是一位专业的教育分析师，具备强大的数据聚合与教育学诊断能力。

请接收已完成评分与解析的整卷JSON数据，进行多维度分析并生成总结报告。

输入格式：
{
  "exam_name": "考试名称（可能缺失）",
  "questions": [
    {
      "question_number": "题号",
      "score": "满分分值",
      "earned_score": 实际得分,
      "knowledge_point": "知识点",
      "student_answer": "学生答案",
      "analysis": "解析"
    }
  ]
}

分析要求：
1. 统计总分和总得分，计算得分率
2. 分析知识点分布
3. 识别薄弱环节与优势板块
4. 生成150-300字的专业分析总结

输出格式（必须是严格JSON）：
{
  "exam_name": "考试名称",
  "total_score": 总分,
  "total_earned_score": 实际得分,
  "summary": "分析总结（150-300字）"
}

注意：只返回JSON格式，不要包含Markdown代码块符号。"""

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
            exam_name = exam_data.get('name', exam_data.get('exam_name', ''))
            questions = exam_data.get('questions', [])

            input_data = {
                "exam_name": exam_name,
                "questions": []
            }

            for q in questions:
                knowledge_tags = q.get('knowledge_tags', [])
                if isinstance(knowledge_tags, list):
                    knowledge_point = knowledge_tags[0] if knowledge_tags else ''
                else:
                    knowledge_point = str(knowledge_tags) if knowledge_tags else ''
                
                question_item = {
                    "question_number": q.get('question_number', q.get('question_index', '')),
                    "score": str(q.get('score', q.get('max_score', 0))),
                    "earned_score": q.get('user_score', q.get('earned_score', 0)),
                    "knowledge_point": knowledge_point,
                    "student_answer": q.get('student_answer', q.get('user_answer_text', '')),
                    "analysis": q.get('analysis', q.get('feedback', ''))
                }
                input_data["questions"].append(question_item)

            questions_json = json.dumps(input_data, ensure_ascii=False, indent=2)

            prompt_content = custom_prompt or self.DEFAULT_PROMPT
            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'AnalysisAgent 发送分析数据',
                      model=self.analysis_model,
                      exam_name=exam_name,
                      question_count=len(questions),
                      input_json=questions_json[:800],
                      prompt=prompt_content[:500] if prompt_content else 'Empty')

            messages = [
                {"role": "system", "content": prompt_content},
                {"role": "user", "content": questions_json}
            ]

            result = self.call_api(messages, model=self.analysis_model)

            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'AnalysisAgent 返回结果',
                      model=self.analysis_model,
                      raw_result=result[:1500] if result else 'Empty')

            validated_result = self.json_processor.validate_and_normalize_analysis_result(result)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AnalysisAgent 分析完成',
                      exam_name=validated_result.get('exam_name', exam_name),
                      total_score=validated_result.get('total_score'),
                      total_earned_score=validated_result.get('total_earned_score'),
                      summary=validated_result.get('summary', '')[:100])

            return validated_result

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'AnalysisAgent 分析失败', error=str(e))
            return self.json_processor.validate_and_normalize_analysis_result(None)

    def analyze_exam(self, exam_info: dict, questions: list, custom_prompt=None):
        """
        分析考试数据（兼容旧接口）

        Args:
            exam_info: 考试信息字典
            questions: 题目列表
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 分析报告
        """
        exam_data = {
            'name': exam_info.get('name', ''),
            'date': exam_info.get('date', ''),
            'subject_name': exam_info.get('subject_name', ''),
            'questions': [q.to_dict() if hasattr(q, 'to_dict') else q for q in questions]
        }
        return self.analyze(exam_data, custom_prompt)


class SubjectAnalysisAgent(AIAgent):
    """
    学科综合分析Agent
    负责对整个学科进行综合分析，生成学科分析报告
    """

    def __init__(self):
        super().__init__(agent_type='subject_analysis')

    DEFAULT_PROMPT = None

    def analyze(self, subject_data, custom_prompt=None):
        """
        分析学科数据，生成学科综合分析报告

        Args:
            subject_data: 学科数据字典
            custom_prompt: 自定义提示词（可选）

        Returns:
            dict: 包含analysis_report的分析结果
        """
        try:
            subject_name = subject_data.get('name', '')
            exams = subject_data.get('exams', [])

            input_data = {
                "id": subject_data.get('id', 0),
                "name": subject_name,
                "analysis_report": subject_data.get('analysis_report', ''),
                "exam_count": len(exams),
                "created_at": subject_data.get('created_at', ''),
                "updated_at": subject_data.get('updated_at', ''),
                "exams": []
            }

            for exam in exams:
                exam_item = {
                    "id": exam.get('id', 0),
                    "subject_id": exam.get('subject_id', 0),
                    "name": exam.get('name', ''),
                    "date": exam.get('date', ''),
                    "analysis_report": exam.get('analysis_report', ''),
                    "image_paths": exam.get('image_paths', []),
                    "question_count": exam.get('question_count', 0),
                    "total_score": exam.get('total_score', 0),
                    "user_score": exam.get('user_score', 0),
                    "created_at": exam.get('created_at', ''),
                    "updated_at": exam.get('updated_at', ''),
                    "questions": exam.get('questions', [])
                }
                input_data["exams"].append(exam_item)

            questions_json = json.dumps(input_data, ensure_ascii=False, indent=2)

            prompt_content = custom_prompt
            if not prompt_content:
                prompt_content = load_prompt_from_file('Subject_Ana')

            logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], 'SubjectAnalysisAgent 发送分析数据',
                      model=self.analysis_model,
                      subject_name=subject_name,
                      exam_count=len(exams),
                      input_json=questions_json[:800],
                      prompt=prompt_content[:500] if prompt_content else 'Empty')

            messages = [
                {"role": "system", "content": prompt_content},
                {"role": "user", "content": questions_json}
            ]

            result = self.call_api(messages, model=self.analysis_model)

            logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], 'SubjectAnalysisAgent 返回结果',
                      model=self.analysis_model,
                      raw_result=result[:1500] if result else 'Empty')

            try:
                result_data = json.loads(result)
                if isinstance(result_data, str):
                    result_data = json.loads(result_data)
            except:
                result_data = {
                    "id": subject_data.get('id', 0),
                    "name": subject_name,
                    "analysis_report": result if result else '',
                    "exam_count": len(exams),
                    "exams": input_data["exams"]
                }

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'SubjectAnalysisAgent 分析完成',
                      subject_name=subject_name,
                      exam_count=len(exams))

            return result_data

        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'SubjectAnalysisAgent 分析失败', error=str(e))
            return {
                "id": subject_data.get('id', 0),
                "name": subject_data.get('name', ''),
                "analysis_report": f"分析失败：{str(e)}",
                "exam_count": len(subject_data.get('exams', [])),
                "exams": []
            }
