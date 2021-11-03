#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests

#-------------------------------------------------
# Classes
#-------------------------------------------------

# Represents a Fantasy Football team.
class Team(object):
    Name = None
    RosterId = 0
    OwnerId = 0
    PlayoffBoundScenarios = 0
    PlayoffSpotClinchedScenarios = 0
    PlayoffSpotFinishes = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    Schedule = [False, False, False, False, False, False, False, False, False, False, False, False, False, False]
    Winss = 0
    Losses = 0
    Ties = 0

    # Initializes a new instance of the class.
    def __init__(self, name, rosterId, owner_id, wins, losses, ties):
        self.Name = name
        self.RosterId = rosterId
        self.OwnerId = owner_id
        self.PlayoffBoundScenarios = 0
        self.PlayoffSpotClinchedScenarios = 0
        self.PlayoffSpotFinishes = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.Schedule = [False, False, False, False, False, False, False, False, False, False, False, False, False, False]
        self.Winss = wins
        self.Losses = losses
        self.Ties = ties

    # Returns the number of wins in the season.
    @property
    def Wins(self):
        return sum(self.Schedule)

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
        teams[weeklyMatchups[0].RosterId-1].Schedule[mp] = (i == 0)
        teams[weeklyMatchups[0].OpponentRosterId-1].Schedule[mp] = (i == 1)

        for j in range(0, 2, 1):
            teams[weeklyMatchups[1].RosterId-1].Schedule[mp] = (j == 0)
            teams[weeklyMatchups[1].OpponentRosterId-1].Schedule[mp] = (j == 1)

            for k in range(0, 2, 1):
                teams[weeklyMatchups[2].RosterId-1].Schedule[mp] = (k == 0)
                teams[weeklyMatchups[2].OpponentRosterId-1].Schedule[mp] = (k == 1)

                for l in range(0, 2, 1):
                    teams[weeklyMatchups[3].RosterId-1].Schedule[mp] = (l == 0)
                    teams[weeklyMatchups[3].OpponentRosterId-1].Schedule[mp] = (l == 1)
                
                    for m in range(0, 2, 1):
                        teams[weeklyMatchups[4].RosterId-1].Schedule[mp] = (m == 0)
                        teams[weeklyMatchups[4].OpponentRosterId-1].Schedule[mp] = (m == 1)

                        if (matchupPeriod == 13):
                            DeterminePlayoffSpotFinishes()
                            DeterminePlayoffChances()                                
                        else:
                            ProcessWeeklyMatchups(matchupPeriod+1)

# Determine the playoff spot finishes in the current scenario.
def DeterminePlayoffSpotFinishes():
    sortedTeams = sorted(teams, key=lambda x: x.Wins, reverse=True)

    rank = 0
    for r in range(0, 10, 1):
        if (r != 0 and sortedTeams[r].Wins < sortedTeams[r - 1].Wins):
            rank = r
        teams[sortedTeams[r].RosterId - 1].PlayoffSpotFinishes[rank]+=1

# Determine the playoff chances in the current scenario.
def DeterminePlayoffChances():
    minimumWins = sorted(teams, key=lambda x: x.Wins, reverse=True)[league_playoff_teams-1].Wins

    for team in teams:
        if (team.Wins == minimumWins):
            team.PlayoffBoundScenarios += 1
        elif (team.Wins > minimumWins):
            team.PlayoffBoundScenarios += 1
            team.PlayoffSpotClinchedScenarios += 1 


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
starting_week = 9

league = GetLeague(league_id)
league_playoff_week_start = league["settings"]["playoff_week_start"]
league_playoff_teams = league["settings"]["playoff_teams"]
league_total_rosters = league["total_rosters"]

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
    team = Team("", league_roster["roster_id"], league_roster["owner_id"], league_roster["settings"]["wins"], league_roster["settings"]["losses"], league_roster["settings"]["ties"])
    for w in range (0, team.Winss):
        team.Schedule[w] = True
    teams.append(team)

# Retrieve the names for all the teams.
users = GetLeagueUsers(league_id)
for user in users:
    index = next((i for i, team in enumerate(teams) if user["user_id"] == team.OwnerId), -1)
    teams[index].Name = user["display_name"]

# Print the amount of time it should take to run the app.
scenarios = math.pow(math.pow(2, league_total_rosters/2),((league_playoff_week_start-1)-(starting_week-1))) # 2^(num_teams/2).
time_per_scenario = 0.00009700441
print("There are {} scenarios starting in week {}. This will take approx {} seconds (or {} minutes).".format(scenarios, starting_week, scenarios*time_per_scenario, (scenarios*time_per_scenario)/60))

# Process all the matchups.
ProcessWeeklyMatchups(starting_week)

# Print the ordered results.
for team in sorted(teams, key=lambda x: x.PlayoffSpotClinchedScenarios, reverse=True):
    team_name = team.Name.split(' ')[0]
    potential_playoff_spot_scenarios = round((team.PlayoffBoundScenarios/scenarios)*100, 2)
    clinched_playoff_spot_scenarios = round((team.PlayoffSpotClinchedScenarios/scenarios)*100, 2)
    print("{} {}% ({}%)".format(team_name, potential_playoff_spot_scenarios, clinched_playoff_spot_scenarios))

# Print the potential finishes.
print("\nName\t1\t2\t3\t4\t5\t6\t7\t8\t9\t10")
for team in sorted(teams, key=lambda x: x.PlayoffSpotClinchedScenarios, reverse=True):
    formatted_string = team.Name.split(' ')[0]
    for i in range(0, 10, 1):
        formatted_string += ("\t{}".format(team.PlayoffSpotFinishes[i]))
    print (formatted_string)