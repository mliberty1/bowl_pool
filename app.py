from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response
from flask_wtf.csrf import CSRFProtect
from models import db, Bowl, Participant, Pick, Settings
from config import Config
from functools import wraps
from datetime import datetime, timezone
import random
import os
import requests
import re
import subprocess
import tempfile
import shutil
from email_validator import validate_email, EmailNotValidError


app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
csrf = CSRFProtect(app)


# Input validation helpers
def validate_string_length(value, field_name, max_length):
    """Validate string length and return sanitized value"""
    if not value:
        return None
    value = str(value).strip()
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or less")
    return value if value else None


def validate_and_sanitize_email(email):
    """Validate email format and sanitize"""
    if not email:
        return None
    email = str(email).strip()
    if not email:
        return None
    try:
        # Validate email format
        validated = validate_email(email, check_deliverability=False)
        return validated.normalized
    except EmailNotValidError as e:
        raise ValueError(f"Invalid email address: {str(e)}")


def sanitize_name(name):
    """Remove newlines and control characters from names to prevent header injection"""
    if not name:
        return name
    # Remove newlines, carriage returns, and other control characters
    name = re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', str(name))
    return name.strip()


@app.context_processor
def inject_current_user():
    """Make current participant available to all templates"""
    participant = None
    if 'participant_id' in session:
        participant = Participant.query.get(session['participant_id'])

    # Also inject test mode status
    settings = Settings.get_instance()
    test_mode = settings.override_datetime is not None

    return dict(current_user=participant, test_mode=test_mode, test_datetime=settings.override_datetime)


def get_current_datetime():
    """Get current datetime, or override if set (for testing)"""
    settings = Settings.get_instance()
    if settings.override_datetime:
        return settings.override_datetime
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'participant_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'participant_id' not in session:
            return redirect(url_for('login'))
        participant = Participant.query.get(session['participant_id'])
        if not participant or not participant.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_participant():
    """Get the currently logged in participant"""
    if 'participant_id' in session:
        return Participant.query.get(session['participant_id'])
    return None


def picks_are_locked():
    """Check if picks are locked (first bowl game has started)"""
    first_bowl = Bowl.query.order_by(Bowl.datetime_utc).first()
    if first_bowl:
        return get_current_datetime() >= first_bowl.datetime_utc
    return False


def calculate_scores():
    """
    Calculate scores for all active participants for all bowls.
    Returns a dict: {participant_id: {bowl_id: score, 'total': total_score}}
    """
    participants = Participant.query.filter_by(is_active=True).all()
    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()

    scores = {}
    for participant in participants:
        scores[participant.id] = {'total': 0}

    for bowl in bowls:
        winner = bowl.get_winner()

        # Skip if game not finished or is a push
        if winner is None:
            for participant in participants:
                scores[participant.id][bowl.id] = 0
            continue

        if winner == 'push':
            for participant in participants:
                scores[participant.id][bowl.id] = 0
            continue

        # Get all picks for this bowl
        picks_for_bowl = Pick.query.filter_by(bowl_id=bowl.id).all()
        pick_dict = {pick.participant_id: pick.picked_team for pick in picks_for_bowl}

        # Count winners and losers
        winners = []
        losers = []
        for participant in participants:
            picked = pick_dict.get(participant.id)
            if picked == winner:
                winners.append(participant.id)
            elif picked:  # They picked but picked wrong
                losers.append(participant.id)
            # If they didn't pick, they don't participate in this game

        num_winners = len(winners)
        num_losers = len(losers)

        # Calculate scores
        for participant in participants:
            if participant.id in winners:
                score = num_losers  # Each winner gets +1 for each loser
                scores[participant.id][bowl.id] = score
                scores[participant.id]['total'] += score
            elif participant.id in losers:
                score = -num_winners  # Each loser gets -1 for each winner
                scores[participant.id][bowl.id] = score
                scores[participant.id]['total'] += score
            else:
                scores[participant.id][bowl.id] = 0

    return scores


