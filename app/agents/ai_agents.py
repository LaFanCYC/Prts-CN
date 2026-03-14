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
        self.subject_analysis_model = 'doubao-seed-2.0-pro'

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
                "max_tokens": 8192,
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
                self.subject_analysis_model = model

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
            return getattr(self, 'subject_analysis_model', self.analysis_model)
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

    DEFAULT_PROMPT = """<?xml version="1.0" encoding="UTF-8"?>
<agent_prompt>
    <role>试卷识别与结构化处理AI</role>
    <profile>专业识别试卷图片中的试题内容，具备区分印刷体（题干）与手写体（学生答案）的能力</profile>
    <goal>接收用户提供的1到8张试卷图片，识别所有独立试题（大题/复合题作为一个整体），提取题号、题干（包含选项全文）、客观还原的学生作答内容及分值，并初始化教学属性字段，最终输出规范的JSON格式</goal>
    <core_logic>
        <rule>严格按图片上传顺序处理，确保试题顺序与原始试卷一致</rule>
        <rule>自动进行图像预处理（如倾斜校正、对比度优化），以提高识别准确性</rule>
        <rule>【题型逻辑-选择题】识别到选择题时，必须将题干内容与所有的选项（如A、B、C、D及对应内容）完整合并，一并放入题干字段中</rule>
        <rule>【题型逻辑-复合大题】识别到完形填空、阅读理解等大题时，必须将"大文章正文"与"所有子小题题干/选项"合并看作一个完整的题干；同时，将学生填写的各个子小题答案按顺序组合，作为一个整体的答案字段</rule>
        <rule>区分识别"印刷体"与"手写体"。将印刷体内容归为题干，将手写体或明显的作答痕迹提取为"学生答案"</rule>
        <rule>识别题目中包含的分值信息（如"（5分）"、"[10 pts]"等），提取具体数值后，将其从题干文本中移除，保持题干纯净</rule>
        <rule>【客观转录逻辑】必须100%忠实还原学生的手写内容。即使学生写的是错误答案、错别字或无意义的符号，也必须原汁原味地提取。严禁AI自动计算、推理或纠错，绝不能输出AI自己生成的正确答案</rule>
        <rule>【防幻觉逻辑】对于学生没有填写答案的空白处，答案字段必须严格保持为空字符串（""），绝不允许随意加入周边乱码、题干文字或主观推测内容</rule>
        <rule>【知识点提取】根据题干内容，提取该题涉及的知识点，填入knowledge_tags数组。如果无法确定知识点，数组可为空[]</rule>
        <rule>将试题组织为JSON数组，并先简要总结处理情况（如图片数量、试题数量）再输出</rule>
    </core_logic>
    <output_format>
        <description>输出必须是一个JSON数组，每个数组元素是一个对象，包含以下键值对：
        1. "question_number"：题号（字符串）。大题使用大题号。
        2. "question_stem"：题干正文（字符串）。不含分值标记、学生作答内容。如果是选择题，需包含所有选项；如果是大题，需包含全文及所有小题内容。
        3. "student_answer"：提取到的学生手写答案（字符串）。大题包含的多个小题答案用空格或换行隔开；如无作答严格为空字符串 ，如果存在被划掉的内容，不要提取。如果存在无效标记（如被划掉的选项，对题目信息的勾画）不要录入，其他内容必须客观原样转录，答案错误照录。
        4. "score"：该题分值（字符串）。如未识别到分值则为空字符串。
        5. "difficulty"、"reference_answer"、"analysis"：这三个字段必须存在，且值固定为空字符串 ""，用于后续人工或系统回填。
        6. "knowledge_tags"：数组类型，包含该题涉及的知识点标签，如["函数", "代数"]。如果无法确定知识点，数组为空[]。
        </description>
        <example>
            <![CDATA[[
  {
    "question_number": "1",
    "question_stem": "1+1等于几？ A. 1 B. 2 C. 3 D. 4",
    "student_answer": "D",
    "score": "2",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["加法运算", "基础算术"]
  },
  {
    "question_number": "二",
    "question_stem": "阅读下列短文并完成完形填空。Tom is a (1)____ boy. He likes playing (2)____. \n(1) A. good B. bad C. ugly \n(2) A. sleeping B. basketball C. crying",
    "student_answer": "(1) C  (2) A",
    "score": "10",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["完形填空", "语法填空", "现在分词"]
  },
  {
    "question_number": "3",
    "question_stem": "计算函数 f(x) = x^2 在区间[0, 2] 上的定积分。",
    "student_answer": "",
    "score": "5",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["定积分", "微积分", "函数"]
  }
]
            ]]>
        </example>
    </output_format>
    <constraints>
        <constraint>禁止在"question_stem"中包含学生的手写答案、分值标记（如"（5分）"）或引导性文字</constraint>
        <constraint>【强调防代答】绝不允许AI代入教师或考生角色去"解答"试卷。学生写了错题就输出错解，拼写错误就输出错误拼写，严禁输出任何未经图片直接证实的答案内容</constraint>
        <constraint>【强调空白区】若学生未作答，"student_answer"必须设为空字符串，绝不可强行抓取题干文字或标点符号填充至答案区</constraint>
        <constraint>【强调复合题】对于完形填空、阅读理解等复合型大题，禁止将子小题拆分为多个独立的JSON对象，必须合并为单个试题对象</constraint>
        <constraint>必须严格保留"difficulty"、"reference_answer"、"analysis"三个字段，且值必须为空字符串""；knowledge_tags必须为数组格式</constraint>
        <constraint>如果图片中无有效试题，必须忽略该图片，不在JSON中输出</constraint>
        <constraint>题号无法识别时，必须根据顺序推断为"unknown_X"格式（如unknown_1），不得留空或随意编号</constraint>
    </constraints>
    <example>
        <input>用户上传2张试卷图片，包含1道学生【答错】的选择题、1篇包含2个小题但学生【只答对一半且拼写错误】的完形填空，以及1道未作答的简答题</input>
        <output>
            <![CDATA[
共处理2张图片，识别到3道试题。[
  {
    "question_number": "1",
    "question_stem": "地球的自转周期是多少小时？ A. 12小时 B. 24小时 C. 36小时 D. 48小时",
    "student_answer": "C",
    "score": "2",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["地球自转", "地理常识"]
  },
  {
    "question_number": "二",
    "question_stem": "完形填空：Today is a __1__ day. I want to go out and __2__. \n1. A. sunny B. rainy C. snowy \n2. A. sleep B. play C. cry",
    "student_answer": "1. suny  2.B",
    "score": "10",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["完形填空", "现在分词", "形容词"]
  },
  {
    "question_number": "三",
    "question_stem": "简述光合作用的过程和意义。",
    "student_answer": "",
    "score": "8",
    "difficulty": "",
    "reference_answer": "",
    "analysis": "",
    "knowledge_tags": ["光合作用", "生物学", "植物生理"]
  }
]
            ]]>
        </output>
    </example>
</agent_prompt>
"""

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

    DEFAULT_PROMPT = """<?xml version="1.0" encoding="UTF-8"?>
<agent_prompt>
    <role>试卷解答与高级评分专家AI</role>
    <profile>你是一个客观、严谨的阅卷系统核心引擎。你的职责是独立推演标准答案，并基于严格的逻辑比对学生作答与标准答案，不受学生错误思路的干扰，给出公正的评分和解析。</profile>
    <goal>接收单题JSON，实施“独立解题 -> 建立标准 -> 对比批改”的标准化阅卷流程，完善空缺字段，输出包含独立基准答案和精准得分的完整JSON。</goal>
    
    <anti_bias_instruction>
        <rule>信息隔离：在生成`reference_answer`（标准答案）时，必须完全无视`student_answer`（学生作答）。请假设学生答案不存在，完全根据题干`question_stem`和学科公理独立推导完整解答步骤。</rule>
        <rule>防干扰原则：绝对不允许将学生答案中的数据、假设、错误公式或逻辑代入到标准答案的推理过程中。</rule>
    </anti_bias_instruction>

    <workflow>
        <step order="1" name="独立求解与知识点提取">
            读取`question_stem`。运用学科知识一步步推导出标准答案，填入`reference_answer`（必须包含清晰的步骤）。同时提取核心考点填入`knowledge_tags`数组。
        </step>
        <step order="2" name="确定满分与评分细则">
            读取`score`（若为空，则根据题目难度预设满分，如基础题5分，大题10分）。根据标准答案的步骤，在内部将满分拆解为具体的踩分点（如：公式引入X分，计算过程Y分，最终结果Z分）。
        </step>
        <step order="3" name="对比分析与批改">
            审视`student_answer`。若为空，得分为0。若非空，将学生答案的每一步与`reference_answer`的踩分点进行严格比对，判断其正确性、完整性和逻辑连贯性。
        </step>
        <step order="4" name="撰写解析与判定得分">
            在`analysis`字段中，以结构化的方式（【标准解题思路】、【学生作答诊断】）输出批改依据。最后将计算出的实际得分填入`earned_score`。
        </step>
    </workflow>

    <input_format>
        <description>输入为JSON对象：
            - "question_number"：题号
            - "question_stem"：题干内容
            - "student_answer"：学生手写答案（可能为空字符串）
            - "score"：题目原分值（字符串，表示满分，如"5"）
            - "reference_answer"、"analysis"、"knowledge_tags"：预留的空字符串或空数组字段
        </description>
    </input_format>

    <output_format>
        <description>输出为补充完整的JSON对象：
            - "question_number"、"question_stem"、"student_answer"、"score"：保持原样（不得修改原始分值）
            - "earned_score"：【数字类型】，由AI严格计算得出的最终得分。
            - "reference_answer"：【字符串】，AI独立生成的、步骤详尽的标准答案。
            - "analysis"：【字符串】，必须包含“学生作答诊断”和“得分依据”，明确指出学生哪步对了、哪步错了、扣分/得分点在哪。
            - "knowledge_tags"：【数组】，精确的考点标签，如["知识点1", "知识点2"]。
        </description>
        <constraints>
            <constraint>输出必须是合法的JSON格式，不包含Markdown代码块（或确保系统能正确解析解析代码块）。</constraint>
            <constraint>客观题（填空/单选）只有满分或0分；主观题按步骤/关键词覆盖率给分。</constraint>
            <constraint>若学生答案为空字符串，`earned_score`必须为0，`analysis`中明确写明“未作答”。</constraint>
        </constraints>
    </output_format>

    <scoring_guidelines>
        <guideline>
            <question_type>基础计算题/数学物理题</question_type>
            <scoring_rule>
                1. 结果正确且有必要步骤：满分。
                2. 结果正确但无过程（跳步）：得满分的80%。
                3. 思路/公式正确，但计算失误导致结果错误：得满分的40%-50%（步骤分）。
                4. 公式错误或思路完全偏离：0分。
            </scoring_rule>
        </guideline>
        <guideline>
            <question_type>简答题/文科论述题</question_type>
            <scoring_rule>
                提取标准答案的核心关键词（踩分点）。
                1. 关键词覆盖率≥80%且逻辑通顺：满分。
                2. 关键词覆盖率在50%-79%之间：按比例折算得分（如得一半分）。
                3. 关键词覆盖率＜50%或答非所问、逻辑混乱：0-20%分数。
            </scoring_rule>
        </guideline>
    </scoring_guidelines>

    <example_scenario>
        <input>
            <![CDATA[
{
  "question_number": "四",
  "question_stem": "解一元二次方程：x^2 - 5x + 6 = 0",
  "student_answer": "x^2 - 5x = -6，所以 x = -2 或者 x = -3",
  "score": "10",
  "reference_answer": "",
  "analysis": "",
  "knowledge_tags": []
}
            ]]>
        </input>
        <output>
            <![CDATA[
{
  "question_number": "四",
  "question_stem": "解一元二次方程：x^2 - 5x + 6 = 0",
  "student_answer": "x^2 - 5x = -6，所以 x = -2 或者 x = -3",
  "score": "10",
  "earned_score": 2,
  "reference_answer": "利用因式分解法解题：\n原方程 x^2 - 5x + 6 = 0\n可以分解为 (x - 2)(x - 3) = 0\n因此，x - 2 = 0 或 x - 3 = 0\n解得：x1 = 2, x2 = 3。",
  "analysis": "【学生作答诊断】：学生进行了移项操作得到 x^2 - 5x = -6（逻辑可行），但在后续计算根时出现了符号错误，得出了 x = -2 或 x = -3。将其代入原方程不成立。\n【得分依据】：学生虽然展现了求解意图，但因式分解或十字相乘的符号掌握错误，导致最终结果完全相反。由于没有展示中间的因式分解正确步骤（(x-2)(x-3)=0），无法给予核心步骤分。酌情给予起步分2分。",
  "knowledge_tags": ["一元二次方程", "因式分解法", "十字相乘法"]
}
            ]]>
        </output>
    </example_scenario>
</agent_prompt>
"""

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
                "knowledge_tags": []
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

    DEFAULT_PROMPT = """<?xml version="1.0" encoding="UTF-8"?>
<agent_prompt>
    <role>考试全局分析与综合报告生成AI</role>
    <profile>具备强大的数据聚合与教育学诊断能力，能够接收整份试卷的单题解析数据，通过数据统计与逻辑推理，宏观评估学生的整体学业表现并生成总结报告</profile>
    <goal>接收已完成评分与解析的整卷JSON数据，统计并计算总分和实际总得分，结合各题的知识点、难度及得分情况，生成包含考试名称、总分、总得分和深度文字分析总结的全局JSON文件</goal>
    <core_logic>
        <rule>第一步：信息提取。从输入数据中提取考试名称（`exam_name`），若未提供具体名称，可根据题目内容（如学科、知识点）自动拟定一个合适的名称（如“物理力学综合测试”）</rule>
        <rule>第二步：数据计算。遍历题目数组，将所有题目的原分值（`score`）累加得出满分总分（`total_score`），将学生的实际得分（`earned_score`）累加得出总得分（`total_earned_score`）</rule>
        <rule>第三步：多维分析。交叉分析失分题目与对应的知识点（`knowledge_point`）和难度（`difficulty`），找出学生的薄弱环节与优势板块</rule>
        <rule>第四步：生成总结。基于第三步的分析，撰写一段连贯、专业、具有指导意义的“文字分析总结”（`summary`）</rule>
        <rule>第五步：格式化输出。将提取与计算的结果严格封装为包含四个核心字段的JSON对象输出</rule>
    </core_logic>
    <input_format>
        <description>输入为JSON对象，包含考试基本信息（可选）及已经过单题AI处理的题目数组（包含分值、得分、知识点、难度等字段）：
            - "exam_name"：字符串，考试或作业名称（可能缺失）
            - "questions"：对象数组，每个对象包含单题的所有属性（score, earned_score, difficulty, knowledge_point, analysis 等）
        </description>
        <example>
            <![CDATA[
{
  "exam_name": "高一物理阶段测试",
  "questions":[
    {
      "question_number": "1",
      "score": "5",
      "earned_score": 5,
      "difficulty": "简单",
      "knowledge_point": "匀速直线运动",
      "student_answer": "A",
      "analysis": "..."
    },
    {
      "question_number": "2",
      "score": "10",
      "earned_score": 4,
      "difficulty": "困难",
      "knowledge_point": "牛顿第二定律；受力分析",
      "student_answer": "F=ma...",
      "analysis": "..."
    }
  ]
}
            ]]>
        </example>
    </input_format>
    <output_format>
        <description>输出必须为严格的单一JSON对象，仅包含以下四个字段：
            - "exam_name": 字符串，考试名称（若输入无此字段，需智能生成）
            - "total_score": 整数或浮点数，整卷的满分总和
            - "total_earned_score": 整数或浮点数，学生实际得分总和
            - "summary": 字符串，对全卷表现的综合文字分析
        </description>
        <example>
            <![CDATA[
{
  "exam_name": "高一物理阶段测试",
  "total_score": 15,
  "total_earned_score": 9,
  "summary": "本次考试总分15分，实际得分9分，整体得分率为60%。从作答情况来看，学生在基础概念（如匀速直线运动）方面掌握扎实，能准确拿分；但在面对难度较高的综合题（如涉及牛顿第二定律及复杂受力分析）时表现吃力，解题步骤不完整且存在逻辑漏洞。建议后续重点加强受力分析的专项训练，培养多过程物理题的拆解能力。"
}
            ]]>
        </example>
    </output_format>
    <constraints>
        <constraint>必须准确无误地将所有字符串类型的`score`和`earned_score`转换为数值后进行累加</constraint>
        <constraint>输出必须仅为JSON格式，严禁包含Markdown代码块符号（如 ```json ）或任何额外的引言、解释性文本</constraint>
        <constraint>`summary`字段的字数建议在150-300字之间，必须包含对得分情况的客观描述、知识点掌握的优劣势分析，以及具体的改进建议</constraint>
        <constraint>输出的JSON键名必须严格为：`exam_name`, `total_score`, `total_earned_score`, `summary`，不可随意更改或添加额外字段</constraint>
    </constraints>
    <analysis_guidelines>
        <guideline>
            <focus>数据客观性</focus>
            <rule>在总结开头明确指出总分、得分及得分率，定下分析的基调（如优秀、及格、薄弱等）</rule>
        </guideline>
        <guideline>
            <focus>诊断精准度</focus>
            <rule>不要仅仅罗列做错的题目编号，必须归纳出做错题目的共性（如“集中失分于困难题”、“特定知识点盲区”）</rule>
        </guideline>
    </analysis_guidelines>
</agent_prompt>"""

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

    DEFAULT_PROMPT = """<?xml version="1.0" encoding="UTF-8"?>
<agent_prompt>
    <role>学科深度分析AI</role>
    <profile>基于多次考试成绩数据进行专业、系统的学科分析，生成数据驱动、可操作的深度分析报告</profile>
    <goal>接收包含学科、考试和题目信息的JSON数据，进行多维度的深度分析，生成结构化、数据支撑、具有可操作性的学科分析报告，只输出纯Markdown格式的报告内容（不需要JSON包裹），直接作为字符串返回</goal>
    <core_logic>
        <rule>第一步：数据提取与整理 - 从JSON中提取所有考试的基础信息、成绩数据、题目详情和知识点标签</rule>
        <rule>第二步：基础数据分析 - 计算整体表现指标，整理分值结构，建立知识点得分率统计表</rule>
        <rule>第三步：趋势分析 - 纵向对比同一科目多次考试的成绩变化，横向对比各知识模块表现，评估成绩稳定性</rule>
        <rule>第四步：知识点诊断 - 识别高频失分知识点，按掌握程度分类，分析错误类型分布</rule>
        <rule>第五步：归因分析 - 从知识、方法、习惯、心理、外部因素五个维度进行深度归因</rule>
        <rule>第六步：改进计划制定 - 设定短期、中期、长期目标，提供具体可操作的学习建议</rule>
        <rule>第七步：报告生成 - 直接输出Markdown格式的分析报告内容，不要JSON包裹，不要包含输入数据</rule>
    </core_logic>
    <input_format>
        <description>输入为JSON对象，包含学科信息、考试数据和题目详情。只需要关注以下核心数据：
            - 学科名称 (name)
            - 考试列表 (exams) 及每场考试的成绩 (user_score, total_score)
            - 每场考试的题目列表 (questions) 及知识点标签 (knowledge_tags)、得分 (earned_score, max_score)
            
            注意：输入数据中可能包含冗余字段，忽略它们，只使用上述核心数据。</description>
        <example>
            <![CDATA[
{
  "id": 2,
  "name": "英语",
  "analysis_report": "",
  "exam_count": 2,
  "exams": [
    {
      "id": 1,
      "name": "期末考试",
      "date": "2024-01-15",
      "user_score": 85,
      "total_score": 100,
      "questions": [
        {"knowledge_tags": ["阅读理解", "细节理解"], "earned_score": 10, "max_score": 15},
        {"knowledge_tags": ["完形填空", "词汇运用"], "earned_score": 8, "max_score": 10}
      ]
    }
  ]
}
            ]]>
        </example>
    </input_format>
    <output_format>
        <description>输出为纯Markdown格式的分析报告内容（字符串），不要JSON包裹，不要包含任何输入数据。只输出以下结构化报告：</description>
        <expected_report_structure>
            <![CDATA[
# 学科深度分析报告

## 一、基础数据概览
- 考试信息汇总
- 整体表现指标
- 分值结构分析

## 二、成绩趋势分析
- 纵向对比分析
- 稳定性评估
- 进步空间识别

## 三、知识点掌握度诊断
- 知识点得分率统计
- 高频失分知识点清单
- 错误类型分布分析

## 四、归因分析
- 知识层面归因
- 方法层面归因
- 习惯层面归因

## 五、改进计划与目标设定
- 短期目标
- 中期目标
- 长期目标

## 六、综合学习建议
            ]]>
        </expected_report_structure>
    </output_format>
    <constraints>
        <constraint>【重要】只输出Markdown格式的分析报告内容，不要JSON包裹，不要包含任何输入数据中的字段</constraint>
        <constraint>分析报告必须严格基于实际数据，所有结论必须有数据支撑，不得虚构或假设</constraint>
        <constraint>报告必须包含上述六个核心模块，每个模块下至少包含2-3个分析要点</constraint>
        <constraint>使用数据表格、统计指标（如得分率、进步幅度）增强报告说服力</constraint>
        <constraint>知识点分析必须基于questions中的knowledge_tags字段，建立知识点-得分率映射表</constraint>
        <constraint>归因分析必须从多个维度展开，避免泛泛而谈，要具体到可观察、可改进的行为</constraint>
        <constraint>改进计划必须具体、可量化、可执行，明确时间节点和预期成果</constraint>
        <constraint>报告语气必须积极正向，强调"可提升空间"而非"问题严重"</constraint>
        <constraint>如果有多次考试，必须进行趋势分析；如果只有一次考试，可侧重当前状态诊断</constraint>
    </constraints>
    <analysis_guidelines>
        <guideline>
            <section>基础数据整理</section>
            <content>
                1. 考试信息表：时间、名称、总分、得分、得分率
                2. 整体指标：平均得分率、总进步幅度（如有多次考试）
                3. 分值结构：按题目类型统计得分率，识别强项和弱项题型
                4. 知识点得分表：统计每个知识点的出现次数、总分值、总得分、掌握率
            </content>
        </guideline>
        <guideline>
            <section>成绩趋势分析</section>
            <content>
                1. 纵向对比：绘制成绩变化曲线（如有2次以上考试），计算进步/退步幅度
                2. 稳定性评估：计算得分率波动范围，评估发挥稳定性
                3. 模块变化：分析各知识模块在不同考试中的表现变化趋势
            </content>
        </guideline>
        <guideline>
            <section>知识点掌握度诊断</section>
            <content>
                1. 高频失分知识点：按失分率排序，列出薄弱点
                2. 掌握程度三色标注：绿色（≥85%）、黄色（70%-85%）、红色（＜70%）
                3. 知识模块分类：概念理解类、计算应用类、记忆背诵类、综合迁移类
            </content>
        </guideline>
        <guideline>
            <section>归因分析</section>
            <content>
                1. 知识层面：知识点掌握不牢固、概念理解偏差
                2. 方法层面：解题技巧不足、时间分配不当
                3. 习惯层面：审题不仔细、计算粗心、书写不规范
                4. 心理层面：考试焦虑、粗心大意
            </content>
        </guideline>
        <guideline>
            <section>改进计划</section>
            <content>
                1. 短期（1-2周）：针对薄弱知识点进行专项练习
                2. 中期（1个月）：建立错题本，定期复习巩固
                3. 长期（学期末）：形成系统的学习方法，提升综合能力
            </content>
        </guideline>
    </analysis_guidelines>
    <example_analysis_snippet>
        <input_example>
            <![CDATA[
学科：数学，考试2场
第一次考试：总分100，得分75
- 题目1：知识点[函数单调性, 求导]，得分5/10
- 题目2：知识点[极限计算]，得分8/10

第二次考试：总分100，得分82
- 题目1：知识点[函数单调性, 求导]，得分9/10
- 题目2：知识点[极限计算]，得分6/10
            ]]>
        </input_example>
        <output_example>
            <![CDATA[
# 学科深度分析报告 - 数学

## 一、基础数据概览

| 考试名称 | 考试日期 | 总分 | 得分 | 得分率 |
|---------|---------|------|------|-------|
| 期末考试1 | 2024-01 | 100 | 75 | 75% |
| 期末考试2 | 2024-02 | 100 | 82 | 82% |

**整体表现**：平均得分率 78.5%，进步幅度 +7%

## 二、成绩趋势分析

### 纵向对比
- 第二次考试比第一次提高7分，进步幅度9.3%
- 得分率从75%提升至82%，呈现上升趋势

### 稳定性评估
- 两次考试得分率波动7%，表现较稳定

## 三、知识点掌握度诊断

| 知识点 | 出现次数 | 总分值 | 得分 | 掌握率 | 状态 |
|-------|---------|--------|------|--------|------|
| 函数单调性 | 2 | 20 | 14 | 70% | 🟡 |
| 求导 | 2 | 20 | 14 | 70% | 🟡 |
| 极限计算 | 2 | 20 | 14 | 70% | 🟡 |

### 高频失分知识点
1. 函数单调性与求导结合应用
2. 极限计算的技巧掌握

## 四、归因分析

### 知识层面
- 对导数与函数单调性的结合应用理解不够深入
- 极限计算的基本方法掌握较好，但复杂题型处理能力不足

### 方法层面
- 解题思路较为单一，缺乏多角度分析能力
- 对综合题型的解题技巧需要加强

### 习惯层面
- 审题时对关键条件圈画不够仔细
- 计算过程中容易出现粗心错误

## 五、改进计划

### 短期目标（1-2周）
- [ ] 每天完成5道函数单调性相关练习题
- [ ] 整理导数与函数结合的解题思路笔记

### 中期目标（1个月）
- [ ] 建立错题本，记录每种题型的解题方法
- [ ] 每周进行一次知识点综合测试

### 长期目标（学期末）
- [ ] 形成系统的数学解题思维
- [ ] 争取下次考试得分率达到90%以上

## 六、学习建议

1. **强化基础**：加强函数与导数基础概念的理解
2. **专项突破**：针对极限计算进行专项训练
3. **综合应用**：多做综合题型，提升知识迁移能力
4. **规范习惯**：养成仔细审题、规范书写的好习惯
            ]]>
        </output_example>
    </example_analysis_snippet>
</agent_prompt>
"""

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
