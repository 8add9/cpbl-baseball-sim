import { useEffect, useMemo, useState } from 'react'
import {
  createManager, listManagerRosterCandidates, listManagers, ManagerCard,
  ManagerLineupCard, ManagerTeam, ManagerView, mutateManager, renameManagerTeam,
  replaceManagerCard, updateManagerLineup, updateManagerRotation,
} from '../api'

type ManagerAction = 'simulate-next-game' | 'simulate-round' | 'simulate-season' | 'advance-season'
type ManagerTab = 'roster' | 'catalog' | 'standings' | 'team-stats' | 'league-stats'

const TABS: Array<[ManagerTab, string]> = [
  ['roster', '陣容'], ['catalog', '球員目錄'], ['standings', '戰績'],
  ['team-stats', '球隊球員數據'], ['league-stats', '聯盟球員數據'],
]

function formatPct(value: number) {
  return value.toFixed(3).replace(/^0/, '')
}

function CardRatings({ card }: { card: ManagerCard | ManagerLineupCard }) {
  return <div className="manager-ratings">
    {Object.entries(card.abilities).map(([ability, value]) => <div key={ability}>
      <span>{ability}</span><strong>{Math.round(value)}</strong>
      <i><b style={{ width: `${Math.max(0, Math.min(100, (value - 30) / 80 * 100))}%` }} /></i>
    </div>)}
  </div>
}

function RosterTable({ team, onSelect, onMove, disabled }: {
  team: ManagerTeam; onSelect: (card: ManagerLineupCard) => void
  onMove: (index: number, delta: number) => void; disabled: boolean
}) {
  return <section className="manager-panel manager-lineup">
    <div className="manager-section-title"><h2>先發打線</h2><span>9 人</span></div>
    <div className="manager-table manager-lineup-table" role="table">
      <div className="manager-table-head" role="row">
        <span>#</span><span>位置</span><span>球員</span><span>年度</span><span>級別</span><span>排序</span>
      </div>
      {team.lineup.map((card, index) => <button role="row" key={card.card_id} onClick={() => onSelect(card)}>
        <span>{index + 1}</span><strong>{card.position}</strong><span>{card.player_name}</span>
        <span>{card.season_year}</span><em data-tier={card.tier}>{card.tier}</em>
        <span className="manager-order-buttons">
          <i role="button" aria-label={`上移 ${card.player_name}`} onClick={event => { event.stopPropagation(); onMove(index, -1) }} aria-disabled={disabled || index === 0}>↑</i>
          <i role="button" aria-label={`下移 ${card.player_name}`} onClick={event => { event.stopPropagation(); onMove(index, 1) }} aria-disabled={disabled || index === team.lineup.length - 1}>↓</i>
        </span>
      </button>)}
    </div>
  </section>
}

function CompactRoster({ title, cards, nextStarter, available }: {
  title: string; cards: ManagerCard[]; nextStarter?: string; available?: Set<string>
}) {
  return <section className="manager-roster-group">
    <div className="manager-section-title"><h3>{title}</h3><span>{cards.length} 人</span></div>
    {cards.map(card => <div className="manager-roster-row" key={card.card_id}>
      <span>{card.role ?? card.profile_position}</span>
      <strong>{card.player_name}</strong><span>{card.season_year}</span>
      <em data-tier={card.tier}>{card.tier}</em><span>{card.cost}</span>
      {nextStarter === card.card_id ? <small>下一場</small> : null}
      {available && !available.has(card.card_id) ? <small className="unavailable">休息</small> : null}
    </div>)}
  </section>
}

function Standings({ manager }: { manager: ManagerView }) {
  const names = Object.fromEntries(manager.teams.map(team => [team.team_id, team.name]))
  return <section className="manager-panel manager-standings">
    <div className="manager-section-title"><h2>聯盟戰績</h2><span>{manager.games_completed} / {manager.total_games}</span></div>
    <div className="manager-table" role="table">
      <div className="manager-table-head standings-row" role="row">
        <span>#</span><span>球隊</span><span>W</span><span>L</span><span>PCT</span><span>GB</span>
      </div>
      {manager.standings.map(row => <div className="standings-row" role="row" key={row.team_id}>
        <strong>{row.rank}</strong><span>{names[row.team_id] ?? row.team_id}</span><span>{row.wins}</span><span>{row.losses}</span>
        <span>{formatPct(row.winning_percentage)}</span><span>{row.games_behind || '—'}</span>
      </div>)}
    </div>
  </section>
}

