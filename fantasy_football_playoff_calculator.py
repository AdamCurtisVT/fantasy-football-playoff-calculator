#-------------------------------------------------
# Imports
#-------------------------------------------------
import math
import requests
import timeit
import time
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from tabulate import tabulate
from dataclasses import dataclass
from typing import Optional, List, Dict
from tqdm import tqdm

import numpy as np
from numba import njit, prange, get_num_threads

#-------------------------------------------------
# Logging Setup
#-------------------------------------------------

def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Set up logging configuration for console output only.
    """
    level = logging.DEBUG if verbose else logging.INFO

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(console_handler)

    return logger

#-------------------------------------------------
# Configuration
#-------------------------------------------------

@dataclass
class Config:
    """Configuration settings for the playoff calculator."""
    DEFAULT_LEAGUE_ID: str = '1245761367646937088'
    MAX_EXACT_SECONDS: float = 60.0          # Wall-time budget before falling back to Monte Carlo
    NUMPY_EXACT_BIT_LIMIT: int = 29          # Use vectorized NumPy up to 2**29 = ~500M scenarios
    NUMPY_BATCH_SIZE: int = 1 << 20          # 1M scenarios per matmul batch (~120 MB peak per batch)
    NUMBA_NS_PER_SCENARIO: float = 200.0     # Rough wall-time estimate per Numba bitmask iteration
    MAX_SIMULATIONS: int = 1_000_000         # MC default; ~1 s with the Numba kernel
    MAX_WORKERS: int = 8                     # Cap on parallel API fetches
    API_RETRY_ATTEMPTS: int = 3
    API_RETRY_DELAY: float = 1.0
    API_TIMEOUT: float = 10.0
    API_BASE_URL: str = 'https://api.sleeper.app/v1'

CONFIG = Config()

# Module-level HTTP session reuses TCP/TLS connections across API calls.
SESSION = requests.Session()


def _api_get(endpoint: str):
    """GET an endpoint with bounded exponential-backoff retries; raise on persistent failure."""
    last_exc: Optional[Exception] = None
    for attempt in range(CONFIG.API_RETRY_ATTEMPTS):
        try:
            response = SESSION.get(endpoint, timeout=CONFIG.API_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < CONFIG.API_RETRY_ATTEMPTS - 1:
                time.sleep(CONFIG.API_RETRY_DELAY * (2 ** attempt))
    raise RuntimeError(
        f"API call failed after {CONFIG.API_RETRY_ATTEMPTS} attempts: {endpoint}"
    ) from last_exc

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
# Sleeper imports
#-------------------------------------------------

def import_league_settings(league_id: str) -> League:
    """Import the league settings from the Sleeper API."""
    sleeper_league = get_league(league_id)
    return League(
        id=league_id,
        current_week=sleeper_league["settings"]["leg"],
        playoff_week_start=sleeper_league["settings"]["playoff_week_start"],
        last_week_of_regular_season=sleeper_league["settings"]["playoff_week_start"] - 1,
        number_of_playoff_teams=sleeper_league["settings"]["playoff_teams"],
        number_of_teams=sleeper_league["total_rosters"],
    )


def import_matchups(league_id: str, starting_week: int, league_playoff_week_start: int) -> List[Matchup]:
    """
    Import all remaining league matchups from the Sleeper API.
    Per-week API calls are issued in parallel; pairing is O(rows) using a dict.
    """
    weeks = list(range(starting_week, league_playoff_week_start + 1))
    if not weeks:
        return []

    with ThreadPoolExecutor(max_workers=min(len(weeks), CONFIG.MAX_WORKERS)) as executor:
        weekly_payloads = list(executor.map(
            lambda w: (w, get_league_matchups(league_id, w)),
            weeks,
        ))

    matchups: List[Matchup] = []
    for week, payload in weekly_payloads:
        index_by_id: Dict[int, int] = {}
        for league_matchup in payload:
            matchup_id = league_matchup["matchup_id"]
            existing = index_by_id.get(matchup_id)
            if existing is not None:
                matchups[existing].opponent_roster_id = league_matchup["roster_id"]
            else:
                index_by_id[matchup_id] = len(matchups)
                matchups.append(Matchup(
                    matchup_period=week,
                    matchup_id=matchup_id,
                    roster_id=league_matchup["roster_id"],
                    opponent_roster_id=None,
                ))
    return matchups


def import_team_list(league_id: str) -> List[Team]:
    """Import all of the league teams along with the owner's display name."""
    teams: List[Team] = []
    league_rosters = get_league_rosters(league_id)
    league_users = get_league_users(league_id)

    for league_roster in league_rosters:
        teams.append(Team(
            roster_id=league_roster["roster_id"],
            owner_id=league_roster["owner_id"],
            wins=league_roster["settings"]["wins"],
            losses=league_roster["settings"]["losses"],
            fantasy_points_for=league_roster["settings"]["fpts"],
            fantasy_points_against=league_roster["settings"]["fpts_against"],
        ))

    name_by_user_id = {user["user_id"]: user["display_name"] for user in league_users}
    for team in teams:
        if team.owner_id in name_by_user_id:
            team.name = name_by_user_id[team.owner_id]

    return teams


