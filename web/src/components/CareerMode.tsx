import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Archetype, CareerSkillName, CareerView, createCareer, listCareers, mutateCareer, planCareerWeek, WeeklyAction } from '../api'

const SKILLS: Array<[CareerSkillName, string]> = [['contact', 'Contact'], ['power', 'Power'], ['eye', 'Eye'], ['speed_proxy', 'SpeedProxy']]
const ARCHETYPES: Array<[Archetype, string, string]> = [
  ['contact', '巧打者', 'Contact 66 · Power 55'], ['power', '強打者', 'Power 68 · Contact 57'],
  ['patient', '選球型', 'Eye 67 · Contact 58'], ['speed', '速度型', 'SpeedProxy 68'], ['balanced', '均衡型', '四項能力皆 60'],
]
const ACTIONS: Array<[WeeklyAction, string, number]> = [
  ['contact_training', 'Contact 訓練', 2], ['power_training', 'Power 訓練', 2], ['eye_training', 'Eye 訓練', 2],
  ['speed_training', '速度訓練', 1], ['recovery', '恢復', 1], ['video_study', '影片研究', 1], ['extra_batting_practice', '額外打擊', 1],
]
const DAYS = ['一', '二', '三', '四', '五', '六', '日']
const PHASES: Record<string, string> = { week_planning: '安排本週', day_ready: '球季進行中', season_review: '球季總結', awards: '年度獎項', contract: '合約談判', offseason_training: '休季訓練', ready_next_season: '準備下一季', retired: '已退休' }
function fmt(value: number) { return value.toFixed(3).replace(/^0/, '') }
function Stats({ title, stats }: { title: string; stats: CareerView['season_stats'] }) {
  return <section className="career-card stats-card"><h2>{title}</h2><div className="counting-grid">
    {[['G', stats.games], ['PA', stats.pa], ['H', stats.hits], ['HR', stats.home_runs], ['BB', stats.walks], ['SO', stats.strikeouts]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
  </div><div className="slash-line">{[['AVG', stats.avg], ['OBP', stats.obp], ['SLG', stats.slg], ['OPS', stats.ops]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{fmt(Number(value))}</strong></div>)}</div></section>
}

function CareerCreate({ onCreated }: { onCreated: (career: CareerView) => void }) {
  const [name, setName] = useState('自創球員'); const [archetype, setArchetype] = useState<Archetype>('balanced')
  const [position, setPosition] = useState('OF'); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { onCreated(await createCareer({ name, archetype, position, bats: 'right', throws: 'right' })) } catch (reason) { setError(reason instanceof Error ? reason.message : '建立失敗') } finally { setBusy(false) } }
  return <form className="career-create" onSubmit={submit}><div><p className="eyebrow">CAREER MODE</p><h1>建立你的職棒生涯</h1><p>安排每週訓練、控制疲勞，走完球季、獎項、合約與休季。</p></div>
    <label>球員姓名<input value={name} maxLength={60} onChange={event => setName(event.target.value)} /></label>
    <fieldset><legend>打者類型</legend><div className="archetype-grid">{ARCHETYPES.map(([value, label, preview]) => <label className={archetype === value ? 'selected' : ''} key={value}><input type="radio" checked={archetype === value} onChange={() => setArchetype(value)} /><strong>{label}</strong><small>{preview}</small></label>)}</div></fieldset>
    <label>守備位置<select value={position} onChange={event => setPosition(event.target.value)}><option>C</option><option>IF</option><option>OF</option><option>DH</option></select></label>
    {error ? <p className="career-error">{error}</p> : null}<button className="career-primary" disabled={busy || !name.trim()}>{busy ? '建立中…' : '開始生涯'}</button></form>
}

export function CareerMode({ onBack }: { onBack: () => void }) {
  const [careers, setCareers] = useState<CareerView[]>([]); const [career, setCareer] = useState<CareerView | null>(null)
  const [plans, setPlans] = useState<Record<number, WeeklyAction | ''>>({}); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState('')
  const accept = (next: CareerView) => { setCareer(next); setCareers(current => [next, ...current.filter(item => item.career_id !== next.career_id)]); setPlans({}) }
  useEffect(() => { listCareers().then(items => { setCareers(items); setCareer(items[0] ?? null) }).catch(reason => setError(reason instanceof Error ? reason.message : '載入失敗')).finally(() => setLoading(false)) }, [])
  const usedAp = useMemo(() => Object.values(plans).reduce((sum, action) => sum + (ACTIONS.find(item => item[0] === action)?.[2] ?? 0), 0), [plans])
  async function command(run: () => Promise<CareerView>) { setBusy(true); setError(''); try { accept(await run()) } catch (reason) { setError(reason instanceof Error ? reason.message : '操作失敗') } finally { setBusy(false) } }
  async function submitPlan() { if (!career) return; const actions = Object.entries(plans).filter(([, action]) => action).map(([weekday, action]) => ({ weekday: Number(weekday), action: action as WeeklyAction })); await command(() => planCareerWeek(career, actions)) }
  if (loading) return <main className="career-shell"><div className="manager-empty">載入生涯模式…</div></main>
  if (!career) return <main className="career-shell"><header className="career-topbar"><button onClick={onBack}>← 經理模式</button><strong>CPBL 生涯模式</strong></header><CareerCreate onCreated={accept} /></main>
  const boundary = ['season_review', 'awards', 'contract', 'offseason_training', 'ready_next_season'].includes(career.phase)
  return <main className="career-shell"><header className="career-topbar"><button onClick={onBack}>← 經理模式</button><strong><span>CPBL</span> 生涯模式</strong><div className="save-state">● 已自動儲存 · rev {career.revision}</div></header>
    {error ? <div className="error-banner" role="alert">{error}</div> : null}
    <section className="career-v4-hero"><div><p className="eyebrow">{PHASES[career.phase] ?? career.phase}</p><h1>{career.name}</h1><span>{career.age} 歲 · {career.position} · {career.season_year} · 第 {career.completed_seasons + 1} 季</span></div><div><span>教練信任</span><strong>{Math.round(career.coach_trust)}</strong><small>{career.team_status}</small></div><div><span>疲勞</span><strong>{Math.round(career.fatigue)}</strong><small>狀態 {career.form.toFixed(2)}</small></div><button onClick={() => setCareer(null)}>＋ 新生涯</button></section>
    {careers.length > 1 ? <select className="career-save-picker" value={career.career_id} onChange={event => setCareer(careers.find(item => item.career_id === event.target.value) ?? career)}>{careers.map(item => <option value={item.career_id} key={item.career_id}>{item.name} · {item.season_year}</option>)}</select> : null}
    <div className="career-layout">
      <section className="career-card development-card"><div className="development-heading"><div><p className="eyebrow">PLAYER DEVELOPMENT</p><h2>能力與訓練 XP</h2></div><strong>AP {career.action_points_remaining}</strong></div>{SKILLS.map(([key, label]) => { const item = career.skills[key]; return <div className="career-skill" key={key}><div><span>{label}</span>{key === 'speed_proxy' ? <small>跑壘代理，暫不影響 PA</small> : null}</div><strong>{item.rating_display}</strong><div className="career-meter"><i style={{ width: `${Math.max(0, Math.min(100, (item.rating_raw - 30) / 80 * 100))}%` }} /></div><span className="score-copy">Score {item.score.toFixed(2)} · XP {item.xp.toFixed(1)}</span></div>})}</section>
      <section className="career-card season-progress"><div><p className="eyebrow">WEEKLY CALENDAR</p><h2>第 {career.week} 週</h2></div><strong>{career.games_played} / 120 場</strong><div className="career-week-grid">{career.calendar_days.map(day => <label className={day.is_game_day ? 'game-day' : ''} key={day.weekday}><strong>週{DAYS[day.weekday - 1]}</strong>{day.is_game_day ? <span>{day.is_home ? '主場' : '客場'} vs {day.opponent_id}</span> : career.phase === 'week_planning' ? <select value={plans[day.weekday] ?? ''} onChange={event => setPlans(current => ({ ...current, [day.weekday]: event.target.value as WeeklyAction | '' }))}><option value="">休息</option>{ACTIONS.map(([value, label, cost]) => <option value={value} key={value}>{label} ({cost} AP)</option>)}</select> : <span>{day.planned_action ?? '休息'}</span>}</label>)}</div>
        {career.phase === 'week_planning' ? <div className="career-controls"><button className="career-primary" disabled={busy || usedAp > 4} onClick={submitPlan}>確認本週安排（{usedAp}/4 AP）</button></div> : null}
        {career.phase === 'day_ready' ? <div className="career-controls"><button disabled={busy} onClick={() => command(() => mutateCareer(career, 'advance-day'))}>進行今天</button><button className="career-primary" disabled={busy} onClick={() => command(() => mutateCareer(career, 'simulate-week'))}>模擬本週</button><button disabled={busy} onClick={() => command(() => mutateCareer(career, 'simulate-season'))}>模擬剩餘球季</button></div> : null}
      </section>
      <Stats title="本季成績" stats={career.season_stats} /><Stats title="生涯累積" stats={career.career_stats} />
      {boundary ? <section className="career-card career-offseason"><p className="eyebrow">SEASON LIFECYCLE</p><h2>{PHASES[career.phase]}</h2>{career.phase === 'season_review' ? <p>本季 OPS {fmt(career.season_stats.ops)} · {career.season_award}</p> : null}{career.phase === 'awards' ? <p>年度評價：{career.season_award}</p> : null}{career.phase === 'contract' ? <p>球團提出：{career.contract_summary}</p> : null}{career.phase === 'offseason_training' ? <p>完成休季調整後才能進入下一季。</p> : null}{career.phase === 'ready_next_season' ? <p>新球季日曆與本季成績將重設，生涯累積保留。</p> : null}<button className="career-primary" disabled={busy} onClick={() => command(() => mutateCareer(career, 'advance-phase'))}>{career.phase === 'ready_next_season' ? '進入下一個賽季' : '繼續'}</button></section> : null}
    </div></main>
}
