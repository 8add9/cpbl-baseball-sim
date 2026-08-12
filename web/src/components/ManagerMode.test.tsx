import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { ManagerMode } from './ManagerMode'

const batter = (index: number, position: string) => ({
  card_id: `b-${index}`, player_name: `打者 ${index}`, season_year: 2025,
  profile_position: position, position, role: null, tier: index === 1 ? 'SR' : 'N',
  cost: index === 1 ? 6 : 1, abilities: { Contact: 70, Power: 68, Eye: 66 },
})
const pitcher = (index: number, role: string) => ({
  card_id: `p-${index}`, player_name: `投手 ${index}`, season_year: 2024, team: '測試隊',
  profile_position: 'P', role, tier: 'N', cost: 1,
  abilities: { Stuff: 68, Control: 67, HRSuppression: 66, Stamina: 70 },
})
const positions = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH']
const lineup = positions.map((position, index) => batter(index + 1, position))
const team = {
  team_id: 'team-1', name: 'AI Team 1', strategy: 'balanced', games_played: 0,
  roster_cost: 42, batter_count: 13, rotation_count: 4, bullpen_count: 5,
  next_starter_card_id: 'p-1', lineup,
  bench: positions.slice(0, 4).map((position, index) => ({ ...batter(index + 10, position), team: '測試隊' })),
  rotation: [1, 2, 3, 4].map(index => pitcher(index, 'SP')),
  bullpen: [5, 6, 7, 8, 9].map(index => pitcher(index, index < 8 ? 'RP' : 'Swingman')),
  tier_counts: { N: 21, R: 0, SR: 1, SSR: 0 },
  available_bullpen_card_ids: ['p-5', 'p-6', 'p-7', 'p-8', 'p-9'],
}
const manager = {
  manager_id: '11111111-1111-4111-8111-111111111111', revision: 1,
  autosaved_at: '2026-08-12T00:00:00Z', persistence_version: 'manager-sqlite-v1',
  schema_version: 1, model_version: 'manager-league-v0.1',
  catalog_snapshot_version: 'rating-snapshot-v0.2:test', catalog_fingerprint: 'a'.repeat(64),
  seed: 42, games_completed: 0, total_games: 360, finished: false,
  next_game: { game_number: 1, round_number: 1, away_team_id: 'team-1', home_team_id: 'team-2' },
  standings: [1, 2, 3, 4, 5, 6].map(rank => ({
    rank, team_id: `team-${rank}`, wins: 0, losses: 0, runs_scored: 0,
    runs_allowed: 0, run_differential: 0, winning_percentage: 0, games_behind: 0,
  })),
  teams: [team, ...[2, 3, 4, 5, 6].map(index => ({ ...team, team_id: `team-${index}`, name: `AI Team ${index}` }))],
  recent_results: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: () => Promise.resolve({ managers: [manager] }),
  }))
})
afterEach(cleanup)

test('renders server-authoritative roster, standings, ratings, and three controls', async () => {
  render(<ManagerMode onBack={() => undefined} />)
  expect(await screen.findByRole('heading', { name: '先發打線' })).toBeInTheDocument()
  expect(screen.getByText('42')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /模擬下一場/ })).toBeEnabled()
  expect(screen.getByRole('button', { name: /模擬下一輪/ })).toBeEnabled()
  expect(screen.getByRole('button', { name: /模擬剩餘球季/ })).toBeEnabled()
  expect(screen.getByText('Contact')).toBeInTheDocument()
  expect(screen.queryByText('Overall')).not.toBeInTheDocument()
  expect(screen.queryByText('Fielding')).not.toBeInTheDocument()
  expect(screen.queryByText('Arm')).not.toBeInTheDocument()
})

test('mobile tabs expose standings and mutation sends current revision', async () => {
  render(<ManagerMode onBack={() => undefined} />)
  await screen.findByRole('heading', { name: '先發打線' })
  fireEvent.click(screen.getByRole('button', { name: '戰績' }))
  expect(screen.getByRole('heading', { name: '聯盟戰績' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /模擬下一場/ }))
  expect(fetch).toHaveBeenLastCalledWith(
    `/api/managers/${manager.manager_id}/simulate-next-game`,
    expect.objectContaining({ method: 'POST' }),
  )
})

test('preseason roster builder surfaces server-side star limit rejection', async () => {
  const star = {
    ...batter(99, 'C'), team: '測試隊', player_name: '明星捕手', tier: 'SSR', cost: 10,
  }
  vi.mocked(fetch)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ managers: [manager] }) } as Response)
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ candidates: [star] }) } as Response)
    .mockResolvedValueOnce({
      ok: false,
      text: () => Promise.resolve(JSON.stringify({ code: 'manager_invalid', message: 'SSR count 3 exceeds cap 2' })),
    } as Response)
  render(<ManagerMode onBack={() => undefined} />)
  await screen.findByRole('heading', { name: '先發打線' })
  fireEvent.click(screen.getByRole('button', { name: '替換此卡' }))
  expect(await screen.findByText('明星捕手')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /明星捕手/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('SSR count 3 exceeds cap 2')
})
