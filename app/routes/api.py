from flask import Blueprint, request, jsonify
from app import db
from app.models import Subject, Exam, Question, Prompt, Setting
from app.agents import VisionAgent, MetadataAgent, GradingAgent, AnalysisAgent, SubjectAnalysisAgent
from app.agents.prompt_generator import init_prompts, get_prompt
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
import json
from logger import logger, LOG_CATEGORIES

api = Blueprint('api', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def normalize_api_base(url):
    """规范化API基础URL，兼容完整路径和简写形式
    
    - 如果URL已经包含完整的v3端点（如ark.cn-beijing.volces.com/api/v3），直接返回
    - 如果URL是简写形式，添加/v1后缀
    """
    if not url:
        return 'https://ark.cn-beijing.volces.com/api/v3'

    url = url.strip().rstrip('/')

    if '/chat/completions' in url or '/v1/models' in url:
        base_url = url.rsplit('/chat/completions', 1)[0].rsplit('/v1/models', 1)[0]
        if '/v1' in base_url:
            return base_url
        else:
            return base_url + '/v1'

    if url.endswith('/v1'):
        return url

    if '/v1/' in url:
        return url
    
    if 'volces.com/api/v3' in url:
        return url

    if '/v1/' not in url:
        return url + '/v1'

    return url


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
    name = data.get('name')
    
    # 检查学科名称是否重复
    existing_subject = Subject.query.filter_by(name=name).first()
    if existing_subject:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '创建学科失败', error='学科名称已存在', name=name)
        return jsonify({'error': '学科名称已存在'}), 400
    
    subject = Subject(name=name)
    db.session.add(subject)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '创建学科完成', subject_id=subject.id, subject_name=subject.name)
    return jsonify(subject.to_dict()), 201


@api.route('/subjects/<int:subject_id>', methods=['GET'])
def get_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '获取学科详情请求', subject_id=subject_id)
    subject = Subject.query.get_or_404(subject_id)
    subject_dict = subject.to_dict()
    
    if subject_dict.get('analysis_report'):
        try:
            if isinstance(subject_dict['analysis_report'], str):
                subject_dict['analysis_report'] = json.loads(subject_dict['analysis_report'])
        except:
            pass
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取学科详情完成', subject_id=subject.id, subject_name=subject.name)
    return jsonify(subject_dict)


@api.route('/subjects/<int:subject_id>', methods=['PUT'])
def update_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '更新学科请求', subject_id=subject_id, data=request.get_json())
    subject = Subject.query.get_or_404(subject_id)
    data = request.get_json()
    new_name = data.get('name', subject.name)
    
    # 检查学科名称是否重复（排除当前学科）
    if new_name != subject.name:
        existing_subject = Subject.query.filter_by(name=new_name).first()
        if existing_subject:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '更新学科失败', error='学科名称已存在', name=new_name)
            return jsonify({'error': '学科名称已存在'}), 400
    
    subject.name = new_name
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
    subject_id = data.get('subject_id')
    name = data.get('name')
    date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
    
    # 检查同一学科内考试名称是否重复
    existing_exam = Exam.query.filter_by(subject_id=subject_id, name=name).first()
    if existing_exam:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '创建考试失败', error='考试名称已存在', name=name, subject_id=subject_id)
        return jsonify({'error': '考试名称已存在'}), 400
    
    exam = Exam(
        subject_id=subject_id,
        name=name,
        date=date
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
    new_name = data.get('name', exam.name)
    
    # 检查同一学科内考试名称是否重复（排除当前考试）
    if new_name != exam.name:
        existing_exam = Exam.query.filter_by(subject_id=exam.subject_id, name=new_name).first()
        if existing_exam:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '更新考试失败', error='考试名称已存在', name=new_name, subject_id=exam.subject_id)
            return jsonify({'error': '考试名称已存在'}), 400
    
    exam.name = new_name
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
    
    image_paths = exam.get_image_paths()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    
    for img_path in image_paths:
        if img_path.startswith('/'):
            img_path = img_path[1:]
        full_path = os.path.join(project_root, img_path.replace('/', os.sep))
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除图片文件', path=full_path)
            except Exception as e:
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '删除图片文件失败', path=full_path, error=str(e))
    
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
    if 'user_score' in data:
        question.user_score = data['user_score']
    if 'standard_answer' in data:
        question.standard_answer = data['standard_answer']
    if 'feedback' in data:
        question.feedback = data['feedback']
    if 'student_answer' in data:
        question.student_answer = data['student_answer']
    if 'analysis' in data:
        question.analysis = data['analysis']
    
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '更新题目完成', question_id=question.id)
    return jsonify(question.to_dict())