# Routes
@app.route('/')
def index():
    """Home page - redirect to scoreboard"""
    return redirect(url_for('scoreboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login using invite token"""
    # Check for token in URL query parameter first
    token_from_url = request.args.get('token', '').strip()
    if token_from_url:
        participant = Participant.query.filter_by(invite_token=token_from_url).first()
        if participant:
            session['participant_id'] = participant.id
            flash(f'Welcome, {participant.get_display_name()}!', 'success')
            # Redirect to scoreboard if picks are locked, otherwise to picks page
            if picks_are_locked():
                return redirect(url_for('scoreboard'))
            return redirect(url_for('picks'))
        else:
            flash('Invalid invite token', 'error')

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        participant = Participant.query.filter_by(invite_token=token).first()

        if participant:
            session['participant_id'] = participant.id
            flash(f'Welcome, {participant.get_display_name()}!', 'success')
            # Redirect to scoreboard if picks are locked, otherwise to picks page
            if picks_are_locked():
                return redirect(url_for('scoreboard'))
            return redirect(url_for('picks'))
        else:
            flash('Invalid invite token', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout"""
    session.pop('participant_id', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Edit participant profile"""
    participant = get_current_participant()

    if request.method == 'POST':
        try:
            # Validate and update participant info
            name = validate_string_length(request.form.get('name'), 'Name', 100)
            if not name:
                flash('Name is required', 'error')
                return redirect(url_for('profile'))

            nickname = validate_string_length(request.form.get('nickname'), 'Nickname', 50)
            email = validate_and_sanitize_email(request.form.get('email'))

            participant.name = sanitize_name(name)
            participant.nickname = sanitize_name(nickname) if nickname else None
            participant.email = email

            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('profile'))
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('profile'))

    return render_template('profile.html', participant=participant)


@app.route('/picks', methods=['GET'])
@login_required
def picks():
    """Entry form for participants to make their picks"""
    participant = get_current_participant()
    locked = picks_are_locked()

    # Get bowls and current picks
    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()
    current_picks = {}
    for pick in participant.picks:
        current_picks[pick.bowl_id] = pick.picked_team

    # Check if all picks are made
    all_picks_made = len(current_picks) == len(bowls)

    return render_template('picks.html',
                           participant=participant,
                           bowls=bowls,
                           current_picks=current_picks,
                           locked=locked,
                           all_picks_made=all_picks_made)


@app.route('/api/save-pick', methods=['POST'])
@login_required
def save_pick():
    """Auto-save a single pick"""
    participant = get_current_participant()
    locked = picks_are_locked()

    if locked:
        return jsonify({'success': False, 'error': 'Picks are locked'}), 400

    data = request.get_json()
    bowl_id = data.get('bowl_id')
    picked_team = data.get('picked_team')

    if not bowl_id or picked_team not in ['favored', 'opponent']:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400

    # Validate bowl exists
    bowl = Bowl.query.get(bowl_id)
    if not bowl:
        return jsonify({'success': False, 'error': 'Bowl game not found'}), 404

    # Update or create pick
    existing_pick = Pick.query.filter_by(
        participant_id=participant.id,
        bowl_id=bowl_id
    ).first()

    if existing_pick:
        existing_pick.picked_team = picked_team
    else:
        new_pick = Pick(
            participant_id=participant.id,
            bowl_id=bowl_id,
            picked_team=picked_team
        )
        db.session.add(new_pick)

    # Check if all picks are now made
    bowls = Bowl.query.all()
    total_bowls = len(bowls)
    total_picks = Pick.query.filter_by(participant_id=participant.id).count()

    # Set is_active to true if all picks are made
    if total_picks == total_bowls:
        participant.is_active = True
    else:
        participant.is_active = False

    db.session.commit()

    return jsonify({
        'success': True,
        'is_active': participant.is_active,
        'total_picks': total_picks,
        'total_bowls': total_bowls
    })


@app.route('/api/clear-picks', methods=['POST'])
@login_required
def clear_picks():
    """Clear all picks"""
    participant = get_current_participant()
    locked = picks_are_locked()

    if locked:
        return jsonify({'success': False, 'error': 'Picks are locked'}), 400

    # Delete all picks for this participant
    Pick.query.filter_by(participant_id=participant.id).delete()

    # Set is_active to false
    participant.is_active = False

    db.session.commit()

    return jsonify({'success': True})


@app.route('/api/randomize-picks', methods=['POST'])
@login_required
def randomize_picks():
    """Randomize all remaining picks"""
    participant = get_current_participant()
    locked = picks_are_locked()

    if locked:
        return jsonify({'success': False, 'error': 'Picks are locked'}), 400

    # Get all bowls
    bowls = Bowl.query.all()

    # Get current picks
    current_picks = {pick.bowl_id: pick for pick in participant.picks}

    # Randomize picks for bowls that don't have picks yet
    for bowl in bowls:
        if bowl.id not in current_picks:
            picked_team = random.choice(['favored', 'opponent'])
            new_pick = Pick(
                participant_id=participant.id,
                bowl_id=bowl.id,
                picked_team=picked_team
            )
            db.session.add(new_pick)

    # Set is_active to true (all picks are now made)
    participant.is_active = True

    db.session.commit()

    # Return all picks for updating the UI
    all_picks = {}
    for pick in Pick.query.filter_by(participant_id=participant.id).all():
        all_picks[pick.bowl_id] = pick.picked_team

    return jsonify({'success': True, 'picks': all_picks})


@app.route('/scoreboard')
def scoreboard():
    """Display scoreboard with all active participants' picks and scores"""
    participants = Participant.query.filter_by(is_active=True).all()
    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()
    locked = picks_are_locked()

    # Get all picks
    all_picks = Pick.query.all()
    pick_dict = {}  # {(participant_id, bowl_id): pick}
    for pick in all_picks:
        pick_dict[(pick.participant_id, pick.bowl_id)] = pick

    # Calculate scores
    scores = calculate_scores()

    # Count picks per team for coloring (before games start)
    pick_counts = {}  # {bowl_id: {'favored': count, 'opponent': count}}
    for bowl in bowls:
        pick_counts[bowl.id] = {'favored': 0, 'opponent': 0}
        for participant in participants:
            pick = pick_dict.get((participant.id, bowl.id))
            if pick:
                pick_counts[bowl.id][pick.picked_team] += 1

    return render_template('scoreboard.html',
                           participants=participants,
                           bowls=bowls,
                           pick_dict=pick_dict,
                           scores=scores,
                           locked=locked,
                           pick_counts=pick_counts,
                           total_participants=len(participants))


@app.route('/admin')
@admin_required
def admin_index():
    """Admin dashboard"""
    return render_template('admin_index.html')


@app.route('/admin/scores', methods=['GET', 'POST'])
@admin_required
def admin_scores():
    """Admin page to enter/update bowl scores"""
    if request.method == 'POST':
        bowl_id = request.form.get('bowl_id')
        bowl = Bowl.query.get(bowl_id)

        if bowl:
            bowl.favored_team_score = request.form.get('favored_team_score', type=int)
            bowl.opponent_score = request.form.get('opponent_score', type=int)
            bowl.status = request.form.get('status', 'not_started')
            bowl.is_ignored = request.form.get('is_ignored') == 'on'

            db.session.commit()
            flash(f'Updated {bowl.name}', 'success')

        return redirect(url_for('admin_scores'))

    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()
    return render_template('admin_scores.html', bowls=bowls)


@app.route('/admin/bowls', methods=['GET', 'POST'])
@admin_required
def admin_bowls():
    """Admin page to manage bowl games"""
    if request.method == 'POST':
        action = request.form.get('action')

        try:
            if action == 'add':
                # Validate inputs
                name = validate_string_length(request.form.get('name'), 'Bowl name', 100)
                favored_team = validate_string_length(request.form.get('favored_team'), 'Favored team', 100)
                opponent = validate_string_length(request.form.get('opponent'), 'Opponent', 100)
                tv_channel = validate_string_length(request.form.get('tv_channel'), 'TV channel', 50)

                if not name or not favored_team or not opponent:
                    flash('Bowl name, favored team, and opponent are required', 'error')
                    return redirect(url_for('admin_bowls'))

                try:
                    datetime_utc = datetime.fromisoformat(request.form.get('datetime_utc'))
                except (ValueError, TypeError):
                    flash('Invalid date/time format', 'error')
                    return redirect(url_for('admin_bowls'))

                # Add new bowl
                bowl = Bowl(
                    name=name,
                    datetime_utc=datetime_utc,
                    favored_team=favored_team,
                    opponent=opponent,
                    spread=float(request.form.get('spread')),
                    tv_channel=tv_channel
                )
                db.session.add(bowl)
                db.session.commit()
                flash(f'Added {bowl.name}', 'success')

            elif action == 'edit':
                bowl_id = request.form.get('bowl_id')
                bowl = Bowl.query.get(bowl_id)
                if bowl:
                    # Validate inputs
                    name = validate_string_length(request.form.get('name'), 'Bowl name', 100)
                    favored_team = validate_string_length(request.form.get('favored_team'), 'Favored team', 100)
                    opponent = validate_string_length(request.form.get('opponent'), 'Opponent', 100)
                    tv_channel = validate_string_length(request.form.get('tv_channel'), 'TV channel', 50)

                    if not name or not favored_team or not opponent:
                        flash('Bowl name, favored team, and opponent are required', 'error')
                        return redirect(url_for('admin_bowls'))

                    try:
                        datetime_utc = datetime.fromisoformat(request.form.get('datetime_utc'))
                    except (ValueError, TypeError):
                        flash('Invalid date/time format', 'error')
                        return redirect(url_for('admin_bowls'))

                    bowl.name = name
                    bowl.datetime_utc = datetime_utc
                    bowl.favored_team = favored_team
                    bowl.opponent = opponent
                    bowl.spread = float(request.form.get('spread'))
                    bowl.tv_channel = tv_channel
                    db.session.commit()
                    flash(f'Updated {bowl.name}', 'success')

            elif action == 'delete':
                bowl_id = request.form.get('bowl_id')
                bowl = Bowl.query.get(bowl_id)
                if bowl:
                    db.session.delete(bowl)
                    db.session.commit()
                    flash(f'Deleted {bowl.name}', 'success')

        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('admin_bowls'))

        return redirect(url_for('admin_bowls'))

    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()
    edit_bowl_id = request.args.get('edit', type=int)
    editing_bowl = None
    if edit_bowl_id:
        editing_bowl = Bowl.query.get(edit_bowl_id)

    return render_template('admin_bowls.html', bowls=bowls, editing_bowl=editing_bowl)