def recalculate_records(league_id: str, teams: List[Team], up_to_week: int,
                        logger: logging.Logger) -> None:
    """
    Reset each team's wins/losses to reflect only the outcomes of weeks 1..up_to_week-1.
    Use when running the playoff simulation 'as of' a past week.
    Winner is decided by 'points'; ties count as neither a win nor a loss.
    """
    weeks = list(range(1, up_to_week))
    if not weeks:
        for team in teams:
            team.wins = 0
            team.losses = 0
        return

    with ThreadPoolExecutor(max_workers=min(len(weeks), CONFIG.MAX_WORKERS)) as executor:
        weekly_payloads = list(executor.map(
            lambda w: (w, get_league_matchups(league_id, w)),
            weeks,
        ))

    wins = {team.roster_id: 0 for team in teams}
    losses = {team.roster_id: 0 for team in teams}
    ties = 0

    for week, payload in weekly_payloads:
        by_matchup: Dict[int, List[dict]] = {}
        for entry in payload:
            by_matchup.setdefault(entry["matchup_id"], []).append(entry)

        for matchup_id, entries in by_matchup.items():
            if len(entries) != 2:
                logger.warning(
                    f"Week {week} matchup {matchup_id}: {len(entries)} entries (expected 2); skipping"
                )
                continue
            a, b = entries
            pts_a = a.get("points") or 0.0
            pts_b = b.get("points") or 0.0
            if pts_a > pts_b:
                wins[a["roster_id"]] += 1
                losses[b["roster_id"]] += 1
            elif pts_b > pts_a:
                wins[b["roster_id"]] += 1
                losses[a["roster_id"]] += 1
            else:
                ties += 1

    if ties:
        logger.warning(f"Skipped {ties} tied matchup(s) (counted as neither win nor loss)")

    for team in teams:
        team.wins = wins[team.roster_id]
        team.losses = losses[team.roster_id]


def prompt_start_week(default: int, max_week: int) -> int:
    """Prompt for a start week between 1 and max_week, defaulting on empty input."""
    while True:
        user_input = input(f"Start from which week? (1-{max_week}, default {default}): ").strip()
        if not user_input:
            return default
        try:
            week = int(user_input)
            if 1 <= week <= max_week:
                return week
            print(f"Please enter a week between 1 and {max_week}.")
        except ValueError:
            print("Please enter a valid integer.")

#-------------------------------------------------
# Compute kernels
#-------------------------------------------------

def _build_arrays(matchups: List[Matchup], teams: List[Team]):
    """Convert dataclasses to typed arrays for the hot path. Maps roster_id -> 0..N-1."""
    roster_to_idx = {team.roster_id: i for i, team in enumerate(teams)}
    matchup_pairs = np.array(
        [[roster_to_idx[m.roster_id], roster_to_idx[m.opponent_roster_id]] for m in matchups],
        dtype=np.int32,
    )
    initial_wins = np.array([t.wins for t in teams], dtype=np.int32)
    return matchup_pairs, initial_wins


