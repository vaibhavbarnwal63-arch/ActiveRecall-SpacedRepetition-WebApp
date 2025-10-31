from flask import Flask, render_template, redirect, url_for, request,flash
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Float,ForeignKey,DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.fields.simple import TextAreaField
from wtforms.validators import DataRequired
import requests
from datetime import datetime
from supermemo import SuperMemo2
import os


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_KEY")
Bootstrap5(app)
sm2 = SuperMemo2()



#----------------------------------------DATABASE----------------------------------------------------------
# CREATE DB
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///subjects.db")
# Create the extension
db = SQLAlchemy(model_class=Base)
# Initialise the app with the extension
db.init_app(app)
migrate = Migrate(app,db)
csrf = CSRFProtect(app)

class Subject(db.Model):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    Subs: Mapped[str] = mapped_column(String(250), unique=True)

    # Define relationship to access children
    chapters = relationship("Chapter", back_populates="subject", cascade = "all, delete-orphan")


class Chapter(db.Model):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("subjects.id"))
    Chapters: Mapped[str] = mapped_column(String(250), unique=True)

    # Define relationship to access parent
    subject = relationship("Subject", back_populates="chapters")

    # Define relationship to access parent chapter
    questions = relationship("QuesAns", back_populates="chapter",cascade = "all, delete-orphan")


class QuesAns(db.Model):
    __tablename__ = "quesans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("chapters.id"))
    Question: Mapped[str] = mapped_column(String(500))
    Answer: Mapped[str] = mapped_column(String(1000))

    # SuperMemo 2 Algorithm Fields
    RevisedDate: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=None)
    RecallDate: Mapped[datetime] = mapped_column(DateTime, nullable=True, default=None)
    EasinessFactor: Mapped[float] = mapped_column(Float, server_default='2.5')
    Repetitions: Mapped[int] = mapped_column(Integer, server_default='0')
    Interval: Mapped[int] = mapped_column(Integer, server_default='1')
    LastGrade: Mapped[int] = mapped_column(Integer, nullable=True, default=None)

    # Timestamps for tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Define relationship to access parent chapter
    chapter = relationship("Chapter", back_populates="questions")


with app.app_context():
    db.create_all()

#------------------------------------------DATABASE-------------------------------------------
#------------------------FORMS------------------------------------------------------
class AddSubForm(FlaskForm):
    subject = StringField(label='Enter Subject',validators=[DataRequired()])
    submit = SubmitField(label="Done")

class EditSubForm(FlaskForm):
    subject = StringField(label="Edit Subject Name",validators = [DataRequired()])
    submit = SubmitField(label = "Done")

class AddChapterForm(FlaskForm):
    chapter = StringField(label = "Enter Chapter",validators = [DataRequired()])
    submit = SubmitField(label = "Done")

class EditChapterForm(FlaskForm):
    chapter = StringField(label = "Edit Chapter Name",validators=[DataRequired()])
    submit = SubmitField(label = "Done")

class AddQuesAnsForm(FlaskForm):
    question = TextAreaField(label = "Enter Question",validators = [DataRequired()])
    answer = TextAreaField(label = "Enter Answer",validators = [DataRequired()])
    submit = SubmitField(label = "Done")

class EditQuesAnsForm(FlaskForm):
    question = TextAreaField(label = "Enter Question",validators = [DataRequired()])
    answer = TextAreaField(label = "Enter Answer",validators = [DataRequired()])
    submit = SubmitField(label = "Done")
#-----------------------------------------------------FORMS----------------------------------------------------
# -----------------------------------------------------HELPER FUNCTIONS-----------------------------------------
def has_questions_due_today(entity):
    """
    Checks if a Subject or Chapter has any questions due for review today
    based on the SuperMemo2 algorithm's determination.
    """
    today = datetime.now().date()

    chapters_to_check = []
    if isinstance(entity, Subject):
        chapters_to_check = entity.chapters
    elif isinstance(entity, Chapter):
        chapters_to_check = [entity]
    else:
        return False # Invalid entity type

    for chapter in chapters_to_check:
        # Accessing `chapter.questions` loads all questions for this chapter.
        # This might trigger a DB query if not already loaded by a join.
        all_questions_in_chapter = chapter.questions

        # Use the sm2 method to determine actual study questions for today
        # limit=None ensures all due questions are considered
        questions_for_study = sm2.get_chapter_questions_for_study(all_questions_in_chapter, limit=None)

        # If there are any questions returned by sm2.get_chapter_questions_for_study,
        # it means there's something due for review.
        if len(questions_for_study) > 0:
            return True
    return False

# -----------------------------------------------------HELPER FUNCTIONS-----------------------------------------


@app.route("/")
def home():
    with app.app_context():
        result = db.session.execute(db.select(Subject))
        all_subs = result.scalars().all()

        # Augment each subject with a flag indicating if it has due questions
        subjects_with_due_status = []
        for subject in all_subs:
            # Check if this subject or any of its chapters has questions due today
            subject.has_due_questions = has_questions_due_today(subject)
            subjects_with_due_status.append(subject)

    return render_template('index.html', sub_list=subjects_with_due_status)

