from flask import Blueprint, request, jsonify
from app import db
from app.models import Subject, Exam, Question, Prompt, Setting
from app.agents import VisionAgent, MetadataAgent, GradingAgent, AnalysisAgent
from app.agents.prompt_generator import init_prompts, get_prompt
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
import json
from logger import logger, LOG_CATEGORIES

api = Blueprint('api', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@api.route('/subjects', methods=['GET'])
def get_subjects():
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取学科列表请求')
    subjects = Subject.query.all()
    result = [s.to_dict() for s in subjects]
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取学科列表完成', count=len(result))
    return jsonify(result)


@api.route('/subjects', methods=['POST'])
def create_subject():
    logger.log(LOG_CATEGORIES['USER_ACTION'], '创建学科请求', data=request.get_json())
    data = request.get_json()
    subject = Subject(name=data.get('name'))
    db.session.add(subject)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '创建学科完成', subject_id=subject.id, subject_name=subject.name)
    return jsonify(subject.to_dict()), 201


@api.route('/subjects/<int:subject_id>', methods=['GET'])
def get_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取学科详情请求', subject_id=subject_id)
    subject = Subject.query.get_or_404(subject_id)
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取学科详情完成', subject_id=subject.id, subject_name=subject.name)
    return jsonify(subject.to_dict())


@api.route('/subjects/<int:subject_id>', methods=['PUT'])
def update_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '更新学科请求', subject_id=subject_id, data=request.get_json())
    subject = Subject.query.get_or_404(subject_id)
    data = request.get_json()
    subject.name = data.get('name', subject.name)
    subject.analysis_report = data.get('analysis_report', subject.analysis_report)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新学科完成', subject_id=subject.id, subject_name=subject.name)
    return jsonify(subject.to_dict())


@api.route('/subjects/<int:subject_id>', methods=['DELETE'])
def delete_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '删除学科请求', subject_id=subject_id)
    subject = Subject.query.get_or_404(subject_id)
    db.session.delete(subject)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除学科完成', subject_id=subject_id)
    return jsonify({'message': 'Subject deleted'})


@api.route('/subjects/<int:subject_id>/exams', methods=['GET'])
def get_exams(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取考试列表请求', subject_id=subject_id)
    exams = Exam.query.filter_by(subject_id=subject_id).order_by(Exam.date.desc()).all()
    result = [e.to_dict() for e in exams]
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取考试列表完成', subject_id=subject_id, count=len(result))
    return jsonify(result)


@api.route('/exams', methods=['POST'])
def create_exam():
    logger.log(LOG_CATEGORIES['USER_ACTION'], '创建考试请求', data=request.get_json())
    data = request.get_json()
    exam = Exam(
        subject_id=data.get('subject_id'),
        name=data.get('name'),
        date=datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    )
    db.session.add(exam)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '创建考试完成', exam_id=exam.id, exam_name=exam.name)
    return jsonify(exam.to_dict()), 201


