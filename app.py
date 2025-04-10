from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_migrate import Migrate
from models import db, Teacher, Student, Answer, QuestionPaper, Question, ExamAnswer
from werkzeug.security import generate_password_hash, check_password_hash
from transformers import pipeline
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io,os
from sqlalchemy.orm import joinedload
import pytesseract
from PIL import Image
import cv2
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer, util

app = Flask(__name__)


# Set up the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///grading_system.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'

# Initialize the database and migration objects
db.init_app(app)
migrate = Migrate(app, db)

# Load a pre-trained transformer model for question answering
sbert_model = SentenceTransformer("paraphrase-MiniLM-L6-v2")

def grade_answer(question, student_answer, ideal_answer):
    """
    Grades a student's answer by comparing it with an ideal answer using a transformer model.
    Returns a similarity score as a percentage.
    """
    try:
        # Convert student and ideal answers into embeddings
        student_embedding = sbert_model.encode(student_answer, convert_to_tensor=True)
        ideal_embedding = sbert_model.encode(ideal_answer, convert_to_tensor=True)

        # Compute cosine similarity
        similarity_score = util.pytorch_cos_sim(student_embedding, ideal_embedding).item()

        return round(similarity_score * 100, 2)
    except Exception as e:
        print(f"Error during grading: {e}")
        return 0


# Route to display the main index page with buttons
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        student = Student.query.filter_by(email=email).first()
        
        if student and check_password_hash(student.password, password):
            session['user_id'] = student.id
            session['role'] = 'student'
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials, please try again.', 'danger')
    
    return render_template('login.html', role='Student')

@app.route('/student_register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Check if the email or username already exists
        if Student.query.filter_by(email=email).first():
            return "Email already registered!"
        if Student.query.filter_by(username=username).first():
            return "Username already taken!"

        new_student = Student(username=username, email=email, password=hashed_password)
        db.session.add(new_student)
        db.session.commit()

        return redirect(url_for('student_login'))
    
    return render_template('register.html', role='Student')

# Student Dashboard
@app.route('/student_dashboard')
def student_dashboard():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('student_login'))
    
    student = Student.query.get(session['user_id'])
    
    # Fetch active question papers
    active_question_papers = QuestionPaper.query.filter_by(is_active=True).all()
    
    # Debug: Check what papers are fetched
    print(f"Active Question Papers: {active_question_papers}")
    
    return render_template('student_dashboard.html', student=student, active_question_papers=active_question_papers)

@app.route('/start_exam/<int:paper_id>', methods=['GET', 'POST'])
def start_exam(paper_id):
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('student_login'))
    
    # Get the question paper by ID
    question_paper = QuestionPaper.query.get_or_404(paper_id)
    
    # Get all questions for the paper
    questions = question_paper.questions
    
    if request.method == 'POST':
        # Handle form submission, save answers for the current question
        student_id = session['user_id']
        
        # Loop through questions and save answers
        for idx, question in enumerate(questions):
            answer_text = request.form.get(f'answer_{question.id}')
            if answer_text:
                # Create and store the answer in the ExamAnswer table
                exam_answer = ExamAnswer(
                    student_id=student_id,
                    question_id=question.id,
                    answer=answer_text,
                    exam_paper_id=question_paper.id
                )
                db.session.add(exam_answer)
        
        db.session.commit()
        flash('Exam submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))
    
    # Render the exam page with the first question
    return render_template('take_exam.html', paper=question_paper, questions=questions)


@app.route('/view_exam_answers/<int:paper_id>', methods=['GET'])
def view_exam_answers(paper_id):
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('student_login'))

    # Fetch the question paper and questions
    question_paper = QuestionPaper.query.get_or_404(paper_id)
    questions = question_paper.questions

    # Fetch the student's answers for this exam
    student_answers = ExamAnswer.query.filter_by(
        exam_paper_id=question_paper.id,
        student_id=session['user_id']
    ).all()

    # Create a dictionary of student answers for quick access
    student_answers_dict = {answer.question_id: answer for answer in student_answers}

    # Generate graded answers
    graded_answers = []
    for question in questions:
        student_answer = student_answers_dict.get(question.id, None)
        ideal_answer = "; ".join([ans.text for ans in question.answers])
        grade = grade_answer(question.text, student_answer.answer if student_answer else "", ideal_answer)
        graded_answers.append((question, student_answer, ideal_answer, grade))

    # Pass the question paper and graded answers to the template
    return render_template('view_exam.html', paper=question_paper, graded_answers=graded_answers)

