"""
Seed the database with sample data for testing.
"""
from datetime import datetime, timedelta
from app import app
from models import db, Bowl, Participant
import os


def seed_database():
    """Seed the database with sample bowl games and participants"""
    with app.app_context():
        # Clear existing data (optional)
        print("Clearing existing data...")
        Bowl.query.delete()
        Participant.query.delete()
        db.session.commit()

        # Add sample participants
        print("Adding participants...")
        admin = Participant(
            name="Admin User",
            nickname="Admin",
            email="admin@example.com",
            invite_token=Participant.generate_token(),
            is_admin=True
        )
        db.session.add(admin)

        participants = [
            Participant(
                name="John Smith",
                nickname="John",
                email="john@example.com",
                invite_token=Participant.generate_token()
            ),
            Participant(
                name="Jane Doe",
                nickname="Jane",
                email="jane@example.com",
                invite_token=Participant.generate_token()
            ),
            Participant(
                name="Bob Johnson",
                nickname="Bob",
                email="bob@example.com",
                invite_token=Participant.generate_token()
            ),
        ]

        for participant in participants:
            db.session.add(participant)

        # Add sample bowl games
        print("Adding bowl games...")
        start_date = datetime.utcnow() + timedelta(days=7)

        bowls = [
            Bowl(
                name="Rose Bowl",
                datetime_utc=start_date,
                favored_team="Ohio State",
                opponent="Oregon",
                spread=-3.5
            ),
            Bowl(
                name="Sugar Bowl",
                datetime_utc=start_date + timedelta(hours=4),
                favored_team="Georgia",
                opponent="Texas",
                spread=-7.0
            ),
            Bowl(
                name="Orange Bowl",
                datetime_utc=start_date + timedelta(days=1),
                favored_team="Florida State",
                opponent="Alabama",
                spread=-2.5
            ),
            Bowl(
                name="Cotton Bowl",
                datetime_utc=start_date + timedelta(days=1, hours=4),
                favored_team="Notre Dame",
                opponent="Clemson",
                spread=-4.0
            ),
            Bowl(
                name="Peach Bowl",
                datetime_utc=start_date + timedelta(days=2),
                favored_team="Michigan",
                opponent="Penn State",
                spread=-6.5
            ),
        ]

        for bowl in bowls:
            db.session.add(bowl)

        db.session.commit()

        # Print participant login URLs
        # Use environment variable for base URL, default to Render deployment
        base_url = os.environ.get('BASE_URL', 'https://bowl.libertyfamily.us')

        print("\n" + "="*80)
        print("PARTICIPANT LOGIN URLs")
        print("="*80)
        all_participants = Participant.query.all()
        for p in all_participants:
            print(f"\n{p.name} ({p.nickname})")
            print(f"  Admin: {p.is_admin}")
            print(f"  Login URL: {base_url}/login?token={p.invite_token}")

        print("\n" + "="*80)
        print(f"Successfully seeded {len(all_participants)} participants and {len(bowls)} bowl games!")
        print("Copy and paste the login URLs above to automatically log in as each user.")
        print("="*80)


if __name__ == '__main__':
    seed_database()
