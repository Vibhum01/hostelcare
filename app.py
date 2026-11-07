
import os
import uuid
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

from io import BytesIO
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

from database import (
    save_complaint,
    get_complaints,
    get_all_complaints,
    get_complaint_by_id,
    update_complaint_status,
    update_complaint_priority,
    register_student,
    get_student_by_email,
    submit_complaint_feedback,
    get_feedback_analytics
)

from email_service import send_email

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

app.config['SESSION_PERMANENT'] = False
app.config['SESSION_REFRESH_EACH_REQUEST'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def student_required():
    return session.get('student_id') is not None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if student_required():
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        student_name = request.form.get('student_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not student_name or not email or not password:
            return render_template(
                'student_register.html',
                error='All fields are required.'
            )

        if len(password) < 8:
            return render_template(
                'student_register.html',
                error='Password must contain at least 8 characters.'
            )

        if password != confirm_password:
            return render_template(
                'student_register.html',
                error='Passwords do not match.'
            )

        if register_student(student_name, email, password):
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('student_login'))

        return render_template(
            'student_register.html',
            error='This email is already registered.'
        )

    return render_template('student_register.html')


@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if student_required():
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        student = get_student_by_email(email)

        if student and check_password_hash(student[3], password):
            session['student_id'] = student[0]
            session['student_name'] = student[1]
            session['student_email'] = student[2]

            flash('Login successful!', 'success')
            return redirect(url_for('student_dashboard'))

        return render_template(
            'student_login.html',
            error='Invalid email or password.'
        )

    return render_template('student_login.html')


@app.route('/student/dashboard')
def student_dashboard():
    if not student_required():
        return redirect(url_for('student_login'))

    complaints = get_complaints(session['student_email'])

    return render_template(
        'student_dashboard.html',
        complaints=complaints,
        searched=True
    )

@app.route('/student/feedback/<int:complaint_id>', methods=['GET', 'POST'])
def student_feedback(complaint_id):
    if not student_required():
        return redirect(url_for('student_login'))

    complaints = get_complaints(session['student_email'])

    complaint = next(
        (item for item in complaints if item[0] == complaint_id),
        None
    )

    if complaint is None:
        flash('Complaint not found.', 'error')
        return redirect(url_for('student_dashboard'))

    if complaint[7] != 'Resolved':
        flash('Feedback is available only for resolved complaints.', 'error')
        return redirect(url_for('student_dashboard'))

    if complaint[11] is not None:
        flash('Feedback has already been submitted.', 'error')
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        rating = request.form.get('rating', '')
        feedback = request.form.get('feedback', '').strip()

        if rating not in ['1', '2', '3', '4', '5'] or not feedback:
            return render_template(
                'feedback.html',
                complaint_id = complaint_id,
                error = 'Please select a rating and enter your feedback.'
            )

        saved = submit_complaint_feedback(
            complaint_id,
            session['student_email'],
            int(rating),
            feedback
        )

        if saved:
            flash('Feedback submitted successfully!', 'success')
        else:
            flash('Feedback could not be submitted. Please try again.', 'error')

        return redirect(url_for('student_dashboard'))

    return render_template(
        'feedback.html',
        complaint_id=complaint_id
    )


@app.route('/student/logout')
def student_logout():
    session.clear()

    flash('You have been logged out.', 'success')
    return redirect(url_for('student_login'))


@app.route('/complaint')
def complaint():
    if not student_required():
        return redirect(url_for('student_login'))

    return render_template('submit_complaint.html')


@app.route('/submit', methods=['POST'])
def submit():
    if not student_required():
        return redirect(url_for('student_login'))

    student_name = session['student_name']
    email = session['student_email']

    room_number = request.form['room_number']
    category = request.form['category']
    subject = request.form['subject']
    description = request.form['description']

    image = request.files.get('complaint_image')
    image_filename = None

    if image and image.filename:
        if not allowed_file(image.filename):
            flash(
                'Only PNG, JPG, JPEG and WEBP images are allowed.',
                'error'
            )
            return redirect(url_for('complaint'))

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        original_filename = secure_filename(image.filename)
        extension = original_filename.rsplit('.', 1)[1].lower()
        image_filename = f"{uuid.uuid4().hex}.{extension}"

        image_path = os.path.join(
            app.config['UPLOAD_FOLDER'],
            image_filename
        )

        image.save(image_path)

    complaint_id = save_complaint(
        student_name,
        email,
        room_number,
        category,
        subject,
        description,
        image_filename
    )

    email_subject = f"HostelCare Complaint Received - #{complaint_id}"

    email_body = f"""
Hello {student_name},

Your complaint has been successfully submitted to HostelCare.

Complaint ID: #{complaint_id}
Category: {category}
Subject: {subject}
Room Number: {room_number}
Current Status: Pending

Our hostel administration will review your complaint.

You can track your complaint through your student dashboard.

Thank you,
HostelCare Team
"""

    send_email(email, email_subject, email_body)

    flash('Complaint submitted successfully!', 'success')
    return redirect(url_for('student_dashboard'))


@app.route('/track')
def track():
    if not student_required():
        return redirect(url_for('student_login'))

    return redirect(url_for('student_dashboard'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.clear()
            session.permanent = False
            session['admin_logged_in'] = True

            flash('Admin login successful!', 'success')
            return redirect(url_for('admin'))

        flash('Invalid username or password.', 'error')

    return render_template('admin_login.html')


@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    all_complaints = get_all_complaints()

    total_complaints = len(all_complaints)

    pending_complaints = sum(
        1 for complaint in all_complaints
        if complaint[7] == 'Pending'
    )

    in_progress_complaints = sum(
        1 for complaint in all_complaints
        if complaint[7] == 'In Progress'
    )

    resolved_complaints = sum(
        1 for complaint in all_complaints
        if complaint[7] == 'Resolved'
    )

    search_query = request.args.get('search', '').strip()
    selected_status = request.args.get('status', '')
    selected_category = request.args.get('category', '')
    selected_priority = request.args.get('priority', '')
    sort_by = request.args.get('sort', 'newest')

    complaints = all_complaints

    if search_query:
        complaints = [
            complaint for complaint in complaints
            if search_query.lower() in complaint[1].lower()
            or search_query.lower() in complaint[2].lower()
        ]

    if selected_status:
        complaints = [
            complaint for complaint in complaints
            if complaint[7] == selected_status
        ]

    if selected_category:
        complaints = [
            complaint for complaint in complaints
            if complaint[4] == selected_category
        ]

    if selected_priority:
        complaints = [
            complaint for complaint in complaints
            if complaint[8] == selected_priority
        ]

    if sort_by == 'newest':
        complaints.sort(
            key=lambda complaint: complaint[0],
            reverse=True
        )

    elif sort_by == 'oldest':
        complaints.sort(
            key=lambda complaint: complaint[0]
        )

    elif sort_by == 'high_priority':
        priority_order = {
            'High': 1,
            'Medium': 2,
            'Low': 3
        }

        complaints.sort(
            key=lambda complaint: (
                priority_order.get(complaint[8], 4),
                -complaint[0]
            )
        )

    elif sort_by == 'low_priority':
        priority_order = {
            'Low': 1,
            'Medium': 2,
            'High': 3
        }

        complaints.sort(
            key=lambda complaint: (
                priority_order.get(complaint[8], 4),
                -complaint[0]
            )
        )

    else:
        sort_by = 'newest'
        complaints.sort(
            key=lambda complaint: complaint[0],
            reverse=True
        )

    categories = sorted(set(
        complaint[4] for complaint in all_complaints
    ))

    category_counts = {
        category: sum(
            1 for complaint in all_complaints
            if complaint[4] == category
        )
        for category in categories
    }

    feedback_analytics = get_feedback_analytics()

    return render_template(
        'admin.html',
        complaints=complaints,
        total_complaints=total_complaints,
        pending_complaints=pending_complaints,
        in_progress_complaints=in_progress_complaints,
        resolved_complaints=resolved_complaints,
        categories=categories,
        category_counts=category_counts,
        search_query=search_query,
        selected_status=selected_status,
        selected_category=selected_category,
        selected_priority=selected_priority,
        sort_by=sort_by,
        feedback_analytics=feedback_analytics
    )


@app.route('/admin/export/excel')
def export_excel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    complaints = get_all_complaints()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Hostel Complaints'

    headers = [
        'Complaint ID',
        'Student Name',
        'Email',
        'Room Number',
        'Category',
        'Subject',
        'Description',
        'Status',
        'Priority',
        'Image',
        'Submitted On',
        'Rating',
        'Feedback',
        'Feedback Submitted On'
    ]

    worksheet.append(headers)

    for complaint in complaints:
        worksheet.append(list(complaint))

    for column in worksheet.columns:
        max_length = 0
        column_letter = column[0].column_letter

        for cell in column:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))

        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 40)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='HostelCare_Complaints.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/admin/export/pdf')
