interface BaseDiamondProps {
  bases: { first: string | null; second: string | null; third: string | null }
}

export function BaseDiamond({ bases }: BaseDiamondProps) {
  return (
    <div className="diamond" aria-label="壘包狀態">
      <div className={`base base-second ${bases.second ? 'occupied' : ''}`} title={bases.second ?? '二壘'} />
      <div className={`base base-third ${bases.third ? 'occupied' : ''}`} title={bases.third ?? '三壘'} />
      <div className={`base base-first ${bases.first ? 'occupied' : ''}`} title={bases.first ?? '一壘'} />
      <div className="home-plate" />
      <span className="diamond-label">{Object.values(bases).filter(Boolean).length ? `跑者 ${Object.values(bases).filter(Boolean).length} 人` : '壘上無人'}</span>
    </div>
  )
}