@app.route('/admin/test-mode', methods=['GET', 'POST'])
@admin_required
def admin_test_mode():
    """Admin page to set test mode datetime override"""
    settings = Settings.get_instance()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'set':
            datetime_str = request.form.get('override_datetime')
            try:
                override_dt = datetime.fromisoformat(datetime_str)
                settings.override_datetime = override_dt
                db.session.commit()
                flash(f'Test mode enabled: Time set to {override_dt.strftime("%Y-%m-%d %H:%M UTC")}', 'success')
            except ValueError:
                flash('Invalid datetime format', 'error')

        elif action == 'clear':
            settings.override_datetime = None
            db.session.commit()
            flash('Test mode disabled: Using real time', 'success')

        return redirect(url_for('admin_test_mode'))

    # Get first bowl game for reference
    first_bowl = Bowl.query.order_by(Bowl.datetime_utc).first()

    return render_template('admin_test_mode.html',
                           settings=settings,
                           current_datetime=get_current_datetime(),
                           real_datetime=datetime.now(timezone.utc).replace(tzinfo=None),
                           first_bowl=first_bowl)


@app.route('/admin/participants', methods=['GET', 'POST'])
@admin_required
def admin_participants():
    """Admin page to manage participants"""
    if request.method == 'POST':
        action = request.form.get('action')

        try:
            if action == 'add':
                # Validate inputs
                name = validate_string_length(request.form.get('name'), 'Name', 100)
                if not name:
                    flash('Name is required', 'error')
                    return redirect(url_for('admin_participants'))

                nickname = validate_string_length(request.form.get('nickname'), 'Nickname', 50)
                email = validate_and_sanitize_email(request.form.get('email'))

                # Add new participant
                participant = Participant(
                    name=sanitize_name(name),
                    nickname=sanitize_name(nickname) if nickname else None,
                    email=email,
                    invite_token=Participant.generate_token(),
                    is_admin=request.form.get('is_admin') == 'on'
                )
                db.session.add(participant)
                db.session.commit()
                flash(f'Added {participant.name}', 'success')

            elif action == 'edit':
                participant_id = request.form.get('participant_id')
                participant = Participant.query.get(participant_id)
                if participant:
                    # Validate inputs
                    name = validate_string_length(request.form.get('name'), 'Name', 100)
                    if not name:
                        flash('Name is required', 'error')
                        return redirect(url_for('admin_participants'))

                    nickname = validate_string_length(request.form.get('nickname'), 'Nickname', 50)
                    email = validate_and_sanitize_email(request.form.get('email'))

                    participant.name = sanitize_name(name)
                    participant.nickname = sanitize_name(nickname) if nickname else None
                    participant.email = email
                    participant.is_admin = request.form.get('is_admin') == 'on'
                    db.session.commit()
                    flash(f'Updated {participant.name}', 'success')

            elif action == 'delete':
                participant_id = request.form.get('participant_id')
                participant = Participant.query.get(participant_id)
                if participant:
                    db.session.delete(participant)
                    db.session.commit()
                    flash(f'Deleted {participant.name}', 'success')

        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('admin_participants'))

        return redirect(url_for('admin_participants'))

    participants = Participant.query.all()
    edit_participant_id = request.args.get('edit', type=int)
    editing_participant = None
    if edit_participant_id:
        editing_participant = Participant.query.get(edit_participant_id)

    return render_template('admin_participants.html', participants=participants, editing_participant=editing_participant)


