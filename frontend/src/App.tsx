// App.tsx - Trail's runner, contact, history, and community product flows.
import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowRight, Bell, CheckCircle2, ChevronRight, Clock3, Compass, Footprints, HeartHandshake, History, Home, Leaf, Loader2, LockKeyhole, LogOut, MapPin, Navigation, Play, Plus, Radio, Route, Search, Settings2, ShieldCheck, Siren, Sparkles, Users, X } from 'lucide-react';
import { TrailMap } from './components/TrailMap';
import { Timeline } from './components/Timeline';
import { RoutePreview } from './components/RoutePreview';
import { useSession } from './hooks/useSession';
import { api, clockTime, duration } from './services/api';
import type { CommunityAlert, Contact, Suggestion, TrailSession, User } from './types';

type Page = 'home' | 'history' | 'contacts' | 'following' | 'community' | 'retrace' | 'profile';
const nav = [{id: 'home', label: 'Your Trail', icon: Home}, {id: 'history', label: 'Trail history', icon: History},
  {id: 'contacts', label: 'Your circle', icon: Users}, {id: 'following', label: 'Following', icon: Radio},
  {id: 'community', label: 'Community', icon: HeartHandshake}] as const;

export default function App() {
  // Account state stays in memory; the server manages the HttpOnly session cookie.
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<Page>('home');
  const [history, setHistory] = useState<TrailSession[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [shared, setShared] = useState<TrailSession[]>([]);
  const [alerts, setAlerts] = useState<CommunityAlert[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const {session, setSession, connection} = useSession(sessionId);
  const [selectedContacts, setSelectedContacts] = useState<string[]>([]);
  const [community, setCommunity] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [item, setItem] = useState('');
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [now, setNow] = useState(Date.now() / 1000);
  const [gps, setGps] = useState(false);
  const [demoPerspective, setDemoPerspective] = useState(false);
  const [zone, setZone] = useState<CommunityAlert | undefined>();
  const watch = useRef<number | null>(null);
  const lastGps = useRef(0);
  const ownsSession = session?.user_id === user?.id;
  const active = Boolean(session?.active && ownsSession);

  async function refresh() {
    // Fetch independent dashboard data together so navigation stays responsive.
    const [routes, people, followed] = await Promise.all([api<TrailSession[]>('/sessions/history'), api<Contact[]>('/trusted-contacts'), api<TrailSession[]>('/sessions/shared')]);
    setHistory(routes); setContacts(people); setShared(followed);
    return routes;
  }

  async function run(task: () => Promise<void>) {
    // Keep every product action accountable with visible loading and error feedback.
    setBusy(true); setError(''); setNotice('');
    try { await task(); } catch (failure) { setError(failure instanceof Error ? failure.message : 'Something went wrong'); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    // Restore the signed-in account and active session on a full page refresh.
    api<User>('/users/me').then(async account => {
      setUser(account); setCommunity(account.community_opt_in);
      const routes = await refresh();
      setSessionId(routes.find(route => route.active)?.id || null);
    }).catch(() => setUser(null));
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    // Foreground browser geolocation is opt-in and never runs for simulated sessions.
    if (!gps || !sessionId || !active || session?.is_demo) return;
    if (!navigator.geolocation) { setError('This browser does not support location access'); setGps(false); return; }
    watch.current = navigator.geolocation.watchPosition(position => {
      if (position.timestamp - lastGps.current < 3000) return;
      lastGps.current = position.timestamp;
      api<TrailSession>(`/sessions/${sessionId}/location`, 'POST', {latitude: position.coords.latitude, longitude: position.coords.longitude,
        accuracy: Math.min(position.coords.accuracy, 200), timestamp: position.timestamp / 1000}).then(setSession).catch(failure => setError(failure.message));
    }, failure => { setError(`Location access: ${failure.message}`); setGps(false); }, {enableHighAccuracy: true, maximumAge: 0, timeout: 15000});
    return () => { if (watch.current !== null) navigator.geolocation.clearWatch(watch.current); };
  }, [gps, sessionId, active, session?.is_demo]);

  useEffect(() => {
    // Refresh recipient views independently of the runner's authorized WebSocket.
    if (!user || !['community', 'following'].includes(page)) return;
    let disposed = false;
    const load = async () => {
      try {
        if (demoPerspective && session?.is_demo && ownsSession) {
          const data = await api<{contact: TrailSession; community: CommunityAlert[]}>(`/demo/perspectives/${session.id}`);
          if (!disposed) { setShared([data.contact]); setAlerts(data.community); }
        } else if (page === 'community') {
          const data = await api<CommunityAlert[]>('/community/alerts');
          if (!disposed) setAlerts(data);
        } else {
          const data = await api<TrailSession[]>('/sessions/shared');
          if (!disposed) setShared(data);
        }
      } catch (failure) { if (!disposed) setError((failure as Error).message); }
    };
    void load(); const timer = setInterval(load, 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [page, user?.id, demoPerspective, session?.id]);

  async function startDemo(scenario: 'safety' | 'normal') {
    // The demo button explicitly creates a disposable account if no user is signed in.
    await run(async () => {
      if (!user) {
        const id = crypto.randomUUID();
        const account = await api<User>('/auth/register', 'POST', {email: `trail-${id}@example.com`, password: crypto.randomUUID() + crypto.randomUUID(), display_name: 'Jamie'});
        setUser(account);
      }
      const trail = await api<TrailSession>('/demo/start', 'POST', {scenario});
      setSessionId(trail.id); setSession(trail); setPage('home'); setDemoPerspective(false);
      setCommunity(true); setUser(await api<User>('/users/me')); await refresh();
    });
  }

  async function startTrail() {
    // Starting a real Trail transmits only the sharing permissions currently selected.
    if (!user) { setAuthMode('register'); setAuthOpen(true); return; }
    await run(async () => {
      const trail = await api<TrailSession>('/sessions', 'POST', {share_with: selectedContacts, community_enabled: community});
      setSessionId(trail.id); setSession(trail); setGps(true); setPage('home'); await refresh();
    });
  }

  async function respond(response: 'OK' | 'HELP') {
    // Human responses are persisted immediately; the modal follows backend state.
    if (!session) return;
    await run(async () => { setSession(await api<TrailSession>(`/sessions/${session.id}/checkin-response`, 'POST', {response})); });
  }

  async function toggleCommunity() {
    // Global opt-in and active-session opt-in are separately recorded by the API.
    if (!user) { setAuthOpen(true); return; }
    await run(async () => {
      const value = !community;
      setUser(await api<User>('/users/me', 'PATCH', {...user, community_opt_in: value}));
      if (active && session) setSession(await api<TrailSession>(`/sessions/${session.id}/sharing`, 'PATCH', {share_with: session.share_with, community_enabled: value}));
      setCommunity(value);
    });
  }

  function selectPage(next: Page) {
    // Load fresh history after a session finishes and clear stale search results.
    setPage(next); setError(''); setNotice('');
    if (next === 'home') {
      const current = history.find(trail => trail.active);
      if (current) setSessionId(current.id);
    }
    if (user) void refresh().catch(failure => setError(failure.message));
  }

  const risk = session?.state.risk_score;
  const riskText = risk == null ? 'Not assessed' : session?.state.risk_level || 'Low';
  const elevated = (risk ?? 0) > 60;
  const pageTitle: Record<Page, string> = {home: 'Your outside, with peace of mind.', history: 'Every Trail has a story.', contacts: 'Good company. Even from afar.', following: 'Stay close, wherever they go.', community: 'A little care goes a long way.', retrace: 'Take a few steps back.', profile: 'Make Trail yours.'};

  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#" onClick={e => {e.preventDefault(); selectPage('home');}}><span className="brand-mark"><Navigation size={25}/></span>trail<span className="brand-period">.</span></a>
      <div className="workspace-label">A LITTLE MORE PEACE OF MIND</div>
      <nav aria-label="Main navigation">{nav.map(({id,label,icon: Icon}) => <button key={id} className={`nav-item ${page === id ? 'selected' : ''}`} onClick={() => selectPage(id)}><Icon size={19}/><span>{label}</span>{id === 'home' && active && <i className="live-dot"/>}</button>)}</nav>
      <div className="sidebar-note"><div className="small-leaf"><Leaf size={23}/></div><strong>Outside is for everyone.</strong><p>A trusted circle.<br/>A thoughtful community.<br/>A little less worry.</p><span>THE GOOD NEIGHBOR WAY <ArrowDownLeft size={15}/></span></div>
      <button className="nav-item settings" onClick={() => user ? selectPage('profile') : setAuthOpen(true)}><Settings2 size={19}/>Settings & privacy</button>
      <div className="sidebar-bottom"><LockKeyhole size={13}/>Your location. Your permission.</div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb">Your personal safety companion<span>/</span><strong>{page === 'home' ? 'Overview' : page === 'retrace' ? 'Lost item search' : nav.find(n => n.id === page)?.label || 'Profile'}</strong></div><div className="top-actions"><span className="local-pill"><span className="live-dot"/>{session?.agent_mode === 'bedrock' ? 'BEDROCK CONNECTED' : 'LOCAL DEMO READY'}</span><button className="icon-button" aria-label="Open activity" onClick={() => {setPage('home'); document.getElementById('activity')?.scrollIntoView({behavior: 'smooth'});}}><Bell size={19}/></button><button className="avatar" aria-label={user ? 'Open profile' : 'Sign in'} onClick={() => user ? setPage('profile') : setAuthOpen(true)}>{user?.display_name.slice(0,1) || 'T'}</button></div></header>
      <main><div className="page-heading"><div><div className="eyebrow"><span className="short-line"/>{user ? `GOOD TO SEE YOU, ${user.display_name.split(' ')[0].toUpperCase()}` : 'GO AHEAD. TAKE THE SCENIC ROUTE.'}</div><h1>{pageTitle[page]}</h1><p>{page === 'home' ? 'Run freely. Trail watches your back.' : page === 'history' ? 'Your last 10 days outside, kept just for you.' : page === 'retrace' ? 'Find a starting point for the things you left behind.' : 'Connection starts with your permission.'}</p></div>{page === 'home' && <div className="date-note"><span>{new Date().toLocaleDateString([], {weekday: 'long'})}</span>{new Date().toLocaleDateString([], {month: 'long', day: 'numeric'})}</div>}</div>
      {error && <div className="message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}
      {notice && <div className="message" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={16}/></button></div>}
      {busy && <div className="loading-strip" role="status"><Loader2 size={15} className="spin"/>Updating your Trail…</div>}

      {page === 'home' && <>
        <div className="overview-grid"><div className="main-column">
          <section className="map-card"><div className="map-card-header"><div><span className="live-indicator"><span className="live-dot"/>{active ? 'YOUR TRAIL IS LIVE' : 'YOUR NEXT CHAPTER'}</span><h2>{session ? session.is_demo ? 'An evening in Pasadena' : 'Your live Trail' : 'A little fresh air looks good on you.'}</h2></div><span className="map-location"><MapPin size={14}/>{session?.is_demo || !session ? 'Pasadena, CA' : 'Your location'}</span></div>
            <div className="map-wrap"><TrailMap session={session}/><div className="map-top-label"><Compass size={15}/>{session ? session.is_demo ? 'SIMULATED ROUTE & SAFETY DATA' : 'FOREGROUND GPS SESSION' : 'ILLUSTRATIVE PASADENA ROUTE'}</div><div className="map-bottom-label"><span className="map-line orange"/>Your route{session?.state.suggested_route && <><span className="map-line green"/>Suggested alternative</>}<span className="map-location-name">PASADENA</span></div></div>
            <div className="session-stats"><div><span><Clock3 size={14}/>TIME OUTSIDE</span><strong>{session ? duration((session.ended_at || now) - session.started_at) : '00:00'}<small>min</small></strong></div><div><span><Route size={14}/>DISTANCE</span><strong>{session ? (session.distance / 1000).toFixed(2) : '0.00'}<small>km</small></strong></div><div><span><Footprints size={14}/>MOVEMENT</span><strong className="word-stat">{session?.current_status.toLowerCase() || 'Ready to go'}<i className={`live-dot ${active ? '' : 'muted-dot'}`}/></strong></div><div><span><ShieldCheck size={14}/>RISK ESTIMATE</span><strong className={`word-stat ${elevated ? 'text-orange' : ''}`}>{riskText}<small>{risk == null ? '—' : `${risk}/100`}</small></strong></div></div>
            <div className="session-controls">{active ? <><button className="button forest" onClick={() => void respond('OK')} disabled={busy}><ShieldCheck size={18}/>I'm safe</button><button className="button outline" disabled={busy} onClick={() => void run(async () => {setSession(await api<TrailSession>(`/sessions/${sessionId}/end`, 'POST')); setGps(false); await refresh();})}>End Trail</button><button className="button sos" disabled={busy} onClick={() => void respond('HELP')}><Siren size={18}/>SOS</button></> : <><button className="button orange" disabled={busy} onClick={() => void startTrail()}><Navigation size={18}/>Start Trail<ArrowRight size={17}/></button><span className="control-note"><LockKeyhole size={14}/>Shared only with the people you choose.</span></>}{active && <button className="icon-button" title="Bookmark last recorded location" aria-label="Bookmark last recorded location" disabled={busy || !session?.points.length} onClick={() => void run(async () => {setSession(await api<TrailSession>(`/sessions/${sessionId}/mark`, 'POST')); setNotice('Last recorded location bookmarked for retracing.');})}><MapPin size={17}/></button>}{active && <span className="connection"><i className="live-dot"/>{connection}</span>}</div>
          </section>
          {session?.safety_state === 'ESCALATED' && <div className="sos-banner" role="alert"><Siren size={25}/><div><strong>Your trusted contacts have an in-app safety alert.</strong><p>If you are in immediate danger, contact local emergency services.</p><small>Trail does not call emergency services or send SMS.</small></div></div>}
          {session?.state.suggested_route && <div className="route-advice"><Route size={23}/><div><strong>A more connected way back</strong><p>{session.state.suggested_route.explanation}</p><small>Illustrative route only; check actual conditions before following it.</small></div></div>}
          <div className="feature-pair"><button className="feature-card" onClick={() => selectPage('retrace')}><span className="feature-icon peach"><Search size={21}/></span><div><h3>Left something behind?</h3><p>Let your footsteps help you find it.</p><span>Retrace a Trail <ArrowRight size={14}/></span></div></button><button className="feature-card" onClick={() => selectPage('history')}><span className="feature-icon sage"><History size={21}/></span><div><h3>Your last 10 days outside</h3><p>A private record of where you've been.</p><span>Explore your history <ArrowRight size={14}/></span></div></button></div>
          <div id="activity"><Timeline session={session}/></div>
        </div><aside className="right-column"><section className="agent-card"><div className="agent-top"><span className="agent-shield"><ShieldCheck size={25}/></span><span className="agent-status"><span className="live-dot"/>{active ? 'WATCHING YOUR BACK' : 'HERE WHEN YOU NEED US'}</span></div><h2>A quiet companion.<br/>A little more confidence.</h2><p>{active ? 'Trail AI is monitoring your session. If something seems unusual, we’ll check in with you first.' : 'Go at your own pace. Trail keeps an eye on the little things, so you can enjoy being outside.'}</p>{session && <div className="agent-signals"><span>Isolation estimate<strong>{session.state.seclusion_score == null ? 'Unavailable' : session.state.seclusion_score.toFixed(2)}</strong></span><span>Motion anomaly<strong>{(session.state.anomaly_score || 0).toFixed(2)}</strong></span></div>}<div className="agent-bottom"><Sparkles size={15}/><span>{active ? 'Session monitoring active' : 'Ready for your next Trail'}</span><div className="signal-bars"><i/><i/><i/><i/><i/></div></div></section>
          <section className="card circle-card"><div className="section-label"><span>Your trusted circle</span><button className="text-icon" aria-label="Manage trusted contacts" onClick={() => selectPage('contacts')}><Plus size={18}/></button></div>{contacts.length ? contacts.slice(0,3).map((contact,i) => <label className="contact-row" key={contact.id}><span className={`person-avatar color-${i % 3}`}>{contact.display_name.split(' ').map(part => part[0]).join('')}</span><span><strong>{contact.display_name}</strong><small>{session?.share_with.includes(contact.user_id) ? 'Following this Trail' : 'Approved contact'}</small></span><input type="checkbox" aria-label={`Share next Trail with ${contact.display_name}`} checked={active ? Boolean(session?.share_with.includes(contact.user_id)) : selectedContacts.includes(contact.user_id)} disabled={active} onChange={e => setSelectedContacts(e.target.checked ? [...selectedContacts,contact.user_id] : selectedContacts.filter(id => id !== contact.user_id))}/></label>) : <div className="compact-empty"><Users size={23}/><p>Your people, one tap away.</p><button className="text-button" onClick={() => user ? selectPage('contacts') : setAuthOpen(true)}>Add a trusted contact <Plus size={13}/></button></div>}<div className="card-footnote"><LockKeyhole size={12}/>{active ? 'Sharing is set for this Trail.' : 'Select who can follow your next Trail.'}</div></section>
          <section className="card community-card"><div className="section-label"><span><HeartHandshake size={17}/>Good neighbors</span><button className={`toggle ${community ? 'on' : ''}`} role="switch" aria-checked={community} aria-label="Community Safety Network" disabled={busy} onClick={() => void toggleCommunity()}><span/></button></div><p>A helping hand nearby, if you need one.</p><div className="neighbor-avatars"><span>SR</span><span>CC</span><span>TB</span><span>ME</span><span>JL</span><small>5 helpers in the demo</small></div><div className="privacy-note"><ShieldCheck size={15}/><span>Only an approximate area is shared.<br/>Your exact location stays private.</span></div></section>
          <section className="demo-card"><span className="eyebrow"><Play size={13}/>TAKE TRAIL FOR A TEST RUN</span><h3>See care in action.</h3><p>Watch a simulated run move from a quiet check-in to a community helping hand.</p><button className="button outline full" disabled={busy || active} onClick={() => void startDemo('safety')}><Play size={15}/>Run safety demo<ArrowRight size={15}/></button><button className="text-button demo-normal" disabled={busy || active} onClick={() => void startDemo('normal')}>Or try a normal run <ArrowRight size={13}/></button><small>Enables sample contact sharing & community opt-in.<br/>Simulated data · no real notifications sent.</small></section>
        </aside></div>
      </>}

      {page === 'history' && <section className="card content-card"><div className="section-label"><span><History size={18}/>Recent Trails</span><span className="tiny-label">AUTOMATICALLY DELETED AFTER 10 DAYS</span></div>{history.length ? <div className="history-grid">{history.map(trail => <button className="history-card" key={trail.id} onClick={() => {setSessionId(trail.id); setPage('retrace'); setSuggestions([]); setSearched(false);}}><RoutePreview points={trail.route_preview}/><strong>{new Date(trail.started_at * 1000).toLocaleDateString([], {weekday: 'long', month: 'short', day: 'numeric'})}</strong><p>{(trail.distance/1000).toFixed(2)} km · {duration((trail.ended_at || now) - trail.started_at)} · {trail.is_demo ? 'Simulated' : 'GPS'}</p><span className="text-button">Explore & retrace <ArrowRight size={14}/></span></button>)}</div> : <Empty icon="history" title="Your story starts with a first step." text="Start a Trail or run the demo to create your first route."/>}</section>}

      {page === 'retrace' && <div className="retrace-grid"><section className="card content-card"><div className="section-label"><span><Search size={18}/>Lost item search</span></div><label className="form-label">Choose your Trail<select value={sessionId || ''} onChange={e => {setSessionId(e.target.value || null); setSuggestions([]); setSearched(false);}}><option value="">Select a route</option>{history.map(trail => <option key={trail.id} value={trail.id}>{new Date(trail.started_at*1000).toLocaleString()} · {(trail.distance/1000).toFixed(2)} km</option>)}</select></label><label className="form-label">What did you lose? <span className="optional">Optional</span><input value={item} maxLength={100} onChange={e => setItem(e.target.value)} placeholder="Keys, wallet, earbuds…"/></label><button className="button forest full" disabled={!session || !ownsSession || busy} onClick={() => void run(async () => {const data = await api<{suggestions: Suggestion[]}>('/lost-items/analyze', 'POST', {session_id: sessionId, item}); setSuggestions(data.suggestions); setSearched(true);})}><Search size={16}/>Find possible search points</button><p className="muted small">Trail looks at pauses, turns, pace changes, and your marked locations; it cannot know where an item was lost.</p>{suggestions.map((point,i) => <div className="search-result" key={i}><span>{i+1}</span><div><strong>{clockTime(point.timestamp)}</strong><p>{point.reasons.join(' · ')}</p></div></div>)}{searched && !suggestions.length && <p className="message">No distinctive stops or turns were found on this route.</p>}</section><div className="large-map"><TrailMap session={session} suggestions={suggestions}/></div></div>}

      {page === 'contacts' && <div className="two-column"><section className="card content-card"><div className="section-label"><span><Users size={18}/>The people in your corner</span></div>{contacts.map((contact,i) => <div className="contact-row large" key={contact.id}><span className={`person-avatar color-${i%3}`}>{contact.display_name.slice(0,1)}</span><span><strong>{contact.display_name}</strong><small>{contact.email}</small></span><button className="text-button" disabled={busy} onClick={() => void run(async () => {await api(`/trusted-contacts/${contact.id}`, 'DELETE'); await refresh();})}>Remove</button></div>)}{!contacts.length && <Empty icon="people" title="Build your trusted circle." text="Approve someone you know, then select them when you start a Trail."/>}<form onSubmit={e => {e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); void run(async () => {await api('/trusted-contacts', 'POST', {email: data.get('email')}); form.reset(); await refresh();});}}><label className="form-label">Contact's registered email<input required name="email" type="email" placeholder="someone@example.com"/></label><button className="button forest" disabled={busy || !user}><Plus size={16}/>Add trusted contact</button></form></section><section className="card content-card"><ShieldCheck size={32} className="green-icon"/><h2>Sharing should feel personal.</h2><p className="muted">A trusted contact can see your precise route only when you select them for a Trail; removing them revokes access immediately.</p><p className="muted">Notifications appear in their Following view while they are signed in; SMS, email, and emergency dispatch are not connected.</p>{active && <button className="button outline" onClick={() => void run(async () => {setSession(await api<TrailSession>(`/sessions/${sessionId}/sharing`, 'PATCH', {share_with: [], community_enabled: community})); setNotice('All contact sharing has been revoked for this Trail.');})}>Revoke sharing for this Trail</button>}</section></div>}

      {page === 'following' && <><PerspectiveToggle available={Boolean(session?.is_demo && ownsSession)} value={demoPerspective} onChange={setDemoPerspective}/>{shared.length ? shared.map(trail => <section className="card following-card" key={trail.id}><div className="section-label"><span><span className="person-avatar color-0">{trail.runner_name.slice(0,1)}</span>{trail.runner_name}'s Trail</span><span className="status-tag">{trail.active ? 'LIVE' : 'ENDED'}</span></div><div className="following-layout"><div className="large-map"><TrailMap session={trail}/></div><div><h2>{trail.safety_state === 'ESCALATED' ? 'Your person may need a hand.' : 'A little closer, from anywhere.'}</h2><p>{trail.current_status.toLowerCase()} · {(trail.distance/1000).toFixed(2)} km</p><p className="muted">Last update: {trail.state.last_received_at ? clockTime(trail.state.last_received_at) : 'Waiting for location'}</p><Timeline session={trail}/></div></div></section>) : <section className="card"><Empty icon="people" title="You're here for your people." text="Trails appear here when someone approves you and shares a session with you."/></section>}</>}

      {page === 'community' && <><PerspectiveToggle available={Boolean(session?.is_demo && ownsSession)} value={demoPerspective} onChange={setDemoPerspective}/><div className="community-intro"><HeartHandshake size={34}/><div><h2>Close enough to care. Private by design.</h2><p>Community requests show an approximate area; accepting never reveals a runner's exact location.</p></div></div>{!demoPerspective && user && <div className="helper-actions"><button className="button outline" disabled={busy || user.verified} onClick={() => void run(async () => {setUser(await api<User>('/users/me/verify-demo', 'POST'));})}><ShieldCheck size={17}/>{user.verified ? 'Identity verified (simulated)' : 'Simulate identity verification'}</button><button className="button forest" disabled={busy || !user.verified || !user.community_opt_in} onClick={() => void run(async () => {await api('/community/helper', 'PUT', {latitude: 34.153, longitude: -118.145, available: true}); setNotice('Available near the simulated Pasadena route for future alerts.');})}>Available near demo route</button></div>}{alerts.length ? <div className="two-column"><section className="card content-card">{alerts.map(alert => <div className="alert-card" key={alert.id}><span className="status-tag">APPROXIMATE AREA ONLY</span><h3>{alert.description}</h3><p>{alert.radius_km} km zone · {alert.accepted_count} helper(s) available</p><button className="text-button" onClick={() => setZone(alert)}>View assistance area <MapPin size={14}/></button>{!demoPerspective && <div className="helper-actions"><button className="button forest" onClick={() => void run(async () => {await api(`/community/alerts/${alert.id}/accept`, 'POST'); setNotice('Your availability was recorded; precise location remains private.');})}>Available to help</button><button className="button outline" onClick={() => void run(async () => {await api(`/community/alerts/${alert.id}/dismiss`, 'POST'); setAlerts(alerts.filter(a => a.id !== alert.id));})}>Dismiss</button></div>}</div>)}</section><div className="large-map"><TrailMap zone={zone || alerts[0]}/></div></div> : <section className="card"><Empty icon="people" title="A quiet neighborhood is a good thing." text="Eligible nearby requests will appear here; the safety demo also provides a simulated helper preview."/></section>}</>}

      {page === 'profile' && user && <section className="card content-card profile-card"><div className="section-label"><span><Settings2 size={18}/>Your profile & permissions</span></div><form onSubmit={e => {e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {setUser(await api<User>('/users/me', 'PATCH', {display_name: data.get('display_name'), emergency_contact: data.get('emergency_contact'), community_opt_in: community})); setNotice('Profile updated.');});}}><label className="form-label">Your name<input name="display_name" required maxLength={80} defaultValue={user.display_name}/></label><label className="form-label">Emergency contact details<input name="emergency_contact" maxLength={200} defaultValue={user.emergency_contact} placeholder="Name and phone number (private)"/></label><p className="muted small">Emergency contact details are stored privately; they do not configure SMS or calls.</p><div className="contact-row"><span>Community Safety Network</span><button type="button" className={`toggle ${community ? 'on' : ''}`} role="switch" aria-checked={community} onClick={() => void toggleCommunity()}><span/></button></div><button className="button forest" disabled={busy}>Save profile</button></form><hr/><div className="privacy-note"><LockKeyhole size={20}/><span>Routes and their derived location data expire after 10 days; identity verification in this MVP is simulated.</span></div><button className="button outline" onClick={() => void run(async () => {await api('/auth/logout', 'POST'); setGps(false); setUser(null); setSessionId(null); setSession(null); setHistory([]); setContacts([]); setShared([]); setAlerts([]); setSelectedContacts([]); setCommunity(false); setPage('home');})}><LogOut size={16}/>Sign out</button></section>}
      {!user && page !== 'home' && <button className="button orange signin-bottom" onClick={() => setAuthOpen(true)}>Sign in to continue <ArrowRight size={16}/></button>}
      <footer><span><Navigation size={13}/>MADE FOR THE WAY YOU MOVE.</span><p>Trail provides supplemental safety assistance and is not a replacement for emergency services.</p><span>TAKE CARE OUT THERE.</span></footer>
      </main></div>

    {authOpen && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="auth-title"><button className="modal-close icon-button" aria-label="Close sign in" onClick={() => setAuthOpen(false)}><X size={20}/></button><div className="feature-icon peach"><Navigation size={26}/></div><h2 id="auth-title">{authMode === 'login' ? 'Welcome back to Trail.' : 'Your next step starts here.'}</h2><p className="muted">A little peace of mind for your time outside.</p>{error && <p className="message error" role="alert">{error}</p>}<form onSubmit={e => {e.preventDefault(); const data = new FormData(e.currentTarget); void run(async () => {const account = await api<User>(`/auth/${authMode}`, 'POST', {email: data.get('email'), password: data.get('password'), display_name: data.get('display_name')}); setUser(account); setCommunity(account.community_opt_in); setAuthOpen(false); const routes = await refresh(); setSessionId(routes.find(route => route.active)?.id || null);});}}>{authMode === 'register' && <label className="form-label">Your name<input name="display_name" required autoFocus maxLength={80}/></label>}<label className="form-label">Email<input name="email" type="email" required autoComplete="email"/></label><label className="form-label">Password<input name="password" type="password" required minLength={10} maxLength={128} autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}/></label><button className="button orange full" disabled={busy}>{authMode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={17}/></button></form><button className="text-button auth-switch" onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}>{authMode === 'login' ? 'New to Trail? Create an account' : 'Already have an account? Sign in'}</button></section></div>}
    {session?.safety_state === 'CHECK_IN' && ownsSession && <div className="modal-backdrop checkin-backdrop"><section className="modal checkin-modal" role="alertdialog" aria-modal="true" aria-labelledby="checkin-title"><div className="checkin-symbol"><ShieldCheck size={38}/></div><span className="eyebrow">A QUICK CHECK-IN</span><h2 id="checkin-title">Everything okay?</h2><p>Trail noticed you've been stopped longer than usual; take a moment to let your people know you're okay.</p><div className="countdown"><strong>{Math.max(0, Math.ceil((session.checkin_deadline || now) - now))}</strong><span>seconds before an in-app<br/>alert to your trusted contacts</span></div><button className="button forest full" disabled={busy} onClick={() => void respond('OK')}><CheckCircle2 size={19}/>I'm OK</button><button className="button sos full" disabled={busy} onClick={() => void respond('HELP')}><Siren size={18}/>Need help</button>{session.is_demo && <small>{session.demo_scenario === 'normal' ? 'Normal demo: a simulated OK response will close this check-in.' : 'Safety demo: let the countdown finish to see escalation.'}</small>}</section></div>}
  </div>;
}

function Empty({icon, title, text}: {icon: 'history' | 'people'; title: string; text: string}) {
  // Reusable empty states explain the next user action without fabricating data.
  return <div className="empty-state">{icon === 'history' ? <History size={35}/> : <Users size={35}/>}<h3>{title}</h3><p>{text}</p></div>;
}

function PerspectiveToggle({available, value, onChange}: {available: boolean; value: boolean; onChange: (value: boolean) => void}) {
  // Demo previews are owner-only API views, never impersonated recipient accounts.
  return available ? <div className="perspective-bar"><span><Activity size={17}/>{value ? 'Simulated recipient preview' : 'Your real account view'}</span><button className="text-button" onClick={() => onChange(!value)}>{value ? 'Return to my account' : 'Preview demo recipients'}<ChevronRight size={15}/></button></div> : null;
}