def export_pdf():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    complaints = get_all_complaints()

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()

    data = [[
        'ID',
        'Student',
        'Email',
        'Room',
        'Category',
        'Subject',
        'Status',
        'Priority',
        'Submitted',
        'Rating',
        'Feedback'
    ]]

    for complaint in complaints:
        data.append([
            complaint[0],
            complaint[1],
            complaint[2],
            complaint[3],
            complaint[4],
            Paragraph(str(complaint[5]), styles['Normal']),
            complaint[7],
            complaint[8],
            complaint[10],
            complaint[11] if complaint [11] else '-',
            Paragraph(str(complaint[12]) if complaint[12] else '-', styles['Normal'])
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[30, 70, 110, 40, 65, 110, 55, 55, 75, 40, 100]
    )

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1 ,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))

    document.build([table])

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='HostelCare_Complaints.pdf',
        mimetype='application/pdf'
    )


@app.route('/admin/complaint/<int:complaint_id>')
def complaint_details(complaint_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    all_complaints = get_all_complaints()

    complaint = next(
        (
            item for item in all_complaints
            if item[0] == complaint_id
        ),
        None
    )

    if complaint is None:
        flash('Complaint not found.', 'error')
        return redirect(url_for('admin'))

    return render_template(
        'complaint_details.html',
        complaint=complaint
    )


@app.route('/update_status/<int:complaint_id>', methods=['POST'])
def update_status(complaint_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    status = request.form['status']

    if status not in ['Pending', 'In Progress', 'Resolved']:
        flash('Invalid complaint status.', 'error')
        return redirect(url_for('admin'))

    complaint = get_complaint_by_id(complaint_id)

    if complaint is None:
        flash('Complaint not found.', 'error')
        return redirect(url_for('admin'))

    update_complaint_status(complaint_id, status)

    if complaint[4] != status:
        student_name = complaint[1]
        student_email = complaint[2]
        complaint_subject = complaint[3]

        email_subject = f"HostelCare Status Update - #{complaint_id}"

        email_body = f"""
Hello {student_name},

The status of your HostelCare complaint has been updated.

Complaint ID: #{complaint_id}
Subject: {complaint_subject}
Previous Status: {complaint[4]}
New Status: {status}

You can track your complaint through your student dashboard.

Thank you,
HostelCare Team
"""

        send_email(student_email, email_subject, email_body)

    flash('Complaint status updated successfully!', 'success')
    return redirect(url_for('admin'))


@app.route('/update_priority/<int:complaint_id>', methods=['POST'])
def update_priority(complaint_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    priority = request.form['priority']

    if priority not in ['High', 'Medium', 'Low']:
        flash('Invalid complaint priority.', 'error')
        return redirect(url_for('admin'))

    update_complaint_priority(complaint_id, priority)

    flash('Complaint priority updated successfully!', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin_login'))


@app.errorhandler(413)
def file_too_large(error):
    flash('Image size must be less than 16 MB.', 'error')
    return redirect(url_for('complaint'))


@app.after_request
def prevent_admin_cache(response):
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response


if __name__ == '__main__':
    app.run(debug=True)
