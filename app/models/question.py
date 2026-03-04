from app import db
from datetime import datetime
import json

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    question_index = db.Column(db.String(50), nullable=False)
    image_path = db.Column(db.String(500), default='')
    ocr_text = db.Column(db.Text, default='')
    coordinates = db.Column(db.Text, default='[]')
    user_answer_text = db.Column(db.Text, default='')
    user_answer_image_path = db.Column(db.String(500), default='')
    standard_answer = db.Column(db.Text, default='')
    knowledge_tags = db.Column(db.Text, default='[]')
    difficulty = db.Column(db.Integer, default=3)
    max_score = db.Column(db.Float, default=10.0)
    user_score = db.Column(db.Float, default=None)
    feedback = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_coordinates(self):
        try:
            return json.loads(self.coordinates) if self.coordinates else []
        except:
            return []
    
    def set_coordinates(self, coords):
        self.coordinates = json.dumps(coords)
    
    def get_knowledge_tags(self):
        try:
            return json.loads(self.knowledge_tags) if self.knowledge_tags else []
        except:
            return []
    
    def set_knowledge_tags(self, tags):
        self.knowledge_tags = json.dumps(tags)
    
    def to_dict(self):
        return {
            'id': self.id,
            'exam_id': self.exam_id,
            'question_index': self.question_index,
            'image_path': self.image_path,
            'ocr_text': self.ocr_text,
            'coordinates': self.get_coordinates(),
            'user_answer_text': self.user_answer_text,
            'user_answer_image_path': self.user_answer_image_path,
            'standard_answer': self.standard_answer,
            'knowledge_tags': self.get_knowledge_tags(),
            'difficulty': self.difficulty,
            'max_score': self.max_score,
            'user_score': self.user_score,
            'feedback': self.feedback
        }