@api.route('/exams/<int:exam_id>', methods=['GET'])
def get_exam(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取考试详情请求', exam_id=exam_id)
    exam = Exam.query.get_or_404(exam_id)
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取考试详情完成', exam_id=exam.id, exam_name=exam.name)
    return jsonify(exam.to_dict())


@api.route('/exams/<int:exam_id>', methods=['PUT'])
def update_exam(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '更新考试请求', exam_id=exam_id, data=request.get_json())
    exam = Exam.query.get_or_404(exam_id)
    data = request.get_json()
    exam.name = data.get('name', exam.name)
    exam.analysis_report = data.get('analysis_report', exam.analysis_report)
    if 'date' in data:
        exam.date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新考试完成', exam_id=exam.id, exam_name=exam.name)
    return jsonify(exam.to_dict())


@api.route('/exams/<int:exam_id>', methods=['DELETE'])
def delete_exam(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '删除考试请求', exam_id=exam_id)
    exam = Exam.query.get_or_404(exam_id)
    db.session.delete(exam)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除考试完成', exam_id=exam_id)
    return jsonify({'message': 'Exam deleted'})


@api.route('/exams/<int:exam_id>/questions', methods=['GET'])
def get_questions(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取题目列表请求', exam_id=exam_id)
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.id).all()
    result = [q.to_dict() for q in questions]
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取题目列表完成', exam_id=exam_id, count=len(result))
    return jsonify(result)


@api.route('/questions/<int:question_id>', methods=['GET'])
def get_question(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取题目详情请求', question_id=question_id)
    question = Question.query.get_or_404(question_id)
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取题目详情完成', question_id=question.id)
    return jsonify(question.to_dict())


@api.route('/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '更新题目请求', question_id=question_id, data=request.get_json())
    question = Question.query.get_or_404(question_id)
    data = request.get_json()
    
    if 'question_index' in data:
        question.question_index = data['question_index']
    if 'ocr_text' in data:
        question.ocr_text = data['ocr_text']
    if 'max_score' in data:
        question.max_score = data['max_score']
    if 'user_answer_text' in data:
        question.user_answer_text = data['user_answer_text']
    if 'coordinates' in data:
        question.coordinates = json.dumps(data['coordinates'])
    if 'knowledge_tags' in data:
        question.knowledge_tags = json.dumps(data['knowledge_tags'])
    if 'difficulty' in data:
        question.difficulty = data['difficulty']
    if 'user_score' in data:
        question.user_score = data['user_score']
    if 'standard_answer' in data:
        question.standard_answer = data['standard_answer']
    if 'feedback' in data:
        question.feedback = data['feedback']
    
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新题目完成', question_id=question.id)
    return jsonify(question.to_dict())


@api.route('/upload', methods=['POST'])
def upload_image():
    logger.log(LOG_CATEGORIES['USER_ACTION'], '文件上传请求', filename=request.files.get('file', {}).filename, exam_id=request.form.get('exam_id'))
    
    if 'file' not in request.files:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '文件上传失败', error='No file part')
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    exam_id = request.form.get('exam_id')
    extract = request.form.get('extract', 'false').lower() == 'true'
    
    if file.filename == '':
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '文件上传失败', error='No selected file')
        return jsonify({'error': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        upload_folder = os.getenv('UPLOAD_FOLDER', 'app/static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, unique_filename)
        file.save(filepath)
        
        relative_path = f"/static/uploads/{unique_filename}"
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '文件保存成功', filepath=relative_path)
        
        questions_data = []
        vision_result = {}
        
        # 只有当extract为true时才提取题目
        if extract:
            vision_agent = VisionAgent()
            custom_prompt = get_prompt('vision')
            vision_result = vision_agent.analyze(filepath, custom_prompt)
            
            if vision_result.get('is_exam_paper'):
                for item in vision_result.get('items', []):
                    question = Question(
                        exam_id=exam_id,
                        question_index=item.get('index', ''),
                        ocr_text=item.get('text', ''),
                        coordinates=json.dumps(item.get('bbox', [])),
                        image_path=relative_path
                    )
                    db.session.add(question)
                    questions_data.append(question)
                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '试卷识别成功', question_count=len(questions_data))
            else:
                # 如果未检测到试卷，创建一个默认题目
                question = Question(
                    exam_id=exam_id,
                    question_index='1',
                    ocr_text='未检测到题目，请手动输入',
                    coordinates=json.dumps([]),
                    image_path=relative_path
                )
                db.session.add(question)
                questions_data.append(question)
                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '未检测到试卷，创建默认题目')
        else:
            # 不提取题目，只创建一个默认题目
            question = Question(
                exam_id=exam_id,
                question_index='1',
                ocr_text='请点击"提取题目"按钮提取题目',
                coordinates=json.dumps([]),
                image_path=relative_path
            )
            db.session.add(question)
            questions_data.append(question)
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '文件上传成功，等待提取题目')
        
        db.session.commit()
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '题目数据保存成功', question_count=len(questions_data))
        
        return jsonify({
            'image_path': relative_path,
            'vision_result': vision_result,
            'questions': [q.to_dict() for q in questions_data]
        })
    
    logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '文件上传失败', error='Invalid file type')
    return jsonify({'error': 'Invalid file type'}), 400