def send_participant_email(participant, base_url):
    """Send login email to a single participant using Mailgun API"""
    api_key = os.environ.get('MAILGUN_API_KEY')
    if not api_key:
        raise ValueError('MAILGUN_API_KEY environment variable not set')

    # Sanitize names to prevent email header injection
    display_name = sanitize_name(participant.get_display_name())
    participant_name = sanitize_name(participant.name)

    login_url = f"{base_url}/login?token={participant.invite_token}"

    email_body = f"""Hello {display_name},

Welcome to the Bowl Pool! You can access your account and make your picks using the following link:

{login_url}

Good luck!

Bowl Pool Admin
"""

    response = requests.post(
        "https://api.mailgun.net/v3/mg.libertyfamily.us/messages",
        auth=("api", api_key),
        data={
            "from": "Bowl Pool <postmaster@mg.libertyfamily.us>",
            "to": f"{participant_name} <{participant.email}>",
            "subject": "Bowl Pool - Your Login Link",
            "text": email_body
        }
    )

    return response


@app.route('/admin/email-participants', methods=['GET', 'POST'])
@admin_required
def admin_email_participants():
    """Admin page to email all participants their login URLs"""
    if request.method == 'POST':
        # Get base URL from request
        base_url = request.url_root.rstrip('/')

        participants = Participant.query.all()
        success_count = 0
        error_count = 0
        errors = []

        for participant in participants:
            if not participant.email:
                errors.append(f"{participant.name}: No email address")
                error_count += 1
                continue

            try:
                response = send_participant_email(participant, base_url)
                if response.status_code == 200:
                    success_count += 1
                else:
                    errors.append(f"{participant.name}: {response.status_code} - {response.text}")
                    error_count += 1
            except Exception as e:
                errors.append(f"{participant.name}: {str(e)}")
                error_count += 1

        if success_count > 0:
            flash(f'Successfully sent {success_count} email(s)', 'success')
        if error_count > 0:
            flash(f'Failed to send {error_count} email(s)', 'error')
            for error in errors:
                flash(error, 'error')

        return redirect(url_for('admin_email_participants'))

    # GET request - show the page
    participants = Participant.query.all()
    participants_with_email = [p for p in participants if p.email]
    participants_without_email = [p for p in participants if not p.email]

    return render_template('admin_email_participants.html',
                           participants=participants,
                           participants_with_email=participants_with_email,
                           participants_without_email=participants_without_email)


