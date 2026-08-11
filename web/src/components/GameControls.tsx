interface ControlsProps {
  busy: boolean
  finished: boolean
  act: (action: 'next-pa' | 'simulate-half' | 'simulate-full') => void
}

export function GameControls({ busy, finished, act }: ControlsProps) {
  return (
    <div className="game-controls" aria-label="比賽控制">
      <button className="primary" disabled={busy || finished} onClick={() => act('next-pa')}>下一打席 <span>›</span></button>
      <button disabled={busy || finished} onClick={() => act('simulate-half')}>模擬半局 <span>»</span></button>
      <button disabled={busy || finished} onClick={() => act('simulate-full')}>模擬全場 <span>»</span></button>
    </div>
  )
}
