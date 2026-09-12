// components/RoutePreview.tsx - A compact route thumbnail derived from persisted GPS samples.
export function RoutePreview({points}: {points: [number, number][]}) {
  // Normalize latitude and longitude into the thumbnail while preserving route shape.
  if (!points?.length) return <div className="mini-route"><span>Waiting for route points</span></div>;
  const latitudes = points.map(point => point[0]);
  const longitudes = points.map(point => point[1]);
  const minLat = Math.min(...latitudes), maxLat = Math.max(...latitudes);
  const minLon = Math.min(...longitudes), maxLon = Math.max(...longitudes);
  const scale = Math.min(190 / Math.max(maxLon - minLon, 0.00001), 50 / Math.max(maxLat - minLat, 0.00001));
  const project = (point: [number, number]) => [110 + (point[1] - (minLon + maxLon) / 2) * scale,
    35 - (point[0] - (minLat + maxLat) / 2) * scale];
  const start = project(points[0]);
  return <div className="mini-route"><svg viewBox="0 0 220 70" role="img" aria-label="Recorded route preview"><polyline points={points.map(point => project(point).join(',')).join(' ')} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/><circle cx={start[0]} cy={start[1]} r="4" fill="currentColor"/></svg><span>Recorded route</span></div>;
}
