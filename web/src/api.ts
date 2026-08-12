export type Half = 'top' | 'bottom'
export type Team = 'away' | 'home'

export interface RatingSet {
  [key: string]: number
}

export interface GameEvent {
  sequence: number
  inning: number
  half: Half
  outcome: string
  batter: string
  pitcher: string
  runs_scored: number
  description: string
}

export interface GameStateView {
  inning: number
  half: Half
  outs: number
  bases: { first: string | null; second: string | null; third: string | null }
  away_score: number
  home_score: number
  batting_team: Team
  batter: string
  pitcher: string
  plate_appearances: number
  finished: boolean
  winner: Team | null
  seed: number
  away_lineup: string[]
  home_lineup: string[]
}

export interface GameView {
  game_id: string
  model_version: string
  state: GameStateView
  batter_ratings: RatingSet
  pitcher_ratings: RatingSet
  events: GameEvent[]
}

export type Archetype = 'contact' | 'power' | 'patient' | 'balanced'
export type CareerSkillName = 'contact' | 'power' | 'eye' | 'speed_proxy'

export interface CareerSkill {
  score: number
  rating_raw: number
  rating_display: number
  potential_score: number
  next_cost: number | null
  can_train: boolean
}

export interface BattingStats {
  games: number; pa: number; ab: number; hits: number; singles: number
  doubles: number; triples: number; home_runs: number; walks: number
  hbp: number; strikeouts: number; total_bases: number
  avg: number; obp: number; slg: number; ops: number
}

export interface CareerGameResult {
  season_year: number; game_number: number; plate_appearances: number
  outcomes: string[]; hits: number; home_runs: number; walks: number
  xp_earned: number; development_points_earned: number
}

export interface CareerView {
  career_id: string; revision: number; autosaved_at: string
  persistence_version: string; schema_version: number; model_version: string
  name: string; position: string; bats: string; throws: string
  archetype: Archetype; age: number; season_year: number
  games_played: number; season_games: number; experience: number
  development_points: number; expired_development_points: number
  season_purchases: number; retired: boolean
  active_game: null | {
    season_year: number; game_number: number; inning: number; half: 'top' | 'bottom'
    outs: number; bases: Array<string | null>; away_score: number; home_score: number
    batting_team: 'away' | 'home'; batter: string; pitcher: string
    away_pitcher: string; home_pitcher: string; seed: number
    game_plate_appearances: number; career_plate_appearances: number
    career_outcomes: string[]; away_lineup: string[]; home_lineup: string[]
  }
  skills: Record<CareerSkillName, CareerSkill>
  season_stats: BattingStats; career_stats: BattingStats
  recent_results: CareerGameResult[]
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }
let operationCounter = 0