@app.route('/admin/backup')
@admin_required
def admin_backup():
    """Admin page to download database backup"""
    return render_template('admin_backup.html', current_datetime=get_current_datetime())


@app.route('/admin/backup/download')
@admin_required
def admin_backup_download():
    """Download database backup"""
    try:
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        # Handle SQLite databases
        if db_uri.startswith('sqlite:///'):
            # Get the database file path
            db_path = db_uri.replace('sqlite:///', '')
            if not os.path.isabs(db_path):
                # Relative path - resolve it
                db_path = os.path.join(os.getcwd(), db_path)

            if not os.path.exists(db_path):
                flash('Database file not found', 'error')
                return redirect(url_for('admin_backup'))

            # Create SQL dump using sqlite3 command
            try:
                result = subprocess.run(
                    ['sqlite3', db_path, '.dump'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    raise Exception(f"sqlite3 dump failed: {result.stderr}")

                sql_dump = result.stdout
                filename = f'bowl_pool_backup_{timestamp}.sql'

                return Response(
                    sql_dump,
                    mimetype='application/sql',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
            except FileNotFoundError:
                # sqlite3 command not found, fall back to copying the raw database file
                filename = f'bowl_pool_backup_{timestamp}.db'
                return send_file(
                    db_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/x-sqlite3'
                )

        # Handle PostgreSQL databases
        elif db_uri.startswith('postgresql://'):
            # Create temporary file for dump
            temp_dir = tempfile.mkdtemp()
            try:
                dump_file = os.path.join(temp_dir, f'bowl_pool_backup_{timestamp}.sql')

                # Use pg_dump command
                result = subprocess.run(
                    ['pg_dump', db_uri, '-f', dump_file],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    raise Exception(f"pg_dump failed: {result.stderr}")

                if not os.path.exists(dump_file):
                    raise Exception("Dump file was not created")

                # Read the dump file and return it
                with open(dump_file, 'r') as f:
                    sql_dump = f.read()

                filename = f'bowl_pool_backup_{timestamp}.sql'

                return Response(
                    sql_dump,
                    mimetype='application/sql',
                    headers={'Content-Disposition': f'attachment; filename={filename}'}
                )
            finally:
                # Clean up temporary directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        else:
            flash('Unsupported database type for backup', 'error')
            return redirect(url_for('admin_backup'))

    except subprocess.TimeoutExpired:
        flash('Database backup timed out', 'error')
        return redirect(url_for('admin_backup'))
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('admin_backup'))


if __name__ == '__main__':
    app.run(debug=True)