function PlayerStats({ manager, scope }: { manager: ManagerView; scope: 'team' | 'league' }) {
  const stats = scope === 'team'
    ? manager.player_stats.filter(item => item.team_id === manager.user_team_id)
    : manager.player_stats
  return <section className="manager-panel manager-player-stats">
    <div className="manager-section-title"><h2>{manager.season_year} {scope === 'team' ? '球隊球員數據' : '聯盟球員數據'}</h2><span>{stats.length} 筆</span></div>
    <div className="manager-stats-scroll">
      {stats.length === 0 ? <p>尚無本季出賽數據</p> : stats.map(item => <div key={`${item.team_id}:${item.card_id}`}>
        <strong>{item.player_name} <small>{item.card_season_year}</small></strong>
        <small>{scope === 'league' ? `${item.team_name} · ` : ''}{item.kind === 'batter' ? '打者' : '投手'}</small>
        <span>{Object.entries(item.values).map(([key, value]) => `${key} ${typeof value === 'number' && !Number.isInteger(value) ? value.toFixed(3) : value}`).join(' · ')}</span>
      </div>)}
    </div>
  </section>
}

export function ManagerMode({ onBack }: { onBack: () => void }) {
  const [saves, setSaves] = useState<ManagerView[]>([])
  const [manager, setManager] = useState<ManagerView | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState('')
  const [selectedCard, setSelectedCard] = useState<ManagerCard | ManagerLineupCard | null>(null)
  const [swapTarget, setSwapTarget] = useState<ManagerCard | ManagerLineupCard | null>(null)
  const [swapCandidates, setSwapCandidates] = useState<ManagerCard[]>([])
  const [tab, setTab] = useState<ManagerTab>('roster')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [teamName, setTeamName] = useState('')

  const accept = (next: ManagerView) => {
    setManager(next)
    setSelectedCard(null)
    setSwapTarget(null)
    setSwapCandidates([])
    setSaves(current => [next, ...current.filter(item => item.manager_id !== next.manager_id)])
    setSelectedTeamId(current => current && next.teams.some(team => team.team_id === current)
      ? current : next.teams[0]?.team_id ?? '')
  }

  useEffect(() => {
    let active = true
    listManagers().then(items => {
      if (!active) return
      setSaves(items)
      if (items[0]) accept(items[0])
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : '無法載入經理存檔')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const team = useMemo(
    () => manager?.teams.find(item => item.team_id === selectedTeamId) ?? manager?.teams[0] ?? null,
    [manager, selectedTeamId],
  )
  useEffect(() => { setTeamName(team?.name ?? '') }, [team?.name])
  async function createLeague() {
    setBusy(true); setError('')
    try { accept(await createManager()) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '建立聯盟失敗') }
    finally { setBusy(false); setLoading(false) }
  }

  async function act(action: ManagerAction) {
    if (!manager) return
    setBusy(true); setError('')
    try { accept(await mutateManager(manager, action)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '模擬失敗') }
    finally { setBusy(false) }
  }

  async function saveTeamName() {
    if (!manager || !teamName.trim()) return
    setBusy(true); setError('')
    try { accept(await renameManagerTeam(manager, teamName.trim())) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '球隊名稱更新失敗') }
    finally { setBusy(false) }
  }

  async function moveLineup(index: number, delta: number) {
    if (!manager || !team) return
    const target = index + delta
    if (target < 0 || target >= team.lineup.length) return
    const lineup = [...team.lineup]
    ;[lineup[index], lineup[target]] = [lineup[target], lineup[index]]
    setBusy(true); setError('')
    try { accept(await updateManagerLineup(manager, lineup)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '棒次更新失敗') }
    finally { setBusy(false) }
  }

  async function changeRotation(slot: number, cardId: string) {
    if (!manager || !team) return
    const plan = [...team.rotation_plan]
    plan[slot] = cardId
    setBusy(true); setError('')
    try { accept(await updateManagerRotation(manager, plan)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '輪值更新失敗') }
    finally { setBusy(false) }
  }

  async function openRosterBuilder(card: ManagerCard | ManagerLineupCard) {
    if (!manager || !team) return
    setBusy(true); setError('')
    try {
      setSwapCandidates(await listManagerRosterCandidates(manager, team.team_id, card.card_id))
      setSwapTarget(card)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '無法載入替換候選') }
    finally { setBusy(false) }
  }

  async function swapCard(incoming: ManagerCard) {
    if (!manager || !team || !swapTarget) return
    setBusy(true); setError('')
    try {
      accept(await replaceManagerCard(
        manager, team.team_id, swapTarget.card_id, incoming.card_id,
      ))
      setSwapTarget(null); setSwapCandidates([]); setSelectedCard(null)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '球員替換不合法') }
    finally { setBusy(false) }
  }

  if (loading) return <main className="manager-shell"><div className="manager-empty"><strong>載入經理模式…</strong></div></main>
  if (!manager) return <main className="manager-shell">
    <header className="manager-topbar"><button onClick={onBack}>返回比賽</button><strong><span>CPBL</span> 經理模式</strong></header>
    <section className="manager-empty"><h1>建立你的六隊聯盟</h1><p>系統會以真實球員年度卡建立合法、互不重複的 22 人陣容。</p>
      {error ? <p className="manager-error" role="alert">{error}</p> : null}
      <button disabled={busy} onClick={createLeague}>{busy ? '建立中…' : '建立新聯盟'}</button></section>
  </main>

  const next = manager.next_game
  const teamNames = Object.fromEntries(manager.teams.map(item => [item.team_id, item.name]))
  const available = new Set(team?.available_bullpen_card_ids ?? [])
  const allTeamCards = team ? [...team.lineup, ...team.bench, ...team.rotation, ...team.bullpen] : []
  const activeCard = selectedCard && allTeamCards.some(card => card.card_id === selectedCard.card_id)
    ? selectedCard
    : team?.lineup[0] ?? null
  return <main className="manager-shell">
    <header className="manager-topbar"><button onClick={onBack}>返回比賽</button>
      <strong><span>CPBL</span> 經理模式</strong>
      <div className="manager-save"><span>● 已儲存</span><small>rev {manager.revision} · seed {manager.seed}</small>
        <button disabled={busy} onClick={createLeague}>新增聯盟</button></div>
    </header>
    {error ? <div className="error-banner" role="alert">{error}</div> : null}
    <section className="manager-summary">
      <div><span>球隊預算</span><strong>{team?.roster_cost ?? 0} <small>/ {team?.cost_limit ?? '∞'}</small></strong></div>
      <div className="manager-next"><span>下一場</span><strong>{next ? `${teamNames[next.away_team_id] ?? next.away_team_id}  VS  ${teamNames[next.home_team_id] ?? next.home_team_id}` : '球季結束'}</strong>
        <small>{next ? `第 ${next.round_number} 輪 · Game ${next.game_number}` : `${manager.total_games} 場完成`}</small></div>
      <label>目前球隊<select value={team?.team_id ?? ''} onChange={event => {
        setSelectedTeamId(event.target.value); setSelectedCard(null); setSwapTarget(null); setSwapCandidates([])
      }}>
        {manager.teams.map(item => <option value={item.team_id} key={item.team_id}>{item.name}</option>)}</select></label>
      <label>聯盟存檔<select value={manager.manager_id} onChange={event => {
        const selected = saves.find(item => item.manager_id === event.target.value); if (selected) accept(selected)
      }}>{saves.map(item => <option value={item.manager_id} key={item.manager_id}>rev {item.revision} · {item.games_completed} 場</option>)}</select></label>
    </section>
    {team?.team_id === manager.user_team_id ? <section className="manager-customize-bar">
      <label>球隊名稱<input value={teamName} maxLength={40} onChange={event => setTeamName(event.target.value)} /></label>
      <button disabled={busy || teamName.trim() === team.name} onClick={saveTeamName}>儲存名稱</button>
      {team.unlimited_roster ? <strong>8add9 特權：Cost、SSR 與 SR 無上限</strong> : null}
    </section> : null}
    <nav className="manager-tabs" aria-label="經理模式檢視">{TABS.map(([value, label]) =>
      <button className={tab === value ? 'active' : ''} onClick={() => setTab(value)} key={value}>{label}</button>)}</nav>
    <div className={`manager-dashboard tab-${tab}`}>
      <aside className="manager-panel manager-catalog">
        <div className="manager-section-title"><h2>球員目錄</h2><span>目前 22 人</span></div>
        <div className="manager-catalog-list">{allTeamCards.map(card => <button className={activeCard?.card_id === card.card_id ? 'selected' : ''}
          onClick={() => setSelectedCard(card)} key={card.card_id}>
          <span>{'position' in card ? card.position : card.role ?? card.profile_position}</span><strong>{card.player_name}</strong>
          <small>{card.season_year}</small><em data-tier={card.tier}>{card.tier}</em></button>)}</div>
        {activeCard ? <div className="manager-card-detail"><div><strong>{activeCard.player_name}</strong><span>{activeCard.season_year} · {activeCard.tier} · cost {activeCard.cost}</span></div>
          <CardRatings card={activeCard} />
          <button className="manager-swap-open" disabled={busy}
            onClick={() => openRosterBuilder(activeCard)}>替換此卡</button>
        </div> : null}
        {swapTarget ? <div className="manager-swap-builder">
          <div className="manager-section-title"><h3>替換 {swapTarget.player_name}</h3><button onClick={() => { setSwapTarget(null); setSwapCandidates([]) }}>關閉</button></div>
          <p>{team?.unlimited_roster
            ? '8add9 不限制 Cost、SSR 與 SR；仍會檢查守位及投手角色。'
            : '換入後會由伺服器重新檢查 70 點預算、SSR 2 張、SR 5 張、守位與投手角色。'}</p>
          <div>{swapCandidates.map(candidate => <button disabled={busy} onClick={() => swapCard(candidate)} key={candidate.card_id}>
            <span>{candidate.role ?? candidate.profile_position}</span><strong>{candidate.player_name}</strong>
            <small>{candidate.season_year}</small><em data-tier={candidate.tier}>{candidate.tier}</em><b>{candidate.cost}</b>
          </button>)}</div>
        </div> : null}
      </aside>
      <section className="manager-roster-column">
        <div className="manager-budget"><div><span>我的球隊</span><strong>{team?.name}</strong></div>
          <div><span>SSR</span><strong>{team?.tier_counts.SSR ?? 0} / {team?.ssr_limit ?? '∞'}</strong></div>
          <div><span>SR</span><strong>{team?.tier_counts.SR ?? 0} / {team?.sr_limit ?? '∞'}</strong></div></div>
        {team ? <RosterTable team={team} onSelect={setSelectedCard} onMove={moveLineup} disabled={busy} /> : null}
        {team ? <div className="manager-groups">
          <CompactRoster title="替補球員" cards={team.bench} />
          <section className="manager-roster-group"><div className="manager-section-title"><h3>先發輪值</h3><span>可重複同一投手</span></div>
            {team.rotation_plan.map((cardId, index) => <label key={index}>第 {index + 1} 號
              <select disabled={busy} value={cardId} onChange={event => changeRotation(index, event.target.value)}>
                {team.rotation.map(card => <option key={card.card_id} value={card.card_id}>{card.player_name} ({card.season_year})</option>)}
              </select></label>)}
          </section>
          <CompactRoster title="牛棚投手" cards={team.bullpen} available={available} />
        </div> : null}
      </section>
      <aside className="manager-league-column">{tab === 'team-stats' || tab === 'league-stats'
        ? <PlayerStats manager={manager} scope={tab === 'team-stats' ? 'team' : 'league'} />
        : <Standings manager={manager} />}
        <section className="manager-panel manager-recent"><div className="manager-section-title"><h2>最近戰績</h2><span>近 10 場</span></div>
          {manager.recent_results.length ? manager.recent_results.slice().reverse().map(result => <div key={result.game_number}>
            <span>G{result.game_number}</span><strong>{teamNames[result.away_team_id] ?? result.away_team_id} {result.away_runs}–{result.home_runs} {teamNames[result.home_team_id] ?? result.home_team_id}</strong></div>) : <p>尚未進行比賽</p>}</section>
      </aside>
    </div>
    <section className="manager-command"><div><h2>指揮中心</h2><span>{manager.finished ? '球季已完成' : `已完成 ${manager.games_completed} / ${manager.total_games} 場`}</span></div>
      <button disabled={busy || manager.finished} onClick={() => act('simulate-next-game')}>▶ <span>模擬下一場<small>進行下一場比賽</small></span></button>
      <button disabled={busy || manager.finished} onClick={() => act('simulate-round')}>▶▶ <span>模擬下一輪<small>完成本輪賽程</small></span></button>
      <button disabled={busy || manager.finished} onClick={() => act('simulate-season')}>▶▶▶ <span>模擬剩餘球季<small>進行至 360 場</small></span></button>
      <button disabled={busy || !manager.finished} onClick={() => act('advance-season')}>＋ <span>下一個賽季<small>結算排名獎勵</small></span></button>
    </section>
  </main>
}