def exact_numpy(matchup_pairs: np.ndarray, initial_wins: np.ndarray, num_playoffs: int,
                total_scenarios: int) -> tuple:
    """
    Vectorized enumeration of every win/loss combination via int matmul, batched to bound memory.
    For each scenario, count teams 'tied at cutoff or better' and 'guaranteed'.
    """
    M = int(matchup_pairs.shape[0])
    N = int(initial_wins.shape[0])

    # (M, N) one-hot: home_inc[k, t] = 1 iff team t is the "home" side of matchup k
    home_inc = np.zeros((M, N), dtype=np.int32)
    away_inc = np.zeros((M, N), dtype=np.int32)
    if M > 0:
        home_inc[np.arange(M), matchup_pairs[:, 0]] = 1
        away_inc[np.arange(M), matchup_pairs[:, 1]] = 1

    bit_powers = np.arange(M, dtype=np.int64)

    in_count = np.zeros(N, dtype=np.int64)
    guar_count = np.zeros(N, dtype=np.int64)

    batch = min(CONFIG.NUMPY_BATCH_SIZE, total_scenarios)
    cutoff_idx = N - num_playoffs

    with tqdm(total=total_scenarios, desc="Exact (NumPy)", unit="scenarios", file=sys.stdout) as pbar:
        for start in range(0, total_scenarios, batch):
            end = min(start + batch, total_scenarios)
            masks = np.arange(start, end, dtype=np.int64)
            # Shape (B, M) of 0/1
            outcomes = ((masks[:, None] >> bit_powers) & 1).astype(np.int32)
            # Shape (B, N): wins added per team in each scenario
            delta = outcomes @ home_inc + (1 - outcomes) @ away_inc
            final_wins = initial_wins[None, :] + delta
            cutoff = np.partition(final_wins, cutoff_idx, axis=1)[:, cutoff_idx]
            in_count += (final_wins >= cutoff[:, None]).sum(axis=0)
            guar_count += (final_wins > cutoff[:, None]).sum(axis=0)
            pbar.update(end - start)

    return in_count, guar_count


@njit(parallel=True, cache=True)
def exact_numba(matchup_pairs: np.ndarray, initial_wins: np.ndarray, num_playoffs: int,
                total_scenarios: int):
    """
    Bitmask iteration over all 2**M outcomes, parallelized across CPU threads.
    Used when M is large enough that the NumPy matmul batches get expensive.
    """
    N = initial_wins.shape[0]
    M = matchup_pairs.shape[0]
    num_threads = get_num_threads()

    per_thread_in = np.zeros((num_threads, N), dtype=np.int64)
    per_thread_guar = np.zeros((num_threads, N), dtype=np.int64)

    chunk_size = (total_scenarios + num_threads - 1) // num_threads
    cutoff_idx = N - num_playoffs

    for tid in prange(num_threads):
        start = tid * chunk_size
        end = start + chunk_size
        if end > total_scenarios:
            end = total_scenarios

        for mask in range(start, end):
            wins = initial_wins.copy()
            for k in range(M):
                if (mask >> k) & 1:
                    wins[matchup_pairs[k, 0]] += 1
                else:
                    wins[matchup_pairs[k, 1]] += 1
            sorted_wins = np.sort(wins)
            cutoff = sorted_wins[cutoff_idx]
            for t in range(N):
                if wins[t] >= cutoff:
                    per_thread_in[tid, t] += 1
                if wins[t] > cutoff:
                    per_thread_guar[tid, t] += 1

    return per_thread_in.sum(axis=0), per_thread_guar.sum(axis=0)


