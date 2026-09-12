// hooks/useSession.ts - Live WebSocket state with reconnect and visible polling fallback.
import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { TrailSession } from '../types';

export function useSession(id: string | null) {
  // Dispose sockets, retry timers, and fetch results when the selected Trail changes.
  const [session, setSession] = useState<TrailSession | null>(null);
  const [connection, setConnection] = useState('Connecting');
  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    setSession(null);
    if (!id) { setConnection('Ready'); return; }
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/session/${id}`);
      socket.onopen = () => { if (!disposed) setConnection('Live'); };
      socket.onmessage = message => {
        try {
          const event = JSON.parse(message.data);
          if (!disposed && event.type === 'session') setSession(event.data);
        } catch { if (!disposed) setConnection('Reconnecting'); }
      };
      socket.onclose = event => {
        if (disposed) return;
        if (event.code === 4403) { setSession(null); setConnection('Access ended'); return; }
        setConnection('Reconnecting');
        retry = setTimeout(connect, 2500);
      };
    };
    connect();
    const poll = setInterval(() => {
      if (socket?.readyState !== WebSocket.OPEN) api<TrailSession>(`/sessions/${id}`).then(data => {
        if (!disposed) setSession(data);
      }).catch(() => { if (!disposed) setConnection('Offline or access ended'); });
    }, 4000);
    return () => { disposed = true; clearInterval(poll); clearTimeout(retry); socket?.close(); };
  }, [id]);
  return {session, setSession, connection};
}
