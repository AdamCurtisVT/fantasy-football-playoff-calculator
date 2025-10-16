#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests
import timeit
from itertools import product
from tabulate import tabulate
from dataclasses import dataclass
from typing import Optional, List

#-------------------------------------------------
# Classes
#-------------------------------------------------

@dataclass
class League:
    """
    Represents a Fantasy Football league.
    """
    id: str
    current_week: int = 0
    last_week_of_regular_season: int = 0
    playoff_week_start: int = 0
    number_of_teams: int = 0
    number_of_playoff_teams: int = 0

@dataclass
class Matchup:
    """
    Represents a matchup between two teams in a Fantasy Football league.
    """
    matchup_period: int
    matchup_id: int
    roster_id: int
    opponent_roster_id: Optional[int] = None

@dataclass
class Team:
    """
    Represents a Fantasy Football team.
    """
    roster_id: int
    owner_id: str
    wins: int
    losses: int
    fantasy_points_for: float
    fantasy_points_against: float
    name: Optional[str] = None
    playoff_scenarios: int = 0
    guaranteed_playoff_scenarios: int = 0
    playoff_percentage: float = 0.0
    guaranteed_playoff_percentage: float = 0.0

#-------------------------------------------------
# Functions
#-------------------------------------------------

def ImportLeagueSettings(league_id: str) -> League:
    """
    Import the league settings from the Sleeper API.
    """
    sleeper_league = GetLeague(league_id)
    
    league = League(
        id=league_id,
        current_week=sleeper_league["settings"]["leg"],
        playoff_week_start=sleeper_league["settings"]["playoff_week_start"],
        last_week_of_regular_season=sleeper_league["settings"]["playoff_week_start"]-1,
        number_of_playoff_teams=sleeper_league["settings"]["playoff_teams"],
        number_of_teams=sleeper_league["total_rosters"]
    )
    return league


def ImportMatchups(league_id: str, starting_week: int, league_playoff_week_start: int) -> List[Matchup]:
    """
    Import all of the remaining league matchups from the Sleeper API.
    Sleeper does not give the opponents' roster id, so look through the list to see if the matchup id already exists.
    """
    matchups = []
    for week in range(starting_week, league_playoff_week_start+1):
        for league_matchup in GetLeagueMatchups(league_id, week):
            index = next((i for i, matchup in enumerate(matchups) 
                         if matchup.matchup_id == league_matchup["matchup_id"] and matchup.matchup_period == week), -1)
            if index > -1:
                matchups[index].opponent_roster_id = league_matchup["roster_id"]
            else:
                matchups.append(Matchup(
                    matchup_period=week,
                    matchup_id=league_matchup["matchup_id"],
                    roster_id=league_matchup["roster_id"],
                    opponent_roster_id=None
                ))
    return matchups

def ImportTeamList(league_id: str) -> List[Team]:
    """
    Import all of the league teams from the Sleeper API.
    Also import the name of the Owner.
    """
    teams = []
    league_rosters = GetLeagueRosters(league_id)
    league_users = GetLeagueUsers(league_id)

    for league_roster in league_rosters:
        team = Team(
            roster_id=league_roster["roster_id"],
            owner_id=league_roster["owner_id"],
            wins=league_roster["settings"]["wins"],
            losses=league_roster["settings"]["losses"],
            fantasy_points_for=league_roster["settings"]["fpts"],
            fantasy_points_against=league_roster["settings"]["fpts_against"]
        )
        teams.append(team)

    for league_user in league_users:
        index = next((i for i, team in enumerate(teams) if league_user["user_id"] == team.owner_id), -1)
        teams[index].name = league_user["display_name"]

    return teams

def ProcessWeeklyMatchups(matchupPeriod: int) -> None:
    """
    Process all possible outcomes for the given matchup period.
    """
    weeklyMatchups = [t for t in matchups if t.matchup_period == matchupPeriod]
    mp = matchupPeriod - 1
    
    # Pre-compute roster indices to avoid repeated lookups
    roster_indices = [(match.roster_id - 1, match.opponent_roster_id - 1) for match in weeklyMatchups]

    for combination in product([0, 1], repeat=len(weeklyMatchups)):
        # Process all matches at once with fewer operations
        for idx, (team_idx, opp_idx) in enumerate(roster_indices):
            win = combination[idx]
            team_matrix[team_idx][mp] = win
            team_matrix[opp_idx][mp] = 1 - win

        if matchupPeriod == league.last_week_of_regular_season:
            DeterminePlayoffChances()
        else:
            ProcessWeeklyMatchups(matchupPeriod + 1)