function operationId(): string {
  operationCounter = (operationCounter + 1) % 0x1000000
  const timestamp = Date.now().toString(36)
  const counter = operationCounter.toString(36)
  const random = Math.floor(Math.random() * 0x100000000).toString(36)
  return `web-${timestamp}-${counter}-${random}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const detail = await response.text()
    try {
      const parsed = JSON.parse(detail) as { message?: string }
      throw new Error(parsed.message || detail || `Request failed: ${response.status}`)
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(detail || `Request failed: ${response.status}`)
      }
      throw error
    }
  }
  return response.json() as Promise<T>
}

export function createGame(seed: number): Promise<GameView> {
  return request('/api/games', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ seed }),
  })
}

export function mutateGame(gameId: string, action: 'next-pa' | 'simulate-half' | 'simulate-full') {
  return request<GameView>(`/api/games/${gameId}/${action}`, { method: 'POST' })
}

export function resetGame(gameId: string, seed: number): Promise<GameView> {
  return request(`/api/games/${gameId}/reset`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ seed }),
  })
}

export async function listCareers(): Promise<CareerView[]> {
  const response = await request<{ careers: CareerView[] }>('/api/careers')
  return response.careers
}

export function createCareer(input: {
  name: string; archetype: Archetype; bats: 'left' | 'right' | 'switch'
  throws: 'left' | 'right'; position: string
}): Promise<CareerView> {
  return request('/api/careers', {
    method: 'POST', headers: JSON_HEADERS,
    body: JSON.stringify({
      ...input, season_year: 2026, seed: 20260812,
      season_games: 120, expected_revision: 0, operation_id: operationId(),
    }),
  })
}

export function mutateCareer(
  career: CareerView,
  action: 'train' | 'next-pa' | 'simulate-game' | 'simulate-month' | 'simulate-week'
    | 'simulate-to-next-event' | 'simulate-season',
  extra: Record<string, unknown> = {},
): Promise<CareerView> {
  return request(`/api/careers/${career.career_id}/${action}`, {
    method: 'POST', headers: JSON_HEADERS,
    body: JSON.stringify({
      expected_revision: career.revision, operation_id: operationId(), ...extra,
    }),
  })
}

export interface ManagerCard {
  card_id: string; player_name: string; season_year: number; team: string
  profile_position: string; role: string | null; tier: string; cost: number
  abilities: Record<string, number>
}

export interface ManagerLineupCard extends Omit<ManagerCard, 'team'> {
  position: string
}

export interface ManagerTeam {
  team_id: string; name: string; strategy: string; games_played: number
  roster_cost: number; batter_count: number; rotation_count: number; bullpen_count: number
  next_starter_card_id: string; lineup: ManagerLineupCard[]; bench: ManagerCard[]
  rotation: ManagerCard[]; bullpen: ManagerCard[]; tier_counts: Record<string, number>
  available_bullpen_card_ids: string[]
}

export interface ManagerStanding {
  rank: number; team_id: string; wins: number; losses: number
  runs_scored: number; runs_allowed: number; run_differential: number
  winning_percentage: number; games_behind: number
}

export interface ManagerResult {
  game_number: number; away_team_id: string; home_team_id: string
  away_runs: number; home_runs: number
}

export interface ManagerView {
  manager_id: string; revision: number; autosaved_at: string
  persistence_version: string; schema_version: number; model_version: string
  catalog_snapshot_version: string; catalog_fingerprint: string; seed: number
  games_completed: number; total_games: number; finished: boolean
  next_game: null | { game_number: number; round_number: number; away_team_id: string; home_team_id: string }
  standings: ManagerStanding[]; teams: ManagerTeam[]; recent_results: ManagerResult[]
}

export async function listManagers(): Promise<ManagerView[]> {
  const response = await request<{ managers: ManagerView[] }>('/api/managers')
  return response.managers
}

export function createManager(seed = 20260812): Promise<ManagerView> {
  return request('/api/managers', {
    method: 'POST', headers: JSON_HEADERS,
    body: JSON.stringify({
      seed, expected_revision: 0, operation_id: operationId(),
    }),
  })
}

export function mutateManager(
  manager: ManagerView,
  action: 'simulate-next-game' | 'simulate-round' | 'simulate-season',
): Promise<ManagerView> {
  return request(`/api/managers/${manager.manager_id}/${action}`, {
    method: 'POST', headers: JSON_HEADERS,
    body: JSON.stringify({
      expected_revision: manager.revision, operation_id: operationId(),
    }),
  })
}

export async function listManagerRosterCandidates(
  manager: ManagerView,
  teamId: string,
  outgoingCardId: string,
): Promise<ManagerCard[]> {
  const query = new URLSearchParams({ team_id: teamId, outgoing_card_id: outgoingCardId })
  const response = await request<{ candidates: ManagerCard[] }>(
    `/api/managers/${manager.manager_id}/roster-candidates?${query}`,
  )
  return response.candidates
}

export function replaceManagerCard(
  manager: ManagerView,
  teamId: string,
  outgoingCardId: string,
  incomingCardId: string,
): Promise<ManagerView> {
  return request(`/api/managers/${manager.manager_id}/replace-card`, {
    method: 'POST', headers: JSON_HEADERS,
    body: JSON.stringify({
      expected_revision: manager.revision,
      operation_id: operationId(),
      team_id: teamId,
      outgoing_card_id: outgoingCardId,
      incoming_card_id: incomingCardId,
    }),
  })
}
