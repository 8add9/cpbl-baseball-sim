import { useCallback, useEffect, useRef, useState } from 'react'

import { createGame, type GameView, mutateGame, resetGame } from './api'

const DEFAULT_SEED = 20260811

export function useGame() {
  const [game, setGame] = useState<GameView | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const initialized = useRef(false)

  const run = useCallback(async (operation: () => Promise<GameView>) => {
    setBusy(true)
    setError(null)
    try {
      setGame(await operation())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '無法連線到比賽伺服器')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    void run(() => createGame(DEFAULT_SEED))
  }, [run])

  const act = useCallback(
    (action: 'next-pa' | 'simulate-half' | 'simulate-full') => {
      if (game) void run(() => mutateGame(game.game_id, action))
    },
    [game, run],
  )

  const reset = useCallback(() => {
    if (game) void run(() => resetGame(game.game_id, game.state.seed))
  }, [game, run])

  return { game, busy, error, act, reset }
}
