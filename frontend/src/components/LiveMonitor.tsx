import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useLiveMonitorSession, Detection, LiveAlert, QueryPresence } from './useLiveMonitorSession';

const API = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:5001';

/* ── tiny beep for alerts ── */
function playBeep() {
  try {
    const ac = new (window.AudioContext || (window as any).webkitAudioContext)();
    const o = ac.createOscillator(); const g = ac.createGain();
    o.connect(g); g.connect(ac.destination);
    o.frequency.value = 880; g.gain.value = 0.15;
    o.start(); o.stop(ac.currentTime + 0.12);
  } catch {}
}

function fmtDur(sec: number) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
function fmtTime(iso: string | null) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}

/* ── clip storage ── */
interface VideoClip { idx: number; filename: string; url: string; start: string; end: string; dur: number; }

export const LiveMonitor: React.FC = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [alerts, setAlerts] = useState<LiveAlert[]>([]);
  const [queryImages, setQueryImages] = useState<File[]>([]);
  const [queryPreviews, setQueryPreviews] = useState<string[]>([]);
  const [stats, setStats] = useState({ fps: 0, objectCount: 0 });
  const [clips, setClips] = useState<VideoClip[]>([]);
  const [audioEnabled, setAudioEnabled] = useState(true);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const frameCountRef = useRef(0);
  const lastFpsRef = useRef(Date.now());

  // MediaRecorder per query index
  const recordersRef = useRef<Map<number, MediaRecorder>>(new Map());
  const chunksRef = useRef<Map<number, Blob[]>>(new Map());
  const recStartRef = useRef<Map<number, string>>(new Map());

  const session = useLiveMonitorSession();
  const prevPresenceRef = useRef<Map<number, boolean>>(new Map());

  /* ── query image selection ── */
  const handleQuerySelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setQueryImages(files);
    setQueryPreviews([]);
    files.forEach(f => {
      const r = new FileReader();
      r.onload = ev => setQueryPreviews(p => [...p, ev.target?.result as string]);
      r.readAsDataURL(f);
    });
  };

  const removeQueryImage = (idx: number) => {
    setQueryImages(p => p.filter((_, i) => i !== idx));
    setQueryPreviews(p => p.filter((_, i) => i !== idx));
  };

  /* ── recording helpers ── */
  const startRecording = useCallback((qIdx: number, filename: string) => {
    if (!streamRef.current || recordersRef.current.has(qIdx)) return;
    try {
      const mr = new MediaRecorder(streamRef.current, { mimeType: 'video/webm;codecs=vp9' });
      const ch: Blob[] = [];
      mr.ondataavailable = e => { if (e.data.size > 0) ch.push(e.data); };
      mr.onstop = () => {
        const blob = new Blob(ch, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        const start = recStartRef.current.get(qIdx) || new Date().toISOString();
        const end = new Date().toISOString();
        const dur = (new Date(end).getTime() - new Date(start).getTime()) / 1000;
        setClips(p => [...p, { idx: qIdx, filename, url, start, end, dur }]);
        recordersRef.current.delete(qIdx);
        chunksRef.current.delete(qIdx);
        recStartRef.current.delete(qIdx);
      };
      chunksRef.current.set(qIdx, ch);
      recStartRef.current.set(qIdx, new Date().toISOString());
      recordersRef.current.set(qIdx, mr);
      mr.start(1000);
    } catch (err) { console.error('Recording start error:', err); }
  }, []);

  const stopRecording = useCallback((qIdx: number) => {
    const mr = recordersRef.current.get(qIdx);
    if (mr && mr.state !== 'inactive') mr.stop();
  }, []);

  /* ── webcam start/stop ── */
  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        setIsStreaming(true);

        // Start session if query images present
        if (queryImages.length > 0) {
          await session.startSession(queryImages);
        }

        intervalRef.current = window.setInterval(() => processFrame(), 500);
      }
    } catch (err) {
      console.error('Webcam error:', err);
      alert('Could not access webcam.');
    }
  };

  const stopWebcam = async () => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    // Stop all recorders
    recordersRef.current.forEach((mr, idx) => { if (mr.state !== 'inactive') mr.stop(); });

    const summary = await session.stopSession();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setIsStreaming(false);
    setDetections([]);
    frameCountRef.current = 0;
    prevPresenceRef.current.clear();
  };

  /* ── frame processing ── */
  const processFrame = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    const v = videoRef.current, c = canvasRef.current, ctx = c.getContext('2d');
    if (!ctx || v.readyState !== v.HAVE_ENOUGH_DATA) return;
    c.width = v.videoWidth; c.height = v.videoHeight;
    ctx.drawImage(v, 0, 0, c.width, c.height);

    c.toBlob(async blob => {
      if (!blob) return;

      // Always try session endpoint first (hook uses ref, immune to stale closures)
      let data: any = null;
      const sessionResult = await session.processFrame(blob);
      if (sessionResult) {
        data = sessionResult;
      } else {
        // No active session — fallback to stateless endpoint
        const fd = new FormData();
        fd.append('frame', blob, 'frame.jpg');
        try {
          const res = await fetch(`${API}/process-frame`, { method: 'POST', body: fd });
          if (res.ok) data = await res.json();
        } catch {}
      }

      if (!data) return;
      setDetections(data.detections || []);

      // Process alerts
      if (data.alerts?.length) {
        const newAlerts = data.alerts.map((a: any) => ({ ...a, timestamp: a.timestamp || new Date().toISOString() }));
        setAlerts(prev => [...newAlerts, ...prev].slice(0, 100));
        // Beep on query match
        if (audioEnabled && newAlerts.some((a: any) => a.type === 'query_match')) playBeep();
      }

      // Handle recording based on presence changes
      if (data.queryPresence) {
        for (const qp of data.queryPresence as QueryPresence[]) {
          const wasPresent = prevPresenceRef.current.get(qp.query_index) || false;
          if (qp.is_present && !wasPresent) {
            startRecording(qp.query_index, qp.filename || `query_${qp.query_index}`);
          } else if (!qp.is_present && wasPresent) {
            stopRecording(qp.query_index);
          }
          prevPresenceRef.current.set(qp.query_index, qp.is_present);
        }
      }

      // Update stats
      frameCountRef.current++;
      const now = Date.now(), elapsed = (now - lastFpsRef.current) / 1000;
      if (elapsed >= 1) {
        setStats({ fps: Math.round(frameCountRef.current / elapsed), objectCount: data.detections?.length || 0 });
        frameCountRef.current = 0; lastFpsRef.current = now;
      }

      drawDetections(data.detections || []);
    }, 'image/jpeg', 0.8);
  };

  /* ── draw bounding boxes ── */
  const drawDetections = (dets: Detection[]) => {
    const c = canvasRef.current, ctx = c?.getContext('2d');
    if (!ctx || !c) return;
    ctx.clearRect(0, 0, c.width, c.height);
    dets.forEach(d => {
      const x = d.box.x * c.width, y = d.box.y * c.height;
      const w = d.box.width * c.width, h = d.box.height * c.height;
      const isMatch = d.is_query_match;
      ctx.strokeStyle = isMatch ? '#f56565' : '#48bb78';
      ctx.lineWidth = isMatch ? 4 : 2;
      ctx.strokeRect(x, y, w, h);
      if (isMatch) { ctx.shadowColor = '#f56565'; ctx.shadowBlur = 12; ctx.strokeRect(x, y, w, h); ctx.shadowBlur = 0; }
      ctx.fillStyle = isMatch ? '#f56565' : '#48bb78';
      ctx.fillRect(x, y - 24, Math.max(w, 100), 24);
      ctx.fillStyle = '#fff'; ctx.font = 'bold 14px Arial';
      ctx.fillText(`${isMatch ? '🔍 ' : ''}${d.label} ${(d.confidence * 100).toFixed(0)}%`, x + 4, y - 6);
    });
  };

  useEffect(() => () => { stopWebcam(); }, []);

  const qp = session.queryPresence;
  const summary = session.sessionSummary;

  /* ── inline styles ── */
  const S: any = {
    page: { padding: 24, background: 'linear-gradient(135deg,#0f0c29,#302b63,#24243e)', minHeight: '100vh', fontFamily: "'Inter','Segoe UI',sans-serif", color: '#e2e8f0' },
    grid: { display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, marginBottom: 20 },
    card: { background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(12px)', borderRadius: 16, padding: 20, border: '1px solid rgba(255,255,255,0.1)' },
    title: { fontSize: 32, fontWeight: 800, textAlign: 'center' as const, marginBottom: 8, background: 'linear-gradient(90deg,#667eea,#f093fb)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' },
    sub: { textAlign: 'center' as const, fontSize: 14, opacity: 0.7, marginBottom: 24 },
    vidBox: { position: 'relative' as const, background: '#000', borderRadius: 12, overflow: 'hidden', aspectRatio: '16/9' },
    vid: { width: '100%', height: '100%', objectFit: 'cover' as const },
    cvs: { position: 'absolute' as const, top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' as const },
    badge: (on: boolean) => ({ position: 'absolute' as const, top: 12, right: 12, padding: '6px 14px', borderRadius: 20, background: on ? '#48bb78' : '#e53e3e', color: '#fff', fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }),
    btn: (c: string, dis: boolean) => ({ padding: '10px 20px', fontSize: 14, fontWeight: 600, border: 'none', borderRadius: 10, cursor: dis ? 'not-allowed' : 'pointer', background: dis ? '#4a5568' : c, color: '#fff', opacity: dis ? 0.5 : 1, flex: 1, transition: 'all .2s' }),
    statNum: { fontSize: 26, fontWeight: 800 },
    statLbl: { fontSize: 11, textTransform: 'uppercase' as const, opacity: 0.6, marginBottom: 2 },
    presCard: (present: boolean) => ({ padding: 14, marginBottom: 10, borderRadius: 12, background: present ? 'rgba(72,187,120,0.15)' : 'rgba(255,255,255,0.05)', border: `1px solid ${present ? '#48bb7860' : 'rgba(255,255,255,0.08)'}`, transition: 'all .3s' }),
    alertItem: (sev: string) => {
      const bg: any = { high: 'rgba(245,101,101,0.15)', medium: 'rgba(246,173,85,0.15)', low: 'rgba(144,205,244,0.1)' };
      const br: any = { high: '#f56565', medium: '#f6ad55', low: '#90cdf4' };
      return { padding: 10, marginBottom: 8, borderRadius: 8, borderLeft: `3px solid ${br[sev] || br.low}`, background: bg[sev] || bg.low };
    },
    thumb: { width: 50, height: 50, objectFit: 'cover' as const, borderRadius: 8, border: '2px solid rgba(255,255,255,0.2)' },
    clipCard: { padding: 10, marginBottom: 8, borderRadius: 8, background: 'rgba(102,126,234,0.12)', border: '1px solid rgba(102,126,234,0.3)' },
  };

  return (
    <div style={S.page}>
      <h1 style={S.title}>📹 Live Webcam Monitor</h1>
      <p style={S.sub}>Real-time detection with query image tracking & video trimming</p>

      <div style={S.grid}>
        {/* LEFT COLUMN */}
        <div>
          {/* Video */}
          <div style={S.card}>
            <div style={S.vidBox}>
              <video ref={videoRef} style={S.vid} autoPlay playsInline muted />
              <canvas ref={canvasRef} style={S.cvs} />
              <div style={S.badge(isStreaming)}>
                <span style={isStreaming ? { animation: 'pulse 2s infinite' } : {}}>●</span>
                {isStreaming ? 'LIVE' : 'OFFLINE'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
              <button onClick={startWebcam} disabled={isStreaming} style={S.btn('#667eea', isStreaming)}>🎥 Start</button>
              <button onClick={stopWebcam} disabled={!isStreaming} style={S.btn('#e53e3e', !isStreaming)}>⏹ Stop</button>
              <button onClick={() => setAudioEnabled(p => !p)} style={S.btn(audioEnabled ? '#48bb78' : '#718096', false)}>
                {audioEnabled ? '🔊' : '🔇'}
              </button>
            </div>
          </div>

          {/* Query Images Upload */}
          <div style={{ ...S.card, marginTop: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>🖼️ Query Images {queryImages.length > 0 && `(${queryImages.length})`}</h3>
            <input type="file" multiple accept="image/*" onChange={handleQuerySelect} disabled={isStreaming}
              style={{ display: 'block', fontSize: 13, marginBottom: 10, color: '#a0aec0' }} />
            {queryPreviews.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {queryPreviews.map((p, i) => (
                  <div key={i} style={{ position: 'relative' }}>
                    <img src={p} alt={`Q${i}`} style={S.thumb} />
                    {!isStreaming && (
                      <button onClick={() => removeQueryImage(i)}
                        style={{ position: 'absolute', top: -6, right: -6, width: 18, height: 18, borderRadius: 9,
                          background: '#e53e3e', color: '#fff', border: 'none', fontSize: 10, cursor: 'pointer', lineHeight: '18px', padding: 0 }}>✕</button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {isStreaming && queryImages.length > 0 && (
              <p style={{ fontSize: 12, color: '#48bb78', marginTop: 8 }}>✅ Session active — tracking {queryImages.length} query image(s)</p>
            )}
          </div>

          {/* Query Presence Dashboard */}
          {qp.length > 0 && (
            <div style={{ ...S.card, marginTop: 16 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>🎯 Query Match Dashboard</h3>
              {qp.map((q, i) => (
                <div key={i} style={S.presCard(q.is_present)}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 14 }}>
                      {queryPreviews[q.query_index] && <img src={queryPreviews[q.query_index]} alt="" style={{ width: 28, height: 28, borderRadius: 6, verticalAlign: 'middle', marginRight: 8 }} />}
                      {q.filename || `Query ${q.query_index}`}
                      {session.queryInfo[q.query_index]?.has_face && (
                        <span style={{ marginLeft: 8, fontSize: 10, background: 'rgba(102,126,234,0.3)', padding: '2px 6px', borderRadius: 4, color: '#a3bffa' }}>
                          👤 Face Rec Active
                        </span>
                      )}
                    </span>
                    <span style={{
                      padding: '4px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                      background: q.is_present ? '#48bb78' : q.first_seen_at ? '#f6ad55' : '#718096',
                      color: '#fff'
                    }}>
                      {q.is_present ? '🟢 PRESENT' : q.first_seen_at ? '🟡 WAS HERE' : '🔴 NOT FOUND'}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12, opacity: 0.85 }}>
                    <div><strong>First seen:</strong> {fmtTime(q.first_seen_at)}</div>
                    <div><strong>Last seen:</strong> {fmtTime(q.last_seen_at)}</div>
                    <div><strong>Duration:</strong> {fmtDur(q.total_presence_sec)}</div>
                    <div><strong>Current:</strong> {q.is_present ? fmtDur(q.current_segment_sec) : '—'}</div>
                  </div>
                  {q.match_reason && <div style={{ fontSize: 11, marginTop: 4, opacity: 0.6 }}>{q.match_reason}</div>}
                  {q.segments.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 11 }}>
                      <strong>Segments:</strong>
                      {q.segments.map((s, si) => (
                        <div key={si} style={{ padding: '2px 0', opacity: 0.7 }}>
                          #{si + 1}: {fmtTime(s.start)} → {fmtTime(s.end)} ({fmtDur(s.duration_sec)})
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Video Clips */}
          {clips.length > 0 && (
            <div style={{ ...S.card, marginTop: 16 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>🎬 Recorded Clips ({clips.length})</h3>
              {clips.map((cl, i) => (
                <div key={i} style={S.clipCard}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{cl.filename}</div>
                      <div style={{ fontSize: 11, opacity: 0.6 }}>{fmtTime(cl.start)} → {fmtTime(cl.end)} • {fmtDur(cl.dur)}</div>
                    </div>
                    <a href={cl.url} download={`clip_${cl.filename}_${i}.webm`}
                      style={{ padding: '6px 14px', borderRadius: 8, background: '#667eea', color: '#fff', fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>
                      ⬇ Download
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Session Summary */}
          {summary && (
            <div style={{ ...S.card, marginTop: 16, border: '1px solid rgba(102,126,234,0.4)' }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>📊 Session Summary</h3>
              {summary.queries.map((q, i) => (
                <div key={i} style={{ padding: 10, marginBottom: 8, borderRadius: 8, background: 'rgba(255,255,255,0.05)' }}>
                  <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{q.filename}</div>
                  <div style={{ fontSize: 12 }}>
                    {q.was_found ? (
                      <>Found • Total: <strong>{q.total_presence_formatted}</strong> • {q.segments.length} segment(s)</>
                    ) : 'Not found during session'}
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 12, marginTop: 8, opacity: 0.6 }}>Total alerts: {summary.total_alerts}</div>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div>
          {/* Stats */}
          <div style={S.card}>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>📊 Live Stats</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
              <div style={{ padding: 12, borderRadius: 10, background: 'rgba(102,126,234,0.12)' }}>
                <div style={S.statLbl}>FPS</div><div style={S.statNum}>{stats.fps}</div>
              </div>
              <div style={{ padding: 12, borderRadius: 10, background: 'rgba(72,187,120,0.12)' }}>
                <div style={S.statLbl}>Objects</div><div style={S.statNum}>{stats.objectCount}</div>
              </div>
            </div>
            <div style={{ padding: 12, borderRadius: 10, background: alerts.length > 0 ? 'rgba(245,101,101,0.12)' : 'rgba(255,255,255,0.05)' }}>
              <div style={S.statLbl}>Alerts</div><div style={{ ...S.statNum, color: alerts.length > 0 ? '#f56565' : '#48bb78' }}>{alerts.length}</div>
            </div>
          </div>

          {/* Detections */}
          <div style={{ ...S.card, marginTop: 14 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>🔎 Detections</h3>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {detections.length === 0 ? <p style={{ fontSize: 13, opacity: 0.5 }}>No objects detected</p> : detections.map((d, i) => (
                <div key={i} style={{ padding: '8px 10px', marginBottom: 6, borderRadius: 8,
                  background: d.is_query_match ? 'rgba(245,101,101,0.15)' : 'rgba(255,255,255,0.05)',
                  display: 'flex', justifyContent: 'space-between', border: d.is_query_match ? '1px solid rgba(245,101,101,0.3)' : 'none' }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{d.is_query_match ? '🔍 ' : ''}{d.label}</span>
                  <span style={{ color: '#48bb78', fontWeight: 700, fontSize: 13 }}>{(d.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* Alerts */}
          <div style={{ ...S.card, marginTop: 14 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>⚠️ Alerts</h3>
            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
              {alerts.length === 0 ? <p style={{ fontSize: 13, opacity: 0.5 }}>No alerts</p> : alerts.map((a, i) => (
                <div key={i} style={S.alertItem(a.severity)}>
                  <div style={{ fontWeight: 700, fontSize: 11, textTransform: 'uppercase', marginBottom: 2 }}>{a.type} • {a.severity}</div>
                  <div style={{ fontSize: 13, marginBottom: 2 }}>{a.message}</div>
                  <div style={{ fontSize: 10, opacity: 0.5 }}>{fmtTime(a.timestamp)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>
    </div>
  );
};

export default LiveMonitor;
