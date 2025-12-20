"""
Service to automatically fetch and update bowl game scores from ESPN API.
"""

import requests
from datetime import datetime, timedelta
from models import db, Bowl
import logging

logger = logging.getLogger(__name__)


class ScoreUpdater:
    """Fetches college football scores from ESPN and updates bowl games."""

    ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"

    def __init__(self, app=None):
        self.app = app

    def update_scores(self):
        """Fetch latest scores from ESPN and update all bowl games."""
        if not self.app:
            logger.error("ScoreUpdater not initialized with Flask app")
            return

        with self.app.app_context():
            try:
                # Get all bowls that aren't finished or canceled
                active_bowls = Bowl.query.filter(
                    Bowl.status.in_(['not_started', 'in_progress'])
                ).all()

                if not active_bowls:
                    logger.info("No active bowl games to update")
                    return

                # Fetch scores for the date range covering all active bowls
                espn_games = self._fetch_espn_games(active_bowls)

                if not espn_games:
                    logger.warning("No games returned from ESPN API")
                    return

                # Match and update each bowl
                updated_count = 0
                for bowl in active_bowls:
                    if self._update_bowl_from_espn(bowl, espn_games):
                        updated_count += 1

                db.session.commit()
                logger.info(f"Updated {updated_count} bowl game(s)")

            except Exception as e:
                logger.error(f"Error updating scores: {e}")
                db.session.rollback()

    def _fetch_espn_games(self, bowls):
        """Fetch games from ESPN API for the date range of active bowls."""
        if not bowls:
            return []

        # Get date range
        start_date = min(bowl.datetime_utc for bowl in bowls).date()
        end_date = max(bowl.datetime_utc for bowl in bowls).date() + timedelta(days=1)

        # ESPN API uses YYYYMMDD format
        date_param = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

        try:
            # Get all FBS games in the date range
            url = f"{self.ESPN_API_BASE}?groups=80&dates={date_param}"
            logger.info(f"Fetching ESPN data from: {url}")

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data.get('events', [])

        except requests.RequestException as e:
            logger.error(f"Failed to fetch ESPN data: {e}")
            return []

    def _update_bowl_from_espn(self, bowl, espn_games):
        """Update a single bowl game from ESPN data."""
        # Try to find matching ESPN game
        espn_game = self._find_matching_game(bowl, espn_games)

        if not espn_game:
            logger.debug(f"No ESPN match found for {bowl.name}")
            return False

        try:
            # Extract game data
            competitions = espn_game.get('competitions', [])
            if not competitions:
                return False

            competition = competitions[0]
            competitors = competition.get('competitors', [])

            if len(competitors) != 2:
                return False

            # Get status
            status = competition.get('status', {})
            status_type = status.get('type', {}).get('name', '').lower()

            # Map ESPN status to our status
            new_status = self._map_espn_status(status_type)

            # Extract scores
            team_scores = {}
            for competitor in competitors:
                team_name = competitor.get('team', {}).get('displayName', '')
                score = competitor.get('score')
                if score is not None:
                    team_scores[team_name] = int(score)

            # Match teams to favored/opponent
            favored_score = None
            opponent_score = None

            # Try to match by team names (fuzzy matching)
            for team_name, score in team_scores.items():
                if self._teams_match(team_name, bowl.favored_team):
                    favored_score = score
                elif self._teams_match(team_name, bowl.opponent):
                    opponent_score = score

            # Update bowl if we have valid data
            if favored_score is not None and opponent_score is not None:
                bowl.favored_team_score = favored_score
                bowl.opponent_score = opponent_score
                bowl.status = new_status
                logger.info(f"Updated {bowl.name}: {bowl.favored_team} {favored_score} vs {bowl.opponent} {opponent_score} ({new_status})")
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating {bowl.name}: {e}")
            return False

    def _find_matching_game(self, bowl, espn_games):
        """Find ESPN game that matches the bowl game."""
        for game in espn_games:
            competitions = game.get('competitions', [])
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get('competitors', [])

            if len(competitors) != 2:
                continue

            # Get team names
            team_names = [
                comp.get('team', {}).get('displayName', '')
                for comp in competitors
            ]

            # Check if both teams match
            favored_match = any(self._teams_match(name, bowl.favored_team) for name in team_names)
            opponent_match = any(self._teams_match(name, bowl.opponent) for name in team_names)

            if favored_match and opponent_match:
                return game

        return None

    def _teams_match(self, espn_name, bowl_name):
        """Check if ESPN team name matches bowl team name (fuzzy matching)."""
        # Normalize names for comparison
        espn_normalized = self._normalize_team_name(espn_name)
        bowl_normalized = self._normalize_team_name(bowl_name)

        # Exact match
        if espn_normalized == bowl_normalized:
            return True

        # Check if one contains the other (handles abbreviations)
        if espn_normalized in bowl_normalized or bowl_normalized in espn_normalized:
            return True

        return False

    def _normalize_team_name(self, name):
        """Normalize team name for comparison."""
        # Remove common suffixes and convert to lowercase
        normalized = name.lower()
        normalized = normalized.replace(' football', '')
        normalized = normalized.replace('university', '')
        normalized = normalized.replace('college', '')
        normalized = normalized.strip()
        return normalized

    def _map_espn_status(self, espn_status):
        """Map ESPN status to our bowl status."""
        espn_status = espn_status.lower()

        if 'final' in espn_status or 'complete' in espn_status:
            return 'final'
        elif 'progress' in espn_status or 'live' in espn_status:
            return 'in_progress'
        elif 'scheduled' in espn_status or 'pre' in espn_status:
            return 'not_started'
        elif 'cancel' in espn_status or 'postpone' in espn_status:
            return 'canceled'
        else:
            return 'not_started'
