from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets

db = SQLAlchemy()


class Settings(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    override_datetime = db.Column(db.DateTime, nullable=True)  # For testing: override current time

    def __repr__(self):
        return f'<Settings override={self.override_datetime}>'

    @staticmethod
    def get_instance():
        """Get or create the single settings instance"""
        settings = Settings.query.first()
        if not settings:
            settings = Settings()
            db.session.add(settings)
            db.session.commit()
        return settings


class Bowl(db.Model):
    __tablename__ = 'bowls'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    datetime_utc = db.Column(db.DateTime, nullable=False)
    favored_team = db.Column(db.String(100), nullable=False)
    opponent = db.Column(db.String(100), nullable=False)
    spread = db.Column(db.Float, nullable=False)  # Favored team point adjustment (e.g., -3.5)
    favored_team_score = db.Column(db.Integer, nullable=True)
    opponent_score = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='not_started')  # not_started, in_progress, final, canceled
    is_ignored = db.Column(db.Boolean, default=False, nullable=False)
    tv_channel = db.Column(db.String(50), nullable=True)  # TV channel (e.g., "ESPN", "ABC", "FOX")

    # Relationships
    picks = db.relationship('Pick', back_populates='bowl', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Bowl {self.name}>'

    def get_winner(self):
        """Determine the winner against the spread. Returns 'favored', 'opponent', or 'push'"""
        if self.status == 'canceled' or self.is_ignored:
            return 'push'
        if self.favored_team_score is None or self.opponent_score is None:
            return None
        # Only return a winner if the game is final
        if self.status != 'final':
            return None

        # Apply spread to favored team score
        favored_adjusted = self.favored_team_score + self.spread

        if favored_adjusted > self.opponent_score:
            return 'favored'
        elif favored_adjusted < self.opponent_score:
            return 'opponent'
        else:
            return 'push'


class Participant(db.Model):
    __tablename__ = 'participants'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    nickname = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    invite_token = db.Column(db.String(64), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    picks = db.relationship('Pick', back_populates='participant', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Participant {self.name}>'

    @staticmethod
    def generate_token():
        """Generate a unique invite token"""
        return secrets.token_urlsafe(32)

    def get_display_name(self):
        """Get the display name (nickname if available, otherwise name)"""
        return self.nickname if self.nickname else self.name


class Pick(db.Model):
    __tablename__ = 'picks'

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False)
    bowl_id = db.Column(db.Integer, db.ForeignKey('bowls.id'), nullable=False)
    picked_team = db.Column(db.String(20), nullable=False)  # 'favored' or 'opponent'

    # Relationships
    participant = db.relationship('Participant', back_populates='picks')
    bowl = db.relationship('Bowl', back_populates='picks')

    # Unique constraint: one pick per participant per bowl
    __table_args__ = (db.UniqueConstraint('participant_id', 'bowl_id', name='_participant_bowl_uc'),)

    def __repr__(self):
        return f'<Pick {self.participant.name} - {self.bowl.name}: {self.picked_team}>'

    def is_winner(self):
        """Check if this pick won against the spread"""
        winner = self.bowl.get_winner()
        if winner == 'push' or winner is None:
            return None  # Push or game not completed
        return self.picked_team == winner
