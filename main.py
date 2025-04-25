from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

db_config = {
    'host': 'localhost',
    'user': 'eswar_root',
    'password': 'root',
    'database': 'ems'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

def execute_query(query, params=None, fetch_one=False):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params)
    
    if fetch_one:
        result = cursor.fetchone()
    else:
        result = cursor.fetchall()
    
    conn.commit()
    cursor.close()
    conn.close()
    return result

def update_election_statuses():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    execute_query(
        "UPDATE elections SET status = 'upcoming' WHERE start_date > %s",
        (now,)
    )
    execute_query(
        "UPDATE elections SET status = 'ongoing' WHERE start_date <= %s AND end_date >= %s",
        (now, now)
    )
    execute_query(
        "UPDATE elections SET status = 'completed' WHERE end_date < %s",
        (now,)
    )

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        user_type = session['user_type']
        if user_type == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user_type == 'voter':
            return redirect(url_for('voter_dashboard'))
        elif user_type == 'candidate':
            return redirect(url_for('candidate_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = execute_query(
            "SELECT * FROM users WHERE username = %s",
            (username,),
            fetch_one=True
        )
        
        if user and user['password'] == password: 
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['user_type'] = user['user_type']
            session['full_name'] = user['full_name']
            
            if user['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['user_type'] == 'voter':
                return redirect(url_for('voter_dashboard'))
            elif user['user_type'] == 'candidate':
                return redirect(url_for('candidate_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  
        email = request.form['email']
        full_name = request.form['full_name']
        user_type = request.form['user_type']
        
        try:
            
            execute_query(
                "INSERT INTO users (username, password, email, full_name, user_type) VALUES (%s, %s, %s, %s, %s)",
                (username, password, email, full_name, user_type) 
            )
            
            if user_type == 'candidate':
                user = execute_query(
                    "SELECT user_id FROM users WHERE username = %s",
                    (username,),
                    fetch_one=True
                )
                execute_query(
                    "INSERT INTO candidates (user_id) VALUES (%s)",
                    (user['user_id'],)
                )
            elif user_type == 'voter':
                user = execute_query(
                    "SELECT user_id FROM users WHERE username = %s",
                    (username,),
                    fetch_one=True
                )
                execute_query(
                    "INSERT INTO voters (user_id) VALUES (%s)",
                    (user['user_id'],)
                )
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f'Registration failed: {err}', 'danger')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Admin routes
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    update_election_statuses()
    elections = execute_query(
        "SELECT * FROM elections ORDER BY start_date DESC"
    )
    return render_template('admin/admin_dashboard.html', elections=elections)

@app.route('/admin/create_election', methods=['GET', 'POST'])
def create_election():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        
        try:
            execute_query(
                "INSERT INTO elections (title, description, start_date, end_date, created_by) VALUES (%s, %s, %s, %s, %s)",
                (title, description, start_date, end_date, session['user_id'])
            )
            flash('Election created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except mysql.connector.Error as err:
            flash(f'Failed to create election: {err}', 'danger')
    
    return render_template('admin/create_election.html')

@app.route('/admin/election/<int:election_id>')
def view_election(election_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    update_election_statuses()
    election = execute_query(
        "SELECT * FROM elections WHERE election_id = %s",
        (election_id,),
        fetch_one=True
    )
    
    candidates = execute_query(
        """SELECT c.candidate_id, u.full_name, c.party_affiliation 
           FROM election_candidates ec
           JOIN candidates c ON ec.candidate_id = c.candidate_id
           JOIN users u ON c.user_id = u.user_id
           WHERE ec.election_id = %s""",
        (election_id,)
    )
    
    vote_counts = execute_query(
        """SELECT c.candidate_id, u.full_name, COUNT(v.vote_id) as vote_count
           FROM votes v
           JOIN candidates c ON v.candidate_id = c.candidate_id
           JOIN users u ON c.user_id = u.user_id
           WHERE v.election_id = %s
           GROUP BY c.candidate_id, u.full_name""",
        (election_id,)
    )
    
    return render_template('admin/view_election.html', 
                         election=election, 
                         candidates=candidates, 
                         vote_counts=vote_counts)

@app.route('/admin/add_candidate/<int:election_id>', methods=['GET', 'POST'])
def add_candidate(election_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        candidate_id = request.form['candidate_id']
        
        try:
            execute_query(
                "INSERT INTO election_candidates (election_id, candidate_id) VALUES (%s, %s)",
                (election_id, candidate_id)
            )
            flash('Candidate added to election successfully!', 'success')
            return redirect(url_for('view_election', election_id=election_id))
        except mysql.connector.Error as err:
            flash(f'Failed to add candidate: {err}', 'danger')
    
    candidates = execute_query(
        """SELECT c.candidate_id, u.full_name 
           FROM candidates c
           JOIN users u ON c.user_id = u.user_id
           WHERE c.candidate_id NOT IN (
               SELECT candidate_id FROM election_candidates WHERE election_id = %s
           )""",
        (election_id,)
    )
    
    return render_template('admin/add_candidate.html', 
                         election_id=election_id, 
                         candidates=candidates)

# Voter routes
@app.route('/voter/dashboard')
def voter_dashboard():
    if 'user_id' not in session or session['user_type'] != 'voter':
        return redirect(url_for('login'))
    
    update_election_statuses()
    elections = execute_query(
        """SELECT e.* FROM elections e
           WHERE e.end_date > NOW()
           ORDER BY e.start_date ASC"""
    )
    
    voted_elections = execute_query(
        """SELECT e.election_id FROM votes v
           JOIN elections e ON v.election_id = e.election_id
           JOIN voters vr ON v.voter_id = vr.voter_id
           WHERE vr.user_id = %s""",
        (session['user_id'],)
    )
    voted_election_ids = [e['election_id'] for e in voted_elections]
    
    return render_template('voter/voter_dashboard.html', 
                         elections=elections, 
                         voted_election_ids=voted_election_ids)

@app.route('/voter/vote/<int:election_id>', methods=['GET', 'POST'])
def vote(election_id):
    if 'user_id' not in session or session['user_type'] != 'voter':
        return redirect(url_for('login'))
    
    update_election_statuses()
    
    # Check if voter has already voted in this election
    existing_vote = execute_query(
        """SELECT v.vote_id FROM votes v
           JOIN voters vr ON v.voter_id = vr.voter_id
           WHERE vr.user_id = %s AND v.election_id = %s""",
        (session['user_id'], election_id),
        fetch_one=True
    )
    
    if existing_vote:
        flash('You have already voted in this election.', 'warning')
        return redirect(url_for('voter_dashboard'))
    
    # Get election details
    election = execute_query(
        "SELECT * FROM elections WHERE election_id = %s AND end_date > NOW()",
        (election_id,),
        fetch_one=True
    )
    
    if not election:
        flash('This election is not currently active.', 'danger')
        return redirect(url_for('voter_dashboard'))
    
    # Get candidates for this election
    candidates = execute_query(
        """SELECT c.candidate_id, u.full_name, c.party_affiliation, c.bio 
           FROM election_candidates ec
           JOIN candidates c ON ec.candidate_id = c.candidate_id
           JOIN users u ON c.user_id = u.user_id
           WHERE ec.election_id = %s""",
        (election_id,)
    )
    
    if request.method == 'POST':
        candidate_id = request.form['candidate_id']
        
        # Get voter_id from user_id
        voter = execute_query(
            "SELECT voter_id FROM voters WHERE user_id = %s",
            (session['user_id'],),
            fetch_one=True
        )
        
        if not voter:
            flash('Voter record not found.', 'danger')
            return redirect(url_for('voter_dashboard'))
        
        try:
            execute_query(
                "INSERT INTO votes (election_id, candidate_id, voter_id) VALUES (%s, %s, %s)",
                (election_id, candidate_id, voter['voter_id'])
            )
            flash('Your vote has been recorded!', 'success')
            return redirect(url_for('voter_dashboard'))
        except mysql.connector.Error as err:
            flash(f'Failed to record vote: {err}', 'danger')
    
    return render_template('voter/vote.html', 
                         election=election, 
                         candidates=candidates)

# Candidate routes
@app.route('/candidate/dashboard')
def candidate_dashboard():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('login'))
    
    update_election_statuses()
    
    # Get candidate_id from user_id
    candidate = execute_query(
        "SELECT candidate_id FROM candidates WHERE user_id = %s",
        (session['user_id'],),
        fetch_one=True
    )
    
    if not candidate:
        flash('Candidate record not found.', 'danger')
        return redirect(url_for('login'))
    
    # Get elections the candidate is participating in
    elections = execute_query(
        """SELECT e.* FROM elections e
           JOIN election_candidates ec ON e.election_id = ec.election_id
           WHERE ec.candidate_id = %s
           ORDER BY e.start_date DESC""",
        (candidate['candidate_id'],)
    )
    
    return render_template('candidate/candidate_dashboard.html', 
                         elections=elections)

@app.route('/candidate/profile', methods=['GET', 'POST'])
def candidate_profile():
    if 'user_id' not in session or session['user_type'] != 'candidate':
        return redirect(url_for('login'))
    
    # Get candidate info
    candidate = execute_query(
        """SELECT c.*, u.full_name, u.email FROM candidates c
           JOIN users u ON c.user_id = u.user_id
           WHERE c.user_id = %s""",
        (session['user_id'],),
        fetch_one=True
    )
    
    if request.method == 'POST':
        bio = request.form['bio']
        party_affiliation = request.form['party_affiliation']
        
        try:
            execute_query(
                "UPDATE candidates SET bio = %s, party_affiliation = %s WHERE user_id = %s",
                (bio, party_affiliation, session['user_id'])
            )
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('candidate_profile'))
        except mysql.connector.Error as err:
            flash(f'Failed to update profile: {err}', 'danger')
    
    return render_template('candidate/candidate_profile.html', 
                         candidate=candidate)

if __name__ == '__main__':
    app.run(debug=True)