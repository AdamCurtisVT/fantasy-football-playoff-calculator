#-------------------------------------------------
# Imports
#-------------------------------------------------
import sys
import pyodbc
import math

#-------------------------------------------------
# Classes
#-------------------------------------------------

# Represents a Fantasy Football team.
class Team(object):
    Name = None
    RosterId = 0
    PlayoffBoundScenarios = 0
    PlayoffSpotClinchedScenarios = 0
    PlayoffSpotFinishes = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    Schedule = [False, False, False, False, False, False, False, False, False, False, False, False, False]

    # Initializes a new instance of the class.
    def __init__(self, name, rosterId):
        self.Name = name
        self.RosterId = rosterId
        self.PlayoffBoundScenarios = 0
        self.PlayoffSpotClinchedScenarios = 0
        self.Schedule = [False, False, False, False, False, False, False, False, False, False, False, False, False]
        self.PlayoffSpotFinishes = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    # Returns the number of wins in the season.
    @property
    def Wins(self):
        return sum(self.Schedule)

# Represents a Fantasy Football matchup.
class Matchup(object):
    MatchupPeriod = 0
    RosterId = None
    OpponentRosterId = None

    # Initializes a new instance of the class.
    def __init__(self, matchupPeriod, rosterId, opponentRosterId):
        self.MatchupPeriod = matchupPeriod
        self.RosterId = rosterId
        self.OpponentRosterId = opponentRosterId

#-------------------------------------------------
# Functions
#-------------------------------------------------

# Initializes the list of matchups.
def InitializeMatchups(league_id):
    cursor.execute("SELECT MatchupPeriod, RosterId, OpponentRosterId FROM simulation.LeagueSchedule WHERE LeagueId = '{}'".format(league_id))
    rows = cursor.fetchall()
    for row in rows:
        Matchups.append(Matchup(row.MatchupPeriod, row.RosterId, row.OpponentRosterId))

# Initializes the list of teams.
def InitializeTeams(league_id):
    cursor.execute("SELECT LeagueId,RosterId,UserName,WeekOneResult,WeekTwoResult,WeekThreeResult,WeekFourResult,WeekFiveResult,WeekSixResult,WeekSevenResult,WeekEightResult,WeekNineResult,WeekTenResult,WeekElevenResult,WeekTwelveResult,WeekThirteenResult FROM simulation.OwnerSummaryMatchup WHERE LeagueId = '{}' ORDER BY RosterId ASC".format(league_id))
    rows = cursor.fetchall()
    for row in rows:
        tmp = Team(row.UserName, row.RosterId)
        tmp.Schedule[0] = True if row.WeekOneResult == "Win" else False
        tmp.Schedule[1] = True if row.WeekTwoResult == "Win" else False
        tmp.Schedule[2] = True if row.WeekThreeResult == "Win" else False
        tmp.Schedule[3] = True if row.WeekFourResult == "Win" else False
        tmp.Schedule[4] = True if row.WeekFiveResult == "Win" else False
        tmp.Schedule[5] = True if row.WeekSixResult == "Win" else False
        tmp.Schedule[6] = True if row.WeekSevenResult == "Win" else False
        tmp.Schedule[7] = True if row.WeekEightResult == "Win" else False
        tmp.Schedule[8] = True if row.WeekNineResult == "Win" else False
        tmp.Schedule[9] = True if row.WeekTenResult == "Win" else False
        tmp.Schedule[10] = True if row.WeekElevenResult == "Win" else False
        tmp.Schedule[11] = True if row.WeekTwelveResult == "Win" else False
        tmp.Schedule[12] = True if row.WeekThirteenResult == "Win" else False
        Teams.append(tmp)