@api.route('/exams/<int:exam_id>/questions', methods=['POST'])
def create_question(exam_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '创建题目请求', exam_id=exam_id, data=request.get_json())
    data = request.get_json()
    
    question = Question(
        exam_id=exam_id,
        question_index=data.get('question_index', ''),
        ocr_text=data.get('ocr_text', ''),
        max_score=data.get('max_score', 5),
        coordinates=json.dumps(data.get('coordinates', [])),
        knowledge_tags=json.dumps(data.get('knowledge_tags', [])),
        user_answer_text=data.get('user_answer_text', ''),
        standard_answer=data.get('standard_answer', ''),
        user_score=data.get('user_score'),
        feedback=data.get('feedback', '')
    )
    
    db.session.add(question)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '创建题目完成', question_id=question.id)
    return jsonify(question.to_dict()), 201


@api.route('/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '删除题目请求', question_id=question_id)
    question = Question.query.get_or_404(question_id)
    
    db.session.delete(question)
    db.session.commit()
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除题目完成', question_id=question_id)
    return jsonify({'message': 'Question deleted successfully'})


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

            settings = Setting.query.all()
            settings_dict = {s.key: s.value for s in settings}
            api_key = settings_dict.get('vision_api_key') or settings_dict.get('api_key') or os.getenv('AI_VISION_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings_dict.get('vision_api_base') or settings_dict.get('api_base') or os.getenv('AI_VISION_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            api_base = normalize_api_base(api_base)
            model = settings_dict.get('model_vision') or os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro')

            if api_key and api_key.strip():
                vision_agent.client.api_key = api_key
            if api_base and api_base.strip():
                vision_agent.client.base_url = api_base
            if model and model.strip():
                vision_agent.vision_model = model

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'VisionAgent 使用设置',
                      api_key_set=bool(api_key), api_base=api_base, model=model)

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取视觉模型Prompt', prompt=custom_prompt[:200] if custom_prompt else 'None')
            vision_result = vision_agent.analyze(filepath, custom_prompt)
            
            if vision_result.get('is_exam_paper'):
                for item in vision_result.get('items', []):
                    question = Question(
                        exam_id=exam_id,
                        question_index=item.get('index') or item.get('question_number') or item.get('questionNumber', ''),
                        ocr_text=item.get('text') or item.get('question_stem') or item.get('questionStem', ''),
                        student_answer=item.get('student_answer', ''),
                        analysis=item.get('analysis', ''),
                        standard_answer=item.get('reference_answer', ''),
                        knowledge_tags=json.dumps([item.get('knowledge_point', '')]) if item.get('knowledge_point') else '[]',
                        max_score=float(item.get('score', 10)) if item.get('score') else 10.0,
                        coordinates=json.dumps(item.get('bbox', []) if item.get('bbox') else item.get('bbox', [])),
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
        
        exam = Exam.query.get(exam_id)
        if exam:
            image_paths = exam.get_image_paths()
            if relative_path not in image_paths:
                image_paths.append(relative_path)
                exam.set_image_paths(image_paths)
                db.session.commit()
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '考试图片路径已更新', exam_id=exam_id, image_count=len(image_paths))
        
        return jsonify({
            'image_path': relative_path,
            'vision_result': vision_result,
            'questions': [q.to_dict() for q in questions_data],
            'exam': exam.to_dict()
        })
    
    logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '文件上传失败', error='Invalid file type')
    return jsonify({'error': 'Invalid file type'}), 400


