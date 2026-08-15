import { JSON_HEADERS, operationId, request } from './client'

export type Archetype = 'contact' | 'power' | 'patient' | 'speed' | 'balanced'
export type CareerSkillName = 'contact' | 'power' | 'eye' | 'speed_proxy'
export type WeeklyAction = 'contact_training' | 'power_training' | 'eye_training' | 'speed_training' | 'recovery' | 'video_study' | 'extra_batting_practice'
export type BattingApproach = 'normal' | 'aggressive' | 'patient' | 'power_swing' | 'contact' | 'situational'
export type BaserunningStrategy = 'conservative' | 'balanced' | 'aggressive'
export interface CareerV4Skill { score: number; rating_raw: number; rating_display: number; xp: number }
export interface CareerV4Stats { games: number; pa: number; hits: number; home_runs: number; walks: number; strikeouts: number; runs: number; rbi: number; stolen_bases: number; caught_stealing: number; avg: number; obp: number; slg: number; ops: number }
export interface CareerV4Day { weekday: number; is_game_day: boolean; opponent_id: string | null; is_home: boolean | null; planned_action: string | null }
export interface CareerActiveGame { inning: number; half: 'top' | 'bottom'; outs: number; bases: [boolean, boolean, boolean]; away_score: number; home_score: number; player_on_base: number | null; last_outcome: string | null; season_game_number: number }
export interface CareerView {
  career_id: string; revision: number; autosaved_at: string; persistence_version: string; schema_version: number; model_version: string
  migrated_from_schema: number | null; name: string; position: string; bats: string; throws: string; archetype: Archetype; age: number
  season_year: number; games_played: number; week: number; weekday: number; phase: string
  current_plan: Array<{ weekday: number; action: WeeklyAction }> | null; action_points_remaining: number
  fatigue: number; form: number; injured: boolean; coach_trust: number; team_status: string
  skills: Record<CareerSkillName, CareerV4Skill>; season_stats: CareerV4Stats; career_stats: CareerV4Stats
  completed_seasons: number; calendar_days: CareerV4Day[]; available_actions: string[]
  season_award: string | null; contract_summary: string | null
  active_game: CareerActiveGame | null
}

export function listCareers(): Promise<CareerView[]> { return request('/api/careers-v4') }
export function createCareer(input: { name: string; archetype: Archetype; bats: 'left' | 'right' | 'switch'; throws: 'left' | 'right'; position: string }): Promise<CareerView> {
  return request('/api/careers-v4', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({
    ...input, season_year: 2026, seed: Date.now() % 2147483647, team_id: 'career-player',
    opponent_ids: ['中信兄弟', '統一7-ELEVEn獅', '樂天桃猿', '味全龍', '台鋼雄鷹'],
    expected_revision: 0, operation_id: operationId(),
  }) })
}
export function planCareerWeek(career: CareerView, actions: Array<{ weekday: number; action: WeeklyAction }>): Promise<CareerView> {
  return request(`/api/careers-v4/${career.career_id}/plan-week`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ expected_revision: career.revision, operation_id: operationId(), actions }) })
}
export function mutateCareer(career: CareerView, action: 'advance-day' | 'play-game' | 'simulate-game' | 'acknowledge-game' | 'simulate-week' | 'simulate-season' | 'advance-phase'): Promise<CareerView> {
  return request(`/api/careers-v4/${career.career_id}/${action}`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ expected_revision: career.revision, operation_id: operationId() }) })
}
export function resolveCareerPA(career: CareerView, approach: BattingApproach, baserunning: BaserunningStrategy): Promise<CareerView> {
  return request(`/api/careers-v4/${career.career_id}/resolve-pa`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ expected_revision: career.revision, operation_id: operationId(), approach, baserunning }) })
}
