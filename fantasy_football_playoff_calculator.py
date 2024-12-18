#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests
import timeit
from itertools import product
from tabulate import tabulate

#-------------------------------------------------
# Classes
#-------------------------------------------------

# Represents a Fantasy Football league.
class League(object):
    Id = 0
    CurrentWeek = 0
    LastWeekOfRegularSeason = 0
    PlayoffWeekStart = 0
    NumberOfTeams = 0
    NumberOfPlayoffTeams = 0

    # Initializes a new instance of the class.
    def __init__(self, id):
        self.Id = id
        self.CurrentWeek = 0
        self.LastWeekOfRegularSeason = 0
        self.PlayoffWeekStart = 0
        self.NumberOfTeams = 0
        self.NumberOfPlayoffTeams = 0

# Represents a Fantasy Football matchup.
class Matchup(object):
    MatchupPeriod = 0
    MatchupId = 0
    RosterId = None
    OpponentRosterId = None

    # Initializes a new instance of the class.
    def __init__(self, matchupPeriod, matchupId, rosterId, opponentRosterId):
        self.MatchupPeriod = matchupPeriod
        self.MatchupId = matchupId
        self.RosterId = rosterId
        self.OpponentRosterId = opponentRosterId

# Represents a Fantasy Football team.
class Team(object):
    Name = None
    RosterId = 0
    OwnerId = 0
    Wins = 0
    Losses = 0
    PlayoffScenarios = 0
    GuaranteedPlayoffScenarios = 0

    # Initializes a new instance of the class.
    def __init__(self, rosterId, owner_id, wins, losses, fantasy_points_for, fantasy_points_against):
        self.Name = None
        self.RosterId = rosterId
        self.OwnerId = owner_id
        self.Wins = wins
        self.Losses = losses
        self.PlayoffScenarios = 0
        self.GuaranteedPlayoffScenarios = 0
        self.FantasyPointsFor = fantasy_points_for
        self.FantasyPointsAgainst = fantasy_points_against

#-------------------------------------------------
# Functions
#-------------------------------------------------

# Import the league settings from the Sleeper API.
def ImportLeagueSettings(league_id):
    league = League(league_id)
    sleeper_league = GetLeague(league_id)
    league.CurrentWeek = sleeper_league["settings"]["leg"]
    league.PlayoffWeekStart = sleeper_league["settings"]["playoff_week_start"]
    league.LastWeekOfRegularSeason = sleeper_league["settings"]["playoff_week_start"]-1
    league.NumberOfPlayoffTeams = sleeper_league["settings"]["playoff_teams"]
    league.NumberOfTeams = sleeper_league["total_rosters"]
    return league

# Import all of the remaining league matchups from the Sleeper API.
# Sleeper does not give the opponents' roster id, so look through the list to see if the matchup id already exists.
def ImportMatchups(league_id, starting_week, league_playoff_week_start):
    matchups = []
    for week in range(starting_week, league_playoff_week_start+1):
        for league_matchup in GetLeagueMatchups(league_id, week):
            index = next((i for i, matchup in enumerate(matchups) if matchup.MatchupId == league_matchup["matchup_id"] and matchup.MatchupPeriod == week), -1)
            if index > -1:
                matchups[index].OpponentRosterId = league_matchup["roster_id"]
            else:
                matchups.append(Matchup(week, league_matchup["matchup_id"], league_matchup["roster_id"], None))
    return matchups

# Import all of the league teams from the Sleeper API.
# Also import the name of the Owner.
def ImportTeamList(league_id):
    teams = []
    league_rosters = GetLeagueRosters(league_id)
    league_users = GetLeagueUsers(league_id)

    for league_roster in league_rosters:
        team = Team(league_roster["roster_id"], league_roster["owner_id"], league_roster["settings"]["wins"], league_roster["settings"]["losses"], league_roster["settings"]["fpts"], league_roster["settings"]["fpts_against"])
        teams.append(team)

    for league_user in league_users:
        index = next((i for i, team in enumerate(teams) if league_user["user_id"] == team.OwnerId), -1)
        teams[index].Name = league_user["display_name"]

    return teams

# Processes the weekly matchups.
def ProcessWeeklyMatchups(matchupPeriod):
    weeklyMatchups = [t for t in matchups if t.MatchupPeriod == matchupPeriod]
    mp = matchupPeriod - 1
    
    for combination in product([0, 1], repeat=len(weeklyMatchups)):
        for idx, match in enumerate(weeklyMatchups):
            team_matrix[match.RosterId - 1][mp] = combination[idx]
            team_matrix[match.OpponentRosterId - 1][mp] = 1 - combination[idx]

        if matchupPeriod == league.LastWeekOfRegularSeason:
            DeterminePlayoffChances()
        else:
            ProcessWeeklyMatchups(matchupPeriod + 1)