@api.route('/exams/<int:exam_id>/images/<path:image_path>', methods=['DELETE'])
def delete_exam_image(exam_id, image_path):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '删除考试图片请求', exam_id=exam_id, image_path=image_path)
    
    exam = Exam.query.get_or_404(exam_id)
    
    image_paths = exam.get_image_paths()
    image_path_normalized = '/' + image_path if not image_path.startswith('/') else image_path
    
    if image_path_normalized not in image_paths:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片不在考试中', image_path=image_path_normalized)
        return jsonify({'error': 'Image not found in exam'}), 404
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    
    full_path = image_path_normalized.lstrip('/')
    absolute_path = os.path.join(project_root, full_path.replace('/', os.sep))
    
    if os.path.exists(absolute_path):
        try:
            os.remove(absolute_path)
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除图片文件成功', path=absolute_path)
        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '删除图片文件失败', error=str(e))
            return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500
    
    image_paths.remove(image_path_normalized)
    exam.set_image_paths(image_paths)
    db.session.commit()
    
    related_questions = Question.query.filter_by(exam_id=exam_id, image_path=image_path_normalized).all()
    for q in related_questions:
        db.session.delete(q)
    db.session.commit()
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '删除考试图片完成', exam_id=exam_id, remaining_images=len(image_paths))
    return jsonify({'message': 'Image deleted', 'remaining_images': image_paths})


