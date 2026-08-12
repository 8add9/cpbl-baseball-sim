import { JSON_HEADERS, request } from './client'

export type Half = 'top' | 'bottom'
export type Team = 'away' | 'home'

export interface RatingSet { [key: string]: number }

export interface GameEvent {
  sequence: number; inning: number; half: Half; outcome: string
  batter: string; pitcher: string; runs_scored: number; description: string
}

export interface GameStateView {
  inning: number; half: Half; outs: number
  bases: { first: string | null; second: string | null; third: string | null }
  away_score: number; home_score: number; batting_team: Team
  batter: string; pitcher: string; plate_appearances: number
  finished: boolean; winner: Team | null; seed: number
  away_lineup: string[]; home_lineup: string[]
}

export interface GameView {
  game_id: string; model_version: string; state: GameStateView
  batter_ratings: RatingSet; pitcher_ratings: RatingSet; events: GameEvent[]
}

export function createGame(seed: number): Promise<GameView> {
  return request('/api/games', {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ seed }),
  })
}

export function getGame(gameId: string): Promise<GameView> {
  return request(`/api/games/${encodeURIComponent(gameId)}`)
}

export function mutateGame(gameId: string, action: 'next-pa' | 'simulate-half' | 'simulate-full') {
  return request<GameView>(`/api/games/${encodeURIComponent(gameId)}/${action}`, { method: 'POST' })
}

export function resetGame(gameId: string, seed: number): Promise<GameView> {
  return request(`/api/games/${encodeURIComponent(gameId)}/reset`, {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ seed }),
  })
}