@njit(parallel=True, cache=True)
def monte_carlo_numba(num_simulations: int, matchup_pairs: np.ndarray, initial_wins: np.ndarray,
                      num_playoffs: int):
    """
    Monte Carlo simulation parallelized across threads with Numba's thread-local RNG.
    Counts the same metrics as exact mode (tied-at-cutoff-or-better, guaranteed).
    Returns (in_count, guar_count, sims_actually_run).
    """
    N = initial_wins.shape[0]
    M = matchup_pairs.shape[0]
    num_threads = get_num_threads()

    per_thread_in = np.zeros((num_threads, N), dtype=np.int64)
    per_thread_guar = np.zeros((num_threads, N), dtype=np.int64)

    sims_per_thread = num_simulations // num_threads
    cutoff_idx = N - num_playoffs

    for tid in prange(num_threads):
        for _ in range(sims_per_thread):
            wins = initial_wins.copy()
            for k in range(M):
                if np.random.random() < 0.5:
                    wins[matchup_pairs[k, 0]] += 1
                else:
                    wins[matchup_pairs[k, 1]] += 1
            sorted_wins = np.sort(wins)
            cutoff = sorted_wins[cutoff_idx]
            for t in range(N):
                if wins[t] >= cutoff:
                    per_thread_in[tid, t] += 1
                if wins[t] > cutoff:
                    per_thread_guar[tid, t] += 1

    in_count = per_thread_in.sum(axis=0)
    guar_count = per_thread_guar.sum(axis=0)
    return in_count, guar_count, sims_per_thread * num_threads


def choose_algorithm(matchup_count: int) -> str:
    """Pick exact-NumPy / exact-Numba / Monte-Carlo based on size and time budget."""
    total_scenarios = 1 << matchup_count
    if matchup_count <= CONFIG.NUMPY_EXACT_BIT_LIMIT:
        return "numpy_exact"
    estimated_seconds = total_scenarios * CONFIG.NUMBA_NS_PER_SCENARIO / 1e9
    if estimated_seconds <= CONFIG.MAX_EXACT_SECONDS:
        return "numba_exact"
    return "monte_carlo"

#-------------------------------------------------
# Sleeper API
#-------------------------------------------------

@lru_cache(maxsize=128)
def get_league(league_id: str) -> dict:
    return _api_get(f'{CONFIG.API_BASE_URL}/league/{league_id}')

@lru_cache(maxsize=128)
def get_league_matchups(league_id: str, week: int) -> List[dict]:
    return _api_get(f'{CONFIG.API_BASE_URL}/league/{league_id}/matchups/{week}')

@lru_cache(maxsize=128)
def get_league_rosters(league_id: str) -> List[dict]:
    return _api_get(f'{CONFIG.API_BASE_URL}/league/{league_id}/rosters')

@lru_cache(maxsize=128)
def get_league_users(league_id: str) -> List[dict]:
    return _api_get(f'{CONFIG.API_BASE_URL}/league/{league_id}/users')

#-------------------------------------------------
# Main
#-------------------------------------------------