@api.route('/extract-questions', methods=['POST'])
def extract_questions():
    try:
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
        
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '构建图片绝对路径', 
                  original_image_path=request.form.get('image_path'),
                  processed_image_path=image_path,
                  project_root=project_root,
                  absolute_path=absolute_path,
                  path_exists=os.path.exists(absolute_path))
        
        if not os.path.exists(absolute_path):
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error='Image file not found', image_path=absolute_path)
            return jsonify({'error': 'Image file not found'}), 404
        
        # 提取题目
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '开始提取题目', image_path=absolute_path)
        vision_agent = VisionAgent()
        custom_prompt = get_prompt('vision')

        settings = Setting.query.all()
        settings_dict = {s.key: s.value for s in settings}
        api_key = settings_dict.get('vision_api_key') or settings_dict.get('api_key') or os.getenv('AI_VISION_API_KEY') or os.getenv('AI_API_KEY')
        api_base = settings_dict.get('vision_api_base') or settings_dict.get('api_base') or os.getenv('AI_VISION_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
        api_base = normalize_api_base(api_base)
        model = settings_dict.get('model_vision') or os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro')

        if api_key and api_key.strip():
            vision_agent.client.api_key = api_key
        if api_base and api_base.strip():
            vision_agent.client.base_url = api_base
        if model and model.strip():
            vision_agent.vision_model = model

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'VisionAgent 使用设置',
                  api_key_set=bool(api_key), api_base=api_base, model=model)

        vision_result = vision_agent.analyze(absolute_path, custom_prompt)
        
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '视觉模型分析完成', vision_result=vision_result)
        
        # 检查是否有错误
        if vision_result.get('error'):
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目失败', error=vision_result.get('error'))
            return jsonify({'error': vision_result.get('error')}), 500
        
        questions_data = []
        if vision_result.get('is_exam_paper'):
            existing_questions = Question.query.filter_by(exam_id=exam_id).all()
            start_index = len(existing_questions) + 1
            
            for idx, item in enumerate(vision_result.get('items', [])):
                question = Question(
                    exam_id=exam_id,
                    question_index=str(start_index + idx),
                    ocr_text=item.get('text') or item.get('question_stem') or item.get('questionStem', ''),
                    student_answer=item.get('student_answer', ''),
                    analysis=item.get('analysis', ''),
                    standard_answer=item.get('reference_answer', ''),
                    knowledge_tags=json.dumps([item.get('knowledge_point', '')]) if item.get('knowledge_point') else '[]',
                    max_score=float(item.get('score', 10)) if item.get('score') else 10.0,
                    coordinates=json.dumps(item.get('bbox', []) if item.get('bbox') else item.get('bbox', [])),
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
    except Exception as e:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '提取题目过程中发生异常', error=str(e))
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@api.route('/extract-questions-batch', methods=['POST'])
def extract_questions_batch():
    try:
        logger.log(LOG_CATEGORIES['USER_ACTION'], '批量提取题目请求', exam_id=request.form.get('exam_id'))

        exam_id_str = request.form.get('exam_id')
        image_paths = request.form.getlist('image_paths')

        if not exam_id_str:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量提取题目失败', error='No exam id provided')
            return jsonify({'error': 'No exam id provided'}), 400

        if not image_paths:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量提取题目失败', error='No image paths provided')
            return jsonify({'error': 'No image paths provided'}), 400

        try:
            exam_id = int(exam_id_str)
        except ValueError:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量提取题目失败', error=f'Invalid exam id: {exam_id_str}')
            return jsonify({'error': f'Invalid exam id: {exam_id_str}'}), 400

        exam = Exam.query.get(exam_id)
        if not exam:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量提取题目失败', error=f'Exam not found: {exam_id}')
            return jsonify({'error': f'Exam not found: {exam_id}'}), 404

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '批量提取题目', exam_id=exam_id, image_count=len(image_paths))

        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))

        custom_prompt = get_prompt('vision')
        vision_agent = VisionAgent()

        settings = Setting.query.all()
        settings_dict = {s.key: s.value for s in settings}
        api_key = settings_dict.get('vision_api_key') or settings_dict.get('api_key') or os.getenv('AI_VISION_API_KEY') or os.getenv('AI_API_KEY')
        api_base = settings_dict.get('vision_api_base') or settings_dict.get('api_base') or os.getenv('AI_VISION_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
        api_base = normalize_api_base(api_base)
        model = settings_dict.get('model_vision') or os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro')

        if api_key and api_key.strip():
            vision_agent.client.api_key = api_key
        if api_base and api_base.strip():
            vision_agent.client.base_url = api_base
        if model and model.strip():
            vision_agent.vision_model = model

        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'VisionAgent 使用设置(批量)',
                  api_key_set=bool(api_key), api_base=api_base, model=model)

        existing_questions = Question.query.filter_by(exam_id=exam_id).all()
        start_index = len(existing_questions)
        
        all_questions = list(existing_questions)
        question_index = start_index + 1

        for idx, image_path in enumerate(image_paths):
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '处理图片', index=idx, path=image_path)
            
            if image_path.startswith('/'):
                image_path = image_path[1:]
            if not image_path.startswith('app/'):
                image_path = 'app/' + image_path

            absolute_path = os.path.join(project_root, image_path.replace('/', os.sep))

            if not os.path.exists(absolute_path):
                logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '图片文件不存在', image_path=absolute_path)
                continue

            vision_result = vision_agent.analyze(absolute_path, custom_prompt)
            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'Vision分析完成', path=image_path, is_exam_paper=vision_result.get('is_exam_paper'), item_count=len(vision_result.get('items', [])))

            if vision_result.get('is_exam_paper'):
                for item in vision_result.get('items', []):
                    question = Question(
                        exam_id=exam_id,
                        question_index=str(question_index),
                        ocr_text=item.get('text') or item.get('question_stem') or item.get('questionStem', ''),
                        student_answer=item.get('student_answer', ''),
                        analysis=item.get('analysis', ''),
                        standard_answer=item.get('reference_answer', ''),
                        knowledge_tags=json.dumps([item.get('knowledge_point', '')]) if item.get('knowledge_point') else '[]',
                        max_score=float(item.get('score', 10)) if item.get('score') else 10.0,
                        coordinates=json.dumps(item.get('bbox', []) if item.get('bbox') else item.get('bbox', [])),
                        image_path=image_path
                    )
                    db.session.add(question)
                    all_questions.append(question)
                    question_index += 1

        db.session.commit()
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '批量提取题目完成', question_count=len(all_questions))

        return jsonify({
            'questions': [q.to_dict() for q in all_questions]
        })

    except Exception as e:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量提取题目异常', error=str(e))
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500





