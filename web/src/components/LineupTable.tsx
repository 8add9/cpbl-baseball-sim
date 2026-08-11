export function LineupTable({ title, players, current }: { title: string; players: string[]; current: string }) {
  return (
    <section className="lineup-table">
      <h2>{title}</h2>
      <ol>
        {players.map((player, index) => <li className={player === current ? 'current' : ''} key={player}><span>{index + 1}</span><strong>{player}</strong></li>)}
      </ol>
    </section>
  )
}
