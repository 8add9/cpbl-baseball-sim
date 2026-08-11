import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

import { CareerMode } from './CareerMode'

const stats = {
  games: 4, pa: 16, ab: 14, hits: 4, singles: 2, doubles: 1, triples: 0,
  home_runs: 1, walks: 2, hbp: 0, strikeouts: 3, total_bases: 8,
  avg: 4 / 14, obp: 6 / 16, slg: 8 / 14, ops: 6 / 16 + 8 / 14,
}
const skill = { score: -0.6, rating_raw: 60.21, rating_display: 60, potential_score: 5.5, next_cost: 1, can_train: false }
const career = {
  career_id: '11111111-1111-4111-8111-111111111111', revision: 3,
  autosaved_at: '2026-08-12T00:00:00Z', persistence_version: 'career-sqlite-v1',
  schema_version: 3, model_version: 'batter-career-v0.3', name: '測試新秀',
  position: 'OF', bats: 'right', throws: 'right', archetype: 'balanced', age: 18,
  season_year: 2026, games_played: 4, season_games: 120, experience: 16,
  development_points: 0, expired_development_points: 0,
  season_purchases: 0, retired: false, active_game: {
    season_year: 2026, game_number: 5, inning: 3, half: 'top', outs: 1,
    bases: ['career-1', null, 'away-3'], away_score: 2, home_score: 1,
    batting_team: 'away', batter: 'away-4', pitcher: 'home-pitcher',
    away_pitcher: 'away-pitcher', home_pitcher: 'home-pitcher', seed: 42,
    game_plate_appearances: 19, career_plate_appearances: 2,
    career_outcomes: ['1B', 'SO'],
    away_lineup: ['career-1', 'away-2', 'away-3', 'away-4', 'away-5', 'away-6', 'away-7', 'away-8', 'away-9'],
    home_lineup: ['home-1', 'home-2', 'home-3', 'home-4', 'home-5', 'home-6', 'home-7', 'home-8', 'home-9'],
  },
  skills: { contact: skill, power: skill, eye: skill, speed_proxy: skill },
  season_stats: stats, career_stats: stats, recent_results: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: () => Promise.resolve({ careers: [career] }),
  }))
})

test('renders persisted career progression without unsupported abilities', async () => {
  render(<CareerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '測試新秀' })).toBeInTheDocument()
  expect(screen.getByText('SpeedProxy')).toBeInTheDocument()
  expect(screen.getByText('跑壘代理，尚未影響 PA')).toBeInTheDocument()
  expect(screen.queryByText('Fielding')).not.toBeInTheDocument()
  expect(screen.queryByText('Arm')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /下一打席/ })).toBeEnabled()
  expect(screen.getByRole('button', { name: /下一重要事件/ })).toBeEnabled()
  expect(screen.getByText('等待跑壘模型')).toBeInTheDocument()
  expect(screen.getByLabelText('進行中比賽')).toHaveTextContent('3 局上')
  expect(screen.getByLabelText('進行中比賽')).toHaveTextContent('客 2：1 主')
})

test('creation exposes identity fields and numeric archetype previews', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: () => Promise.resolve({ careers: [] }),
  }))
  render(<CareerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '建立你的打者生涯' })).toBeInTheDocument()
  expect(screen.getByLabelText('守備位置')).toBeInTheDocument()
  expect(screen.getByLabelText('打擊慣用手')).toBeInTheDocument()
  expect(screen.getByLabelText('投球慣用手')).toBeInTheDocument()
  expect(screen.getByText('Contact 57 · Power 68 · Eye 57 · SpeedProxy 57')).toBeInTheDocument()
})
