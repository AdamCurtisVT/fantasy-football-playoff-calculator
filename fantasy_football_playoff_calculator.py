#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests
import timeit
import random
import multiprocessing as mp
from functools import lru_cache
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

def ProcessWeeklyMatchups(matchupPeriod: int, teams: List[Team], matchups: List[Matchup], league: League, team_matrix: List[List[int]]) -> None:
    """
    Process all possible outcomes for the given matchup period with early pruning.
    """
    weeklyMatchups = [t for t in matchups if t.matchup_period == matchupPeriod]
    mp = matchupPeriod - 1
    
    # Pre-compute roster indices to avoid repeated lookups
    roster_indices = [(match.roster_id - 1, match.opponent_roster_id - 1) for match in weeklyMatchups]

    # Early pruning: if some teams are already mathematically eliminated or guaranteed,
    # we can skip some combinations
    remaining_weeks = league.last_week_of_regular_season - matchupPeriod + 1
    
    for combination in product([0, 1], repeat=len(weeklyMatchups)):
        # Apply combination to team matrix
        for idx, (team_idx, opp_idx) in enumerate(roster_indices):
            win = combination[idx]
            team_matrix[team_idx][mp] = win
            team_matrix[opp_idx][mp] = 1 - win

        # Early pruning check - calculate if any teams are mathematically eliminated
        if remaining_weeks <= 3:  # Only do expensive check near the end
            if can_skip_scenario(remaining_weeks, teams, league, team_matrix):
                continue

        if matchupPeriod == league.last_week_of_regular_season:
            DeterminePlayoffChances(teams, league, team_matrix)
        else:
            ProcessWeeklyMatchups(matchupPeriod + 1, teams, matchups, league, team_matrix)


def can_skip_scenario(remaining_weeks: int, teams: List[Team], league: League, team_matrix: List[List[int]]) -> bool:
    """
    Determine if we can skip this scenario based on mathematical impossibilities.
    """
    current_wins = []
    for team_idx, team in enumerate(teams):
        current_total = team.wins + sum(team_matrix[team_idx][league.current_week-1:])
        max_possible = current_total + remaining_weeks
        current_wins.append((team_idx, current_total, max_possible))
    
    # Sort by max possible wins
    current_wins.sort(key=lambda x: x[2], reverse=True)
    
    # If the (playoff_spots)th best team's max possible wins is less than
    # the current wins of teams above it, some outcomes are impossible
    if len(current_wins) >= league.number_of_playoff_teams:
        cutoff_max = current_wins[league.number_of_playoff_teams-1][2]
        for i in range(league.number_of_playoff_teams):
            if current_wins[i][1] > cutoff_max:
                return True  # Skip this impossible scenario
    
    return False


def MonteCarloSimulation(num_simulations: int, teams: List[Team], matchups: List[Matchup], league: League) -> None:
    """
    Use Monte Carlo simulation for faster approximate results when scenarios are too numerous.
    """
    # Reset scenario counters
    for team in teams:
        team.playoff_scenarios = 0
        team.guaranteed_playoff_scenarios = 0
    
    remaining_matchups = [m for m in matchups if m.matchup_period >= league.current_week]
    
    for simulation in range(num_simulations):
        # Create a copy of current wins for this simulation
        sim_wins = [team.wins for team in teams]
        
        # Randomly decide outcomes for remaining matchups
        for matchup in remaining_matchups:
            winner = random.choice([matchup.roster_id, matchup.opponent_roster_id])
            if winner == matchup.roster_id:
                sim_wins[matchup.roster_id - 1] += 1
            else:
                sim_wins[matchup.opponent_roster_id - 1] += 1
        
        # Calculate playoff teams for this simulation
        team_records = [(i, wins) for i, wins in enumerate(sim_wins)]
        team_records.sort(key=lambda x: x[1], reverse=True)
        
        # Handle ties more accurately by using points for as tiebreaker
        tied_groups = []
        current_wins = team_records[0][1]
        current_group = [team_records[0]]
        
        for i in range(1, len(team_records)):
            if team_records[i][1] == current_wins:
                current_group.append(team_records[i])
            else:
                tied_groups.append(current_group)
                current_wins = team_records[i][1]
                current_group = [team_records[i]]
        tied_groups.append(current_group)
        
        # Resolve ties using points for
        final_rankings = []
        for group in tied_groups:
            if len(group) > 1:
                # Sort by points for within tied group
                group.sort(key=lambda x: teams[x[0]].fantasy_points_for, reverse=True)
            final_rankings.extend([team_idx for team_idx, _ in group])
        
        # Count playoff scenarios
        playoff_cutoff = min(league.number_of_playoff_teams, len(final_rankings))
        cutoff_wins = sim_wins[final_rankings[playoff_cutoff-1]] if playoff_cutoff > 0 else 0
        
        for i in range(playoff_cutoff):
            team_idx = final_rankings[i]
            teams[team_idx].playoff_scenarios += 1
            
            # Guaranteed spot if wins are higher than cutoff
            if sim_wins[team_idx] > cutoff_wins:
                teams[team_idx].guaranteed_playoff_scenarios += 1


def should_use_monte_carlo(scenarios: float, threshold: float = 100000) -> bool:
    """
    Determine whether to use Monte Carlo simulation based on scenario count.
    """
    return scenarios > threshold