# Processes the weekly matchups.
def ProcessWeeklyMatchups(matchupPeriod):
    weeklyMatchups = list(t for t in Matchups if t.MatchupPeriod == matchupPeriod)
    mp = matchupPeriod-1
    for i in range(0, 2, 1):
        Teams[weeklyMatchups[0].RosterId-1].Schedule[mp] = (i == 0)
        Teams[weeklyMatchups[0].OpponentRosterId-1].Schedule[mp] = (i == 1)

        for j in range(0, 2, 1):
            Teams[weeklyMatchups[1].RosterId-1].Schedule[mp] = (j == 0)
            Teams[weeklyMatchups[1].OpponentRosterId-1].Schedule[mp] = (j == 1)

            for k in range(0, 2, 1):
                Teams[weeklyMatchups[2].RosterId-1].Schedule[mp] = (k == 0)
                Teams[weeklyMatchups[2].OpponentRosterId-1].Schedule[mp] = (k == 1)

                for l in range(0, 2, 1):
                    Teams[weeklyMatchups[3].RosterId-1].Schedule[mp] = (l == 0)
                    Teams[weeklyMatchups[3].OpponentRosterId-1].Schedule[mp] = (l == 1)
                
                    for m in range(0, 2, 1):
                        Teams[weeklyMatchups[4].RosterId-1].Schedule[mp] = (m == 0)
                        Teams[weeklyMatchups[4].OpponentRosterId-1].Schedule[mp] = (m == 1)

                        for n in range(0, 2, 1):
                            Teams[weeklyMatchups[5].RosterId-1].Schedule[mp] = (n == 0)
                            Teams[weeklyMatchups[5].OpponentRosterId-1].Schedule[mp] = (n == 1)

                            if (matchupPeriod == 13):
                                DeterminePlayoffSpotFinishes()
                                DeterminePlayoffChances()                                
                            else:
                                ProcessWeeklyMatchups(matchupPeriod+1)

# Determine the playoff spot finishes in the current scenario.
def DeterminePlayoffSpotFinishes():
    sortedTeams = sorted(Teams, key=lambda x: x.Wins, reverse=True)

    rank = 0
    for r in range(0, 12, 1):
        if (r != 0 and sortedTeams[r].Wins < sortedTeams[r - 1].Wins):
            rank = r
        Teams[sortedTeams[r].RosterId - 1].PlayoffSpotFinishes[rank]+=1

# Determine the playoff chances in the current scenario.
def DeterminePlayoffChances():
    minimumWins = sorted(Teams, key=lambda x: x.Wins, reverse=True)[5].Wins

    for team in Teams:
        if (team.Wins == minimumWins):
            team.PlayoffBoundScenarios += 1
        elif (team.Wins > minimumWins):
            team.PlayoffBoundScenarios += 1
            team.PlayoffSpotClinchedScenarios += 1 

#-------------------------------------------------
# Main
#-------------------------------------------------

# Define constants
LeagueId = ''
StartingWeek = 12
Scenarios = math.pow(64,(13-(StartingWeek-1)))

# Define database constants.
# Define database constants.
server = ''
database = ''
username = ''
password = ''

# Configure a connection and cursor to the database.
connection = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}', autocommit=True)
cursor = connection.cursor()

# Create the list of teams.
Teams = []
InitializeTeams(LeagueId)

# Create the list of matchups.
Matchups = []
InitializeMatchups(LeagueId)

# Print the amount of time it should take to run the app.
print("There are {} scenarios starting in week {}. This will take approx {} seconds.".format(Scenarios, StartingWeek, Scenarios*0.00000762939453125))

# Process all the matchups.
ProcessWeeklyMatchups(StartingWeek)

# Print the ordered results.
for team in sorted(Teams, key=lambda x: x.PlayoffSpotClinchedScenarios, reverse=True):
    team_name = team.Name.split(' ')[0]
    potential_playoff_spot_scenarios = round((team.PlayoffBoundScenarios/Scenarios)*100, 2)
    clinched_playoff_spot_scenarios = round((team.PlayoffSpotClinchedScenarios/Scenarios)*100, 2)
    print("{} {}% {}%".format(team_name, potential_playoff_spot_scenarios, clinched_playoff_spot_scenarios))

# Print the potential finishes.
print("\nName\t1\t2\t3\t4\t5\t6\t7\t8\t9\t10\t11\t12")
for team in sorted(Teams, key=lambda x: x.PlayoffSpotClinchedScenarios, reverse=True):
    formatted_string = team.Name.split(' ')[0]
    for i in range(0, 12, 1):
        formatted_string += ("\t{}".format(team.PlayoffSpotFinishes[i]))
    print (formatted_string)