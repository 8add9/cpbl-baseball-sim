import { useState } from 'react'
import { CareerMode } from './components/CareerMode'
import { GameControls } from './components/GameControls'
import { LineupTable } from './components/LineupTable'
import { ManagerMode } from './components/ManagerMode'
import { PlayerMatchup } from './components/PlayerMatchup'
import { PlayLog } from './components/PlayLog'
import { ScoreRail } from './components/ScoreRail'
import { useGame } from './useGame'

export function App() {
  const [mode, setMode] = useState<'game' | 'career' | 'manager'>('game')
  const { game, busy, error, act, reset, reconnect } = useGame()

  if (mode === 'career') {
    return <CareerMode onBack={() => setMode('game')} />
  }
  if (mode === 'manager') {
    return <ManagerMode onBack={() => setMode('game')} />
  }

  if (!game) {
    return (
      <main className="loading-state">
        <strong>{error ? '遊戲伺服器目前無法連線。' : '正在連線遊戲伺服器…'}</strong>
        {error ? <p>{error}</p> : null}
        {error ? <button onClick={reconnect}>重新連線</button> : null}
      </main>
    )
  }

  return (
    <main className="app-shell">
      <header className="game-header">
        <h1><span>CPBL</span> 數據野球</h1>
        <div className="header-actions">
          <button className="mode-link" onClick={() => setMode('career')}>生涯模式</button>
          <button className="mode-link manager-mode-link" onClick={() => setMode('manager')}>經理模式</button>
          <div className="model-meta"><span>模型 {game.model_version}</span><span>種子 {game.state.seed}</span></div>
          <button className="header-reset" disabled={busy} onClick={reset}>重新開始 <span>↻</span></button>
        </div>
      </header>
      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      <ScoreRail state={game.state} />
      <div className="game-grid">
        <div className="live-region">
          {game.state.finished ? <div className="final-banner">{game.state.winner === 'home' ? '主隊' : '客隊'}獲勝</div> : null}
          <PlayerMatchup game={game} />
          <GameControls busy={busy} finished={game.state.finished} act={act} />
        </div>
        <PlayLog events={game.events} />
      </div>
      <div className="lineup-band">
        <LineupTable title="客隊打線" players={game.state.away_lineup} current={game.state.batter} />
        <section className="game-summary">
          <h2>比賽摘要</h2>
          <div><span>客隊</span><strong>{game.state.away_score}</strong></div>
          <div><span>主隊</span><strong>{game.state.home_score}</strong></div>
          <p>{game.state.finished ? 'FINAL' : `${game.state.inning}局${game.state.half === 'top' ? '上' : '下'} · ${game.state.outs} OUT`}</p>
        </section>
        <LineupTable title="主隊打線" players={game.state.home_lineup} current={game.state.batter} />
      </div>
    </main>
  )
}
