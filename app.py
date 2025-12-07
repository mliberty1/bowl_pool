from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, Bowl, Participant, Pick
from config import Config
from functools import wraps
from datetime import datetime
import random


app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


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
        return datetime.utcnow() >= first_bowl.datetime_utc
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
            return redirect(url_for('picks'))
        else:
            flash('Invalid invite token', 'error')

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        participant = Participant.query.filter_by(invite_token=token).first()

        if participant:
            session['participant_id'] = participant.id
            flash(f'Welcome, {participant.get_display_name()}!', 'success')
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
        # Update participant info
        participant.name = request.form.get('name')
        participant.nickname = request.form.get('nickname')
        participant.email = request.form.get('email')

        db.session.commit()
        flash('Your profile has been updated!', 'success')
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

        if action == 'add':
            # Add new bowl
            bowl = Bowl(
                name=request.form.get('name'),
                datetime_utc=datetime.fromisoformat(request.form.get('datetime_utc')),
                favored_team=request.form.get('favored_team'),
                opponent=request.form.get('opponent'),
                spread=float(request.form.get('spread'))
            )
            db.session.add(bowl)
            db.session.commit()
            flash(f'Added {bowl.name}', 'success')

        elif action == 'edit':
            bowl_id = request.form.get('bowl_id')
            bowl = Bowl.query.get(bowl_id)
            if bowl:
                bowl.name = request.form.get('name')
                bowl.datetime_utc = datetime.fromisoformat(request.form.get('datetime_utc'))
                bowl.favored_team = request.form.get('favored_team')
                bowl.opponent = request.form.get('opponent')
                bowl.spread = float(request.form.get('spread'))
                db.session.commit()
                flash(f'Updated {bowl.name}', 'success')

        elif action == 'delete':
            bowl_id = request.form.get('bowl_id')
            bowl = Bowl.query.get(bowl_id)
            if bowl:
                db.session.delete(bowl)
                db.session.commit()
                flash(f'Deleted {bowl.name}', 'success')

        return redirect(url_for('admin_bowls'))

    bowls = Bowl.query.order_by(Bowl.datetime_utc).all()
    edit_bowl_id = request.args.get('edit', type=int)
    editing_bowl = None
    if edit_bowl_id:
        editing_bowl = Bowl.query.get(edit_bowl_id)

    return render_template('admin_bowls.html', bowls=bowls, editing_bowl=editing_bowl)


@app.route('/admin/participants', methods=['GET', 'POST'])
@admin_required
def admin_participants():
    """Admin page to manage participants"""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            # Add new participant
            participant = Participant(
                name=request.form.get('name'),
                nickname=request.form.get('nickname'),
                email=request.form.get('email'),
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
                participant.name = request.form.get('name')
                participant.nickname = request.form.get('nickname')
                participant.email = request.form.get('email')
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

        return redirect(url_for('admin_participants'))

    participants = Participant.query.all()
    edit_participant_id = request.args.get('edit', type=int)
    editing_participant = None
    if edit_participant_id:
        editing_participant = Participant.query.get(edit_participant_id)

    return render_template('admin_participants.html', participants=participants, editing_participant=editing_participant)


if __name__ == '__main__':
    app.run(debug=True)
