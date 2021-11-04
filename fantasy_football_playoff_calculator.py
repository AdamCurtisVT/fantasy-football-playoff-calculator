#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests
import time

#-------------------------------------------------
# Classes
#-------------------------------------------------

# Represents a Fantasy Football team.
class Team(object):
    Name = None
    RosterId = 0
    OwnerId = 0

    # Initializes a new instance of the class.
    def __init__(self, name, rosterId, owner_id):
        self.Name = name
        self.RosterId = rosterId
        self.OwnerId = owner_id

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

#-------------------------------------------------
# Functions
#-------------------------------------------------

# Processes the weekly matchups.
def ProcessWeeklyMatchups(matchupPeriod):
    weeklyMatchups = list(t for t in matchups if t.MatchupPeriod == matchupPeriod)
    mp = matchupPeriod-1
    for i in range(0, 2, 1):
        team_matrix[weeklyMatchups[0].RosterId-1][mp] = 1 if not i else 0
        team_matrix[weeklyMatchups[0].OpponentRosterId-1][mp] = 0 if not i else 1

        for j in range(0, 2, 1):
            team_matrix[weeklyMatchups[1].RosterId-1][mp] = 1 if not j else 0
            team_matrix[weeklyMatchups[1].OpponentRosterId-1][mp] = 0 if not j else 1

            for k in range(0, 2, 1):
                team_matrix[weeklyMatchups[2].RosterId-1][mp] = 1 if not k else 0
                team_matrix[weeklyMatchups[2].OpponentRosterId-1][mp] = 0 if not k else 1

                for l in range(0, 2, 1):
                    team_matrix[weeklyMatchups[3].RosterId-1][mp] = 1 if not l else 0
                    team_matrix[weeklyMatchups[3].OpponentRosterId-1][mp] = 0 if not l else 1
                
                    for m in range(0, 2, 1):
                        team_matrix[weeklyMatchups[4].RosterId-1][mp] = 1 if not m else 0
                        team_matrix[weeklyMatchups[4].OpponentRosterId-1][mp] = 0 if not m else 1

                        if (matchupPeriod == league_last_week_of_season):
                            DeterminePlayoffChances()                                
                        else:
                            ProcessWeeklyMatchups(matchupPeriod+1)

# Determine the playoff chances in the current scenario.
def DeterminePlayoffChances():
    result = list(map(sum, team_matrix)) # Sum of wins
    minimumWins = sorted(result, key=lambda x: x, reverse=True)[int((league_total_rosters/2)-1)]

    for i in range(0, league_total_rosters, 1):
        if (result[i] >= minimumWins):
            playoff_matrix[i] += 1

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

# Define constants
league_id = '650414955312558080'
starting_week = 12
team_matrix = [[0 for x in range(13)] for y in range(10)] 
playoff_matrix = [0 for x in range(10)] 

league = GetLeague(league_id)
league_playoff_week_start = league["settings"]["playoff_week_start"]
league_last_week_of_season = league["settings"]["playoff_week_start"]-1
league_playoff_teams = league["settings"]["playoff_teams"]
league_total_rosters = int(league["total_rosters"])

# Iterate through the remaining weeks and create the matchups.
# Sleeper does not give the opponents' roster id, so look through the list to see if the matchup id already exists.
matchups = []
for week in range(starting_week, league_playoff_week_start):
    for league_matchup in GetLeagueMatchups(league_id, week):
        index = next((i for i, matchup in enumerate(matchups) if matchup.MatchupId == league_matchup["matchup_id"] and matchup.MatchupPeriod == week), -1)
        if index > -1:
            matchups[index].OpponentRosterId = league_matchup["roster_id"]
        else:
            matchups.append(Matchup(week, league_matchup["matchup_id"], league_matchup["roster_id"], None))


# Create the list of teams.
teams = []
for league_roster in GetLeagueRosters(league_id):
    team = Team("", league_roster["roster_id"], league_roster["owner_id"])
    for wins in range (0, league_roster["settings"]["wins"]):
        team_matrix[league_roster["roster_id"]-1][wins] = 1
    teams.append(team)

# Retrieve the names for all the teams.
users = GetLeagueUsers(league_id)
for user in users:
    index = next((i for i, team in enumerate(teams) if user["user_id"] == team.OwnerId), -1)
    teams[index].Name = user["display_name"]

# Print the amount of time it should take to run the app.
scenarios = math.pow(math.pow(2, league_total_rosters/2),((league_playoff_week_start-1)-(starting_week-1))) # 2^(num_teams/2).
time_per_scenario = 0.00001739501021802425537109375
print("There are {} scenarios starting in week {}. This will take approx {} seconds (or {} minutes).".format(scenarios, starting_week, scenarios*time_per_scenario, (scenarios*time_per_scenario)/60))

start = time.time()
# Process all the matchups.
ProcessWeeklyMatchups(starting_week)
end = time.time()
print(end-start)

# Print the ordered results.
for i in range (0, 10, 1):
    potential_playoff_spot_scenarios = round((playoff_matrix[i]/scenarios)*100, 2)
    index = next((i for i, team in enumerate(teams) if user["user_id"] == team.OwnerId), -1)
    print("{} - {}%".format(teams[index].Name, potential_playoff_spot_scenarios))