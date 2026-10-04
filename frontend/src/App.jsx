import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const API = import.meta.env.VITE_API_URL || ''
const TODAY = new Intl.DateTimeFormat('en-IE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date()).toUpperCase()
const CREWS = [
  { id: 'roads', name: 'Roads crew', icon: '↗', color: '#d77a3f' },
  { id: 'cleanup', name: 'Cleanup crew', icon: '✳', color: '#398e78' },
  { id: 'graffiti', name: 'Graffiti crew', icon: '▧', color: '#8b6bc2' },
  { id: 'lighting', name: 'Lighting crew', icon: '☼', color: '#c69c3a' },
  { id: 'arborist', name: 'Arborist crew', icon: '♧', color: '#5e9b58' },
  { id: 'drainage', name: 'Drainage crew', icon: '⌁', color: '#4d84aa' },
  { id: 'manual_triage', name: 'Manual triage', icon: '⋯', color: '#7c8792' },
]

const DEMO_REPORTS = [
  { id: 'DCC-24018', reference_number: 'DCC-24018', category: 'Pothole / road surface', summary: 'Road surface has broken away beside the pedestrian crossing.', crew_id: 'roads', crew: 'Roads crew', task_type: 'repair', estimated_minutes: 45, latitude: 53.3467, longitude: -6.2672, location_confirmed: true, approved: true, review_state: 'approved', created_at: 'Today, 09:42', address: 'Thomas Street, Dublin 8' },
  { id: 'DCC-24017', reference_number: 'DCC-24017', category: 'Dumped items', summary: 'Two bags and a small chair left beside the public bin.', crew_id: 'cleanup', crew: 'Cleanup crew', task_type: 'removal', estimated_minutes: 30, latitude: 53.3496, longitude: -6.2644, location_confirmed: true, approved: false, review_state: 'needs_review', created_at: 'Today, 09:18', address: 'High Street, Dublin 8' },
  { id: 'DCC-24016', reference_number: 'DCC-24016', category: 'Graffiti', summary: 'Paint on the stone wall at the corner of the lane.', crew_id: 'graffiti', crew: 'Graffiti crew', task_type: 'removal', estimated_minutes: 60, latitude: 53.3436, longitude: -6.2721, location_confirmed: true, approved: false, review_state: 'needs_review', created_at: 'Today, 08:56', address: 'Meath Street, Dublin 8' },
  { id: 'DCC-24015', reference_number: 'DCC-24015', category: 'Street lighting', summary: 'Street light is not working. Needs inspection before repair.', crew_id: 'lighting', crew: 'Lighting crew', task_type: 'inspection', estimated_minutes: null, latitude: null, longitude: null, location_confirmed: false, approved: false, review_state: 'needs_review', created_at: 'Yesterday, 16:20', address: 'Location to confirm' },
  { id: 'DCC-24014', reference_number: 'DCC-24014', category: 'Road surface', summary: 'Uneven paving near the bus stop.', crew_id: 'roads', crew: 'Roads crew', task_type: 'repair', estimated_minutes: 40, latitude: 53.3479, longitude: -6.2713, location_confirmed: true, approved: false, review_state: 'needs_review', created_at: 'Yesterday, 15:47', address: 'Bridgefoot Street, Dublin 8' },
]

async function request(path, options = {}) {
  const response = await fetch(`${API}/api${path}`, options)
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    const message = typeof detail === 'string' ? detail : detail?.message || data?.message || `Request failed (${response.status})`
    throw new Error(message)
  }
  return data
}

function normalizeReport(report) {
  const assignment = report.assignment || {}
  const location = report.location || {}
  const analysis = report.analysis || {}
  const original = report.original || {}
  const crewId = report.crew_id || assignment.crew || report.assigned_crew_id || report.crew || 'manual_triage'
  const crew = CREWS.find((item) => item.id === crewId || item.name === crewId)
  return {
    ...report,
    id: String(report.id ?? report.issue_id ?? report.reference_number),
    reference_number: report.reference || report.reference_number || report.id || report.issue_id,
    category: analysis.category || report.category || original.NAME || report.name || report.issue_type || 'Unclassified report',
    summary: analysis.summary || report.summary || report.description || 'No description provided.',
    crew_id: crew?.id || crewId,
    crew: report.crew_name || crew?.name || String(crewId).replaceAll('_', ' '),
    task_type: assignment.task_type || report.task_type || '',
    estimated_minutes: assignment.estimated_minutes ?? report.estimated_minutes ?? report.time_cost_minutes ?? analysis.time_cost_minutes ?? null,
    latitude: location.lat ?? report.latitude ?? report.lat ?? null,
    longitude: location.lng ?? report.longitude ?? report.lon ?? report.lng ?? null,
    location_confirmed: location.confirmed ?? report.location_confirmed ?? (report.location_confirmed_at != null),
    location_source: location.source || 'none',
    address: report.address || original.INCIDENT_ADDRESS || '',
    created_at: report.incident_date || report.created_at || original.INCIDENT_DATE || '',
    approved: report.review_state === 'approved' || report.approved === true || report.is_approved === true,
    review_state: report.review_state || 'needs_review',
  }
}

