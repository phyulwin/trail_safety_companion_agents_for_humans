// components/Timeline.tsx - Human-readable evidence and agent actions in one timeline.
import { ShieldCheck, Radio, Footprints, Users, Route, Check, BrainCircuit } from 'lucide-react';
import { clockTime } from '../services/api';
import type { TrailSession } from '../types';

export function Timeline({session}: {session: TrailSession | null}) {
  // Merge actual persisted events and decisions; the UI never invents agent activity.
  const rows = session ? [
    ...session.events.filter(event => event.event_type !== 'LOCATION').map(event => ({...event, title: event.event_type.split('_').join(' '), agent: false})),
    ...session.decisions.filter(decision => !['NO_ACTION', 'ANALYSIS_COMPLETE'].includes(decision.action)).map(decision => ({id: decision.id, created_at: decision.created_at, title: decision.action.split('_').join(' '), description: decision.explanation, agent: true})),
  ].sort((a,b) => b.created_at - a.created_at).slice(0, 12) : [];
  return <section className="card timeline-card"><div className="section-label"><span><Radio size={16}/> Trail activity</span><span className="tiny-label">LIVE FEED</span></div>
    {rows.length ? <div className="timeline">{rows.map(row => {
      const Icon = row.agent ? BrainCircuit : row.title.includes('COMMUNITY') || row.title.includes('HELPER') ? Users : row.title.includes('RESOLVED') ? Check : row.title.includes('ROUTE') ? Route : ShieldCheck;
      return <div className="timeline-row" key={row.id}><div className={`timeline-icon ${row.agent ? 'agent-icon' : ''}`}><Icon size={15}/></div><div><div className="timeline-heading"><strong>{row.agent ? 'Trail Safety Agent' : row.title.toLowerCase()}</strong><time>{clockTime(row.created_at)}</time></div><p>{row.description}</p>{row.agent && <span className="tool-tag">{row.title}</span>}</div></div>;
    })}</div> : <div className="empty-activity"><Footprints size={27}/><strong>A little peace of mind, every step.</strong><p>Start a Trail to see your safety check-ins, route insights, and updates here.</p></div>}
    {session && <div className="timeline-footer"><BrainCircuit size={14}/>{session.agent_mode === 'mock' ? 'Strands · deterministic demo model' : 'Strands · Amazon Bedrock'}<span>{session.decisions.filter(d => d.action === 'ANALYSIS_COMPLETE').length} analyses</span></div>}
  </section>;
}