#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Routes for Teacher and Student Login/Registration
@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        teacher = Teacher.query.filter_by(email=email).first()
        
        if teacher and check_password_hash(teacher.password, password):
            session['user_id'] = teacher.id
            session['role'] = 'teacher'
            return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid credentials, please try again.', 'danger')
    
    return render_template('login.html', role='Teacher')

@app.route('/teacher_register', methods=['GET', 'POST'])
def teacher_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Check if the email or username already exists
        if Teacher.query.filter_by(email=email).first():
            return "Email already registered!"
        if Teacher.query.filter_by(username=username).first():
            return "Username already taken!"

        new_teacher = Teacher(username=username, email=email, password=hashed_password)
        db.session.add(new_teacher)
        db.session.commit()

        return redirect(url_for('teacher_login'))
    
    return render_template('register.html', role='Teacher')

@app.route('/teacher_dashboard', methods=['GET', 'POST'])
def teacher_dashboard():
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    teacher_id = session['user_id']

    # Fetch question papers generated by the teacher
    question_papers = QuestionPaper.query.filter_by(teacher_id=teacher_id).all()

    # Handle activation/deactivation
    if request.method == 'POST':
        paper_id = request.form.get('paper_id')
        action = request.form.get('action')

        question_paper = QuestionPaper.query.get(paper_id)
        if question_paper and question_paper.teacher_id == teacher_id:
            if action == 'activate':
                question_paper.is_active = True
            elif action == 'deactivate':
                question_paper.is_active = False

            db.session.commit()
            flash('Question paper status updated successfully!', 'success')

        return redirect(url_for('teacher_dashboard'))

    return render_template('teacher_dashboard.html', question_papers=question_papers)


@app.route('/create_question_paper', methods=['GET', 'POST'])
def create_question_paper():
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))
    
    if request.method == 'POST':
        # Get the title of the question paper
        title = request.form['title']
        teacher_id = session['user_id']

        # Create a new QuestionPaper
        question_paper = QuestionPaper(title=title, teacher_id=teacher_id)
        db.session.add(question_paper)
        db.session.commit()

        # Retrieve questions and their respective answers
        questions = request.form.getlist('questions[]')
        for i, question_text in enumerate(questions):
            # Create a question
            question = Question(text=question_text, paper_id=question_paper.id)
            db.session.add(question)
            db.session.commit()

            # Get corresponding answers
            answer_key = f'answers_{i}[]'
            answers = request.form.getlist(answer_key)
            for answer_text in answers:
                # Create an answer
                answer = Answer(text=answer_text, question_id=question.id)
                db.session.add(answer)

        db.session.commit()
        flash('Question paper created successfully!', 'success')
        return redirect(url_for('teacher_dashboard'))

    return render_template('create_question_paper.html')