@api.route('/grade/<int:question_id>', methods=['POST'])
def grade_question(question_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '题目评分请求', question_id=question_id)

    question = Question.query.get_or_404(question_id)

    grading_agent = GradingAgent()
    custom_prompt = get_prompt('grading')

    question_data = {
        'question_index': question.question_index,
        'question_number': question.question_index,
        'question_stem': question.ocr_text,
        'ocr_text': question.ocr_text,
        'student_answer': question.student_answer if hasattr(question, 'student_answer') else question.user_answer_text,
        'user_answer_text': question.user_answer_text,
        'score': question.max_score,
        'max_score': question.max_score
    }
    result = grading_agent.grade_question(question_data, custom_prompt)

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

    if not questions:
        return jsonify([])

    custom_prompt = get_prompt('grading')

    settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in settings}

    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '获取设置成功',
              keys=list(settings_dict.keys()))

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def grade_single_question(question):
        try:
            agent = GradingAgent()

            api_key = settings_dict.get('grading_api_key') or settings_dict.get('api_key') or os.getenv('AI_GRADING_API_KEY') or os.getenv('AI_API_KEY')
            api_base = settings_dict.get('grading_api_base') or settings_dict.get('api_base') or os.getenv('AI_GRADING_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
            api_base = normalize_api_base(api_base)
            model = settings_dict.get('model_grading') or os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini')

            if api_key and api_key.strip():
                agent.client.api_key = api_key
            if api_base and api_base.strip():
                agent.client.base_url = api_base
            if model and model.strip():
                agent.grading_model = model

            logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '使用设置进行评分',
                      api_key_set=bool(api_key),
                      api_base=api_base,
                      model=model)

            question_data = {
                'question_index': question.question_index,
                'question_number': question.question_index,
                'question_stem': question.ocr_text,
                'ocr_text': question.ocr_text,
                'student_answer': question.student_answer if hasattr(question, 'student_answer') else question.user_answer_text,
                'user_answer_text': question.user_answer_text,
                'score': question.max_score,
                'max_score': question.max_score
            }
            result = agent.grade_question(question_data, custom_prompt)
            return question.id, result, None
        except Exception as e:
            logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], 'GradingAgent评分失败', error=str(e), question_id=question.id)
            return question.id, None, str(e)

    results = []
    question_map = {}
    failed_count = 0
    error_messages = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_question = {executor.submit(grade_single_question, q): q for q in questions}

        for future in as_completed(future_to_question):
            question_id, result, error = future.result()
            if error:
                failed_count += 1
                error_messages.append(f"题目{question_id}: {error}")
                question_map[question_id] = {
                    'standard_answer': '',
                    'user_score': 0,
                    'feedback': f'评分失败: {error}'
                }
            else:
                question_map[question_id] = result

    for question in questions:
        result = question_map.get(question.id, {})
        question.standard_answer = result.get('standard_answer', '')
        question.user_score = result.get('user_score', 0)
        question.feedback = result.get('feedback', '')
        
        knowledge_tags = result.get('knowledge_tags', [])
        if knowledge_tags:
            if isinstance(knowledge_tags, list):
                question.knowledge_tags = json.dumps(knowledge_tags)
            else:
                question.knowledge_tags = json.dumps([knowledge_tags])
        
        results.append(question.to_dict())

    db.session.commit()

    if failed_count > 0:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '批量评分完成但有失败',
                   exam_id=exam_id,
                   question_count=len(questions),
                   failed_count=failed_count,
                   errors=error_messages[:5])
    else:
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '批量评分完成',
                   exam_id=exam_id,
                   question_count=len(questions))

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

    settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in settings}
    api_key = settings_dict.get('analysis_api_key') or settings_dict.get('api_key') or os.getenv('AI_ANALYSIS_API_KEY') or os.getenv('AI_API_KEY')
    api_base = settings_dict.get('analysis_api_base') or settings_dict.get('api_base') or os.getenv('AI_ANALYSIS_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
    api_base = normalize_api_base(api_base)
    model = settings_dict.get('model_analysis') or os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')

    if api_key and api_key.strip():
        analysis_agent.client.api_key = api_key
    if api_base and api_base.strip():
        analysis_agent.client.base_url = api_base
    if model and model.strip():
        analysis_agent.analysis_model = model

    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'AnalysisAgent 使用设置',
              api_key_set=bool(api_key), api_base=api_base, model=model)

    logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], '分析请求 - 发送数据',
              exam_name=exam.name,
              question_count=len(questions),
              sample_question=questions[0].to_dict() if questions else 'None')

    result = analysis_agent.analyze(exam_data, custom_prompt)

    logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], '分析请求 - 返回结果',
              result=str(result)[:500])

    exam.analysis_report = json.dumps(result, ensure_ascii=False)
    db.session.commit()

    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '考试分析完成', exam_id=exam_id, exam_name=exam.name)
    return jsonify(result)