function toApiPatch(changes) {
  const payload = {}
  if ('crew_id' in changes) payload.crew = changes.crew_id
  if ('task_type' in changes) payload.task_type = changes.task_type
  if ('estimated_minutes' in changes) payload.estimated_minutes = changes.estimated_minutes
  if ('approved' in changes) payload.review_state = changes.approved ? 'approved' : 'needs_review'
  if ('latitude' in changes || 'longitude' in changes || 'location_confirmed' in changes) {
    payload.location = { lat: changes.latitude, lng: changes.longitude, confirmed: changes.location_confirmed ?? true }
  }
  return payload
}

function Icon({ name, size = 18 }) {
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    pin: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    arrow: <><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></>,
    upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 16v4h16v-4"/></>,
    route: <><circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h3a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3"/></>,
    refresh: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M5.5 9A7 7 0 0 1 18 6l2 6M4 12l2 6a7 7 0 0 0 12.5-3"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function MapPanel({ reports, selectedId, onSelect, pin, onPin, route = false }) {
  const host = useRef(null)
  const map = useRef(null)
  const layers = useRef(null)
  const handlers = useRef({ onSelect, onPin })

  useEffect(() => {
    handlers.current = { onSelect, onPin }
  }, [onSelect, onPin])

  useEffect(() => {
    if (!host.current) return undefined
    const instance = L.map(host.current, { scrollWheelZoom: false }).setView([53.347, -6.266], 14)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instance)
    const markerLayer = L.layerGroup().addTo(instance)
    instance.on('click', (event) => handlers.current.onPin?.({ latitude: event.latlng.lat, longitude: event.latlng.lng }))
    map.current = instance
    layers.current = markerLayer
    const timer = window.setTimeout(() => instance.invalidateSize(), 80)
    return () => {
      window.clearTimeout(timer)
      instance.remove()
      map.current = null
      layers.current = null
    }
  }, [])

  useEffect(() => {
    if (!map.current || !layers.current) return
    const markerLayer = layers.current
    markerLayer.clearLayers()
    const points = []
    reports.filter((item) => item.latitude != null && item.longitude != null && Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)) && Math.abs(Number(item.latitude)) <= 90 && Math.abs(Number(item.longitude)) <= 180).forEach((item, index) => {
      const point = [Number(item.latitude), Number(item.longitude)]
      points.push(point)
      const color = route ? '#236b51' : (CREWS.find((crew) => crew.id === item.crew_id)?.color || '#617587')
      const icon = L.divIcon({
        className: `leaflet-report-icon${item.id === selectedId ? ' selected' : ''}`,
        html: `<span style="--marker-color:${color}">${route ? (index + 1) : '•'}</span>`,
        iconSize: [26, 30],
        iconAnchor: [13, 26],
      })
      L.marker(point, { icon, keyboard: true, title: item.reference_number || item.category })
        .on('click', () => handlers.current.onSelect?.(item.id))
        .addTo(markerLayer)
    })
    if (pin && Number.isFinite(pin.latitude) && Number.isFinite(pin.longitude)) {
      const pinIcon = L.divIcon({ className: 'leaflet-pin-icon', html: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s8-7.1 8-13a8 8 0 1 0-16 0c0 5.9 8 13 8 13Z"/><circle cx="12" cy="9" r="2.5"/></svg>', iconSize: [26, 32], iconAnchor: [13, 30] })
      L.marker([pin.latitude, pin.longitude], { icon: pinIcon, interactive: false }).addTo(markerLayer)
      points.push([pin.latitude, pin.longitude])
      if (handlers.current.onPin) map.current.setView([pin.latitude, pin.longitude], Math.max(15, map.current.getZoom()))
    }
    if (route && points.length > 1) map.current.fitBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 15 })
  }, [reports, selectedId, pin, route])

  return <div ref={host} className={`map-canvas${onPin ? ' map-pick' : ''}`} aria-label={onPin ? 'Click to set report location' : 'Reports map'} />
}

