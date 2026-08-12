import { useCallback, useEffect, useRef, useState } from 'react'

import { createGame, getGame, getHealth, type GameView, mutateGame, resetGame } from './api'

const DEFAULT_SEED = 20260811
const LAST_GAME_KEY = 'cpbl-baseball-sim:last-game-id:v1'

export function useGame() {
  const [game, setGame] = useState<GameView | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const initialized = useRef(false)

  const run = useCallback(async (operation: () => Promise<GameView>) => {
    setBusy(true)
    setError(null)
    try {
      const nextGame = await operation()
      setGame(nextGame)
      window.localStorage.setItem(LAST_GAME_KEY, nextGame.game_id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '無法連線到比賽伺服器')
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    void run(async () => {
      await getHealth()
      const savedGameId = window.localStorage.getItem(LAST_GAME_KEY)
      if (savedGameId) {
        try {
          return await getGame(savedGameId)
        } catch {
          window.localStorage.removeItem(LAST_GAME_KEY)
        }
      }
      return createGame(DEFAULT_SEED)
    })
  }, [run])

  const reconnect = useCallback(() => {
    void run(async () => {
      await getHealth()
      const savedGameId = window.localStorage.getItem(LAST_GAME_KEY)
      return savedGameId ? getGame(savedGameId) : createGame(DEFAULT_SEED)
    })
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

  return { game, busy, error, act, reset, reconnect }
}
