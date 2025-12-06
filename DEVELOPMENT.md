# Development Guide

## Setup

### Prerequisites
- Python 3.13+
- PostgreSQL (for production) or SQLite (for local development)

### Local Development Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd bowl_pool
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your settings (use SQLite for local dev)
```

5. Initialize the database:
```bash
python init_db.py
```

6. (Optional) Seed with sample data:
```bash
python seed_data.py
```

7. Run the application:
```bash
python app.py
```

The application will be available at http://localhost:5000

## Database

### SQLite (Development)
The default configuration uses SQLite, which requires no setup. The database file `bowl_pool.db` will be created automatically.

### PostgreSQL (Production)
Set the `DATABASE_URL` environment variable:
```
DATABASE_URL=postgresql://username:password@localhost/bowl_pool
```

## Usage

### Admin Access
After seeding the database, use the admin user's invite token to log in. The token will be printed in the console when running `seed_data.py`.

### Adding Participants
1. Log in as an admin
2. Navigate to "Admin: Manage Participants"
3. Add participants and copy their unique invite tokens
4. Share the tokens with participants for login

### Adding Bowl Games
1. Log in as an admin
2. Navigate to "Admin: Manage Bowls"
3. Add bowl games with teams, spreads, and dates

### Entering Scores
1. Log in as an admin
2. Navigate to "Admin: Enter Scores"
3. Update scores and game status as games complete

## Deployment to Render

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Render will automatically detect the `render.yaml` configuration
4. The database and web service will be provisioned automatically
5. Run the database initialization:
   - In the Render shell: `python init_db.py`
   - Then seed data: `python seed_data.py`

## Features

- **Authentication**: Token-based login (no passwords needed)
- **Pick Entry**: Participants select winners against the spread
- **Pick Locking**: Picks lock when the first game starts
- **Scoreboard**: Dynamic table showing all picks and scores
- **Scoring**: Winners get +1 per loser, losers get -1 per winner
- **Admin Controls**: Manage bowls, participants, and scores

## File Structure

```
bowl_pool/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── config.py              # Configuration
├── init_db.py             # Database initialization
├── seed_data.py           # Sample data seeding
├── requirements.txt       # Python dependencies
├── render.yaml            # Render deployment config
├── templates/             # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── picks.html
│   ├── scoreboard.html
│   ├── admin_scores.html
│   ├── admin_bowls.html
│   └── admin_participants.html
└── .env                   # Environment variables (not in git)
```
