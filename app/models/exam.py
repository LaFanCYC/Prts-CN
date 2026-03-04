from app import db
from datetime import datetime

class Exam(db.Model):
    __tablename__ = 'exams'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    analysis_report = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    questions = db.relationship('Question', backref='exam', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        total_score = sum(q.max_score or 0 for q in self.questions)
        user_score = sum(q.user_score or 0 for q in self.questions)
        return {
            'id': self.id,
            'subject_id': self.subject_id,
            'name': self.name,
            'date': self.date.isoformat() if self.date else None,
            'analysis_report': self.analysis_report,
            'question_count': len(self.questions),
            'total_score': total_score,
            'user_score': user_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