def DeterminePlayoffChances():
    """
    Calculate playoff chances for each team based on current standings.
    Updates the PlayoffScenarios and GuaranteedPlayoffScenarios counters for each team.
    
    Uses team_matrix to determine total wins and calculates playoff chances based on league.NumberOfPlayoffTeams teams making the playoffs.
    """
    # Calculate total wins for each team
    total_wins = [sum(row) for row in team_matrix]
    
    # Calculate playoff cutoff line (minimum wins needed)
    playoff_spots = league.NumberOfTeams // 2
    sorted_wins = sorted(total_wins, reverse=True)
    playoff_cutoff = sorted_wins[playoff_spots - 1]

    for team_idx, wins in enumerate(total_wins):
        if wins >= playoff_cutoff:
            teams[team_idx].PlayoffScenarios += 1
        if wins > playoff_cutoff:
            teams[team_idx].GuaranteedPlayoffScenarios += 1

#-------------------------------------------------
# Functions - Sleeper API
#-------------------------------------------------

# Call the Sleeper API to retrieve all league for a specific user in a season.
def GetLeague(league_id):
    endpoint = ('https://api.sleeper.app/v1/league/{}'.format(league_id))
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        return response.json()
    else:
        return None

# Call the Sleeper API to retrieve all matchups in a league for the specified week.
def GetLeagueMatchups(league_id, week):
    endpoint = ('https://api.sleeper.app/v1/league/{}/matchups/{}'.format(league_id, week))
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        matchups = list()
        for matchup in response.json():
            matchups.append(matchup)
        return matchups
    else:
        return None

def GetLeagueRosters(league_id):
    endpoint = ('https://api.sleeper.app/v1/league/{}/rosters'.format(league_id))
    response = requests.get(endpoint)
    
    if response.status_code == 200:
        rosters = list()
        for roster in response.json():
            rosters.append(roster)
        return rosters
    else:
        return None

# Call the Sleeper API to retrieve all users in a specific league['
def GetLeagueUsers(league_id):
    endpoint = ('https://api.sleeper.app/v1/league/{}/users'.format(league_id))
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
teams = ImportTeamList(league.Id)

# Prepare the team matrix.
team_matrix = [[0 for x in range(league.LastWeekOfRegularSeason)] for y in range(league.NumberOfTeams)] 
for team in teams:
    for i in range (0, team.Wins, 1):
        team_matrix[team.RosterId-1][i] = 1
    
# Do not continue if the playoffs have already started.
if (league.CurrentWeek < league.PlayoffWeekStart):
    # Create the list of matchups.
    matchups = ImportMatchups(league.Id, league.CurrentWeek, league.LastWeekOfRegularSeason)

    # Do not continue if there are no matchups.
    if len(matchups) > 0:
        # Calculate how long it should take to run.
        scenarios = math.pow(math.pow(2, league.NumberOfTeams/2),((league.LastWeekOfRegularSeason)-(league.CurrentWeek-1))) # 2^(num_teams/2).
        time_per_scenario = 0.00001507349
        print("There are {:.0f} scenarios starting in week {}. This will take approx {} seconds (or {} minutes).".format(scenarios, league.CurrentWeek, scenarios*time_per_scenario, (scenarios*time_per_scenario)/60))

        # Process all the matchups.
        ProcessWeeklyMatchups(league.CurrentWeek)
        #elapsed_time = timeit.timeit(lambda: ProcessWeeklyMatchups(league.CurrentWeek), number=1)
        #print(f"Elapsed time: {elapsed_time:.6f} seconds")    

        # Process the percentage of scenarios where the team made the playoffs.
        for team in teams:
            team.PlayoffPercentage = round((team.PlayoffScenarios/scenarios), 3)
            team.GuaranteedPlayoffPercentage = round((team.GuaranteedPlayoffScenarios/scenarios), 3)

        # Create a list of lists containing the relevant properties
        team_data = [
            [team.Name, "{}-{}".format(team.Wins, team.Losses), team.FantasyPointsFor, team.FantasyPointsAgainst, team.GuaranteedPlayoffPercentage, team.PlayoffPercentage]
            for team in sorted(teams, key=lambda x: (x.Wins, x.PlayoffPercentage), reverse=True)
        ]

        # Define the headers and print the table.
        headers = ["Name", "Record", "FPF", "FPA", "Guaranteed Spot", "Tied For Cutoff Or Better"]
        print(tabulate(team_data, headers, tablefmt="presto", floatfmt=".2%"))