@api.route('/extract-questions', methods=['POST'])
def extract_questions():
    logger.log(LOG_CATEGORIES['USER_ACTION'], '提取题目请求', image_path=request.form.get('image_path'), exam_id=request.form.get('exam_id'))
    
    image_path = request.form.get('image_path')
    exam_id = request.form.get('exam_id')
    
    if not image_path:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error='No image path provided')
        return jsonify({'error': 'No image path provided'}), 400
    
    if not exam_id:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error='No exam id provided')
        return jsonify({'error': 'No exam id provided'}), 400
    
    # 转换相对路径为绝对路径
    if image_path.startswith('/'):
        image_path = image_path[1:]  # 移除开头的斜杠
    
    # 构建正确的路径：app/static/uploads/filename
    # 确保路径格式正确，避免os.path.join的问题
    if not image_path.startswith('app/'):
        # 直接拼接路径，确保app目录被正确添加
        image_path = 'app/' + image_path
    
    # 使用应用根目录作为基础路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    # 构建绝对路径
    absolute_path = os.path.join(project_root, image_path.replace('/', os.sep))
    
    if not os.path.exists(absolute_path):
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error='Image file not found', image_path=absolute_path)
        return jsonify({'error': 'Image file not found'}), 404
    
    # 提取题目
    vision_agent = VisionAgent()
    custom_prompt = get_prompt('vision')
    vision_result = vision_agent.analyze(absolute_path, custom_prompt)
    
    # 检查是否有错误
    if vision_result.get('error'):
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error=vision_result.get('error'))
        return jsonify({'error': vision_result.get('error')}), 500
    
    questions_data = []
    if vision_result.get('is_exam_paper'):
        # 删除现有的题目
        Question.query.filter_by(exam_id=exam_id).delete()
        
        for item in vision_result.get('items', []):
            question = Question(
                exam_id=exam_id,
                question_index=item.get('index', ''),
                ocr_text=item.get('text', ''),
                coordinates=json.dumps(item.get('bbox', [])),
                image_path=request.form.get('image_path')
            )
            db.session.add(question)
            questions_data.append(question)
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '试卷识别成功', question_count=len(questions_data))
    else:
        # 如果未检测到试卷，创建一个默认题目
        question = Question(
            exam_id=exam_id,
            question_index='1',
            ocr_text='未检测到题目，请手动输入',
            coordinates=json.dumps([]),
            image_path=request.form.get('image_path')
        )
        db.session.add(question)
        questions_data.append(question)
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '未检测到试卷，创建默认题目')
    
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '题目数据保存成功', question_count=len(questions_data))
    
    return jsonify({
        'vision_result': vision_result,
        'questions': [q.to_dict() for q in questions_data]
    })


@api.route('/analyze-metadata/<int:question_id>', methods=['POST'])
def analyze_metadata(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '分析题目元数据请求', question_id=question_id)
    
    question = Question.query.get_or_404(question_id)
    
    metadata_agent = MetadataAgent()
    custom_prompt = get_prompt('metadata')
    result = metadata_agent.analyze(question.ocr_text, custom_prompt)
    
    question.knowledge_tags = json.dumps(result.get('knowledge_tags', []))
    question.difficulty = result.get('difficulty', 3)
    db.session.commit()
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '题目元数据分析完成', question_id=question_id, knowledge_tags=result.get('knowledge_tags', []), difficulty=result.get('difficulty', 3))
    return jsonify(question.to_dict())


@api.route('/grade/<int:question_id>', methods=['POST'])
def grade_question(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '题目评分请求', question_id=question_id)
    
    question = Question.query.get_or_404(question_id)
    
    grading_agent = GradingAgent()
    custom_prompt = get_prompt('grading')
    result = grading_agent.grade(
        question.ocr_text,
        question.user_answer_text,
        question.max_score,
        custom_prompt
    )
    
    question.standard_answer = result.get('standard_answer', '')
    question.user_score = result.get('user_score', 0)
    question.feedback = result.get('feedback', '')
    db.session.commit()
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '题目评分完成', question_id=question_id, score=result.get('user_score', 0), max_score=question.max_score)
    return jsonify(question.to_dict())


@api.route('/grade-all/<int:exam_id>', methods=['POST'])
def grade_all_questions(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '批量评分请求', exam_id=exam_id)
    
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam_id).all()
    
    grading_agent = GradingAgent()
    custom_prompt = get_prompt('grading')
    
    results = []
    for question in questions:
        result = grading_agent.grade(
            question.ocr_text,
            question.user_answer_text,
            question.max_score,
            custom_prompt
        )
        question.standard_answer = result.get('standard_answer', '')
        question.user_score = result.get('user_score', 0)
        question.feedback = result.get('feedback', '')
        results.append(question.to_dict())
    
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '批量评分完成', exam_id=exam_id, question_count=len(questions))
    return jsonify(results)


