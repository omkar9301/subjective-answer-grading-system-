from flask_sqlalchemy import SQLAlchemy

# Initialize the database object
db = SQLAlchemy()

class Teacher(db.Model):
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)  # Define as primary key
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    
    def __repr__(self):
        return f'<Teacher {self.username}>'

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    
    def __repr__(self):
        return f'<Student {self.username}>'

class QuestionPaper(db.Model):
    __tablename__ = 'question_papers'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    teacher = db.relationship('Teacher', backref='question_papers', lazy=True)
    questions = db.relationship('Question', backref='question_paper', cascade="all, delete-orphan")


# class Question(db.Model):
#     __tablename__ = 'questions'
    
#     id = db.Column(db.Integer, primary_key=True)  # Define as primary key
#     text = db.Column(db.Text, nullable=False)
#     paper_id = db.Column(db.Integer, db.ForeignKey('question_papers.id'), nullable=False)  # Correct ForeignKey reference
#     answers = db.relationship('Answer', backref='question', cascade="all, delete-orphan")

class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    max_marks = db.Column(db.Float, default=1.0)  # NEW: Assignable marks
    paper_id = db.Column(db.Integer, db.ForeignKey('question_papers.id'), nullable=False)
    answers = db.relationship('Answer', backref='question', cascade="all, delete-orphan")


class Answer(db.Model):
    __tablename__ = 'answers'
    
    id = db.Column(db.Integer, primary_key=True)  # Define as primary key
    text = db.Column(db.Text, nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)  # Correct ForeignKey reference

class ExamAnswer(db.Model):
    __tablename__ = 'exam_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    exam_paper_id = db.Column(db.Integer, db.ForeignKey('question_papers.id'), nullable=False)
    
    student = db.relationship('Student', backref='exam_answers')
    question = db.relationship('Question', backref='exam_answers')
    exam_paper = db.relationship('QuestionPaper', backref='exam_answers')

    def __repr__(self):
        return f'<ExamAnswer {self.id} - Student {self.student_id} - Question {self.question_id}>'

