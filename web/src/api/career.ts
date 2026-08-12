import { JSON_HEADERS, operationId, request } from './client'

export type Archetype = 'contact' | 'power' | 'patient' | 'balanced'
export type CareerSkillName = 'contact' | 'power' | 'eye' | 'speed_proxy'
export interface CareerSkill { score: number; rating_raw: number; rating_display: number; potential_score: number; next_cost: number | null; can_train: boolean }
export interface BattingStats { games: number; pa: number; ab: number; hits: number; singles: number; doubles: number; triples: number; home_runs: number; walks: number; hbp: number; strikeouts: number; total_bases: number; avg: number; obp: number; slg: number; ops: number }
export interface CareerGameResult { season_year: number; game_number: number; plate_appearances: number; outcomes: string[]; hits: number; home_runs: number; walks: number; xp_earned: number; development_points_earned: number }
export interface CareerView {
  career_id: string; revision: number; autosaved_at: string; persistence_version: string; schema_version: number; model_version: string
  name: string; position: string; bats: string; throws: string; archetype: Archetype; age: number; season_year: number
  games_played: number; season_games: number; experience: number; development_points: number; expired_development_points: number
  season_purchases: number; retired: boolean
  active_game: null | { season_year: number; game_number: number; inning: number; half: 'top' | 'bottom'; outs: number; bases: Array<string | null>; away_score: number; home_score: number; batting_team: 'away' | 'home'; batter: string; pitcher: string; away_pitcher: string; home_pitcher: string; seed: number; game_plate_appearances: number; career_plate_appearances: number; career_outcomes: string[]; away_lineup: string[]; home_lineup: string[] }
  skills: Record<CareerSkillName, CareerSkill>; season_stats: BattingStats; career_stats: BattingStats; recent_results: CareerGameResult[]
}

export async function listCareers(): Promise<CareerView[]> { return (await request<{ careers: CareerView[] }>('/api/careers')).careers }
export function createCareer(input: { name: string; archetype: Archetype; bats: 'left' | 'right' | 'switch'; throws: 'left' | 'right'; position: string }): Promise<CareerView> {
  return request('/api/careers', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ ...input, season_year: 2026, seed: 20260812, season_games: 120, expected_revision: 0, operation_id: operationId() }) })
}
export function mutateCareer(career: CareerView, action: 'train' | 'next-pa' | 'simulate-game' | 'simulate-month' | 'simulate-week' | 'simulate-to-next-event' | 'simulate-season', extra: Record<string, unknown> = {}): Promise<CareerView> {
  return request(`/api/careers/${encodeURIComponent(career.career_id)}/${action}`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ expected_revision: career.revision, operation_id: operationId(), ...extra }) })
}