@api.route('/analyze-exam/<int:exam_id>', methods=['POST'])
def analyze_exam(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '考试分析请求', exam_id=exam_id)
    
    exam = Exam.query.get_or_404(exam_id)
    subject = Subject.query.get(exam.subject_id)
    questions = Question.query.filter_by(exam_id=exam_id).all()
    
    exam_data = {
        'name': exam.name,
        'date': exam.date.isoformat() if exam.date else '',
        'subject_name': subject.name if subject else '',
        'questions': [q.to_dict() for q in questions]
    }
    
    analysis_agent = AnalysisAgent()
    custom_prompt = get_prompt('analysis')
    result = analysis_agent.analyze(exam_data, custom_prompt)
    
    exam.analysis_report = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '考试分析完成', exam_id=exam_id, exam_name=exam.name)
    return jsonify(result)


@api.route('/prompts', methods=['GET'])
def get_prompts():
    prompts = Prompt.query.all()
    return jsonify([p.to_dict() for p in prompts])


@api.route('/prompts/<int:prompt_id>', methods=['GET'])
def get_prompt_by_id(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    return jsonify(prompt.to_dict())


@api.route('/prompts/<int:prompt_id>', methods=['PUT'])
def update_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    data = request.get_json()
    
    prompt.system_prompt = data.get('system_prompt', prompt.system_prompt)
    prompt.role = data.get('role', prompt.role)
    prompt.description = data.get('description', prompt.description)
    prompt.is_active = data.get('is_active', prompt.is_active)
    
    db.session.commit()
    return jsonify(prompt.to_dict())


@api.route('/prompts/<int:prompt_id>/reset', methods=['POST'])
def reset_prompt(prompt_id):
    from app.agents.ai_agents import VisionAgent, MetadataAgent, GradingAgent, AnalysisAgent
    
    prompt = Prompt.query.get_or_404(prompt_id)
    
    defaults = {
        'vision': VisionAgent.DEFAULT_PROMPT,
        'metadata': MetadataAgent.DEFAULT_PROMPT,
        'grading': GradingAgent.DEFAULT_PROMPT,
        'analysis': AnalysisAgent.DEFAULT_PROMPT
    }
    
    prompt.system_prompt = defaults.get(prompt.name, prompt.system_prompt)
    db.session.commit()
    
    return jsonify(prompt.to_dict())


@api.route('/settings', methods=['GET'])
def get_settings():
    settings = Setting.query.all()
    settings_dict = {}
    for setting in settings:
        settings_dict[setting.key] = setting.value
    
    # Default values if not in database
    default_settings = {
        'api_key': os.getenv('AI_API_KEY', 'your-api-key-here'),
        'api_base': os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'model_vision': os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro'),
        'model_grading': os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini'),
        'model_analysis': os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')
    }
    
    for key, default_value in default_settings.items():
        if key not in settings_dict:
            settings_dict[key] = default_value
    
    return jsonify(settings_dict)


@api.route('/settings', methods=['PUT'])
def update_settings():
    data = request.get_json()
    logger.log(LOG_CATEGORIES['USER_ACTION'], '更新设置请求', settings=list(data.keys()))
    
    for key, value in data.items():
        # 不记录API密钥等敏感信息
        if key != 'api_key':
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新设置', key=key, value=value)
        else:
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新设置', key=key, value='[REDACTED]')
        
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(
                key=key,
                value=value
            )
            db.session.add(setting)
    
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '设置更新完成')
    return jsonify({'message': 'Settings updated successfully'})


@api.route('/settings/reset', methods=['POST'])
def reset_settings():
    # Delete all settings
    Setting.query.delete()
    db.session.commit()
    
    # Return default settings
    default_settings = {
        'api_key': os.getenv('AI_API_KEY', 'your-api-key-here'),
        'api_base': os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'model_vision': os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro'),
        'model_grading': os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini'),
        'model_analysis': os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')
    }
    
    return jsonify(default_settings)


@api.route('/dashboard/<int:subject_id>', methods=['GET'])
def get_dashboard(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    exams = Exam.query.filter_by(subject_id=subject_id).order_by(Exam.date).all()
    
    exam_data = []
    for exam in exams:
        questions = Question.query.filter_by(exam_id=exam.id).all()
        total_score = sum(q.max_score or 0 for q in questions)
        user_score = sum(q.user_score or 0 for q in questions)
        
        exam_data.append({
            'id': exam.id,
            'name': exam.name,
            'date': exam.date.isoformat() if exam.date else '',
            'total_score': total_score,
            'user_score': user_score,
            'score_rate': round(user_score / total_score * 100, 1) if total_score > 0 else 0
        })
    
    return jsonify({
        'subject': subject.to_dict(),
        'exams': exam_data
    })