def main():
    """Main execution function for the playoff calculator."""
    logger = setup_logging()

    league_id = input("Enter your league ID: ")
    if league_id == "":
        league_id = CONFIG.DEFAULT_LEAGUE_ID
        logger.info(f"Using default league ID: {league_id}")

    logger.info("Starting fantasy football playoff calculator")
    logger.info(f"Processing league ID: {league_id}")

    logger.info("Importing league settings...")
    league = import_league_settings(league_id)
    logger.info(f"League: {league.number_of_teams} teams, playoffs start week {league.playoff_week_start}")

    logger.info("Importing team data...")
    teams = import_team_list(league.id)
    logger.info(f"Loaded {len(teams)} teams")

    max_week = min(league.current_week, league.last_week_of_regular_season)
    if max_week < 1:
        logger.error(
            f"No valid start week available "
            f"(current_week={league.current_week}, last_regular={league.last_week_of_regular_season})"
        )
        return

    start_week = prompt_start_week(default=max_week, max_week=max_week)

    if start_week < league.current_week:
        logger.info(f"Recalculating team records as of start of week {start_week}...")
        recalculate_records(league.id, teams, start_week, logger)
        logger.info(f"Records recalculated from completed matchups (weeks 1-{start_week - 1})")

    league.current_week = start_week

    if league.current_week >= league.playoff_week_start:
        logger.warning("Playoffs have already started - no calculations needed")
        return

    logger.info("Importing remaining matchups...")
    matchups = import_matchups(league.id, league.current_week, league.last_week_of_regular_season)
    if not matchups:
        logger.warning("No remaining matchups found")
        return

    unpaired = [m for m in matchups if m.opponent_roster_id is None]
    if unpaired:
        logger.warning(
            f"Skipping {len(unpaired)} unpaired matchup(s) — likely bye weeks or an API gap "
            f"(weeks: {sorted({m.matchup_period for m in unpaired})})"
        )
        matchups = [m for m in matchups if m.opponent_roster_id is not None]
        if not matchups:
            logger.warning("No paired matchups remain after filtering")
            return
    logger.info(f"Found {len(matchups)} remaining matchups")

    matchup_pairs, initial_wins = _build_arrays(matchups, teams)
    M = int(matchup_pairs.shape[0])
    total_scenarios = 1 << M
    algorithm = choose_algorithm(M)
    logger.info(f"{total_scenarios:,} total scenarios — selected algorithm: {algorithm}")

    if algorithm == "numpy_exact":
        start = timeit.default_timer()
        in_count, guar_count = exact_numpy(
            matchup_pairs, initial_wins, league.number_of_playoff_teams, total_scenarios,
        )
        elapsed = timeit.default_timer() - start
        denominator = total_scenarios
        algorithm_note = "(Exact, vectorized NumPy)"
        logger.info(f"Exact calculation completed in {elapsed:.2f} seconds")

    elif algorithm == "numba_exact":
        estimated = total_scenarios * CONFIG.NUMBA_NS_PER_SCENARIO / 1e9
        logger.info(f"Estimated wall time: ~{estimated:.0f} seconds (first run includes JIT compile)")
        start = timeit.default_timer()
        in_count, guar_count = exact_numba(
            matchup_pairs, initial_wins, league.number_of_playoff_teams, total_scenarios,
        )
        elapsed = timeit.default_timer() - start
        denominator = total_scenarios
        algorithm_note = "(Exact, Numba parallel)"
        logger.info(f"Exact calculation completed in {elapsed:.2f} seconds")

    else:
        num_simulations = CONFIG.MAX_SIMULATIONS
        logger.info(f"Running {num_simulations:,} Monte Carlo simulations (Numba parallel)...")
        start = timeit.default_timer()
        in_count, guar_count, denominator = monte_carlo_numba(
            num_simulations, matchup_pairs, initial_wins, league.number_of_playoff_teams,
        )
        elapsed = timeit.default_timer() - start
        algorithm_note = f"(Monte Carlo, {denominator:,} simulations)"
        logger.info(f"Monte Carlo simulation completed in {elapsed:.2f} seconds")

    logger.info("Calculating final playoff percentages...")
    is_mc = algorithm == "monte_carlo"
    z_95 = 1.96  # 95% confidence interval z-score for a binomial proportion

    for i, team in enumerate(teams):
        team.playoff_scenarios = int(in_count[i])
        team.guaranteed_playoff_scenarios = int(guar_count[i])
        team.playoff_percentage = team.playoff_scenarios / denominator
        team.guaranteed_playoff_percentage = team.guaranteed_playoff_scenarios / denominator

    def format_pct(p: float) -> str:
        if is_mc:
            ci = z_95 * math.sqrt(p * (1.0 - p) / denominator)
            return f"{p * 100:.2f}% ± {ci * 100:.2f}%"
        return f"{p * 100:.2f}%"

    logger.info("Generating results table...")
    team_data = [
        [
            team.name,
            f"{team.wins}-{team.losses}",
            f"{team.fantasy_points_for}",
            f"{team.fantasy_points_against}",
            format_pct(team.guaranteed_playoff_percentage),
            format_pct(team.playoff_percentage),
        ]
        for team in sorted(teams, key=lambda x: (x.wins, x.playoff_percentage), reverse=True)
    ]
    headers = ["Name", "Record", "FPF", "FPA", "Guaranteed Spot", "Tied For Cutoff Or Better"]

    print(f"\nPlayoff Probabilities {algorithm_note}:")
    print(tabulate(team_data, headers, tablefmt="presto"))

    logger.info("Playoff calculation completed successfully")

if __name__ == "__main__":
    main()
