import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

import { App } from './App'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ managers: [] }) }))
})

test('opens directly in manager mode without the standalone text game', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: '建立你的六隊聯盟' })).toBeInTheDocument()
  expect(screen.getByText(/經理模式/)).toBeInTheDocument()
  expect(screen.queryByText('下一打席')).not.toBeInTheDocument()
})
