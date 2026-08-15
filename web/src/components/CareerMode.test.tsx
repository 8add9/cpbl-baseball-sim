import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { CareerMode } from './CareerMode'

const stats = { games: 4, pa: 16, hits: 4, home_runs: 1, walks: 2, strikeouts: 3, runs: 3, rbi: 4, stolen_bases: 2, caught_stealing: 1, avg: .286, obp: .375, slg: .571, ops: .946 }
const skill = { score: -.6, rating_raw: 60.21, rating_display: 60, xp: 2.5 }
const career = {
  career_id: '11111111-1111-4111-8111-111111111111', revision: 3, autosaved_at: '2026-08-15T00:00:00Z',
  persistence_version: 'career-sqlite-v4', schema_version: 4, model_version: 'batter-career-aggregate-v0.1',
  migrated_from_schema: null, name: '測試新秀', position: 'OF', bats: 'right', throws: 'right', archetype: 'balanced',
  age: 18, season_year: 2026, games_played: 4, week: 2, weekday: 1, phase: 'week_planning',
  current_plan: null, action_points_remaining: 4, fatigue: 21, form: .1, injured: false, coach_trust: 25,
  team_status: 'minor_bench', skills: { contact: skill, power: skill, eye: skill, speed_proxy: skill },
  season_stats: stats, career_stats: stats, completed_seasons: 0,
  calendar_days: [
    { weekday: 1, is_game_day: true, opponent_id: '中信兄弟', is_home: true, planned_action: null },
    { weekday: 2, is_game_day: false, opponent_id: null, is_home: null, planned_action: null },
    { weekday: 3, is_game_day: true, opponent_id: '味全龍', is_home: false, planned_action: null },
    { weekday: 4, is_game_day: false, opponent_id: null, is_home: null, planned_action: null },
    { weekday: 5, is_game_day: true, opponent_id: '台鋼雄鷹', is_home: true, planned_action: null },
    { weekday: 6, is_game_day: false, opponent_id: null, is_home: null, planned_action: null },
    { weekday: 7, is_game_day: true, opponent_id: '樂天桃猿', is_home: false, planned_action: null },
  ],
  available_actions: ['plan_week'], season_award: null, contract_summary: null, active_game: null,
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([career]) }))
})

test('renders the weekly career dashboard instead of next-PA grinding', async () => {
  render(<CareerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '測試新秀' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '第 2 週' })).toBeInTheDocument()
  expect(screen.getByText('SpeedProxy')).toBeInTheDocument()
  expect(screen.getByText('影響盜壘成功率與多進一個壘包')).toBeInTheDocument()
  expect(screen.queryByText('下一打席')).not.toBeInTheDocument()
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'contact_training' } })
  expect(screen.getByRole('button', { name: /2\/4 AP/ })).toBeEnabled()
})

test('creation exposes five archetypes and identity', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }))
  render(<CareerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '建立你的職棒生涯' })).toBeInTheDocument()
  expect(screen.getByLabelText('球員姓名')).toBeInTheDocument()
  expect(screen.getByLabelText('守備位置')).toBeInTheDocument()
  expect(screen.getByText('SpeedProxy 68')).toBeInTheDocument()
})

test('player PA screen exposes batting and baserunning decisions', async () => {
  const active = {
    ...career,
    phase: 'player_pa',
    active_game: {
      inning: 4, half: 'top', outs: 1, bases: [true, false, true],
      away_score: 2, home_score: 1, player_on_base: null,
      last_outcome: 'single', season_game_number: 5,
    },
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([active]) }))
  render(<CareerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '4 局上 · 1 出局' })).toBeInTheDocument()
  expect(screen.getByLabelText('跑壘策略')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /強力揮擊/ })).toBeInTheDocument()
  expect(screen.getByText('1B')).toHaveClass('occupied')
})