@app.route("/<subject_name>/<int:id>") # Changed variable name to subject_name to avoid conflict
def view_chapters(id, subject_name):
    # Fetch chapters related to the subject
    chapters = Chapter.query.filter_by(parent_id=id).all()

    # Augment each chapter with a flag indicating if it has due questions
    chapters_with_due_status = []
    for chapter in chapters:
        chapter.has_due_questions = has_questions_due_today(chapter)
        chapters_with_due_status.append(chapter)

    return render_template('view_chapters.html', chapters=chapters_with_due_status, parent_id=id, subject_name=subject_name)

@app.route("/add",methods = ['GET',"POST"])
def add_subject():
    form = AddSubForm()
    if form.validate_on_submit():
        sub = form.subject.data
        new_subject = Subject(Subs=sub)
        with app.app_context():
            db.session.add(new_subject)
            db.session.commit()
        return redirect(url_for("home"))
    return render_template("add_subject.html",form = form)


@app.route('/delete-subject/<int:id>', methods=["POST"])
def delete_subject(id):
    subject = Subject.query.get_or_404(id)

    try:
        # With cascade="all, delete-orphan" on the Subject->Chapter relationship,
        # deleting the subject will automatically trigger the deletion of its chapters.
        # And because Chapter->QuesAns also has cascade="all, delete-orphan",
        # the questions will be deleted when their parent chapters are deleted.
        db.session.delete(subject)
        db.session.commit()
        flash(f'Subject "{subject.Subs}" and all its chapters/questions deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting subject "{subject.Subs}": {e}', 'error')
        print(f"Error deleting subject: {e}")
    return redirect(url_for('home'))

@app.route('/edit_subject/<int:id>',methods = ["GET","POST"])
def edit_subject(id):
    form = EditSubForm()
    if form.validate_on_submit():
        with app.app_context():
            subject = Subject.query.get_or_404(id)
            subject.Subs = form.subject.data
            db.session.commit()
        return redirect(url_for('home'))
    return render_template("edit_subject.html",form = form,id = id)


@app.route('/add_chapter/<subject_id>', methods=["POST", "GET"])
def add_chapter(subject_id):
    form = AddChapterForm()
    subject = Subject.query.get_or_404(subject_id) # Handles subject not found
    subject_name = subject.Subs

    if form.validate_on_submit():
        chapter_name = form.chapter.data
        new_chapter = Chapter(
            Chapters=chapter_name,
            parent_id=subject.id
        )
        try:
            with app.app_context():
                db.session.add(new_chapter)
                db.session.commit()
            flash(f'Chapter "{chapter_name}" added successfully to "{subject_name}"!', 'success')
            return redirect(url_for("view_chapters", id=subject_id, subject_name=subject_name))
        except Exception as e:
            db.session.rollback()
            if "UNIQUE constraint failed" in str(e):
                flash(f'Error: Chapter "{chapter_name}" already exists. Please choose a different name.', 'error')
                # Redirect to view_chapters upon unique constraint failure
                return redirect(url_for("view_chapters", id=subject_id, subject_name=subject_name))
            else:
                flash(f'Error adding chapter: {e}', 'error')
            print(f"Error adding chapter: {e}") # Log error
    return render_template("add_chapter.html", form=form, id=subject_id, subject_name=subject_name)

@app.route('/delete_chapter/<int:id>',methods = ['POST'])
def delete_chapter(id):
    chapter = Chapter.query.get_or_404(id)
    subject_id = chapter.parent_id  # Store for redirect
    subject = Subject.query.get_or_404(subject_id)
    subject_name = subject.Subs
    QuesAns.query.filter_by(chapter_id=id).delete()
    db.session.delete(chapter)
    db.session.commit()

    flash('Chapter deleted successfully!', 'success')

    # Redirect back to the appropriate chapters view
    return redirect(url_for('view_chapters', id=subject_id,subject_name = subject_name))

@app.route('/edit_chapter/<int:id>',methods = ["POST","GET"])
def edit_chapter(id):
    form = EditChapterForm()
    if form.validate_on_submit():
        with app.app_context():
            chapter = Chapter.query.get_or_404(id)
            chapter.Chapters = form.chapter.data
            subject_id = chapter.parent_id  # Store for redirect
            subject = Subject.query.get_or_404(subject_id)
            subject_name = subject.Subs
            db.session.commit()
        return redirect(url_for('view_chapters', id=subject_id,subject_name = subject_name))
    return render_template("edit_chapter.html",form = form,id = id)

@app.route('/view_deck/<int:chapter_id>')
def view_deck(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)

    questions = QuesAns.query.filter_by(chapter_id = chapter_id).all()

    subject = Subject.query.get_or_404(chapter.parent_id)

    return render_template("view_deck.html",chapter=chapter,questions= questions,subject=subject)



