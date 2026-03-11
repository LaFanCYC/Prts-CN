import os
from app.models import Prompt
from app import db

__all__ = ['VisionAgent', 'GradingAgent', 'AnalysisAgent', 'init_prompts', 'get_prompt', 'load_prompt_from_file']

def load_prompt_from_file(name):
    """
    从prompts文件夹中读取提示词文件

    Args:
        name: 提示词名称（vision, grading, analysis, Subject_Ana）

    Returns:
        str: 提示词内容，如果文件不存在返回None
    """
    prompt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'prompts')
    file_path = os.path.join(prompt_dir, f'{name}.txt')

    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 如果文件内容以XML格式开头，尝试提取纯文本内容
                if content.strip().startswith('<?xml') or '<agent_prompt>' in content:
                    # 尝试提取role和description标签之间的内容作为提示词
                    # 这里我们保留完整内容，因为AI可以理解XML格式的提示词
                    pass
                return content
    except Exception as e:
        from logger import logger, LOG_CATEGORIES
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], f'读取提示词文件失败: {name}.txt', error=str(e))

    return None


# 导入Agent类以获取默认提示词作为后备
from app.agents.ai_agents import VisionAgent, GradingAgent, AnalysisAgent, SubjectAnalysisAgent

DEFAULT_PROMPTS = [
    {
        'name': 'vision',
        'role': 'Vision',
        'system_prompt': None,
        'description': '用于识别试卷图片，提取题目信息和坐标'
    },
    {
        'name': 'grading',
        'role': 'Grade',
        'system_prompt': None,
        'description': '用于批改题目，给出分数和点评'
    },
    {
        'name': 'analysis',
        'role': 'Exam_Analyze',
        'system_prompt': None,
        'description': '用于生成考试分析报告'
    },
    {
        'name': 'Subject_Ana',
        'role': 'Subject_Analyze',
        'system_prompt': None,
        'description': '用于生成学科综合分析报告'
    }
]

def init_prompts():
    """
    初始化提示词配置
    优先从prompts文件夹加载，如果文件不存在则使用Agent类的默认提示词
    """
    for prompt_data in DEFAULT_PROMPTS:
        name = prompt_data['name']

        # 尝试从文件加载提示词
        file_prompt = load_prompt_from_file(name)

        # 确定使用的提示词
        if file_prompt:
            system_prompt = file_prompt
        else:
            if name == 'vision':
                system_prompt = VisionAgent.DEFAULT_PROMPT
            elif name == 'grading':
                system_prompt = GradingAgent.DEFAULT_PROMPT
            elif name == 'analysis':
                system_prompt = AnalysisAgent.DEFAULT_PROMPT
            elif name == 'Subject_Ana':
                system_prompt = load_prompt_from_file('Subject_Ana') or ''
            else:
                system_prompt = ''

        # 检查是否已存在
        existing = Prompt.query.filter_by(name=name).first()

        if existing:
            # 更新已有的提示词
            existing.role = prompt_data['role']
            existing.system_prompt = system_prompt
            existing.description = prompt_data['description']
        else:
            # 创建新的提示词记录
            new_prompt = Prompt(
                name=name,
                role=prompt_data['role'],
                system_prompt=system_prompt,
                description=prompt_data['description'],
                is_active=True
            )
            db.session.add(new_prompt)

    db.session.commit()


def get_prompt(name):
    """
    获取提示词设置

    优先级：
    1. 数据库中活跃的提示词
    2. prompts文件夹中的txt文件
    3. Agent类的默认提示词
    """
    # 首先尝试从数据库获取
    prompt = Prompt.query.filter_by(name=name, is_active=True).first()
    if prompt and prompt.system_prompt:
        return prompt.system_prompt

    # 其次尝试从文件加载
    file_prompt = load_prompt_from_file(name)
    if file_prompt:
        return file_prompt

    # 最后使用Agent类的默认提示词
    if name == 'vision':
        return VisionAgent.DEFAULT_PROMPT
    elif name == 'grading':
        return GradingAgent.DEFAULT_PROMPT
    elif name == 'analysis':
        return AnalysisAgent.DEFAULT_PROMPT

    return None


def reset_prompt_to_default(name):
    """
    重置指定提示词为默认提示词（从文件或Agent类）

    Args:
        name: 提示词名称

    Returns:
        str: 重置后的提示词内容
    """
    file_prompt = load_prompt_from_file(name)

    if file_prompt:
        system_prompt = file_prompt
    else:
        if name == 'vision':
            system_prompt = VisionAgent.DEFAULT_PROMPT
        elif name == 'grading':
            system_prompt = GradingAgent.DEFAULT_PROMPT
        elif name == 'analysis':
            system_prompt = AnalysisAgent.DEFAULT_PROMPT
        else:
            return None

    # 更新数据库
    prompt = Prompt.query.filter_by(name=name).first()
    if prompt:
        prompt.system_prompt = system_prompt
        db.session.commit()

    return system_prompt