function readPhotoGps(file) {
  return new Promise((resolve) => {
    if (!file || !/jpe?g/i.test(file.type)) return resolve(null)
    const reader = new FileReader()
    reader.onerror = () => resolve(null)
    reader.onload = () => {
      try {
        const bytes = new DataView(reader.result)
        if (bytes.getUint16(0) !== 0xffd8) return resolve(null)
        let offset = 2
        while (offset + 4 < bytes.byteLength) {
          if (bytes.getUint8(offset) !== 0xff) break
          const marker = bytes.getUint8(offset + 1)
          const length = bytes.getUint16(offset + 2)
          if (marker === 0xe1 && bytes.getUint32(offset + 4) === 0x45786966 && bytes.getUint16(offset + 8) === 0) {
            const tiff = offset + 10
            const little = bytes.getUint16(tiff) === 0x4949
            const u16 = (at) => bytes.getUint16(at, little)
            const u32 = (at) => bytes.getUint32(at, little)
            const ifd = tiff + u32(tiff + 4)
            const entries = u16(ifd)
            let gpsOffset = null
            for (let index = 0; index < entries; index++) {
              const entry = ifd + 2 + index * 12
              if (u16(entry) === 0x8825) gpsOffset = tiff + u32(entry + 8)
            }
            if (gpsOffset == null) return resolve(null)
            const gpsEntries = u16(gpsOffset)
            const tags = {}
            for (let index = 0; index < gpsEntries; index++) {
              const entry = gpsOffset + 2 + index * 12
              tags[u16(entry)] = entry
            }
            const ascii = (entry) => String.fromCharCode(...Array.from({ length: bytes.getUint32(entry + 4, little) }, (_, index) => bytes.getUint8(tiff + bytes.getUint32(entry + 8, little) + index))).replaceAll('\0', '')
            const coord = (entry) => {
              const start = tiff + u32(entry + 8)
              const parts = Array.from({ length: 3 }, (_, index) => {
                const at = start + index * 8
                return bytes.getUint32(at, little) / (bytes.getUint32(at + 4, little) || 1)
              })
              return parts[0] + parts[1] / 60 + parts[2] / 3600
            }
            if (!tags[1] || !tags[2] || !tags[3] || !tags[4]) return resolve(null)
            let latitude = coord(tags[2]); let longitude = coord(tags[4])
            if (ascii(tags[1]).startsWith('S')) latitude *= -1
            if (ascii(tags[3]).startsWith('W')) longitude *= -1
            if (Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180) return resolve({ latitude, longitude })
            return resolve(null)
          }
          offset += 2 + length
        }
        resolve(null)
      } catch { resolve(null) }
    }
    reader.readAsArrayBuffer(file)
  })
}

