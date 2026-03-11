import json
import re
from typing import Any, Dict, List, Optional, Union
from logger import logger, LOG_CATEGORIES

class JSONProcessor:
    """
    统一的JSON处理工具类
    负责AI响应的解析、验证、清理和错误处理
    """

    @staticmethod
    def clean_json_string(json_str: str) -> str:
        """
        清洗AI返回的JSON字符串，去除各种干扰标记
        """
        if not json_str:
            return "{}"

        clean_str = json_str.strip()

        # 移除Markdown代码块标记 ```json 或 ```
        if '```json' in clean_str:
            clean_str = clean_str.split('```json')[1]
        elif '```' in clean_str:
            clean_str = clean_str.split('```')[1]

        # 处理可能的描述文字前缀（如 "共处理3张图片，识别到5道试题。"）
        # 找到最后一个 ] 或 } 之后的位置
        if ']' in clean_str or '}' in clean_str:
            last_bracket = max(clean_str.rfind(']'), clean_str.rfind('}'))
            if last_bracket != -1:
                potential_json = clean_str[last_bracket+1:].strip()
                if potential_json.startswith('[') or potential_json.startswith('{'):
                    clean_str = potential_json

        # 处理可能的纯文本前缀（如 "共处理3张图片..."）
        # 找到第一个 [ 或 { 的位置
        first_bracket = min(
            clean_str.find('[') if '[' in clean_str else float('inf'),
            clean_str.find('{') if '{' in clean_str else float('inf')
        )
        if first_bracket > 0 and first_bracket != float('inf'):
            clean_str = clean_str[first_bracket:]

        # 清理结尾的 ``` 和其他干扰字符
        clean_str = clean_str.replace('```', '').strip()

        return clean_str

    @staticmethod
    def parse_json(json_str: str, default: Any = None) -> Any:
        """
        解析JSON字符串，返回解析后的对象或默认值
        """
        cleaned = JSONProcessor.clean_json_string(json_str)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.log(
                LOG_CATEGORIES['ERROR_EXCEPTION'],
                'JSON解析失败',
                error=str(e),
                raw_snippet=json_str[:200]
            )
            return default

    @staticmethod
    def validate_and_normalize_vision_result(result: Any) -> Dict:
        """
        验证并规范化Vision Agent的返回结果
        支持新旧两种JSON格式
        """
        if not result:
            return {"is_exam_paper": False, "items": []}

        # 如果是字符串，尝试解析
        if isinstance(result, str):
            result = JSONProcessor.parse_json(result)

        if not isinstance(result, (dict, list)):
            return {"is_exam_paper": False, "items": []}

        # 处理数组格式（新格式：直接返回题目数组）
        if isinstance(result, list):
            return {
                "is_exam_paper": len(result) > 0,
                "items": result
            }

        # 处理字典格式（可能包含is_exam_paper字段）
        if isinstance(result, dict):
            # 兼容旧格式：检查items字段
            if "items" not in result:
                result["items"] = []

            # 兼容旧格式：没有is_exam_paper字段时，根据items判断
            if "is_exam_paper" not in result:
                result["is_exam_paper"] = len(result.get("items", [])) > 0

            # 规范化每个题目项的字段名（新旧兼容）
            normalized_items = []
            for item in result.get("items", []):
                normalized_item = JSONProcessor.normalize_question_item(item)
                normalized_items.append(normalized_item)

            result["items"] = normalized_items
            return result

        return {"is_exam_paper": False, "items": []}

    @staticmethod
    def normalize_question_item(item: Dict) -> Dict:
        """
        规范化题目项的字段名，支持新旧两种格式
        """
        if not isinstance(item, dict):
            return {}

        # 字段名映射（新字段名 -> 旧字段名兼容）
        field_mappings = {
            'question_number': ['questionNumber', 'index', 'question_index'],
            'question_stem': ['questionStem', 'text', 'ocr_text'],
            'student_answer': ['studentAnswer', 'user_answer'],
            'score': ['max_score', 'maxScore', 'score_value'],
            'reference_answer': ['referenceAnswer', 'standard_answer', 'standardAnswer'],
            'analysis': ['analysis_text'],
            'knowledge_point': ['knowledgePoint', 'knowledge_point', 'knowledge'],
            'bbox': ['bbox', 'coordinates', 'position']
        }

        normalized = {}
        for new_field, old_fields in field_mappings.items():
            # 先尝试新字段名
            if new_field in item:
                normalized[new_field] = item[new_field]
            else:
                # 尝试旧字段名
                for old_field in old_fields:
                    if old_field in item:
                        normalized[new_field] = item[old_field]
                        break
                else:
                    # 字段不存在，设置默认值
                    if new_field in ['question_number', 'question_stem', 'student_answer',
                                     'reference_answer', 'analysis', 'knowledge_point']:
                        normalized[new_field] = ''
                    elif new_field == 'score':
                        normalized[new_field] = '10'

        # 处理坐标
        if 'bbox' not in normalized:
            normalized['bbox'] = item.get('bbox', item.get('coordinates', []))

        return normalized

    @staticmethod
    def validate_vision_item(item: Dict) -> bool:
        """
        验证题目项是否包含必要字段
        """
        required_fields = ['question_number', 'question_stem']
        return all(field in item and item[field] for field in required_fields)

    @staticmethod
    def validate_and_normalize_metadata_result(result: Any) -> Dict:
        """
        验证并规范化Metadata Agent的返回结果
        """
        if not result:
            return {"knowledge_tags": []}

        if isinstance(result, str):
            result = JSONProcessor.parse_json(result, default={})

        if not isinstance(result, dict):
            return {"knowledge_tags": []}

        # 确保knowledge_tags是数组
        knowledge_tags = result.get('knowledge_tags', [])
        if isinstance(knowledge_tags, str):
            knowledge_tags = [knowledge_tags] if knowledge_tags else []
        elif not isinstance(knowledge_tags, list):
            knowledge_tags = []

        return {
            "knowledge_tags": knowledge_tags
        }

    @staticmethod
    def validate_and_normalize_grading_result(result: Any, max_score: int = 10) -> Dict:
        """
        验证并规范化Grading Agent的返回结果
        """
        default = {
            "standard_answer": "无法生成标准答案",
            "user_score": 0,
            "feedback": "评分失败，请检查输入",
            "earned_score": 0,
            "reference_answer": "",
            "analysis": "",
            "knowledge_point": ""
        }

        if not result:
            return default

        if isinstance(result, str):
            result = JSONProcessor.parse_json(result, default={})

        if not isinstance(result, dict):
            return default

        # 字段名兼容处理
        earned_score = result.get('earned_score', result.get('user_score', 0))
        try:
            earned_score = int(earned_score)
            earned_score = max(0, min(earned_score, max_score))
        except (ValueError, TypeError):
            earned_score = 0

        return {
            "standard_answer": result.get('standard_answer', result.get('reference_answer', '')),
            "reference_answer": result.get('reference_answer', result.get('standard_answer', '')),
            "user_score": earned_score,
            "earned_score": earned_score,
            "feedback": result.get('feedback', result.get('analysis', '')),
            "analysis": result.get('analysis', result.get('feedback', '')),
            "knowledge_point": result.get('knowledge_point', result.get('knowledge_point', ''))
        }

    @staticmethod
    def validate_and_normalize_analysis_result(result: Any) -> Dict:
        """
        验证并规范化Analysis Agent的返回结果
        支持新格式：exam_name, total_score, total_earned_score, summary
        """
        default = {
            "exam_name": "考试分析",
            "total_score": 0,
            "total_earned_score": 0,
            "summary": "分析生成失败",
            "score_analysis": {
                "total_score": 0,
                "total_earned_score": 0,
                "score_rate": "0%"
            }
        }

        if not result:
            return default

        if isinstance(result, str):
            result = JSONProcessor.parse_json(result, default={})

        if not isinstance(result, dict):
            return default

        exam_name = result.get('exam_name', '')
        total_score = result.get('total_score', 0)
        total_earned_score = result.get('total_earned_score', result.get('total_earned_score', 0))

        try:
            total_score = float(total_score) if total_score else 0
        except (ValueError, TypeError):
            total_score = 0

        try:
            total_earned_score = float(total_earned_score) if total_earned_score else 0
        except (ValueError, TypeError):
            total_earned_score = 0

        score_rate = "0%"
        if total_score > 0:
            score_rate = f"{(total_earned_score / total_score * 100):.1f}%"

        return {
            "exam_name": exam_name,
            "total_score": total_score,
            "total_earned_score": total_earned_score,
            "summary": result.get('summary', ''),
            "score_analysis": {
                "total_score": total_score,
                "total_earned_score": total_earned_score,
                "score_rate": score_rate
            }
        }

    @staticmethod
    def extract_questions_from_response(response: str) -> List[Dict]:
        """
        从AI响应中提取题目列表（专门处理Vision Agent）
        """
        cleaned = JSONProcessor.clean_json_string(response)

        # 尝试直接解析为数组
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [JSONProcessor.normalize_question_item(item) for item in data]
            elif isinstance(data, dict) and 'items' in data:
                return [JSONProcessor.normalize_question_item(item) for item in data.get('items', [])]
        except json.JSONDecodeError:
            pass

        # 尝试提取数组格式 [...]
        array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group())
                if isinstance(data, list):
                    return [JSONProcessor.normalize_question_item(item) for item in data]
            except json.JSONDecodeError:
                pass

        return []

    @staticmethod
    def create_error_response(error_type: str, message: str, details: Any = None) -> Dict:
        """
        创建标准化的错误响应
        """
        error_response = {
            "error": True,
            "error_type": error_type,
            "message": message
        }
        if details:
            error_response["details"] = str(details)

        logger.log(
            LOG_CATEGORIES['ERROR_EXCEPTION'],
            f"{error_type}: {message}",
            details=details
        )

        return error_response
