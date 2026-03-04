from app.agents.ai_agents import VisionAgent, MetadataAgent, GradingAgent, AnalysisAgent
from app.models import Prompt
from app import db

__all__ = ['VisionAgent', 'MetadataAgent', 'GradingAgent', 'AnalysisAgent', 'init_prompts', 'get_prompt']

DEFAULT_PROMPTS = [
    {
        'name': 'vision',
        'role': '试卷数字化专家',
        'system_prompt': VisionAgent.DEFAULT_PROMPT,
        'description': '用于识别试卷图片，提取题目信息和坐标'
    },
    {
        'name': 'metadata',
        'role': '教育专家',
        'system_prompt': MetadataAgent.DEFAULT_PROMPT,
        'description': '用于分析题干，提取知识点和难度'
    },
    {
        'name': 'grading',
        'role': '阅卷老师',
        'system_prompt': GradingAgent.DEFAULT_PROMPT,
        'description': '用于批改题目，给出分数和点评'
    },
    {
        'name': 'analysis',
        'role': '教育分析师',
        'system_prompt': AnalysisAgent.DEFAULT_PROMPT,
        'description': '用于生成考试分析报告'
    }
]

def init_prompts():
    for prompt_data in DEFAULT_PROMPTS:
        existing = Prompt.query.filter_by(name=prompt_data['name']).first()
        if not existing:
            new_prompt = Prompt(
                name=prompt_data['name'],
                role=prompt_data['role'],
                system_prompt=prompt_data['system_prompt'],
                description=prompt_data['description'],
                is_active=True
            )
            db.session.add(new_prompt)
    db.session.commit()

def get_prompt(name):
    prompt = Prompt.query.filter_by(name=name, is_active=True).first()
    return prompt.system_prompt if prompt else None
