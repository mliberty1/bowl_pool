
# Motivation

My family has an NCAA men's football bowl game pool every year.
In 2024, we had 9 participants.
Each person chooses their winner against the spread.
Winners for each game get one point from each loser.
Likewise, each loser gives one point to each winner.

In previous years, we managed the game using a Excel spreadsheet.
The spreadsheet is quite fragile and complicated
using pivot tables for the winnings chart.

This project upgrades the pool management from an Excel spreadsheet
to a more modern web based application.


# Features

1. Bowl database - A structured data store with at least:
   * Bowl name (e.g. "Rose Bowl")
   * Date/time in UTC - can require entry in sorted order
   * Teams: favored_team, opponent
   * Spread: favored_team point adjustment, like -3.5
   * Final score
   * Winner
   * Game status: not_started, in_progress, final, canceled.
   * is_ignored flag

2. Participants
   * Name
   * Nickname
   * Email
   * Unique invite link, which can be the login
   * Full accounts are overkill and likely not needed.
   * is_admin flag to enable admin access for that participant

3. Entry form (per participant)
   * Lists every bowl game with teams and spread.
   * Lets the participant pick one team that covers the spread per game.
     Click on the team to select the winner.
   * Tied to a single participant identity.
   * Picks lock at kickoff of the first bowl game.  We can separately
     enter the UTC time that it locks to make things simple.
   * Participants can continue to edit their picks up until launch
   * Must pick a winner for each game.
     Submission validation should enforce this.

4. Display / scoreboard
   * A dynamic table that you can view in different modes:
   * Rows: one per game (plus header row column(s) showing bowl name, teams, spread, score when final
   * Columns: one per participant.
   * Cell content, per participant per game:
     * Their pick.
       * Before the game is played,
         color RED if only one who has pick,
         colr YELLOW if only two participants have pick.
       * Once game finalizes, green for winners and red for losers
     * Game win/loss amount for that game
     * Toggle option to display running total win/loss rather than per-game win-loss
   * Final total row sowing total win/loss per participant
   * Participants picks should not be visible until picks lock

5. Bowl score entry
   * A page that shows each bowl game and allows score entry or override
   * Alternatively, some automatic way to pull bowl scores
   * Accesible only to admins.

6. Scoring
   * For each bowl game, each winner gets +1 point for each loser.
     Each loser gets -1 point for each winner.
   * On ties, every participant gets 0 (push)
   * Canceled games and is_ignored games are also a push

7. Security
   * At a minimum, tokens in URL to prevent unauthorized access.
   * Unique logins are probably overkill
   * We can generate unique tokens for each participant and email separately.

8. Future
   * The database only needs to be valid for the current year.
   * We can copy the display HTML page and host that HTML for historical purposes.


## Ease of use

This application is split into several different parts:

1. Participant team selection
2. Scoreboard
3. Administration

The ease of use of participant team selection is critical. Participants
are the general population with no requirements on computer proficiency.

The scoreboard should be simple and easily understood.  However, it
has limited interactivity which greatly simplifies ease of use.

The administration sections can demand a high level of technical
proficiency.  While we would prefer to include web-based management,
direct SQL database management for unusual cases is not a show stopper.





# Implementation and Deployment

This application will be implemented in Flask + Python with a Postgres database.
Code will live on GitHub.
It will be deployed using Render automatically.