def parallel_monte_carlo_worker(args) -> tuple:
    """
    Worker function for parallel Monte Carlo simulation.
    """
    simulations_per_worker, remaining_matchups, teams_data, league_data = args
    
    # Initialize local counters
    local_playoff_scenarios = [0] * len(teams_data)
    local_guaranteed_scenarios = [0] * len(teams_data)
    
    for _ in range(simulations_per_worker):
        # Create simulation wins
        sim_wins = [team['wins'] for team in teams_data]
        
        # Randomly decide outcomes
        for matchup in remaining_matchups:
            winner = random.choice([matchup['roster_id'], matchup['opponent_roster_id']])
            if winner == matchup['roster_id']:
                sim_wins[matchup['roster_id'] - 1] += 1
            else:
                sim_wins[matchup['opponent_roster_id'] - 1] += 1
        
        # Calculate rankings with tiebreaker
        team_records = [(i, wins, teams_data[i]['fantasy_points_for']) for i, wins in enumerate(sim_wins)]
        team_records.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        # Count playoff scenarios
        playoff_cutoff = min(league_data['number_of_playoff_teams'], len(team_records))
        cutoff_wins = team_records[playoff_cutoff-1][1] if playoff_cutoff > 0 else 0
        
        for i in range(playoff_cutoff):
            team_idx = team_records[i][0]
            local_playoff_scenarios[team_idx] += 1
            
            if sim_wins[team_idx] > cutoff_wins:
                local_guaranteed_scenarios[team_idx] += 1
    
    return local_playoff_scenarios, local_guaranteed_scenarios


def parallel_monte_carlo_simulation(num_simulations: int, teams: List[Team], matchups: List[Matchup], league: League) -> None:
    """
    Parallel Monte Carlo simulation using multiple CPU cores.
    """
    # Reset counters
    for team in teams:
        team.playoff_scenarios = 0
        team.guaranteed_playoff_scenarios = 0
    
    # Prepare data for workers
    remaining_matchups = [
        {
            'roster_id': m.roster_id,
            'opponent_roster_id': m.opponent_roster_id,
            'matchup_period': m.matchup_period
        }
        for m in matchups if m.matchup_period >= league.current_week
    ]
    
    teams_data = [
        {
            'wins': team.wins,
            'fantasy_points_for': team.fantasy_points_for
        }
        for team in teams
    ]
    
    league_data = {
        'number_of_playoff_teams': league.number_of_playoff_teams,
        'current_week': league.current_week
    }
    
    # Determine number of workers and simulations per worker
    num_workers = min(mp.cpu_count(), 8)  # Cap at 8 to avoid overhead
    simulations_per_worker = num_simulations // num_workers
    
    # Create worker arguments
    worker_args = [
        (simulations_per_worker, remaining_matchups, teams_data, league_data)
        for _ in range(num_workers)
    ]
    
    # Run parallel simulation
    with mp.Pool(num_workers) as pool:
        results = pool.map(parallel_monte_carlo_worker, worker_args)
    
    # Aggregate results
    for playoff_scenarios, guaranteed_scenarios in results:
        for i in range(len(teams)):
            teams[i].playoff_scenarios += playoff_scenarios[i]
            teams[i].guaranteed_playoff_scenarios += guaranteed_scenarios[i]


def DeterminePlayoffChances(teams: List[Team], league: League, team_matrix: List[List[int]]) -> None:
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

@lru_cache(maxsize=128)
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

@lru_cache(maxsize=128)
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

@lru_cache(maxsize=128)
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

@lru_cache(maxsize=128)
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

def main():
    """
    Main execution function for the playoff calculator.
    """
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
            
            print(f"There are {scenarios:.0f} scenarios starting in week {league.current_week}.")
            
            # Choose algorithm based on scenario count
            if should_use_monte_carlo(scenarios):
                print("Using Monte Carlo simulation for faster approximate results...")
                num_simulations = min(500000, int(scenarios * 0.1))  # Use 10% of scenarios, max 500k
                print(f"Running {num_simulations:,} simulations using {mp.cpu_count()} CPU cores...")
                
                start_time = timeit.default_timer()
                parallel_monte_carlo_simulation(num_simulations, teams, matchups, league)
                elapsed_time = timeit.default_timer() - start_time
                
                # Update scenarios count for percentage calculation
                scenarios = num_simulations
                print(f"Monte Carlo simulation completed in {elapsed_time:.2f} seconds")
                print("Note: Results are statistical approximations with ~99% confidence")
                
            else:  # For smaller scenario counts, use exact calculation
                print(f"Using exact calculation. Estimated time: {scenarios*time_per_scenario:.1f} seconds")
                elapsed_time = timeit.timeit(lambda: ProcessWeeklyMatchups(league.current_week, teams, matchups, league, team_matrix), number=1)
                print(f"Exact calculation completed in {elapsed_time:.6f} seconds")

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
            
            # Add algorithm info to output
            if scenarios <= 100000:
                algorithm_note = "(Exact calculation)"
            else:
                algorithm_note = f"(Monte Carlo approximation, {scenarios:,} simulations)"
                
            print(f"\nPlayoff Probabilities {algorithm_note}:")
            print(tabulate(team_data, headers, tablefmt="presto", floatfmt=".2%"))


if __name__ == "__main__":
    main()
