import { FormEvent, useEffect, useState } from 'react'
import {
  Archetype, CareerSkillName, CareerView, createCareer, listCareers, mutateCareer,
} from '../api'

const SKILLS: Array<[CareerSkillName, string]> = [
  ['contact', 'Contact'], ['power', 'Power'], ['eye', 'Eye'], ['speed_proxy', 'SpeedProxy'],
]
const ARCHETYPES: Array<[Archetype, string, string]> = [
  ['contact', '巧打者', '優先發展接觸能力'], ['power', '強打者', '優先發展長打能力'],
  ['patient', '選球型', '優先發展保送能力'], ['speed', '速度型', '優先發展速度潛力'],
  ['balanced', '均衡型', '四項能力平均起步'],
]
const ARCHETYPE_PREVIEW: Record<Archetype, string> = {
  contact: 'Contact 66 · Power 55 · Eye 58 · SpeedProxy 60',
  power: 'Contact 57 · Power 68 · Eye 57 · SpeedProxy 57',
  patient: 'Contact 58 · Power 56 · Eye 67 · SpeedProxy 58',
  speed: 'Contact 58 · Power 56 · Eye 57 · SpeedProxy 68',
  balanced: 'Contact 60 · Power 60 · Eye 60 · SpeedProxy 60',
}

function fmt(value: number) { return value.toFixed(3).replace(/^0/, '') }

function Stats({ title, stats }: { title: string; stats: CareerView['season_stats'] }) {
  const counts = [['PA', stats.pa], ['H', stats.hits], ['HR', stats.home_runs],
    ['BB', stats.walks], ['SO', stats.strikeouts]] as const
  return <section className="career-card stats-card"><h2>{title}</h2>
    <div className="counting-grid">{counts.map(([label, value]) =>
      <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
    <div className="slash-line">
      <div><span>AVG</span><strong>{fmt(stats.avg)}</strong></div>
      <div><span>OBP</span><strong>{fmt(stats.obp)}</strong></div>
      <div><span>SLG</span><strong>{fmt(stats.slg)}</strong></div>
      <div><span>OPS</span><strong>{fmt(stats.ops)}</strong></div>
    </div><p className="fine-print">v0.1 簡化打數：目前打席模型尚未拆分犧牲打。</p></section>
}

function CareerCreate({ onCreated }: { onCreated: (career: CareerView) => void }) {
  const [name, setName] = useState('自創球員')
  const [archetype, setArchetype] = useState<Archetype>('balanced')
  const [position, setPosition] = useState('OF')
  const [bats, setBats] = useState<'left' | 'right' | 'switch'>('right')
  const [throws, setThrows] = useState<'left' | 'right'>('right')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { onCreated(await createCareer({ name, archetype, bats, throws, position })) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '建立失敗') }
    finally { setBusy(false) }
  }
  return <form className="career-create" onSubmit={submit}>
    <div><p className="eyebrow">CAREER 1-1</p><h1>建立你的打者生涯</h1>
      <p>四種模板的起始 Composite Score 總和完全相同；差異只在發展方向。</p></div>
    <label>球員姓名<input value={name} maxLength={60} onChange={event => setName(event.target.value)} /></label>
    <fieldset><legend>打者類型</legend><div className="archetype-grid">{ARCHETYPES.map(([value, label, detail]) =>
      <label className={archetype === value ? 'selected' : ''} key={value}>
        <input type="radio" name="archetype" checked={archetype === value} onChange={() => setArchetype(value)} />
        <strong>{label}</strong><span>{detail}</span><small>{ARCHETYPE_PREVIEW[value]}</small></label>)}</div></fieldset>
    <div className="identity-grid"><label>守備位置<select value={position} onChange={event => setPosition(event.target.value)}>
      <option value="C">C</option><option value="IF">IF</option><option value="OF">OF</option><option value="DH">DH</option>
    </select></label><label>打擊慣用手<select value={bats} onChange={event => setBats(event.target.value as typeof bats)}>
      <option value="right">右打</option><option value="left">左打</option><option value="switch">左右開弓</option>
    </select></label><label>投球慣用手<select value={throws} onChange={event => setThrows(event.target.value as typeof throws)}>
      <option value="right">右投</option><option value="left">左投</option></select></label></div>
    {error ? <p className="career-error" role="alert">{error}</p> : null}
    <button className="career-primary" disabled={busy || !name.trim()}>{busy ? '建立中…' : '開始生涯'}</button>
  </form>
}