@app.route('/view_question_paper/<int:paper_id>', methods=['GET'])
def view_question_paper_details(paper_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    question_paper = QuestionPaper.query.get_or_404(paper_id)
    
    # Ensure the teacher viewing the paper is the one who created it
    if question_paper.teacher_id != session['user_id']:
        flash('You do not have permission to view this question paper.', 'danger')
        return redirect(url_for('teacher_dashboard'))

    # Fetch all questions for this question paper
    questions = Question.query.filter_by(paper_id=paper_id).all()
    answers = {q.id: Answer.query.filter_by(question_id=q.id).all() for q in questions}
    
    return render_template('view_question_paper_details.html', question_paper=question_paper, questions=questions, answers=answers)

# @app.route('/delete_question_paper/<int:paper_id>', methods=['POST'])
# def delete_question_paper(paper_id):
#     if 'role' not in session or session['role'] != 'teacher':
#         return redirect(url_for('teacher_login'))
    
#     question_paper = QuestionPaper.query.get_or_404(paper_id)
    
#     # Ensure the teacher deleting the paper is the one who created it
#     if question_paper.teacher_id != session['user_id']:
#         flash('You do not have permission to delete this question paper.', 'danger')
#         return redirect(url_for('teacher_dashboard'))
    
#     # Delete all related questions and answers first
#     for question in question_paper.questions:
#         for answer in question.answers:
#             db.session.delete(answer)  # Delete answers
#         db.session.delete(question)  # Delete questions
    
#     # Delete the question paper itself
#     db.session.delete(question_paper)
#     db.session.commit()
    
#     flash('Question paper deleted successfully!', 'success')
#     return redirect(url_for('teacher_dashboard'))

@app.route('/delete_question_paper/<int:paper_id>', methods=['POST'])
def delete_question_paper(paper_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))
    
    question_paper = QuestionPaper.query.get_or_404(paper_id)
    
    # Ensure the teacher deleting the paper is the one who created it
    if question_paper.teacher_id != session['user_id']:
        flash('You do not have permission to delete this question paper.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    # Delete all related ExamAnswers explicitly
    for question in question_paper.questions:
        db.session.query(ExamAnswer).filter_by(question_id=question.id).delete()
    
    # Delete all related questions and their answers
    for question in question_paper.questions:
        db.session.query(Answer).filter_by(question_id=question.id).delete()
        db.session.delete(question)
    
    # Delete the question paper itself
    db.session.delete(question_paper)
    db.session.commit()
    
    flash('Question paper deleted successfully!', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/view_students', methods=['GET'])
def view_students():
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    # Get all students
    students = Student.query.all()
    return render_template('view_students.html', students=students)

@app.route('/view_student_profile/<int:student_id>', methods=['GET'])
def view_student_profile(student_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    student = Student.query.get_or_404(student_id)
    return render_template('view_student_profile.html', student=student)

@app.route('/edit_student_profile/<int:student_id>', methods=['GET', 'POST'])
def edit_student_profile(student_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    student = Student.query.get_or_404(student_id)

    if request.method == 'POST':
        student.username = request.form['username']
        student.email = request.form['email']
        student.password = request.form['password']  # Optional, for password change
        
        db.session.commit()
        flash('Student profile updated successfully!', 'success')
        return redirect(url_for('view_students'))

    return render_template('edit_student_profile.html', student=student)

@app.route('/view_student_exams/<int:student_id>', methods=['GET'])
def view_student_exams(student_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    student = Student.query.get_or_404(student_id)
    
    # Get all exam answers submitted by the student
    submitted_exams = ExamAnswer.query.filter_by(student_id=student.id).all()
    
    return render_template('view_student_exams.html', student=student, submitted_exams=submitted_exams)

@app.route('/view_exam_answers_teachers/<int:paper_id>/<int:student_id>', methods=['GET'])
def view_exam_answers_teachers(paper_id, student_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))  # Ensure only teachers can view this

    student = Student.query.get_or_404(student_id)
    exam_paper = QuestionPaper.query.get_or_404(paper_id)
    questions = exam_paper.questions

    submitted_answers = ExamAnswer.query.filter_by(student_id=student.id, exam_paper_id=paper_id).all()
    answers_dict = {answer.question_id: answer.answer for answer in submitted_answers}

    graded_answers = []
    for question in questions:
        student_answer = answers_dict.get(question.id, "")
        ideal_answer = "; ".join([ans.text for ans in question.answers])
        grade = grade_answer(question.text, student_answer, ideal_answer)
        graded_answers.append((question, student_answer, ideal_answer, grade))

    return render_template(
        'view_exam_answers.html',
        graded_answers=graded_answers,
        student=student,
        exam_paper=exam_paper
    )

# Logout Route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/view_database')
def view_database():
    # Fetch data from the database
    teachers = Teacher.query.all()
    students = Student.query.all()
    question_papers = QuestionPaper.query.all()
    questions = Question.query.all()
    answers = Answer.query.all()
    examanswers = ExamAnswer.query.all()

    # Pass data to the template
    return render_template('view_database.html', teachers=teachers, students=students, question_papers=question_papers, questions=questions, answers=answers, examanswers=examanswers)


@app.route('/download_question_paper_pdf/<int:paper_id>', methods=['GET'])
def download_question_paper_pdf(paper_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))
    
    # Fetch the question paper with the teacher information eagerly loaded
    question_paper = QuestionPaper.query.options(joinedload(QuestionPaper.teacher)).get_or_404(paper_id)
    questions = Question.query.filter_by(paper_id=paper_id).all()
    
    # Create the PDF response
    filename = f"question_paper_{paper_id}.pdf"
    response = make_response()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    # Create PDF content
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 12)
    
    # Title
    pdf.drawString(100, 750, f"Question Paper: {question_paper.title}")
    pdf.drawString(100, 735, f"Teacher: {question_paper.teacher.username}")
    # pdf.drawString(100, 720, f"Date: {question_paper.created_at.strftime('%Y-%m-%d')}")
    pdf.drawString(100, 705, "Questions and Answers:")
    
    y_position = 690
    
    # Add questions and their corresponding answers
    for question in questions:
        pdf.drawString(100, y_position, f"Q{question.id}: {question.text}")
        y_position -= 20
        answers = Answer.query.filter_by(question_id=question.id).all()
        for answer in answers:
            pdf.drawString(120, y_position, f"  Answer: {answer.text}")
            y_position -= 20
        y_position -= 10  # Add a space between questions
    
    pdf.showPage()
    pdf.save()
    
    buffer.seek(0)
    response.data = buffer.read()  # Use 'data' instead of 'write'
    return response

@app.route('/download_student_answer_pdf/<int:paper_id>/<int:student_id>', methods=['GET'])
def download_student_answer_pdf(paper_id, student_id):
    if 'role' not in session or session['role'] != 'teacher':
        return redirect(url_for('teacher_login'))

    student = Student.query.get_or_404(student_id)
    question_paper = QuestionPaper.query.get_or_404(paper_id)
    questions = question_paper.questions

    # Fetch the student's answers for this exam
    student_answers = ExamAnswer.query.filter_by(exam_paper_id=paper_id, student_id=student_id).all()
    answers_dict = {answer.question_id: answer for answer in student_answers}

    # Create the PDF response
    filename = f"student_answer_{student_id}_paper_{paper_id}.pdf"
    response = make_response()
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'

    # Create PDF content
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 12)
    
    # Title
    pdf.drawString(100, 750, f"Student Answer Paper: {student.username}")
    pdf.drawString(100, 735, f"Exam Paper: {question_paper.title}")
    pdf.drawString(100, 720, f"Teacher: {question_paper.teacher.username}")
    # pdf.drawString(100, 705, f"Date: {question_paper.created_at.strftime('%Y-%m-%d')}")
    pdf.drawString(100, 690, "Questions and Answers with Grades:")
    
    y_position = 675
    
    # Add questions, student answers, and grades
    for question in questions:
        pdf.drawString(100, y_position, f"Q{question.id}: {question.text}")
        y_position -= 20
        
        student_answer = answers_dict.get(question.id)
        answer_text = student_answer.answer if student_answer else "No Answer"
        grade = grade_answer(question.text, answer_text, "; ".join([ans.text for ans in question.answers]))
        
        pdf.drawString(120, y_position, f"  Your Answer: {answer_text}")
        y_position -= 20
        pdf.drawString(120, y_position, f"  Grade: {grade}%")
        y_position -= 30  # Space between questions
    
    pdf.showPage()
    pdf.save()
    
    buffer.seek(0)
    response.data = buffer.read()  # Correct way to send the PDF content
    return response


@app.route("/extract_text", methods=["POST"])
def extract_text():
    if "image" not in request.files:
        return "No file uploaded", 400

    file = request.files["image"]
    image = Image.open(file)
    
    # Convert image to text
    text = pytesseract.image_to_string(image)

    # Generate a unique filename using timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"extracted_text_{timestamp}.txt"
    output_path = os.path.join("extracted_texts", output_filename)

    # Ensure the directory exists
    os.makedirs("extracted_texts", exist_ok=True)

    # Save text to a file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Display extracted text on screen and mention file name
    return f"Extracted Text:\n{text}\n\n(Saved to: {output_path})"

if __name__ == "__main__":
    app.run(debug=True)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create the database tables
    app.run(debug=True)