@api.route('/analyze-subject/<int:subject_id>', methods=['POST'])
def analyze_subject(subject_id):
    logger.log(LOG_CATEGORIES['USER_ACTION'], '学科分析请求', subject_id=subject_id)
    
    subject = Subject.query.get_or_404(subject_id)
    exams = Exam.query.filter_by(subject_id=subject_id).all()
    
    subject_data = {
        'id': subject.id,
        'name': subject.name,
        'analysis_report': subject.analysis_report,
        'exam_count': len(exams),
        'created_at': subject.created_at.isoformat() if subject.created_at else None,
        'updated_at': subject.updated_at.isoformat() if subject.updated_at else None,
        'exams': [exam.to_dict(include_questions=True) for exam in exams]
    }
    
    subject_analysis_agent = SubjectAnalysisAgent()
    custom_prompt = get_prompt('Subject_Ana')

    settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in settings}
    api_key = settings_dict.get('subject_analysis_api_key') or settings_dict.get('analysis_api_key') or settings_dict.get('api_key') or os.getenv('AI_SUBJECT_ANALYSIS_API_KEY') or os.getenv('AI_ANALYSIS_API_KEY') or os.getenv('AI_API_KEY')
    api_base = settings_dict.get('subject_analysis_api_base') or settings_dict.get('analysis_api_base') or settings_dict.get('api_base') or os.getenv('AI_SUBJECT_ANALYSIS_API_BASE') or os.getenv('AI_ANALYSIS_API_BASE') or os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
    api_base = normalize_api_base(api_base)
    model = settings_dict.get('model_subject_analysis') or settings_dict.get('model_analysis') or os.getenv('AI_MODEL_SUBJECT_ANALYSIS') or os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro')

    if api_key and api_key.strip():
        subject_analysis_agent.client.api_key = api_key
    if api_base and api_base.strip():
        subject_analysis_agent.client.base_url = api_base
    if model and model.strip():
        subject_analysis_agent.analysis_model = model

    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'SubjectAnalysisAgent 使用设置',
              api_key_set=bool(api_key), api_base=api_base, model=model)

    logger.log(LOG_CATEGORIES['NETWORK_REQUEST'], '学科分析请求 - 发送数据',
              subject_name=subject.name,
              exam_count=len(exams),
              sample_exam=exams[0].to_dict(include_questions=True) if exams else 'None')

    result = subject_analysis_agent.analyze(subject_data, custom_prompt)

    logger.log(LOG_CATEGORIES['NETWORK_RESPONSE'], '学科分析请求 - 返回结果',
              result=str(result)[:500])

    analysis_report_content = result.get('analysis_report', '')
    if isinstance(analysis_report_content, dict):
        analysis_report_content = json.dumps(analysis_report_content, ensure_ascii=False)
    subject.analysis_report = analysis_report_content
    db.session.commit()

    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '学科分析完成', subject_id=subject_id, subject_name=subject.name)
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
    try:
        prompt = Prompt.query.get_or_404(prompt_id)
        data = request.get_json()
        
        logger.log(LOG_CATEGORIES['USER_ACTION'], '更新Prompt请求', 
                   prompt_id=prompt_id, 
                   prompt_name=prompt.name,
                   data_keys=list(data.keys()) if data else None)
        
        prompt.system_prompt = data.get('system_prompt', prompt.system_prompt)
        prompt.role = data.get('role', prompt.role)
        prompt.description = data.get('description', prompt.description)
        prompt.is_active = data.get('is_active', prompt.is_active)
        
        db.session.commit()
        return jsonify(prompt.to_dict())
    except Exception as e:
        logger.log(LOG_CATEGORIES['ERROR_EXCEPTION'], '更新Prompt失败', error=str(e))
        return jsonify({'error': str(e)}), 500


