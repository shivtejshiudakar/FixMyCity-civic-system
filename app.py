from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import get_db_connection
from config import Config
from datetime import datetime as dt
import pytz
import os

from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def convert_to_ist(utc_time):
    if not utc_time:
        return utc_time

    utc = pytz.utc
    ist = pytz.timezone("Asia/Kolkata")

    if isinstance(utc_time, str):
        utc_dt = dt.strptime(utc_time, "%Y-%m-%d %H:%M:%S")
    else:
        utc_dt = utc_time

    utc_dt = utc.localize(utc_dt)
    ist_dt = utc_dt.astimezone(ist)

    return ist_dt.strftime("%d %b %Y, %I:%M %p")
    
# Context processor for templates
@app.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
    return dict(current_user=user)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Role required decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role and session.get('role') != 'admin':
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():

    conn = get_db_connection()

    total_issues = conn.execute(
        'SELECT COUNT(*) FROM issues'
    ).fetchone()[0]

    resolved_issues = conn.execute(
        'SELECT COUNT(*) FROM issues WHERE status = "Resolved"'
    ).fetchone()[0]

    conn.close()

    # calculate resolution %
    if total_issues > 0:
        resolution_rate = round((resolved_issues / total_issues) * 100)
    else:
        resolution_rate = 0

    return render_template(
        "index.html",
        total_issues=total_issues,
        resolved_issues=resolved_issues,
        resolution_rate=resolution_rate
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/mission')
def mission():
    return render_template('mission.html')

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        # By default, anyone registering via logic is a citizen
        role = 'citizen' 
        
        # Note: If we want to create staff/admin through form, we'd add logic here.
        # But for security, admins create staff in dashboard, or via direct DB query.
        
        conn = get_db_connection()
        
        # Check if username or email exists
        existing_user = conn.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            conn.close()
            return redirect(url_for('register'))
            
        password_hash = generate_password_hash(password)
        
        # If it's the very first user, make them an admin for demo purposes
        count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if count == 0:
            role = 'admin'
            
        conn.execute('INSERT INTO users (username, email, password_hash, role, full_name) VALUES (?, ?, ?, ?, ?)',
                     (username, email, password_hash, role, full_name))
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, username)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            flash(f'Welcome back, {user["username"]}!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'staff':
                return redirect(url_for('staff_dashboard'))
            else:
                return redirect(url_for('citizen_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))
    
from werkzeug.utils import secure_filename
import uuid
import datetime

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/citizen/dashboard')
@login_required
@role_required('citizen')
def citizen_dashboard():
    conn = get_db_connection()
    user_id = session['user_id']
    
    # Get stats
    total = conn.execute('SELECT COUNT(*) FROM issues WHERE user_id = ?', (user_id,)).fetchone()[0]
    pending = conn.execute('SELECT COUNT(*) FROM issues WHERE user_id = ? AND status IN ("Pending", "In Progress")', (user_id,)).fetchone()[0]
    resolved = conn.execute('SELECT COUNT(*) FROM issues WHERE user_id = ? AND status = "Resolved"', (user_id,)).fetchone()[0]
    
    # Get recent issues
    issues = conn.execute(
        'SELECT * FROM issues WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
        (user_id,)
    ).fetchall()
    issues = [dict(issue) for issue in issues]

    for issue in issues:
        issue['created_at'] = convert_to_ist(issue['created_at'])
    
    conn.close()
    
    return render_template('citizen_dashboard.html', 
                          total_reports=total, 
                          pending_reports=pending, 
                          resolved_reports=resolved, 
                          issues=issues)

@app.route('/submit_issue', methods=['POST'])
@login_required
def submit_issue():
    if request.method == 'POST':
        title = request.form.get('title')
        category = request.form.get('category')
        location_desc = request.form.get('location_desc')
        description = request.form.get('description')
        user_id = session['user_id']
        
        image_path = None
        
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Ensure unique filename
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_path = unique_filename
                
        conn = get_db_connection()
        
        # Simple auto-assignment of department based on category
        department_id = None
        if category == 'Roads & Sidewalks':
            dept = conn.execute('SELECT id FROM departments WHERE name = "Public Works"').fetchone()
        elif category == 'Utilities':
            dept = conn.execute('SELECT id FROM departments WHERE name = "Utilities"').fetchone()
        elif category == 'Sanitation':
            dept = conn.execute('SELECT id FROM departments WHERE name = "Maintenance & Safety"').fetchone()
        else:
            dept = conn.execute('SELECT id FROM departments WHERE name = "Maintenance & Safety"').fetchone()
            
        if dept:
            department_id = dept['id']
            
        cursor = conn.execute(
            'INSERT INTO issues (user_id, title, category, location_desc, description, image_path, department_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, title, category, location_desc, description, image_path, department_id)
        )
        issue_id = cursor.lastrowid
        
        # Add initial status update
        conn.execute(
            'INSERT INTO status_updates (issue_id, user_id, status, remarks) VALUES (?, ?, ?, ?)',
            (issue_id, user_id, 'Pending', 'Issue submitted by citizen.')
        )
        
        conn.commit()
        conn.close()
        
        flash('Issue reported successfully! Municipal staff will review it shortly.', 'success')
        return redirect(url_for('citizen_dashboard'))
        
@app.route('/issue/<int:issue_id>')
@login_required
def view_issue(issue_id):
    conn = get_db_connection()

    issue = conn.execute(
        '''SELECT i.*, u.username as reporter_name, d.name as department_name 
           FROM issues i 
           JOIN users u ON i.user_id = u.id 
           LEFT JOIN departments d ON i.department_id = d.id 
           WHERE i.id = ?''',
        (issue_id,)
    ).fetchone()

    if not issue:
        flash('Issue not found.', 'danger')
        conn.close()
        return redirect(url_for('index'))

    # permission check
    if session.get('role') == 'citizen' and issue['user_id'] != session['user_id']:
        flash('You do not have permission to view this issue.', 'danger')
        conn.close()
        return redirect(url_for('citizen_dashboard'))

    updates = conn.execute(
        '''SELECT s.*, u.username, u.role 
           FROM status_updates s 
           JOIN users u ON s.user_id = u.id 
           WHERE s.issue_id = ? 
           ORDER BY s.created_at DESC''',
        (issue_id,)
    ).fetchall()

    conn.close()

    # convert issue row to dict so we can modify fields
    issue = dict(issue)

    # convert issue timestamps
    issue['created_at'] = convert_to_ist(issue['created_at'])
    if issue.get('updated_at'):
        issue['updated_at'] = convert_to_ist(issue['updated_at'])

    # convert updates timestamps
    updates = [dict(update) for update in updates]
    for update in updates:
        update['created_at'] = convert_to_ist(update['created_at'])

    return render_template('view_issue.html', issue=issue, updates=updates)

@app.route('/update_issue_status/<int:issue_id>', methods=['POST'])
@login_required
def update_issue_status(issue_id):
    if session.get('role') not in ['staff', 'admin']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('index'))
        
    status = request.form.get('status')
    remarks = request.form.get('remarks')
    
    conn = get_db_connection()
    
    # Update issue status
    conn.execute('UPDATE issues SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (status, issue_id))
    
    # Insert new status update
    conn.execute(
        'INSERT INTO status_updates (issue_id, user_id, status, remarks) VALUES (?, ?, ?, ?)',
        (issue_id, session['user_id'], status, remarks)
    )
    
    conn.commit()
    conn.close()
    
    flash('Issue status updated successfully.', 'success')
    return redirect(url_for('view_issue', issue_id=issue_id))

@app.route('/staff/dashboard')
@login_required
@role_required('staff')
def staff_dashboard():
    conn = get_db_connection()
    user = conn.execute('SELECT department_id FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    dept_id = user['department_id'] if user else None
    
    # If staff has no department, they see everything (just in case they are unassigned)
    if dept_id:
        issues = conn.execute(
            '''SELECT i.*, u.username as reporter_name 
               FROM issues i JOIN users u ON i.user_id = u.id 
               WHERE i.department_id = ? 
               ORDER BY i.created_at DESC''', (dept_id,)
        ).fetchall()
        issues = [dict(issue) for issue in issues]
        for issue in issues:
            issue['created_at'] = convert_to_ist(issue['created_at'])
        
        dept_name = conn.execute('SELECT name FROM departments WHERE id = ?', (dept_id,)).fetchone()['name']
    else:
        issues = conn.execute(
            '''SELECT i.*, u.username as reporter_name 
               FROM issues i JOIN users u ON i.user_id = u.id 
               ORDER BY i.created_at DESC'''
        ).fetchall()
        issues = [dict(issue) for issue in issues]
        for issue in issues:
            issue['created_at'] = convert_to_ist(issue['created_at'])
        dept_name = "All Departments (Unassigned Staff)"
        
    # Stats
    total = len(issues)
    pending = sum(1 for i in issues if i['status'] in ['Pending', 'In Progress'])
    resolved = sum(1 for i in issues if i['status'] == 'Resolved')
        
    conn.close()
    return render_template('staff_dashboard.html', 
                          issues=issues, 
                          dept_name=dept_name,
                          total=total,
                          pending=pending,
                          resolved=resolved)

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    
    # Get all stats
    stats = {}
    stats['total_users'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    stats['total_issues'] = conn.execute('SELECT COUNT(*) FROM issues').fetchone()[0]
    stats['resolved_issues'] = conn.execute('SELECT COUNT(*) FROM issues WHERE status = "Resolved"').fetchone()[0]
    stats['pending_issues'] = conn.execute('SELECT COUNT(*) FROM issues WHERE status IN ("Pending", "In Progress")').fetchone()[0]
    
    # Issues breakdown by category
    categories_raw = conn.execute('SELECT category, COUNT(*) as count FROM issues GROUP BY category').fetchall()
    categories_keys = [c['category'] for c in categories_raw]
    categories_values = [c['count'] for c in categories_raw]
    
    # Recent issues
    recent_issues = conn.execute(
    '''SELECT i.*, u.username as reporter_name, d.name as department_name 
       FROM issues i 
       JOIN users u ON i.user_id = u.id 
       LEFT JOIN departments d ON i.department_id = d.id 
       ORDER BY i.created_at DESC LIMIT 10'''
).fetchall()

    recent_issues = [dict(issue) for issue in recent_issues]
    for issue in recent_issues:
        issue['created_at'] = convert_to_ist(issue['created_at'])

    # Staff list (to allow simple management view)
    all_users = conn.execute(
        '''SELECT u.id, u.username, u.email, u.role, d.name as department_name 
           FROM users u LEFT JOIN departments d ON u.department_id = d.id 
           ORDER BY u.created_at DESC LIMIT 50'''
    ).fetchall()
    
    conn.close()
    
    chart_data = {
        'labels': categories_keys,
        'data': categories_values
    }
    
    return render_template('admin_dashboard.html', 
                          stats=stats, 
                          recent_issues=recent_issues,
                          users=all_users,
                          chart_data=chart_data)

@app.route('/admin/add_staff', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def add_staff():
    conn = get_db_connection()

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        department_id = request.form.get('department_id')

        # validation
        if not username or not email or not password or not department_id:
            flash('All fields are required.', 'danger')
            conn.close()
            return redirect(url_for('add_staff'))

        # check existing email
        existing_user = conn.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()

        if existing_user:
            flash('Email already registered.', 'danger')
            conn.close()
            return redirect(url_for('add_staff'))

        hashed_password = generate_password_hash(password)

        conn.execute(
            '''INSERT INTO users 
               (username, email, password_hash, role, department_id) 
               VALUES (?, ?, ?, "staff", ?)''',
            (username, email, hashed_password, department_id)
        )

        conn.commit()
        conn.close()

        flash('Staff member added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))

    # GET request → load departments for dropdown
    departments = conn.execute(
        'SELECT * FROM departments'
    ).fetchall()

    conn.close()

    return render_template('add_staff.html', departments=departments)


import csv
from flask import Response

@app.route('/admin/export_report')
@login_required
@role_required('admin')
def export_report_form():

    conn = get_db_connection()

    departments = conn.execute(
        "SELECT id, name FROM departments"
    ).fetchall()

    conn.close()

    return render_template("export_report.html", departments=departments)

@app.route('/admin/export_report_download')
@login_required
@role_required('admin')
def export_report_download():

    month = request.args.get("month")
    department = request.args.get("department")

    conn = get_db_connection()

    query = '''
        SELECT i.id, i.title, i.category, i.location_desc, i.status,
               i.created_at, u.username as reporter_name,
               d.name as department
        FROM issues i
        JOIN users u ON i.user_id = u.id
        LEFT JOIN departments d ON i.department_id = d.id
        WHERE 1=1
    '''

    params = []

    if month:
        query += " AND strftime('%Y-%m', i.created_at) = ?"
        params.append(month)

    if department and department != "all":
        query += " AND i.department_id = ?"
        params.append(department)

    query += " ORDER BY i.created_at DESC"

    issues = conn.execute(query, params).fetchall()

    conn.close()

    issues = [dict(issue) for issue in issues]

    for issue in issues:
        issue['created_at'] = convert_to_ist(issue['created_at'])

    def generate():

        header = [
            "Issue ID",
            "Title",
            "Category",
            "Location",
            "Status",
            "Reporter",
            "Department",
            "Reported Time (IST)"
        ]

        yield ','.join(header) + '\n'

        for issue in issues:
            row = [
                str(issue['id']),
                issue['title'],
                issue['category'],
                issue['location_desc'],
                issue['status'],
                issue['reporter_name'],
                issue['department'] if issue['department'] else "Unassigned",
                issue['created_at']
            ]

            yield ','.join(row) + '\n'

    return Response(
        generate(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=fixmycity_report.csv"
        }
    )


@app.route('/staff/export_report')
@login_required
@role_required('staff')
def staff_export_report():

    conn = get_db_connection()

    # Get department of logged-in staff
    user = conn.execute(
        "SELECT department_id FROM users WHERE id = ?",
        (session['user_id'],)
    ).fetchone()

    department_id = user['department_id']

    # Get issues only for this department
    issues = conn.execute(
        '''
        SELECT i.id, i.title, i.category, i.location_desc,
               i.status, i.created_at,
               u.username as reporter_name
        FROM issues i
        JOIN users u ON i.user_id = u.id
        WHERE i.department_id = ?
        ORDER BY i.created_at DESC
        ''',
        (department_id,)
    ).fetchall()

    conn.close()

    issues = [dict(issue) for issue in issues]

    # Convert time to IST
    for issue in issues:
        issue['created_at'] = convert_to_ist(issue['created_at'])

    def generate():

        header = [
            "Issue ID",
            "Title",
            "Category",
            "Location",
            "Status",
            "Reporter",
            "Reported Time (IST)"
        ]

        yield ",".join(header) + "\n"

        for issue in issues:
            row = [
                str(issue["id"]),
                issue["title"],
                issue["category"],
                issue["location_desc"],
                issue["status"],
                issue["reporter_name"],
                issue["created_at"]
            ]

            yield ",".join(row) + "\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=department_issues_report.csv"
        }
    )

@app.route('/admin/delete_issue/<int:issue_id>', methods=['POST'])
@login_required
@role_required('admin')
def delete_issue(issue_id):
    conn = get_db_connection()

    # Delete related status updates first (important for foreign key)
    conn.execute('DELETE FROM status_updates WHERE issue_id = ?', (issue_id,))

    # Delete issue
    conn.execute('DELETE FROM issues WHERE id = ?', (issue_id,))

    conn.commit()
    conn.close()

    flash('Issue deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))




if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)