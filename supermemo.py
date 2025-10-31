from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session


class SuperMemo2:
    """
    SuperMemo 2 Algorithm implementation for spaced repetition learning
    Adapted for question-answer format with database integration
    """

    def __init__(self):
        self.DEFAULT_EASINESS = 2.5
        self.DEFAULT_REPETITIONS = 0
        self.DEFAULT_INTERVAL = 1
        self.MIN_EASINESS = 1.3

    def calculate_next_revision(self, question: 'QuesAns', grade: int) -> Dict[str, Any]:
        """
        Calculate the next revision date based on SuperMemo 2 algorithm

        Args:
            question: QuesAns object
            grade: User's recall grade (1-5, where 1=worst, 5=best)

        Returns:
            Dictionary with updated values for the question
        """
        if not (1 <= grade <= 5):
            raise ValueError("Grade must be between 1 and 5")

        # Get current values or defaults for new questions
        easiness_factor = question.EasinessFactor or self.DEFAULT_EASINESS
        repetitions = question.Repetitions or self.DEFAULT_REPETITIONS
        interval = question.Interval or self.DEFAULT_INTERVAL

        current_date = datetime.now()

        # SuperMemo 2 Algorithm Implementation

        # Step 1: Update easiness factor based on grade
        # Formula: EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
        new_easiness_factor = max(
            self.MIN_EASINESS,
            easiness_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
        )

        # Step 2: Determine new interval based on grade
        if grade < 3:
            # Poor recall (grade 1 or 2) - restart the sequence
            new_repetitions = 0
            new_interval = 1
        else:
            # Good recall (grade 3, 4, or 5) - continue the sequence
            new_repetitions = repetitions + 1

            if new_repetitions == 1:
                new_interval = 1
            elif new_repetitions == 2:
                new_interval = 6
            else:
                # For repetitions > 2: I(n) = I(n-1) * EF
                new_interval = round(interval * new_easiness_factor)

        # Step 3: Calculate next recall date
        next_recall_date = current_date + timedelta(days=new_interval)

        return {
            'RevisedDate': current_date,
            'RecallDate': next_recall_date,
            'EasinessFactor': round(new_easiness_factor, 2),
            'Repetitions': new_repetitions,
            'Interval': new_interval,
            'LastGrade': grade
        }

    def update_question_after_review(self, db_session: Session, question: 'QuesAns', grade: int):
        """
        Update a question in the database after review

        Args:
            db_session: SQLAlchemy session
            question: QuesAns object to update
            grade: User's recall grade (1-5)
        """
        update_data = self.calculate_next_revision(question, grade)

        # Update the question object
        for key, value in update_data.items():
            setattr(question, key, value)

        # Commit changes to database
        db_session.commit()

        return question

    def get_due_questions(self, questions: List['QuesAns']) -> List['QuesAns']:
        """
        Get questions that are due for review from a list of questions

        Args:
            questions: List of QuesAns objects

        Returns:
            List of QuesAns objects due for review
        """
        today = datetime.now().date()

        due_questions = []
        for question in questions:
            # New questions (never studied) are always due
            if question.RecallDate is None:
                due_questions.append(question)
            # Questions with recall date <= today are due
            elif question.RecallDate.date() <= today:
                due_questions.append(question)

        return due_questions

    def get_new_questions(self, questions: List['QuesAns']) -> List['QuesAns']:
        """
        Get questions that haven't been studied yet from a list of questions

        Args:
            questions: List of QuesAns objects

        Returns:
            List of new QuesAns objects
        """
        return [q for q in questions if q.RevisedDate is None]

    def get_study_statistics(self, questions: List['QuesAns']) -> Dict[str, Any]:
        """
        Get study statistics for a list of questions

        Args:
            questions: List of QuesAns objects

        Returns:
            Dictionary with study statistics
        """
        if not questions:
            return {
                'total_questions': 0,
                'due_today': 0,
                'new_questions': 0,
                'studied_questions': 0,
                'average_easiness_factor': self.DEFAULT_EASINESS,
                'completion_rate': 0
            }

        due_questions = self.get_due_questions(questions)
        new_questions = self.get_new_questions(questions)
        studied_questions = [q for q in questions if q.RevisedDate is not None]

        # Calculate average easiness factor
        if studied_questions:
            avg_easiness = sum(q.EasinessFactor for q in studied_questions) / len(studied_questions)
        else:
            avg_easiness = self.DEFAULT_EASINESS

        return {
            'total_questions': len(questions),
            'due_today': len(due_questions),
            'new_questions': len(new_questions),
            'studied_questions': len(studied_questions),
            'average_easiness_factor': round(avg_easiness, 2),
            'completion_rate': round((len(studied_questions) / len(questions)) * 100, 1) if questions else 0
        }

    def get_next_review_batch(self, questions: List['QuesAns'], batch_size: int = 10) -> List['QuesAns']:
        """
        Get the next batch of questions for review, prioritizing overdue questions

        Args:
            questions: List of QuesAns objects
            batch_size: Number of questions to return

        Returns:
            List of QuesAns objects for review
        """
        due_questions = self.get_due_questions(questions)

        # Sort by RecallDate (overdue first, then new questions)
        sorted_questions = sorted(
            due_questions,
            key=lambda q: q.RecallDate if q.RecallDate else datetime.min
        )

        return sorted_questions[:batch_size]

    def update_questions_batch(self, questions: List['QuesAns'], question_grades: Dict[int, int]) -> Dict[str, Any]:
        """
        Update multiple questions at once after batch review

        Args:
            questions: List of QuesAns objects
            question_grades: Dictionary mapping question_id to grade (1-5)
                           e.g., {1: 4, 2: 3, 3: 5}

        Returns:
            Dictionary with batch update results
        """
        if not question_grades:
            return {'success': False, 'message': 'No questions to update'}

        # Create a lookup dictionary for questions by ID
        question_lookup = {q.id: q for q in questions}

        updated_questions = []
        errors = []

        try:
            # Process each question in the batch
            for question_id, grade in question_grades.items():
                try:
                    # Validate grade
                    if not (1 <= grade <= 5):
                        errors.append(f"Question {question_id}: Invalid grade {grade}")
                        continue

                    # Get the question from the list
                    question = question_lookup.get(question_id)
                    if not question:
                        errors.append(f"Question {question_id}: Not found in provided list")
                        continue

                    # Calculate new values using SuperMemo 2
                    update_data = self.calculate_next_revision(question, grade)

                    # Update the question object
                    for key, value in update_data.items():
                        setattr(question, key, value)

                    updated_questions.append({
                        'id': question_id,
                        'next_review': update_data['RecallDate'].strftime('%Y-%m-%d'),
                        'interval': update_data['Interval'],
                        'easiness': update_data['EasinessFactor']
                    })

                except Exception as e:
                    errors.append(f"Question {question_id}: {str(e)}")

            return {
                'success': True,
                'updated_count': len(updated_questions),
                'updated_questions': updated_questions,
                'errors': errors,
                'message': f"Successfully updated {len(updated_questions)} questions"
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Batch update failed: {str(e)}",
                'errors': errors
            }

    def get_chapter_questions_for_study(self, questions: List['QuesAns'], limit: int = None) -> List['QuesAns']:
        """
        Get questions that are due for study from a list of questions

        Args:
            questions: List of QuesAns objects
            limit: Optional limit on number of questions

        Returns:
            List of QuesAns objects for the study deck
        """
        # Get due questions (including new ones)
        due_questions = self.get_due_questions(questions)

        # Sort by priority: overdue first, then new, then by recall date
        sorted_questions = sorted(
            due_questions,
            key=lambda q: (
                q.RecallDate if q.RecallDate else datetime.min,
                q.id
            )
        )

        if limit:
            return sorted_questions[:limit]

        return sorted_questions

