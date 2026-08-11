interface RatingMeterProps {
  label: string
  value: number
  tone: 'batter' | 'pitcher'
}

export function RatingMeter({ label, value, tone }: RatingMeterProps) {
  const width = `${Math.max(0, Math.min(100, ((value - 30) / 80) * 100))}%`
  return (
    <div className={`rating-meter ${tone}`}>
      <div className="rating-copy"><span>{label}</span><strong>{Math.round(value)}</strong></div>
      <div className="rating-track"><span style={{ width }} /></div>
    </div>
  )
}
