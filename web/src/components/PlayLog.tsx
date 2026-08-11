import type { GameEvent } from '../api'

export function PlayLog({ events }: { events: GameEvent[] }) {
  return (
    <aside className="play-log">
      <div className="section-heading"><h2>攻防紀錄</h2><span>{events.length} PA</span></div>
      <ol aria-live="polite">
        {[...events].reverse().map((event) => (
          <li key={event.sequence}>
            <span className="log-inning">{event.inning}{event.half === 'top' ? '上' : '下'}</span>
            <span className={`outcome outcome-${event.outcome.toLowerCase()}`}>{event.outcome}</span>
            <p>{event.description}</p>
          </li>
        ))}
      </ol>
      {events.length === 0 ? <p className="empty-log">按下「下一打席」開始比賽。</p> : null}
    </aside>
  )
}