@api.route('/prompts/<int:prompt_id>/reset', methods=['POST'])
def reset_prompt(prompt_id):
    from app.agents.ai_agents import VisionAgent, GradingAgent, AnalysisAgent
    
    prompt = Prompt.query.get_or_404(prompt_id)
    
    defaults = {
        'vision': VisionAgent.DEFAULT_PROMPT,
        'grading': GradingAgent.DEFAULT_PROMPT,
        'analysis': AnalysisAgent.DEFAULT_PROMPT,
        'Subject_Ana': load_prompt_from_file('Subject_Ana')
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

    default_settings = {
        'api_key': os.getenv('AI_API_KEY', ''),
        'api_base': os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'model_general': os.getenv('AI_MODEL_GENERAL', 'doubao-seed-2.0-pro'),
        'model_vision': os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro'),
        'model_grading': os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini'),
        'model_analysis': os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro'),
        'model_metadata': os.getenv('AI_MODEL_METADATA', 'doubao-seed-2.0-mini'),
        'vision_api_key': os.getenv('AI_VISION_API_KEY', ''),
        'vision_api_base': os.getenv('AI_VISION_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'grading_api_key': os.getenv('AI_GRADING_API_KEY', ''),
        'grading_api_base': os.getenv('AI_GRADING_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'analysis_api_key': os.getenv('AI_ANALYSIS_API_KEY', ''),
        'analysis_api_base': os.getenv('AI_ANALYSIS_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'metadata_api_key': os.getenv('AI_METADATA_API_KEY', ''),
        'metadata_api_base': os.getenv('AI_METADATA_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'vision_deep_thinking': os.getenv('AI_VISION_DEEP_THINKING', 'false'),
        'grading_deep_thinking': os.getenv('AI_GRADING_DEEP_THINKING', 'false'),
        'analysis_deep_thinking': os.getenv('AI_ANALYSIS_DEEP_THINKING', 'false'),
        'subject_analysis_deep_thinking': os.getenv('AI_SUBJECT_ANALYSIS_DEEP_THINKING', 'false'),
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
    Setting.query.delete()
    db.session.commit()

    default_settings = {
        'api_key': os.getenv('AI_API_KEY', ''),
        'api_base': os.getenv('AI_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'model_general': os.getenv('AI_MODEL_GENERAL', 'doubao-seed-2.0-pro'),
        'model_vision': os.getenv('AI_MODEL_VISION', 'doubao-seed-2.0-pro'),
        'model_grading': os.getenv('AI_MODEL_GRADING', 'doubao-seed-2.0-mini'),
        'model_analysis': os.getenv('AI_MODEL_ANALYSIS', 'doubao-seed-2.0-pro'),
        'model_metadata': os.getenv('AI_MODEL_METADATA', 'doubao-seed-2.0-mini'),
        'vision_api_key': os.getenv('AI_VISION_API_KEY', ''),
        'vision_api_base': os.getenv('AI_VISION_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'grading_api_key': os.getenv('AI_GRADING_API_KEY', ''),
        'grading_api_base': os.getenv('AI_GRADING_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'analysis_api_key': os.getenv('AI_ANALYSIS_API_KEY', ''),
        'analysis_api_base': os.getenv('AI_ANALYSIS_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'metadata_api_key': os.getenv('AI_METADATA_API_KEY', ''),
        'metadata_api_base': os.getenv('AI_METADATA_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3'),
        'vision_deep_thinking': os.getenv('AI_VISION_DEEP_THINKING', 'false'),
        'grading_deep_thinking': os.getenv('AI_GRADING_DEEP_THINKING', 'false'),
        'analysis_deep_thinking': os.getenv('AI_ANALYSIS_DEEP_THINKING', 'false'),
        'subject_analysis_deep_thinking': os.getenv('AI_SUBJECT_ANALYSIS_DEEP_THINKING', 'false'),
    }

    return jsonify(default_settings)


@api.route('/settings/test', methods=['POST'])
def test_api_connection():
    from openai import OpenAI
    import requests
    
    data = request.get_json()
    api_key = data.get('api_key', '')
    api_base = data.get('api_base', '')
    model = data.get('model', '')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'API密钥不能为空'})
    
    if not api_base:
        return jsonify({'success': False, 'message': 'API地址不能为空'})
    
    if not model:
        return jsonify({'success': False, 'message': '模型名称不能为空'})
    
    logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], '测试API连接', api_base=api_base, model=model)
    
    try:
        normalized_base = api_base.rstrip('/')
        if '/v3' not in normalized_base and '/v1' not in normalized_base:
            normalized_base = f"{normalized_base}/v3"
        
        client = OpenAI(
            api_key=api_key,
            base_url=normalized_base,
            timeout=30.0
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100
        )
        
        logger.log(LOG_CATEGORIES['SYSTEM_STATUS'], 'API连接测试成功', model=model)
        return jsonify({
            'success': True, 
            'message': f'连接成功！模型: {model}',
            'response': response.choices[0].message.content if response.choices else ''
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.log(LOG_CATEGORIES['ERROR'], 'API连接测试失败', error=error_msg)
        return jsonify({'success': False, 'message': f'连接失败: {error_msg}'})


@api.route('/dashboard/<int:subject_id>', methods=['GET'])
def get_dashboard(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    exams = Exam.query.filter_by(subject_id=subject_id).order_by(Exam.date).all()
    
    exam_data = []
    for exam in exams:
        questions = Question.query.filter_by(exam_id=exam.id).all()
        total_score = sum(q.max_score or 0 for q in questions)
        user_score = sum(q.user_score or 0 for q in questions)
        
        analysis_report = exam.analysis_report
        if analysis_report:
            try:
                if isinstance(analysis_report, str):
                    analysis_report = json.loads(analysis_report)
            except:
                analysis_report = analysis_report
        
        exam_data.append({
            'id': exam.id,
            'name': exam.name,
            'date': exam.date.isoformat() if exam.date else '',
            'total_score': total_score,
            'user_score': user_score,
            'score_rate': round(user_score / total_score * 100, 1) if total_score > 0 else 0,
            'analysis_report': analysis_report
        })
    
    return jsonify({
        'subject': subject.to_dict(),
        'exams': exam_data
    })
