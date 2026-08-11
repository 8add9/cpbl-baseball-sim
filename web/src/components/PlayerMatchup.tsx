import type { GameView } from '../api'
import { BaseDiamond } from './BaseDiamond'
import { RatingMeter } from './RatingMeter'

const BATTER_LABELS = [['contact', 'Contact'], ['power', 'Power'], ['eye', 'Eye']] as const
const PITCHER_LABELS = [['stuff', 'Stuff'], ['control', 'Control'], ['hr_suppression', 'HR Supp.']] as const

export function PlayerMatchup({ game }: { game: GameView }) {
  return (
    <section className="matchup-panel">
      <div className="player-side batter-side">
        <span className="side-label">打者</span>
        <h2>{game.state.batter}</h2>
        <div className="ratings">
          {BATTER_LABELS.map(([key, label]) => <RatingMeter key={key} label={label} value={game.batter_ratings[key] ?? 65} tone="batter" />)}
        </div>
      </div>
      <BaseDiamond bases={game.state.bases} />
      <div className="player-side pitcher-side">
        <span className="side-label">投手</span>
        <h2>{game.state.pitcher}</h2>
        <div className="ratings">
          {PITCHER_LABELS.map(([key, label]) => <RatingMeter key={key} label={label} value={game.pitcher_ratings[key] ?? 65} tone="pitcher" />)}
        </div>
      </div>
    </section>
  )
}
