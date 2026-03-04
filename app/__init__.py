import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

db = SQLAlchemy()

def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, 
               template_folder=os.path.join(base_dir, 'templates'),
               static_folder=os.path.join(base_dir, 'static'))
    
    from dotenv import load_dotenv
    load_dotenv()
    
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'gradeai-secret-key-2024')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URI', 
        'sqlite:///gradeai.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'app/static/uploads')
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))
    
    db.init_app(app)
    CORS(app)
    
    from app.routes.main import main
    from app.routes.api import api
    app.register_blueprint(main)
    app.register_blueprint(api, url_prefix='/api')
    
    with app.app_context():
        from app.models import subject, exam, question, prompt, setting
        db.create_all()
        from app.agents.prompt_generator import init_prompts
        init_prompts()
    
    return app
