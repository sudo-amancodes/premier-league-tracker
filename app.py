import os, flask, requests, json, flask_login
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from src.models import db, User, SoccerTeam, UserWatchlistTeams
from flask import request, jsonify, redirect, url_for, session, render_template, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

from flask import request, jsonify, redirect, url_for, session, render_template

app = flask.Flask(__name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASS")}@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}'
app.secret_key = os.getenv("SECRET_KEY")

db.init_app(app)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.get('/')
@login_required
def index():
    uri = 'https://api.football-data.org/v4/competitions/PL/standings'
    headers = { 'X-Auth-Token': os.getenv("API_KEY") }

    response = requests.get(uri, headers=headers)

    if response.status_code == 200:
        data = response.json()
        teams = [
            {
                'id': team['team']['id'],
                'name': team['team']['name'],
                'wins_draws_losses': f"{team['won']}-{team['draw']}-{team['lost']}",
                'crest': team['team']['crest']
            }
            for team in data['standings'][0]['table']
        ]

        for team in teams:
            existing_team = SoccerTeam.query.filter_by(team_id=team['id']).first()
            if not existing_team:
                new_team = SoccerTeam(
                    team_id=team['id'],
                    team_name=team['name'],
                    wins_draws_losses=team['wins_draws_losses'],
                    logo=team['crest']
                )
                db.session.add(new_team)
        db.session.commit()

        user_watchlist_team_ids = [t.team_id for t in current_user.watchlist_teams]

        available_teams = [team for team in teams if team['id'] not in user_watchlist_team_ids]

        return render_template('index.html', teams=available_teams)
    else:
        flash('Failed to fetch teams (API is overcalled). Please try again in 1 minute.', 'danger')
        return render_template('index.html')

@app.get('/register')
def register_page():
    return render_template('register.html')

@app.post('/register')
def register():
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    username = request.form.get('username')
    password = request.form.get('password')

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash('Username already exists.', 'danger')
        return redirect(url_for('login_page'))

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256:600000')
    
    new_user = User(first_name=first_name, last_name=last_name, username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    flash('Registration successful. Please log in.', 'success')
    return redirect(url_for('login'))
    

@app.get('/login')
def login_page():
    return render_template('login.html')

@app.post('/login')
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password, password):
        login_user(user)
        flash('Login successful!', 'success')
        return redirect(url_for('index'))
    else:
        flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.get('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login_page'))


@app.get('/upcominggames')
@login_required
def upcoming_games():
    sort_by = request.args.get('sort_by', 'date')

    watchlist_team_ids = [wt.team_id for wt in UserWatchlistTeams.query.filter_by(user_id=current_user.user_id).all()]

    if not watchlist_team_ids:
        return render_template('upcoming_games.html', grouped_matches={}, sort_by=sort_by, response_status=200)

    upcoming_matches = set()
    for team_id in watchlist_team_ids:
        uri = f'https://api.football-data.org/v4/teams/{team_id}/matches?status=SCHEDULED'
        headers = {'X-Auth-Token': os.getenv("API_KEY")}
        response = requests.get(uri, headers=headers)

        if response.status_code == 200:
            matches = response.json()['matches']
            for match in matches:
                match_info = (
                    match['homeTeam']['name'],
                    match['awayTeam']['name'],
                    match['utcDate'],
                    match['homeTeam']['crest'],
                    match['awayTeam']['crest']
                )
                upcoming_matches.add(match_info)

    if not upcoming_matches:
        return render_template('upcoming_games.html', grouped_matches={}, sort_by=sort_by, response_status=404)
    
    upcoming_matches_list = [
        {
            'home_team': m[0],
            'away_team': m[1],
            'date': m[2],
            'home_logo': m[3],   
            'away_logo': m[4]    
        } for m in upcoming_matches
    ]
    upcoming_matches_list.sort(key=lambda x: x['date'])

    if sort_by == 'home_team':
        upcoming_matches_list.sort(key=lambda x: x['home_team'])
    elif sort_by == 'away_team':
        upcoming_matches_list.sort(key=lambda x: x['away_team'])
    elif sort_by == 'date_top':
        upcoming_matches_list.sort(key=lambda x: x['date'])
    elif sort_by == 'date_bottom':
        upcoming_matches_list.sort(key=lambda x: x['date'], reverse=True)

    grouped_matches = {}
    for match in upcoming_matches_list:
        match_date = match['date'][:10] 
        if match_date not in grouped_matches:
            grouped_matches[match_date] = []
        grouped_matches[match_date].append(match)

    return render_template('upcoming_games.html', grouped_matches=grouped_matches, sort_by=sort_by, response_status=response.status_code)

@app.post('/add_to_watchlist')
@login_required
def add_to_watchlist():
    team_id = request.json.get('team_id')
    
    existing_watchlist_entry = UserWatchlistTeams.query.filter_by(user_id=current_user.user_id, team_id=team_id).first()

    if not existing_watchlist_entry:
        new_watchlist_entry = UserWatchlistTeams(user_id=current_user.user_id, team_id=team_id)
        db.session.add(new_watchlist_entry)
        db.session.commit()
        return jsonify({'message': 'Team added to watchlist successfully!'}), 200
    else:
        return jsonify({'message': 'Team is already in your watchlist.'}), 200

@app.get('/profile')
@login_required
def profile():
    watchlist_teams = [
        SoccerTeam.query.filter_by(team_id=team.team_id).first()
        for team in current_user.watchlist_teams
    ]
    
    teams_count = len(watchlist_teams)

    return render_template('profile.html', watchlist_teams=watchlist_teams, teams_count=teams_count)


@app.post('/update_profile_pic')
@login_required
def update_profile_pic():
    if 'profile_pic' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('profile'))

    file = request.files['profile_pic']
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('profile'))

    if file and allowed_file(file.filename):  
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.root_path, 'static/profile_pics', filename)
        file.save(filepath)

        current_user.profile_picture = filename
        db.session.commit()

        flash('Profile picture updated!', 'success')
        return redirect(url_for('profile'))
    else:
        flash('Invalid file type', 'danger')
        return redirect(url_for('profile'))
    
@app.post('/remove_team/<int:team_id>')
@login_required
def remove_team(team_id):
    watchlist_entry = UserWatchlistTeams.query.filter_by(user_id=current_user.user_id, team_id=team_id).first()

    if watchlist_entry:
        db.session.delete(watchlist_entry)
        db.session.commit()
        flash('Team removed from your watchlist.', 'success')
    else:
        flash('Team not found in your watchlist.', 'danger')

    return redirect(url_for('profile'))



app.config['TEMPLATES_AUTO_RELOAD'] = True

if __name__ == '__main__':
    app.run(debug=True)