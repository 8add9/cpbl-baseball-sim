import type { GameStateView } from '../api'

export function ScoreRail({ state }: { state: GameStateView }) {
  const half = state.half === 'top' ? '上' : '下'
  return (
    <section className="score-rail" aria-label="比賽比分">
      <div className="team-score away"><span>客隊</span><strong>{state.away_score}</strong></div>
      <div className="inning-state">
        <strong>{state.finished ? '比賽結束' : `${state.inning} 局${half}`}</strong>
        <span>{state.outs} OUT · 第 {state.plate_appearances + 1} 打席</span>
      </div>
      <div className="team-score home"><strong>{state.home_score}</strong><span>主隊</span></div>
    </section>
  )
}
