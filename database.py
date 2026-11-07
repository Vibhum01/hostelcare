
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash


def connect_db():
    return sqlite3.connect('hostel.db')


def create_table():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            email TEXT NOT NULL,
            room_number TEXT NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            priority TEXT DEFAULT 'Medium',
            image_filename TEXT,
            submitted_at TEXT,
            rating INTEGER,
            feedback TEXT,
            feedback_submitted_at TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT
        )
    ''')

    cursor.execute("PRAGMA table_info(complaints)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'priority' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Medium'"
        )

    if 'image_filename' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN image_filename TEXT"
        )

    if 'submitted_at' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN submitted_at TEXT"
        )

    if 'rating' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN rating INTEGER"
        )

    if 'feedback' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN feedback TEXT"
        )

    if 'feedback_submitted_at' not in columns:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN feedback_submitted_at TEXT"
        )

    conn.commit()
    conn.close()


def register_student(student_name, email, password):
    conn = connect_db()
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        cursor.execute('''
            INSERT INTO students
            (student_name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (
            student_name,
            email.lower().strip(),
            password_hash,
            datetime.now().strftime('%d-%m-%Y %I:%M %p')
        ))

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        conn.close()


def get_student_by_email(email):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, student_name, email, password_hash
        FROM students
        WHERE email = ?
    ''', (email.lower().strip(),))

    student = cursor.fetchone()
    conn.close()

    return student


def save_complaint(student_name, email, room_number, category, subject, description, image_filename=None):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO complaints
        (student_name, email, room_number, category, subject, description, image_filename, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        student_name,
        email,
        room_number,
        category,
        subject,
        description,
        image_filename,
        datetime.now().strftime('%d-%m-%Y %I:%M %p')
    ))

    complaint_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return complaint_id


def get_complaints(email):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, student_name, email, room_number, category,
               subject, description, status, priority, image_filename,
               submitted_at, rating, feedback, feedback_submitted_at
        FROM complaints
        WHERE email = ?
        ORDER BY id DESC
    ''', (email,))

    complaints = cursor.fetchall()
    conn.close()

    return complaints


def get_all_complaints():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, student_name, email, room_number, category,
               subject, description, status, priority, image_filename,
               submitted_at, rating, feedback, feedback_submitted_at
        FROM complaints
        ORDER BY id DESC
    ''')

    complaints = cursor.fetchall()
    conn.close()

    return complaints


def get_complaint_by_id(complaint_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, student_name, email, subject, status
        FROM complaints
        WHERE id = ?
    ''', (complaint_id,))

    complaint = cursor.fetchone()
    conn.close()

    return complaint


def update_complaint_status(complaint_id, status):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE complaints
        SET status = ?
        WHERE id = ?
    ''', (status, complaint_id))

    conn.commit()
    conn.close()


def update_complaint_priority(complaint_id, priority):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE complaints
        SET priority = ?
        WHERE id = ?
    ''', (priority, complaint_id))

    conn.commit()
    conn.close()


def submit_complaint_feedback(complaint_id, email, rating, feedback):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE complaints
        SET rating = ?, feedback = ?, feedback_submitted_at = ?
        WHERE id = ? AND email = ? AND status = 'Resolved'
        AND rating IS NULL
    ''', (
        rating,
        feedback,
        datetime.now().strftime('%d-%m-%Y %I:%M %p'),
        complaint_id,
        email
    ))

    updated = cursor.rowcount

    conn.commit()
    conn.close()

    return updated > 0


def get_feedback_analytics():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT COUNT(rating), AVG(rating) FROM complaints WHERE rating IS NOT NULL
    ''')
    total_feedback, average_rating = cursor.fetchone()

    cursor.execute('''
    SELECT rating, COUNT(*) FROM complaints WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating
    ''')

    rating_data = cursor.fetchall()
    conn.close()

    rating_counts = {
        rating: 0 for rating in range(1, 6)
    }

    for rating, count in rating_data:
        rating_counts[rating] = count

    return {
        'total_feedback': total_feedback,
        'average_rating': round(average_rating, 2) if average_rating else 0,
        'rating_counts': rating_counts
    }

create_table()
