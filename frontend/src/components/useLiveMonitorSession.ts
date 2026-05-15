import { useState, useRef, useCallback } from 'react';

const API = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:5001';

export interface QueryPresence {
  query_index: number;
  filename: string;
  is_present: boolean;
  first_seen_at: string | null;
  last_seen_at: string | null;
  continuous_since: string | null;
  left_at: string | null;
  total_presence_sec: number;
  current_segment_sec: number;
  segments: Array<{ start: string; end: string; duration_sec: number }>;
  match_reason: string | null;
  error?: string;
}

export interface Detection {
  label: string;
  confidence: number;
  box: { x: number; y: number; width: number; height: number };
  is_query_match?: boolean;
}

export interface LiveAlert {
  type: string;
  severity: string;
  message: string;
  timestamp: string;
  query_index?: number;
  event?: string;
  duration_sec?: number;
}

export interface SessionSummary {
  queries: Array<{
    query_index: number;
    filename: string;
    was_found: boolean;
    first_seen_at: string | null;
    last_seen_at: string | null;
    total_presence_sec: number;
    total_presence_formatted: string;
    segments: Array<{ start: string; end: string; duration_sec: number }>;
    match_reason: string | null;
  }>;
  alerts: LiveAlert[];
  total_alerts: number;
}

export function useLiveMonitorSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [queryPresence, setQueryPresence] = useState<QueryPresence[]>([]);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const [queryInfo, setQueryInfo] = useState<Array<{ filename: string; has_face: boolean; labels: string[] }>>([]);
  const sessionIdRef = useRef<string | null>(null);

  const startSession = useCallback(async (queryImages: File[]): Promise<string | null> => {
    if (!queryImages.length) return null;
    const fd = new FormData();
    queryImages.forEach(f => fd.append('query_images', f, f.name));
    try {
      const res = await fetch(`${API}/live-monitor/start-session`, { method: 'POST', body: fd });
      if (!res.ok) { console.error('Start session failed'); return null; }
      const data = await res.json();
      const sid = data.session_id;
      setSessionId(sid);
      sessionIdRef.current = sid;
      setQueryInfo(data.queries || []);
      setSessionSummary(null);
      setQueryPresence([]);
      return sid;
    } catch (e) { console.error('Start session error:', e); return null; }
  }, []);

  const processFrame = useCallback(async (blob: Blob): Promise<{
    detections: Detection[];
    alerts: LiveAlert[];
    queryPresence: QueryPresence[];
  } | null> => {
    const sid = sessionIdRef.current;
    if (!sid) return null;
    const fd = new FormData();
    fd.append('session_id', sid);
    fd.append('frame', blob, 'frame.jpg');
    try {
      const res = await fetch(`${API}/live-monitor/process-frame`, { method: 'POST', body: fd });
      if (!res.ok) return null;
      const data = await res.json();
      if (data.query_presence) setQueryPresence(data.query_presence);
      return {
        detections: data.detections || [],
        alerts: data.alerts || [],
        queryPresence: data.query_presence || [],
      };
    } catch { return null; }
  }, []);

  const stopSession = useCallback(async (): Promise<SessionSummary | null> => {
    const sid = sessionIdRef.current;
    if (!sid) return null;
    sessionIdRef.current = null;
    setSessionId(null);
    try {
      const res = await fetch(`${API}/live-monitor/stop-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      setSessionSummary(data);
      return data;
    } catch { return null; }
  }, []);

  return { sessionId, queryPresence, sessionSummary, queryInfo, startSession, processFrame, stopSession };
}