function App() {
  const [page, setPage] = useState('dispatch')
  const [reports, setReports] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [crewFilter, setCrewFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [loadState, setLoadState] = useState('loading')
  const [loadError, setLoadError] = useState('')
  const [isDemo, setIsDemo] = useState(false)
  const [plan, setPlan] = useState(null)
  const [planState, setPlanState] = useState('idle')
  const [planError, setPlanError] = useState('')
  const [toast, setToast] = useState('')
  const [mobileNav, setMobileNav] = useState(false)

  const loadReports = useCallback(async ({ showLoading = false } = {}) => {
    if (showLoading) setLoadState('loading')
    setLoadError('')
    try {
      const data = await request('/issues')
      const items = Array.isArray(data) ? data : data?.reports || data?.issues || data?.items || []
      setReports(items.map(normalizeReport))
      setIsDemo(false)
      setLoadState('ready')
    } catch (error) {
      setLoadError(error.message)
      setLoadState('error')
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => loadReports(), 0)
    return () => window.clearTimeout(timer)
  }, [loadReports])
  const selected = reports.find((item) => item.id === selectedId) || null
  const filtered = useMemo(() => reports.filter((item) => {
    const query = search.trim().toLowerCase()
    const matchesCrew = crewFilter === 'all' || item.crew_id === crewFilter
    const matchesSearch = !query || `${item.reference_number} ${item.category} ${item.summary} ${item.address || ''}`.toLowerCase().includes(query)
    return matchesCrew && matchesSearch
  }), [reports, crewFilter, search])
  const needsReview = reports.filter((item) => !item.approved).length
  const located = reports.filter((item) => item.latitude != null && item.longitude != null).length

  const updateReport = async (id, changes) => {
    const previous = reports.find((item) => item.id === id)
    const updated = normalizeReport({ ...previous, ...changes, approved: false, review_state: 'needs_review' })
    setReports((items) => items.map((item) => item.id === id ? updated : item))
    try {
      await request(`/issues/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(toApiPatch(changes)) })
      setToast('Changes saved. Review the updated task before approval.')
    } catch (error) {
      setReports((items) => items.map((item) => item.id === id ? previous : item))
      setToast(`Could not save changes: ${error.message}`)
    }
  }

  const approveReport = async (report) => {
    if (!report || !report.location_confirmed || !Number.isFinite(report.latitude) || !Number.isFinite(report.longitude) || Math.abs(report.latitude) > 90 || Math.abs(report.longitude) > 180 || !Number.isFinite(report.estimated_minutes) || report.estimated_minutes <= 0 || !report.task_type) {
      setToast('Add a confirmed location, task type and positive duration before approval.')
      return
    }
    const payload = { crew: report.crew_id, task_type: report.task_type, estimated_minutes: report.estimated_minutes, location: { lat: report.latitude, lng: report.longitude, confirmed: true }, review_state: 'approved' }
    const old = report
    setReports((items) => items.map((item) => item.id === report.id ? { ...item, approved: true, review_state: 'approved' } : item))
    try {
      await request(`/issues/${encodeURIComponent(report.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      setToast('Task approved for the current crew, location and duration.')
    } catch (error) {
      setReports((items) => items.map((item) => item.id === report.id ? old : item))
      setToast(`Could not approve task: ${error.message}`)
    }
  }

  const generatePlan = async () => {
    if (crewFilter === 'all') {
      setToast('Choose a crew before generating its day plan.')
      return
    }
    setPlanState('loading'); setPlanError(''); setPlan(null)
    try {
      const result = await request('/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ crew: crewFilter }) })
      setPlan(result); setPlanState('ready')
    } catch (error) { setPlanError(error.message); setPlanState('error') }
  }

  const addDemo = () => {
    setReports(DEMO_REPORTS.map(normalizeReport)); setSelectedId(DEMO_REPORTS[0].id); setIsDemo(true); setLoadState('ready'); setLoadError('')
  }

  return <div className="app-shell">
    <aside className={`sidebar${mobileNav ? ' nav-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><span/><span/><span/><span/></div><div><strong>CityWorks</strong><small>DUBLIN CITY COUNCIL</small></div><button className="mobile-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><Icon name="close"/></button></div>
      <div className="nav-caption">WORKSPACE</div>
      <button className={`nav-item${page === 'dispatch' ? ' active' : ''}`} onClick={() => { setPage('dispatch'); setMobileNav(false) }}><Icon name="grid"/><span>Dispatch board</span><span className="nav-count">{needsReview}</span></button>
      <button className={`nav-item${page === 'report' ? ' active' : ''}`} onClick={() => { setPage('report'); setMobileNav(false) }}><Icon name="pin"/><span>Report an issue</span></button>
      <div className="sidebar-bottom"><div className="status-light"/><div><strong>Service area active</strong><span>Dublin City · Live workspace</span></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="mobile-menu" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Icon name="menu"/></button><div className="breadcrumb">Operations <span>/</span> <strong>{page === 'dispatch' ? 'Dispatch board' : 'Report an issue'}</strong></div><div className="topbar-right"><span className="today-pill"><span className="live-dot"/> Operations live</span><div className="avatar">DC</div></div></header>
      {page === 'dispatch' ? <div className="page-content">
        <div className="page-heading"><div><div className="eyebrow">{TODAY} <span>·</span> DAILY OPERATIONS</div><h1>Dispatch board</h1><p>Review incoming reports and build a workable day for each crew.</p></div><button className="button button-dark" onClick={() => { setPage('report'); setMobileNav(false) }}><Icon name="plus" size={17}/> New report</button></div>
        <section className="metrics">
          <article className="metric-card"><span className="metric-icon orange"><Icon name="pin"/></span><div><small>OPEN REPORTS</small><strong>{loadState === 'ready' ? reports.length : '—'}</strong><span>Awaiting field resolution</span></div><span className="metric-mark">↗</span></article>
          <article className="metric-card"><span className="metric-icon amber"><Icon name="clock"/></span><div><small>NEEDS REVIEW</small><strong>{loadState === 'ready' ? needsReview : '—'}</strong><span>Dispatcher action required</span></div><span className="metric-mark">↗</span></article>
          <article className="metric-card"><span className="metric-icon green"><Icon name="check"/></span><div><small>LOCATED REPORTS</small><strong>{loadState === 'ready' ? located : '—'}</strong><span>Ready for location-aware planning</span></div><span className="metric-mark">↗</span></article>
        </section>
        {isDemo && <div className="demo-banner"><span>DEMO PREVIEW</span> Sample reports are for layout preview only. Live API data replaces them after refresh.<button onClick={loadReports}>Return to live data</button></div>}
        <section className="workspace-grid">
          <div className="reports-panel panel">
            <div className="panel-heading"><div><div className="section-kicker">INCOMING WORK</div><h2>Issue reports <span className="count-pill">{filtered.length}</span></h2></div><button className="icon-button" onClick={() => loadReports({ showLoading: true })} title="Refresh reports" aria-label="Refresh reports"><Icon name="refresh"/></button></div>
            <div className="filter-row"><label className="search-box"><Icon name="search" size={17}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search reports…" aria-label="Search reports"/></label><select aria-label="Filter by crew" value={crewFilter} onChange={(event) => { setCrewFilter(event.target.value); setPlan(null) }}><option value="all">All crews</option>{CREWS.map((crew) => <option value={crew.id} key={crew.id}>{crew.name}</option>)}</select></div>
            <div className="report-list">
              {loadState === 'loading' && <div className="empty-state"><span className="spinner"/>Loading reports…</div>}
              {loadState === 'error' && <div className="empty-state error-state"><div className="empty-icon">!</div><strong>Couldn’t load reports</strong><p>{loadError}</p><button className="button button-outline" onClick={() => loadReports({ showLoading: true })}><Icon name="refresh" size={15}/> Try again</button><button className="text-action" onClick={addDemo}>Preview the board with sample reports</button></div>}
              {loadState === 'ready' && filtered.length === 0 && <div className="empty-state"><div className="empty-icon"><Icon name="search"/></div><strong>No reports found</strong><p>Try another search or crew.</p></div>}
              {loadState === 'ready' && filtered.map((report) => <button key={report.id} className={`report-row${selectedId === report.id ? ' selected' : ''}`} onClick={() => setSelectedId(report.id)}>
                <span className="category-icon" style={{ '--crew-color': CREWS.find((crew) => crew.id === report.crew_id)?.color || '#77828d' }}>{report.category.toLowerCase().includes('graffiti') ? '▧' : report.category.toLowerCase().includes('pothole') || report.category.toLowerCase().includes('road') ? '⌁' : report.category.toLowerCase().includes('light') ? '☼' : '✳'}</span>
                <span className="report-copy"><span className="report-topline"><strong>{report.category}</strong><span className={`review-badge${report.approved ? ' approved' : ''}`}>{report.approved ? 'Approved' : 'Review'}</span></span><span className="report-summary">{report.summary}</span><span className="report-meta"><span>{report.reference_number}</span><span>·</span><span>{report.created_at || 'Recently'}</span></span></span>
                <span className="row-chevron"><Icon name="arrow" size={16}/></span>
              </button>)}
            </div>
            <div className="list-footer">Showing {filtered.length} of {reports.length} reports <span>Last synced just now</span></div>
          </div>
          <div className="map-panel panel"><div className="panel-heading map-heading"><div><div className="section-kicker">SERVICE AREA</div><h2>Central Dublin</h2></div><span className="map-live"><span className="live-dot"/> {located} located</span></div><MapPanel reports={filtered} selectedId={selectedId} onSelect={setSelectedId} /><div className="map-legend"><span><i className="legend-dot roads-dot"/> Roads</span><span><i className="legend-dot clean-dot"/> Cleanup</span><span><i className="legend-dot graffiti-dot"/> Graffiti</span><span><i className="legend-dot other-dot"/> Other</span></div></div>
        </section>
        {selected && <section className="detail-panel panel"><div className="detail-header"><div><div className="section-kicker">REPORT DETAILS</div><h2>{selected.category}<span className="ref-inline">{selected.reference_number}</span></h2></div><button className="icon-button" onClick={() => setSelectedId(null)} aria-label="Close report details"><Icon name="close"/></button></div><div className="detail-content"><div className="detail-description"><p>{selected.summary}</p><div className="detail-location"><Icon name="pin" size={16}/><span>{selected.address || (selected.latitude != null ? `${Number(selected.latitude).toFixed(5)}, ${Number(selected.longitude).toFixed(5)}` : 'Location not confirmed')}</span><span className={selected.location_confirmed ? 'confirmed-label' : 'unconfirmed-label'}>{selected.location_confirmed ? 'Confirmed' : 'Needs pin'}</span></div></div><div className="edit-fields"><label>Crew<select value={selected.crew_id} onChange={(event) => updateReport(selected.id, { crew_id: event.target.value })}>{CREWS.map((crew) => <option key={crew.id} value={crew.id}>{crew.name}</option>)}</select></label><label>Task type<select value={selected.task_type || ''} onChange={(event) => updateReport(selected.id, { task_type: event.target.value })}><option value="">Select task</option><option value="repair">Repair</option><option value="removal">Removal</option><option value="inspection">Inspection</option><option value="manual_triage">Manual triage</option></select></label><label>Duration <span className="unit-label">minutes</span><input type="number" min="1" value={selected.estimated_minutes ?? ''} placeholder="Set duration" onChange={(event) => setReports((items) => items.map((item) => item.id === selected.id ? { ...item, estimated_minutes: event.target.value === '' ? null : Number(event.target.value) } : item))} onBlur={(event) => { if (event.target.value) updateReport(selected.id, { estimated_minutes: Number(event.target.value) }) }}/></label><label>Latitude<input type="number" step="0.00001" value={selected.latitude ?? ''} placeholder="Choose on map" onChange={(event) => setReports((items) => items.map((item) => item.id === selected.id ? { ...item, latitude: event.target.value === '' ? null : Number(event.target.value), location_confirmed: false } : item))} onBlur={(event) => { if (event.target.value && selected.longitude != null) updateReport(selected.id, { latitude: Number(event.target.value), longitude: selected.longitude, location_confirmed: true }) }}/></label><label>Longitude<input type="number" step="0.00001" value={selected.longitude ?? ''} placeholder="Choose on map" onChange={(event) => setReports((items) => items.map((item) => item.id === selected.id ? { ...item, longitude: event.target.value === '' ? null : Number(event.target.value), location_confirmed: false } : item))} onBlur={(event) => { if (event.target.value && selected.latitude != null) updateReport(selected.id, { latitude: selected.latitude, longitude: Number(event.target.value), location_confirmed: true }) }}/></label></div><button className={`button ${selected.approved ? 'button-approved' : 'button-dark'}`} onClick={() => approveReport(selected)} disabled={selected.approved}><Icon name="check" size={16}/>{selected.approved ? 'Approved for current task' : 'Approve task'}</button></div></section>}
        <section className="plan-panel panel"><div className="plan-copy"><span className="plan-icon"><Icon name="route" size={21}/></span><div><div className="section-kicker">CREW PLANNING</div><h2>Build a day plan</h2><p>Get a suggested feasible route with travel time, lunch and depot return built in.</p></div></div><div className="plan-actions"><label className="plan-select-label">CREW<select value={crewFilter} onChange={(event) => { setCrewFilter(event.target.value); setPlan(null) }}><option value="all">Choose a crew</option>{CREWS.map((crew) => <option key={crew.id} value={crew.id}>{crew.name}</option>)}</select></label><button className="button button-dark" onClick={generatePlan} disabled={planState === 'loading' || isDemo}><Icon name="route" size={16}/>{planState === 'loading' ? 'Planning…' : 'Generate day plan'}</button></div>
          {isDemo && <p className="plan-note">Day planning is disabled for sample data. Connect the live API to generate an itinerary.</p>}
          {planState === 'error' && <div className="plan-error"><strong>Plan could not be generated</strong><span>{planError}</span><button onClick={generatePlan}>Try again</button></div>}
          {planState === 'ready' && <PlanResult plan={plan} reports={reports} />}
        </section>
      </div> : <ReportForm onSubmitted={(result) => { const reference = result?.reference || result?.reference_number || result?.id || 'saved'; const analysisState = result?.analysis_state; const message = analysisState === 'failed' ? `Report saved · ${reference} · Analysis needs dispatcher review` : analysisState === 'pending' ? `Report saved · ${reference} · Analysis is pending` : `Report saved and analysed · Reference ${reference}`; setToast(message); setPage('dispatch'); loadReports() }} />}
    </main>
    {toast && <div className="toast" role="status"><span><Icon name="check" size={16}/></span>{toast}<button onClick={() => setToast('')} aria-label="Dismiss message"><Icon name="close" size={16}/></button></div>}
  </div>
}

function PlanResult({ plan, reports }) {
  if (!plan) return null
  const stops = plan.stops || plan.itinerary || []
  const omitted = plan.omitted_jobs || plan.omitted || []
  const totals = plan.totals || {}
  const reportFor = (stop) => reports.find((item) => item.id === String(stop.report_id ?? stop.issue_id ?? stop.id))
  return <div className="plan-result"><div className="plan-result-header"><strong><Icon name="check" size={16}/> {plan.label || 'Suggested feasible route'}</strong><span>{totals.travel_minutes ?? plan.travel_total_minutes ?? plan.total_travel_minutes ?? '—'} min travel <i/> {totals.task_minutes ?? plan.task_total_minutes ?? plan.total_task_minutes ?? '—'} min on site</span></div><div className="itinerary-layout"><div className="itinerary-list">{stops.map((stop, index) => { const report = reportFor(stop); return <div className="itinerary-stop" key={stop.report_id || stop.id || index}><span className="stop-number">{stop.order || index + 1}</span><div><strong>{report?.category || stop.category || `Report ${stop.report_id || stop.id || index + 1}`}</strong><span>{stop.arrive || stop.arrival_time || stop.arrival || '—'} arrival · {stop.complete || stop.completion_time || stop.departure_time || '—'} complete</span></div><span className="stop-duration">{stop.task_minutes ?? stop.duration_minutes ?? stop.estimated_minutes ?? '—'}m</span></div>})}{stops.length === 0 && <p className="no-stops">No approved tasks fit this crew’s shift.</p>}<div className="lunch-row"><span className="lunch-icon">☕</span><div><strong>Lunch break</strong><span>{plan.lunch?.start || plan.lunch_start || '12:00'} – {plan.lunch?.end || plan.lunch_end || '13:00'} · at current location</span></div></div><div className="depot-row"><span>⌂</span> Return to depot <strong>{plan.depot_return || plan.depot_return_time || plan.return_time || '—'}</strong></div></div><div className="itinerary-map"><MapPanel reports={stops.map((stop, index) => ({ ...(reportFor(stop) || {}), id: String(stop.report_id ?? stop.issue_id ?? stop.id ?? index), latitude: stop.lat ?? stop.latitude, longitude: stop.lng ?? stop.lon ?? stop.longitude }))} route /></div></div>{omitted.length > 0 && <details className="omitted-list"><summary>{omitted.length} omitted report{omitted.length !== 1 ? 's' : ''}</summary>{omitted.map((item, index) => <div key={item.report_id || item.id || index}><span>{item.reference_number || item.report_id || item.id || 'Report'}</span><span>{item.message || item.reason || item.omission_reason || 'Not eligible for this plan'}</span></div>)}</details>}</div>
}

function ReportForm({ onSubmitted }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [description, setDescription] = useState('')
  const [email, setEmail] = useState('')
  const [address, setAddress] = useState('')
  const [pin, setPin] = useState(null)
  const [gpsFound, setGpsFound] = useState(false)
  const [locationConfirmed, setLocationConfirmed] = useState(false)
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')
  const inputRef = useRef(null)
  const chooseFile = async (selected) => {
    if (!selected) return
    setFile(selected); setPreview(URL.createObjectURL(selected)); setGpsFound(false); setPin(null); setLocationConfirmed(false)
    const gps = await readPhotoGps(selected)
    if (gps) { setPin(gps); setGpsFound(true) }
  }
  const submit = async (event) => {
    event.preventDefault(); setState('loading'); setError('')
    const body = new FormData()
    body.append('photo', file)
    body.append('description', description)
    body.append('email', email)
    if (address) body.append('address', address)
    if (pin && locationConfirmed) {
      body.append('lat', String(pin.latitude))
      body.append('lng', String(pin.longitude))
      body.append('location_confirmed', 'true')
    }
    try {
      const result = await request('/issues', { method: 'POST', body })
      onSubmitted(result)
    } catch (failure) { setError(failure.message); setState('error') }
  }
  return <div className="page-content report-page"><div className="page-heading"><div><div className="eyebrow">DUBLIN CITY · COMMUNITY REPORTING</div><h1>Report an issue</h1><p>Share a photo and details. Our team will review it and get it to the right crew.</p></div><span className="secure-note"><Icon name="check" size={14}/> Your details stay private</span></div>
    <div className="report-layout"><form className="report-form panel" onSubmit={submit}><div className="form-section-heading"><span className="step-index">1</span><div><h2>What needs attention?</h2><p>A clear photo helps us understand what’s going on.</p></div></div>
      {!file ? <button type="button" className="upload-zone" onClick={() => inputRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files?.[0]) }}><span className="upload-icon"><Icon name="upload" size={22}/></span><strong>Drop a photo here or <span>browse files</span></strong><small>JPG, PNG or HEIC · up to 15 MB</small><input ref={inputRef} type="file" accept="image/*" hidden onChange={(event) => chooseFile(event.target.files?.[0])}/></button> : <div className="photo-preview"><img src={preview} alt="Preview of issue"/><div className="photo-info"><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(1)} MB · {gpsFound ? 'Photo GPS found' : 'No photo GPS found'}</span></div><button type="button" className="icon-button" onClick={() => { setFile(null); setPreview(''); setPin(null); setGpsFound(false); setLocationConfirmed(false); if (inputRef.current) inputRef.current.value = '' }} aria-label="Remove photo"><Icon name="close"/></button></div>}
      <label className="form-label">Description <span>What did you notice?</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows="3" maxLength="1000" placeholder="Add a few details to help the crew…" required/></label>
      <div className="form-divider"/><div className="form-section-heading"><span className="step-index">2</span><div><h2>Where is the issue?</h2><p>{gpsFound ? 'Photo location detected. Confirm the pin is in the right place.' : 'Choose the location on the map so the crew can find it.'}</p></div></div>
      <div className="location-source-note"><Icon name="pin" size={16}/><span>{gpsFound ? 'Photo GPS is shown on the map. Confirm it or choose a more precise pin.' : 'Tap the map to set a report location. Address text alone can’t be used for routing.'}</span></div>
      <MapPanel reports={[]} pin={pin} onPin={(point) => { setPin(point); setLocationConfirmed(true) }}/><div className="pin-status">{pin ? <><span className={locationConfirmed ? 'live-dot' : 'pending-dot'}/>{locationConfirmed ? 'Location confirmed' : 'Confirm the photo location'} · {pin.latitude.toFixed(5)}, {pin.longitude.toFixed(5)}</> : <><Icon name="pin" size={15}/> Tap the map to drop a pin</>}</div>
      {!gpsFound && <label className="form-label address-label">Nearest address or landmark <span>Optional context</span><input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="Street, building or nearby landmark"/></label>}
      <div className="form-divider"/><div className="form-section-heading"><span className="step-index">3</span><div><h2>How can we contact you?</h2><p>Your email is private and won’t be shared with the crew.</p></div></div>
      <label className="form-label">Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required/></label>
      {error && <div className="form-error"><strong>Report wasn’t saved</strong><span>{error}. Your details are still here; please try again.</span></div>}
      <button className="button button-dark submit-button" disabled={state === 'loading' || !file}>{state === 'loading' ? <><span className="spinner spinner-light"/> Sending report…</> : <>Submit report <Icon name="arrow" size={17}/></>}</button><p className="submit-hint">Reports without a confirmed pin can be saved for dispatcher review, but won’t be scheduled until located.</p>
    </form><aside className="report-aside"><div className="aside-card"><span className="aside-icon"><Icon name="check"/></span><h3>What happens next?</h3><ol><li><b>01</b><span><strong>We review your report</strong><small>Our team checks the details and photo.</small></span></li><li><b>02</b><span><strong>It goes to the right crew</strong><small>We match the issue with the people best placed to help.</small></span></li><li><b>03</b><span><strong>We plan the work</strong><small>The dispatcher adds approved work to a crew’s day.</small></span></li></ol></div><div className="privacy-card"><Icon name="pin" size={18}/><div><strong>A quick note about location</strong><p>A confirmed pin gives crews a usable location. If your photo has GPS, the team can check it against the map pin.</p></div></div></aside></div>
  </div>
}

export default App
