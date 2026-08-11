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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Request failed: ${response.status}`)
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
      season_games: 120, expected_revision: 0, operation_id: crypto.randomUUID(),
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
      expected_revision: career.revision, operation_id: crypto.randomUUID(), ...extra,
    }),
  })
}