@app.route('/add_question/<int:chapter_id>', methods=['GET', 'POST'])
def add_question(chapter_id):
    # Get the chapter to ensure it exists
    chapter = Chapter.query.get_or_404(chapter_id)

    # Create form instance
    form = AddQuesAnsForm()

    if form.validate_on_submit():
        # Create new question and answer entry
        new_question = QuesAns(
            Question=form.question.data,
            Answer=form.answer.data,
            chapter_id=chapter_id
        )

        try:
            # Add to database
            db.session.add(new_question)
            db.session.commit()

            # Flash success message
            flash('Question added successfully!', 'success')

            # Redirect to view deck or back to add another question
            return redirect(url_for('view_deck', chapter_id=chapter_id))

        except Exception as e:
            # Handle database errors
            db.session.rollback()
            flash('Error adding question. Please try again.', 'error')

    return render_template('add_question.html', form=form, chapter=chapter)

@app.route('/delete_question/<int:question_id>',methods = ["POST","GET"])
def delete_question(question_id):
    question = QuesAns.query.get_or_404(question_id)
    chapter_id = question.chapter_id

    db.session.delete(question)
    db.session.commit()

    flash('Question deleted successfully!', 'success')
    return redirect(url_for('view_deck', chapter_id=chapter_id))

@app.route('/edit_question/<int:question_id>',methods = ["POST","GET"])
def edit_question(question_id):
    question = QuesAns.query.get_or_404(question_id)

    form = EditQuesAnsForm()

    if form.validate_on_submit():
        question.Question = form.question.data
        question.Answer = form.answer.data
        chapter_id = question.chapter_id

        db.session.commit()

        return redirect(url_for("view_deck",chapter_id = chapter_id))

    return render_template("edit_question.html",form = form,question_id = question_id)


@app.route('/submit_study_deck/<int:chapter_id>', methods=['POST'])
def submit_study_deck(chapter_id):
    # Get question grades from form
    question_grades = {}
    for key, value in request.form.items():
        if key.startswith('question_'):
            try:
                question_id = int(key.replace('question_', ''))
                grade = int(value)
                question_grades[question_id] = grade
            except ValueError:
                # Handle cases where parsing fails (e.g., malformed data)
                print(f"Warning: Could not parse form data for key {key}, value {value}")
                continue

    # Get the actual question objects
    question_ids = list(question_grades.keys())

    # IMPORTANT: Fetch only the questions that were submitted, within the chapter.
    # This prevents malicious users from submitting grades for questions outside their chapter.
    questions = QuesAns.query.filter(
        QuesAns.id.in_(question_ids),
        QuesAns.chapter_id == chapter_id  # Added chapter_id filter for security
    ).all()

    # Update using algorithm (modifies the objects in-place)
    result = sm2.update_questions_batch(questions, question_grades)

    if result['success']:
        db.session.commit()  # YOU handle the database commit
        # --- ADDED: Flash message and redirect for user feedback ---
        from flask import flash, redirect, url_for
        flash(result.get('message', 'Study session completed successfully!'), 'success')
        # Redirect back to the study deck for the same chapter
        return redirect(url_for('study_deck', chapter_id=chapter_id))
    else:
        db.session.rollback()
        # --- ADDED: Flash message and redirect for user feedback ---
        from flask import flash, redirect, url_for
        error_message = result.get('message', 'An error occurred during study session.')
        if result.get('errors'):
            error_message += " Errors: " + ", ".join(result['errors'])
        flash(error_message, 'error')
        # Redirect back to the study deck for the same chapter
        return redirect(url_for('study_deck', chapter_id=chapter_id))


@app.route('/study_deck/<int:chapter_id>')
def study_deck(chapter_id):

    all_questions = QuesAns.query.filter_by(chapter_id=chapter_id).all()
    chapter = Chapter.query.get_or_404(chapter_id)
    chapter_name = chapter.Chapters

    # Pass the list to the algorithm
    study_questions = sm2.get_chapter_questions_for_study(all_questions, limit=200)
    stats = sm2.get_study_statistics(all_questions)

    # --- ADDED: Prepare questions for the template with is_new and days_until_review ---
    from datetime import datetime, timedelta

    processed_study_questions = []
    for q in study_questions:
        q.is_new = (q.RevisedDate is None)
        if q.RecallDate:
            q.days_until_review = (q.RecallDate.date() - datetime.now().date()).days
        else:
            q.days_until_review = 0  # Or some other default for new questions to not show as overdue
        processed_study_questions.append(q)
    # ----------------------------------------------------------------------------------

    return render_template('study_deck.html',
                           questions=processed_study_questions,  # Pass the processed list
                           stats=stats,
                           chapter_id=chapter_id,
                           chapter_name = chapter_name
                           )  # Ensure chapter_id is passed for the form action and title

if __name__ == '__main__':
    app.run(debug=True)