export function CareerMode({ onBack }: { onBack: () => void }) {
  const [careers, setCareers] = useState<CareerView[]>([])
  const [career, setCareer] = useState<CareerView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const acceptCareer = (next: CareerView) => {
    setCareer(next)
    setCareers(current => [next, ...current.filter(item => item.career_id !== next.career_id)])
  }
  useEffect(() => { listCareers().then(items => { setCareers(items); setCareer(items[0] ?? null) }).catch(() => {}) }, [])
  async function act(action: 'next-pa' | 'simulate-game' | 'simulate-week' | 'simulate-to-next-event', extra = {}) {
    if (!career) return; setBusy(true); setError('')
    try { acceptCareer(await mutateCareer(career, action, extra)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '操作失敗') }
    finally { setBusy(false) }
  }
  async function train(skill: CareerSkillName) {
    if (!career) return; setBusy(true); setError('')
    try { acceptCareer(await mutateCareer(career, 'train', { skill, purchases: 1 })) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '訓練失敗') }
    finally { setBusy(false) }
  }
  if (!career) return <main className="career-shell"><header className="career-topbar"><button onClick={onBack}>← 文字賽事</button><strong>CPBL 生涯模式</strong></header><CareerCreate onCreated={acceptCareer} /></main>
  const progress = Math.round(career.games_played / career.season_games * 100)
  return <main className="career-shell"><header className="career-topbar"><button onClick={onBack}>← 文字賽事</button>
    <strong><span>CPBL</span> 生涯模式</strong><div className="save-state">● 已自動儲存 · rev {career.revision}</div></header>
    {error ? <div className="error-banner" role="alert">{error}</div> : null}
    <div className="career-layout">
      <aside className="career-card player-profile"><p className="eyebrow">CREATED BATTER</p><h1>{career.name}</h1>
        <div className="age-tile"><strong>{career.age}</strong><span>歲</span></div><dl>
          <div><dt>打者類型</dt><dd>{ARCHETYPES.find(item => item[0] === career.archetype)?.[1]}</dd></div>
          <div><dt>守備位置</dt><dd>{career.position}</dd></div><div><dt>目前球季</dt><dd>{career.season_year}</dd></div>
          <div><dt>生涯狀態</dt><dd>{career.retired ? '已退休' : '現役'}</dd></div></dl>
        <button className="new-career" onClick={() => setCareer(null)}>＋ 建立新生涯</button>
        {careers.length > 1 ? <select aria-label="切換存檔" value={career.career_id}
          onChange={event => setCareer(careers.find(item => item.career_id === event.target.value) ?? career)}>
          {careers.map(item => <option value={item.career_id} key={item.career_id}>{item.name}</option>)}</select> : null}</aside>
      <section className="career-card development-card"><div className="development-heading"><div><p className="eyebrow">PLAYER DEVELOPMENT</p><h2>能力發展</h2></div>
        <div className="dp-bank"><span>可用發展點數</span><strong>{career.development_points}</strong></div></div>
        {SKILLS.map(([key, label]) => { const item = career.skills[key]; const width = Math.max(0, Math.min(100, (item.rating_raw - 30) / 80 * 100)); return <div className="career-skill" key={key}>
          <div><span>{label}</span>{key === 'speed_proxy' ? <small>跑壘代理，尚未影響 PA</small> : null}</div><strong>{item.rating_display}</strong>
          <div className="career-meter"><i style={{ width: `${width}%` }} /></div><span className="score-copy">Score {item.score.toFixed(2)}</span>
          <button disabled={busy || !item.can_train} onClick={() => train(key)}>{key === 'speed_proxy' ? '唯讀' : '+0.1'} <small>{key === 'speed_proxy' ? '等待跑壘模型' : item.next_cost == null ? '上限' : `${item.next_cost} DP`}</small></button></div> })}</section>
      <Stats title="本季成績" stats={career.season_stats} />
      <section className="career-card season-progress"><div><p className="eyebrow">SEASON PROGRESS</p><h2>{career.season_year} 球季</h2></div>
        <strong>{career.games_played} / {career.season_games} 場</strong><div className="progress-track"><i style={{ width: `${progress}%` }} /></div><span>{progress}%</span>
        {career.active_game ? <div className="active-game" aria-label="進行中比賽">
          <strong>第 {career.active_game.game_number} 場 · {career.active_game.inning} 局{career.active_game.half === 'top' ? '上' : '下'}</strong>
          <span>客 {career.active_game.away_score}：{career.active_game.home_score} 主 · {career.active_game.outs} 出局</span>
          <span>壘包 {career.active_game.bases.map((runner, index) => runner ? `${index + 1}B` : '—').join(' / ')}</span>
          <small>你的打席 {career.active_game.career_plate_appearances} · {career.active_game.career_outcomes.join(' / ') || '等待首打席'}</small>
        </div> : null}
        <div className="career-controls"><button disabled={busy || career.retired || career.games_played === career.season_games} onClick={() => act('next-pa', { plate_appearances: 4 })}>● 下一打席</button>
          <button disabled={busy || career.retired || career.games_played === career.season_games} onClick={() => act('simulate-game', { plate_appearances: 4 })}>▶ 快速完成本場</button>
          <button disabled={busy || career.retired || career.games_played === career.season_games} onClick={() => act('simulate-week', { games: Math.min(6, career.season_games - career.games_played), plate_appearances: 4 })}>▶▶ 一週（最多6場）</button>
          <button className="career-primary" disabled={busy || career.retired} onClick={() => act('simulate-to-next-event', { plate_appearances: 4 })}>⏭ 下一重要事件</button></div></section>
      <Stats title="生涯累積" stats={career.career_stats} />
      <section className="career-card recent-results"><h2>近期比賽</h2>{career.recent_results.length ? career.recent_results.slice().reverse().map(result =>
        <div key={`${result.season_year}-${result.game_number}`}><span>G{result.game_number}</span><strong>{result.hits} H · {result.home_runs} HR · {result.walks} BB</strong><small>{result.outcomes.join(' / ')}</small></div>) : <p>尚無比賽紀錄</p>}</section>
    </div></main>
}