def DeterminePlayoffChances() -> None:
    """
    Calculate playoff chances with optimized sorting approach.
    """
    # Calculate total wins for each team - keep track of team index
    team_wins = [(team_idx, team.wins + sum(team_matrix[team_idx][league.current_week-1:])) 
                 for team_idx, team in enumerate(teams)]
    
    # Sort by wins in descending order
    team_wins.sort(key=lambda x: x[1], reverse=True)
    
    # Find cutoff (without sorting twice)
    playoff_spots = league.number_of_playoff_teams
    if playoff_spots <= len(team_wins):
        cutoff_wins = team_wins[playoff_spots-1][1]
        
        # Update scenarios in a single pass
        for team_idx, wins in team_wins:
            if wins >= cutoff_wins:
                teams[team_idx].playoff_scenarios += 1
            if wins > cutoff_wins:
                teams[team_idx].guaranteed_playoff_scenarios += 1

#-------------------------------------------------
# Functions - Sleeper API
#-------------------------------------------------

def GetLeague(league_id: str) -> Optional[dict]:
    """
    Call the Sleeper API to retrieve all league for a specific user in a season.
    """
    endpoint = f'https://api.sleeper.app/v1/league/{league_id}'
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        return response.json()
    else:
        return None

def GetLeagueMatchups(league_id: str, week: int) -> Optional[List[dict]]:
    """
    Call the Sleeper API to retrieve all matchups in a league for the specified week.
    """
    endpoint = f'https://api.sleeper.app/v1/league/{league_id}/matchups/{week}'
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        matchups = list()
        for matchup in response.json():
            matchups.append(matchup)
        return matchups
    else:
        return None

def GetLeagueRosters(league_id: str) -> Optional[List[dict]]:
    """
    Call the Sleeper API to retrieve all rosters in a specific league.
    """
    endpoint = f'https://api.sleeper.app/v1/league/{league_id}/rosters'
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        rosters = list()
        for roster in response.json():
            rosters.append(roster)
        return rosters
    else:
        return None

def GetLeagueUsers(league_id: str) -> Optional[List[dict]]:
    """
    Call the Sleeper API to retrieve all users in a specific league.
    """
    endpoint = f'https://api.sleeper.app/v1/league/{league_id}/users'
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        users = list()
        for user in response.json():
            users.append(user)
        return users
    else:
        return None

#-------------------------------------------------
# Main
#-------------------------------------------------

# Retrieve the league ID.
league_id = input("Enter your league ID: ")
if league_id == "":
    league_id = '981569071558832128'

# Retrieve the league settings.
league = ImportLeagueSettings(league_id)

# Create the list of teams.
teams = ImportTeamList(league.id)

# Prepare the team matrix.
team_matrix = [[0 for x in range(league.last_week_of_regular_season)] for y in range(league.number_of_teams)] 
for team in teams:
    for i in range (0, team.wins, 1):
        team_matrix[team.roster_id-1][i] = 1

# Do not continue if the playoffs have already started.
if (league.current_week < league.playoff_week_start):
    # Create the list of matchups.
    matchups = ImportMatchups(league.id, league.current_week, league.last_week_of_regular_season)

    # Do not continue if there are no matchups.
    if len(matchups) > 0:
        # Calculate how long it should take to run.
        scenarios = math.pow(math.pow(2, league.number_of_teams/2),((league.last_week_of_regular_season)-(league.current_week-1))) # 2^(num_teams/2).
        time_per_scenario = 0.00000213671875
        print(f"There are {scenarios:.0f} scenarios starting in week {league.current_week}. This will take approx {scenarios*time_per_scenario} seconds (or {(scenarios*time_per_scenario)/60} minutes).")

        # Process all the matchups.
        #ProcessWeeklyMatchups(league.CurrentWeek)
        elapsed_time = timeit.timeit(lambda: ProcessWeeklyMatchups(league.current_week), number=1)
        print(f"Elapsed time: {elapsed_time:.6f} seconds")    

        # Process the percentage of scenarios where the team made the playoffs.
        for team in teams:
            team.playoff_percentage = round((team.playoff_scenarios/scenarios), 3)
            team.guaranteed_playoff_percentage = round((team.guaranteed_playoff_scenarios/scenarios), 3)

        # Create a list of lists containing the relevant properties
        team_data = [
            [team.name, f"{team.wins}-{team.losses}", team.fantasy_points_for, team.fantasy_points_against, team.guaranteed_playoff_percentage, team.playoff_percentage]
            for team in sorted(teams, key=lambda x: (x.wins, x.playoff_percentage), reverse=True)
        ]

        # Define the headers and print the table.
        headers = ["Name", "Record", "FPF", "FPA", "Guaranteed Spot", "Tied For Cutoff Or Better"]
        print(tabulate(team_data, headers, tablefmt="presto", floatfmt=".2%"))
