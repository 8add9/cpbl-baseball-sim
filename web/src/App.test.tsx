import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

import { App } from './App'

const fixture = {
  game_id: 'test', model_version: 'pa-hierarchical-v0.1',
  state: { inning: 1, half: 'top', outs: 0, bases: { first: null, second: null, third: null }, away_score: 0, home_score: 0, batting_team: 'away', batter: '客一', pitcher: '主投', plate_appearances: 0, finished: false, winner: null, seed: 42, away_lineup: ['客一','客二','客三','客四','客五','客六','客七','客八','客九'], home_lineup: ['主一','主二','主三','主四','主五','主六','主七','主八','主九'] },
  batter_ratings: { contact: 65, power: 65, eye: 65 },
  pitcher_ratings: { stuff: 65, control: 65, hr_suppression: 65 }, events: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(fixture) }))
})

test('renders the live game controls and matchup', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: '客一' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /下一打席/ })).toBeEnabled()
  expect(screen.getByText('主投')).toBeInTheDocument()
  expect(screen.queryByText('Fielding')).not.toBeInTheDocument()
})
