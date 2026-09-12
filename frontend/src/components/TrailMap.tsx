// components/TrailMap.tsx - OpenStreetMap with authorized routes and coarse helper zones.
import { useEffect } from 'react';
import { MapContainer, TileLayer, Polyline, CircleMarker, Circle, Tooltip, useMap } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import type { CommunityAlert, Suggestion, TrailSession } from '../types';
import 'leaflet/dist/leaflet.css';

const preview: [number, number][] = [[34.1498,-118.1453],[34.1506,-118.1453],[34.1514,-118.1453],[34.1522,-118.1453],[34.1530,-118.1453],[34.1540,-118.1451]];

function MapFrame({session, zone}: {session?: TrailSession | null; zone?: CommunityAlert}) {
  // Reframe on a different Trail, leaving the user free to pan during live updates.
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    if (zone) map.setView([zone.zone_latitude, zone.zone_longitude], 13);
    else if (session?.points.length) map.fitBounds(session.points.map(p => [p.latitude, p.longitude]), {padding: [45, 45], maxZoom: 16});
    else map.fitBounds(preview, {padding: [60, 60]});
  }, [map, session?.id, session?.points.length, zone?.id]);
  useEffect(() => {
    // Keep Leaflet's canvas aligned when the desktop or phone layout changes size.
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return null;
}

export function TrailMap({session, suggestions = [], zone}: {session?: TrailSession | null; suggestions?: Suggestion[]; zone?: CommunityAlert}) {
  // Community mode omits the runner path entirely; it renders only an approved coarse zone.
  const route: LatLngExpression[] = zone ? [] : session ? session.points.map(p => [p.latitude, p.longitude]) : preview;
  const current = route.at(-1);
  return <MapContainer center={[34.1519, -118.1453]} zoom={15} scrollWheelZoom={false} className="trail-map" aria-label={zone ? 'Approximate community assistance area' : 'Trail route map'}>
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <MapFrame session={session} zone={zone}/>
    {route.length > 0 && <Polyline positions={route} pathOptions={{color: '#d16a40', weight: 6, opacity: 0.9, dashArray: session ? undefined : '8 10'}}/>}
    {route[0] && <CircleMarker center={route[0]} radius={7} pathOptions={{color: '#fff', fillColor: '#263f36', fillOpacity: 1, weight: 3}}><Tooltip>Trail start</Tooltip></CircleMarker>}
    {current && <><CircleMarker center={current} radius={18} pathOptions={{stroke: false, fillColor: '#cf704c', fillOpacity: 0.16}}/><CircleMarker center={current} radius={8} pathOptions={{color: '#fff', fillColor: '#d16a40', fillOpacity: 1, weight: 3}}><Tooltip>{session ? 'Current authorized location' : 'Illustrative Pasadena route'}</Tooltip></CircleMarker></>}
    {!zone && session?.state.suggested_route && <><Polyline positions={session.state.suggested_route.points} pathOptions={{color: '#426859', weight: 5, dashArray: '8 8'}}/>{session.state.suggested_route.safe_points.map(point => <CircleMarker key={point.label} center={[point.latitude, point.longitude]} radius={6} pathOptions={{color: '#426859', fillOpacity: 1}}><Tooltip>{point.label}</Tooltip></CircleMarker>)}</>}
    {suggestions.map((point, i) => <CircleMarker key={i} center={[point.latitude, point.longitude]} radius={11} pathOptions={{color: '#fff', fillColor: '#75649d', fillOpacity: 1, weight: 3}}><Tooltip permanent>{i + 1}: {point.reasons.join(', ')}</Tooltip></CircleMarker>)}
    {zone && <Circle center={[zone.zone_latitude, zone.zone_longitude]} radius={zone.radius_km * 1000} pathOptions={{color: '#cc734d', fillColor: '#cc734d', fillOpacity: 0.13, dashArray: '6 8'}}><Tooltip>Approximate zone only</Tooltip></Circle>}
  </MapContainer>;
}
