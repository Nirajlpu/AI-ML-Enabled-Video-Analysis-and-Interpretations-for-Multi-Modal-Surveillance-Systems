import React, { useState, useRef } from 'react';
import { analyzeVideo, matchVideoQueries, VideoAnalyticsResult, TrackedPerson } from '../services/detectionService';

interface AnalysisState {
  loading: boolean;
  error: string | null;
  result: VideoAnalyticsResult | null;
  mode: 'full' | 'query';
}

const styles = {
  container: {
    padding: '32px',
    background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
    minHeight: '100vh',
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
  },
  header: {
    marginBottom: '40px',
    textAlign: 'center' as const,
  },
  title: {
    fontSize: '42px',
    fontWeight: '700',
    color: '#1a202c',
    marginBottom: '8px',
    letterSpacing: '-0.5px'
  },
  subtitle: {
    fontSize: '16px',
    color: '#718096',
    marginTop: '8px'
  },
  section: {
    background: 'white',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '24px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    border: '1px solid #e2e8f0'
  },
  sectionTitle: {
    fontSize: '18px',
    fontWeight: '600',
    color: '#2d3748',
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  },
  inputContainer: {
    marginTop: '12px'
  },
  fileInput: {
    display: 'block',
    padding: '12px 16px',
    backgroundColor: '#f7fafc',
    border: '2px dashed #cbd5e0',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    fontSize: '14px'
  },
  fileSelected: {
    display: 'inline-block',
    marginTop: '12px',
    padding: '8px 12px',
    backgroundColor: '#c6f6d5',
    color: '#22543d',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '500'
  },
  buttonContainer: {
    display: 'flex',
    gap: '12px',
    marginTop: '24px',
    flexWrap: 'wrap' as const
  },
  button: (isLoading: boolean, isDisabled: boolean, bgColor: string) => ({
    flex: '1',
    minWidth: '200px',
    padding: '14px 24px',
    fontSize: '15px',
    fontWeight: '600',
    border: 'none',
    borderRadius: '8px',
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    transition: 'all 0.3s ease',
    backgroundColor: isDisabled ? '#cbd5e0' : bgColor,
    color: 'white',
    opacity: isDisabled ? 0.6 : 1,
    boxShadow: isDisabled ? 'none' : `0 4px 12px ${bgColor}40`,
  }),
  errorAlert: {
    backgroundColor: '#fed7d7',
    border: '1px solid #fc8181',
    borderRadius: '8px',
    padding: '14px 16px',
    marginBottom: '20px',
    color: '#c53030',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px'
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: '16px',
    marginBottom: '24px'
  },
  statCard: (bgColor: string) => ({
    backgroundColor: bgColor,
    padding: '20px',
    borderRadius: '10px',
    border: '1px solid rgba(0,0,0,0.05)'
  }),
  statLabel: {
    fontSize: '13px',
    fontWeight: '600',
    color: '#4a5568',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    marginBottom: '8px'
  },
  statValue: {
    fontSize: '32px',
    fontWeight: '700',
    color: '#2d3748'
  },
  queryCard: (matched: boolean) => ({
    padding: '16px',
    marginBottom: '12px',
    borderRadius: '10px',
    border: matched ? '2px solid #48bb78' : '2px solid #e2e8f0',
    backgroundColor: matched ? '#f0fdf4' : '#f8f9fa',
    transition: 'all 0.3s ease',
    cursor: 'pointer'
  }),
  queryHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '12px',
    fontSize: '15px',
    fontWeight: '600'
  },
  matchBadge: (matched: boolean) => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 12px',
    borderRadius: '20px',
    fontSize: '12px',
    fontWeight: '600',
    backgroundColor: matched ? '#c6f6d5' : '#e2e8f0',
    color: matched ? '#22543d' : '#4a5568'
  }),
  queryDetails: {
    fontSize: '13px',
    color: '#4a5568',
    lineHeight: '1.6'
  },
  alertCard: (severity: string) => {
    const colors: Record<string, { bg: string; border: string }> = {
      high: { bg: '#fff5f5', border: '#fc8181' },
      medium: { bg: '#fffaf0', border: '#f6ad55' },
      low: { bg: '#edf2f7', border: '#90cdf4' }
    };
    const color = colors[severity] || colors.low;
    return {
      padding: '14px',
      marginBottom: '12px',
      borderLeft: `4px solid ${color.border}`,
      backgroundColor: color.bg,
      borderRadius: '6px'
    };
  },
  alertType: (severity: string) => {
    const colors: Record<string, string> = {
      high: '#c53030',
      medium: '#c05621',
      low: '#2c5282'
    };
    return {
      fontWeight: '700',
      color: colors[severity] || colors.low,
      marginBottom: '6px',
      fontSize: '13px',
      textTransform: 'uppercase' as const,
      letterSpacing: '0.3px'
    };
  },
  loadingSpinner: {
    display: 'inline-block',
    width: '20px',
    height: '20px',
    border: '3px solid rgba(255,255,255,0.3)',
    borderRadius: '50%',
    borderTopColor: 'white',
    animation: 'spin 1s linear infinite'
  }
};

// ─── Person Gallery card ─────────────────────────────────────────────────────
const PersonCard: React.FC<{ person: TrackedPerson; index: number }> = ({ person, index }) => {
  const duration = (person.last_seen - person.first_seen).toFixed(1);
  return (
    <div
      style={{
        background: 'white',
        borderRadius: '14px',
        overflow: 'hidden',
        boxShadow: '0 4px 16px rgba(0,0,0,0.10)',
        border: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        transition: 'transform 0.2s, box-shadow 0.2s',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-4px)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 8px 24px rgba(0,0,0,0.15)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(0)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 16px rgba(0,0,0,0.10)';
      }}
    >
      {/* Image area */}
      <div style={{ position: 'relative', background: '#1a202c', minHeight: '160px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <img
          src={`data:image/jpeg;base64,${person.image}`}
          alt={`Person ${index + 1}`}
          style={{ width: '100%', maxHeight: '220px', objectFit: 'cover', display: 'block' }}
        />
        <span style={{
          position: 'absolute', top: '8px', left: '8px',
          background: 'rgba(0,0,0,0.65)', color: 'white',
          borderRadius: '20px', padding: '3px 10px', fontSize: '12px', fontWeight: '700',
        }}>
          #{index + 1}
        </span>
        <span style={{
          position: 'absolute', top: '8px', right: '8px',
          background: 'rgba(72,187,120,0.9)', color: 'white',
          borderRadius: '20px', padding: '3px 10px', fontSize: '11px', fontWeight: '700',
        }}>
          {(person.confidence * 100).toFixed(0)}% conf
        </span>
      </div>

      {/* Info */}
      <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '7px' }}>
        <div style={{ fontSize: '13px', fontWeight: '700', color: '#2d3748' }}>
          Track ID: <span style={{ color: '#4c51bf' }}>#{person.track_id}</span>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ background: '#e6f7ff', color: '#2c5282', borderRadius: '6px', padding: '3px 8px', fontSize: '11px', fontWeight: '600' }}>
            🕐 First: {person.first_seen.toFixed(1)}s
          </span>
          <span style={{ background: '#fff5f0', color: '#c05621', borderRadius: '6px', padding: '3px 8px', fontSize: '11px', fontWeight: '600' }}>
            🕒 Last: {person.last_seen.toFixed(1)}s
          </span>
        </div>
        <div style={{ fontSize: '12px', color: '#718096' }}>
          ⏱ Duration: <strong style={{ color: '#2d3748' }}>{duration}s</strong>
        </div>
      </div>
    </div>
  );
};

// ─── Main component ───────────────────────────────────────────────────────────
export const VideoAnalyzer: React.FC = () => {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [queryImages, setQueryImages] = useState<File[]>([]);
  const [analysisState, setAnalysisState] = useState<AnalysisState>({
    loading: false,
    error: null,
    result: null,
    mode: 'full'
  });
  const videoInputRef = useRef<HTMLInputElement>(null);
  const queryInputRef = useRef<HTMLInputElement>(null);

  const handleVideoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files?.[0]) {
      setVideoFile(files[0]);
      setAnalysisState(prev => ({ ...prev, error: null }));
    }
  };

  const handleQuerySelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQueryImages(Array.from(e.target.files || []));
  };

  const handleFullAnalysis = async () => {
    if (!videoFile) {
      setAnalysisState(prev => ({ ...prev, error: 'Please select a video first' }));
      return;
    }
    setAnalysisState(prev => ({ ...prev, loading: true, error: null, mode: 'full' }));
    try {
      const result = await analyzeVideo(videoFile, queryImages);
      setAnalysisState(prev => ({ ...prev, loading: false, result }));
    } catch (err) {
      setAnalysisState(prev => ({
        ...prev, loading: false,
        error: err instanceof Error ? err.message : 'Analysis failed'
      }));
    }
  };

  const handleQueryMatching = async () => {
    if (!videoFile) {
      setAnalysisState(prev => ({ ...prev, error: 'Please select a video first' }));
      return;
    }
    if (queryImages.length === 0) {
      setAnalysisState(prev => ({ ...prev, error: 'Please select at least one query image' }));
      return;
    }
    setAnalysisState(prev => ({ ...prev, loading: true, error: null, mode: 'query' }));
    try {
      const results = await matchVideoQueries(videoFile, queryImages);
      setAnalysisState(prev => ({
        ...prev, loading: false,
        result: {
          processed_frames: 0, video_duration_sec: 0,
          object_counts: {}, object_detections: [],
          alerts: [], alert_count: 0, heatmap: [],
          queries: results as any[]
        }
      }));
    } catch (err) {
      setAnalysisState(prev => ({
        ...prev, loading: false,
        error: err instanceof Error ? err.message : 'Query matching failed'
      }));
    }
  };

  const result = analysisState.result;

  return (
    <div style={styles.container}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .fade-in { animation: fadeIn 0.3s ease; }
      `}</style>

      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.title}>🎥 Video Surveillance Analytics</h1>
        <p style={styles.subtitle}>Advanced AI-powered video analysis with object detection &amp; face recognition</p>
      </div>

      {/* Upload Video */}
      <div style={styles.section} className="fade-in">
        <div style={styles.sectionTitle}><span>📹</span><span>Upload Video</span></div>
        <div style={styles.inputContainer}>
          <label style={{ display: 'block', cursor: 'pointer' }}>
            <input type="file" ref={videoInputRef} onChange={handleVideoSelect} accept="video/*" style={{ display: 'none' }} />
            <div style={styles.fileInput}>{videoFile ? `📁 ${videoFile.name}` : '📂 Click to select video file'}</div>
          </label>
          {videoFile && <div style={styles.fileSelected}>✓ Video ready: {(videoFile.size / (1024 * 1024)).toFixed(2)} MB</div>}
        </div>
      </div>

      {/* Query Images */}
      <div style={styles.section} className="fade-in">
        <div style={styles.sectionTitle}>
          <span>🖼️</span><span>Query Images</span>
          <span style={{ fontSize: '12px', color: '#cbd5e0', fontWeight: 'normal' }}>(Optional)</span>
        </div>
        <p style={{ fontSize: '14px', color: '#718096', marginBottom: '12px' }}>
          Upload photos of people or objects to search for in the video
        </p>
        <div style={styles.inputContainer}>
          <label style={{ display: 'block', cursor: 'pointer' }}>
            <input type="file" ref={queryInputRef} onChange={handleQuerySelect} accept="image/*" multiple style={{ display: 'none' }} />
            <div style={styles.fileInput}>
              {queryImages.length > 0 ? `🖼️ ${queryImages.length} image(s) selected` : '🖼️ Click to select query images (multiple allowed)'}
            </div>
          </label>
          {queryImages.length > 0 && <div style={styles.fileSelected}>✓ {queryImages.map(img => img.name).join(', ')}</div>}
        </div>
      </div>

      {/* Action Buttons */}
      <div style={styles.section} className="fade-in">
        <div style={styles.buttonContainer}>
          <button onClick={handleFullAnalysis} disabled={analysisState.loading || !videoFile}
            style={styles.button(analysisState.loading && analysisState.mode === 'full', analysisState.loading || !videoFile, '#4c51bf')}>
            {analysisState.loading && analysisState.mode === 'full'
              ? <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}><span style={styles.loadingSpinner} />Analyzing...</span>
              : <span>📊 Full Analysis</span>}
          </button>
          <button onClick={handleQueryMatching} disabled={analysisState.loading || !videoFile || queryImages.length === 0}
            style={styles.button(analysisState.loading && analysisState.mode === 'query', analysisState.loading || !videoFile || queryImages.length === 0, '#38a169')}>
            {analysisState.loading && analysisState.mode === 'query'
              ? <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}><span style={styles.loadingSpinner} />Matching...</span>
              : <span>🔍 Query Match</span>}
          </button>
        </div>
      </div>

      {/* Error */}
      {analysisState.error && (
        <div style={styles.errorAlert} className="fade-in">
          <span style={{ fontSize: '20px' }}>⚠️</span>
          <span>{analysisState.error}</span>
        </div>
      )}

      {/* ─── FULL ANALYSIS RESULTS ─────────────────────────────────────────── */}
      {result && analysisState.mode === 'full' && (
        <div className="fade-in">
          {/* Summary Stats */}
          <div style={styles.section}>
            <h2 style={{ fontSize: '26px', fontWeight: '700', color: '#2d3748', marginBottom: '20px' }}>📈 Analysis Results</h2>
            <div style={styles.statsGrid}>
              <div style={styles.statCard('#e6f7ff')}>
                <div style={styles.statLabel}>Duration</div>
                <div style={styles.statValue}>{result.video_duration_sec.toFixed(1)}s</div>
              </div>
              <div style={styles.statCard('#f0f9ff')}>
                <div style={styles.statLabel}>Frames Processed</div>
                <div style={styles.statValue}>{result.processed_frames}</div>
              </div>
              <div style={styles.statCard('#f0fff4')}>
                <div style={styles.statLabel}>Unique Persons</div>
                <div style={{ ...styles.statValue, color: '#276749' }}>
                  {result.tracked_persons?.length ?? result.object_counts['person'] ?? 0}
                </div>
              </div>
              <div style={styles.statCard('#fff5f0')}>
                <div style={styles.statLabel}>Alerts</div>
                <div style={{ ...styles.statValue, color: result.alert_count > 0 ? '#e53e3e' : '#48bb78' }}>
                  {result.alert_count}
                </div>
              </div>
            </div>
          </div>

          {/* Object Detections Table */}
          {result.object_detections && result.object_detections.length > 0 && (
            <div style={styles.section}>
              <h3 style={{ fontSize: '20px', fontWeight: '600', color: '#2d3748', marginBottom: '4px' }}>🎯 Object Detections Timeline</h3>
              <p style={{ fontSize: '13px', color: '#718096', marginBottom: '16px' }}>
                <strong>Unique Count</strong> = distinct individuals/objects tracked by ID — not per-frame detections.
              </p>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#edf2f7', borderBottom: '2px solid #cbd5e0' }}>
                      {['Object Type', 'Unique Count', 'First Seen', 'Last Seen', 'Timestamps (seconds)'].map(h => (
                        <th key={h} style={{ padding: '14px', textAlign: h === 'Object Type' || h === 'Timestamps (seconds)' ? 'left' : 'center', fontSize: '13px', fontWeight: '600', color: '#4a5568' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.object_detections.map((d) => (
                      <tr key={d.label} style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '12px', fontSize: '14px', fontWeight: '600' }}>{d.label}</td>
                        <td style={{ padding: '12px', textAlign: 'center', fontWeight: '700', fontSize: '16px', color: '#4c51bf' }}>{d.count}</td>
                        <td style={{ padding: '12px', textAlign: 'center', fontSize: '13px' }}>
                          <span style={{ backgroundColor: '#e6f7ff', padding: '4px 8px', borderRadius: '6px', fontWeight: '600' }}>{d.first_seen?.toFixed(2)}s</span>
                        </td>
                        <td style={{ padding: '12px', textAlign: 'center', fontSize: '13px' }}>
                          <span style={{ backgroundColor: '#fff5f0', padding: '4px 8px', borderRadius: '6px', fontWeight: '600' }}>{d.last_seen?.toFixed(2)}s</span>
                        </td>
                        <td style={{ padding: '12px', fontSize: '12px', color: '#4a5568' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {d.timestamps.slice(0, 10).map((t, i) => (
                              <span key={i} style={{ backgroundColor: '#f7fafc', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', border: '1px solid #e2e8f0' }}>{t.toFixed(1)}s</span>
                            ))}
                            {d.timestamps.length > 10 && <span style={{ padding: '2px 6px', color: '#718096', fontSize: '11px' }}>+{d.timestamps.length - 10} more</span>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Alerts */}
          {result.alerts && result.alerts.length > 0 && (
            <div style={styles.section}>
              <h3 style={{ fontSize: '20px', fontWeight: '600', color: '#2d3748', marginBottom: '16px' }}>⚠️ Alerts &amp; Unusual Behavior</h3>
              <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
                {result.alerts.map((alert, idx) => (
                  <div key={idx} style={styles.alertCard(alert.severity)}>
                    <div style={styles.alertType(alert.severity)}>{alert.type.replace(/_/g, ' ')} • {alert.severity}</div>
                    <div style={{ color: '#4a5568', marginBottom: '6px', fontSize: '14px', lineHeight: '1.5' }}>{alert.message}</div>
                    <div style={{ fontSize: '12px', color: '#a0aec0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span>🕐</span><span>{alert.time_sec.toFixed(2)}s</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Heatmap */}
          {result.heatmap && result.heatmap.length > 0 && (
            <div style={styles.section}>
              <h3 style={{ fontSize: '20px', fontWeight: '600', color: '#2d3748', marginBottom: '16px' }}>🔥 Activity Heatmap</h3>
              <p style={{ fontSize: '13px', color: '#718096', marginBottom: '12px' }}>Showing {result.heatmap.length} activity hotspots</p>
              <div style={{ background: 'linear-gradient(to right, #3b82f6, #06b6d4, #fbbf24, #ef4444)', height: '32px', borderRadius: '8px', marginBottom: '12px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#718096' }}>
                <span>❄️ Low Activity</span>
                <span>🔥 High Activity</span>
              </div>
            </div>
          )}

          {/* ─── Detected Persons Gallery ──────────────────────────────────── */}
          {result.tracked_persons && result.tracked_persons.length > 0 && (
            <div style={styles.section}>
              <h3 style={{ fontSize: '20px', fontWeight: '600', color: '#2d3748', marginBottom: '4px' }}>
                👥 Detected Persons Gallery
              </h3>
              <p style={{ fontSize: '13px', color: '#718096', marginBottom: '20px' }}>
                <strong>{result.tracked_persons.length} unique {result.tracked_persons.length === 1 ? 'person' : 'people'}</strong> detected.
                Best-quality frame captured per person — no need to manually watch the video.
              </p>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: '16px'
              }}>
                {result.tracked_persons.map((person, idx) => (
                  <PersonCard key={person.track_id} person={person} index={idx} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── QUERY MODE RESULTS ─────────────────────────────────────────────── */}
      {result && analysisState.mode === 'query' && (
        <div style={styles.section} className="fade-in">
          <h2 style={{ fontSize: '28px', fontWeight: '700', color: '#2d3748', marginBottom: '24px' }}>🔍 Query Match Results</h2>
          {result.queries && result.queries.length > 0 ? (
            <>
              <div style={{ marginBottom: '20px', padding: '12px', backgroundColor: '#edf2f7', borderRadius: '8px' }}>
                <p style={{ fontSize: '14px', color: '#4a5568', margin: 0 }}>
                  <strong>Total:</strong> {result.queries.length} &nbsp;•&nbsp;
                  <strong>Matched:</strong> <span style={{ color: '#38a169', fontWeight: '700' }}>{result.queries.filter(q => q.matched).length}</span> &nbsp;•&nbsp;
                  <strong>Not Found:</strong> <span style={{ color: '#e53e3e', fontWeight: '700' }}>{result.queries.filter(q => !q.matched).length}</span>
                </p>
              </div>
              <div style={{ display: 'grid', gap: '16px' }}>
                {result.queries.map((query, idx) => (
                  <div key={idx} style={styles.queryCard(query.matched)}
                    onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; }}
                    onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'none'; }}>
                    <div style={styles.queryHeader}>
                      <span>#{idx + 1}</span>
                      <span style={{ flex: 1, color: '#2d3748' }}>{query.filename}</span>
                      <span style={styles.matchBadge(query.matched)}>{query.matched ? '✅ FOUND' : '❌ NOT FOUND'}</span>
                    </div>
                    {(query as any).error ? (
                      <div style={{ padding: '10px', backgroundColor: '#fed7d7', borderRadius: '6px', color: '#c53030', fontSize: '13px' }}>
                        <strong>Error:</strong> {(query as any).error}
                      </div>
                    ) : (
                      <div style={styles.queryDetails}>
                        {query.matched && query.first_match_time_sec != null && (
                          <div style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: '600', color: '#2d3748' }}>First Match:</span>
                            <span style={{ backgroundColor: '#c6f6d5', color: '#22543d', padding: '4px 10px', borderRadius: '6px', fontSize: '12px', fontWeight: '600' }}>
                              {query.first_match_time_sec.toFixed(2)}s
                            </span>
                            {query.match_reason && <span style={{ color: '#718096' }}>• {query.match_reason}</span>}
                          </div>
                        )}
                        {(() => {
                          const labels = (query as any).labels_in_query || (query as any).labels;
                          return labels?.length > 0 && (
                            <div style={{ marginTop: '8px' }}>
                              <span style={{ fontWeight: '600', color: '#4a5568', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Detected Objects:</span>
                              <div style={{ marginTop: '6px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {labels.map((label: string, li: number) => (
                                  <span key={li} style={{ padding: '4px 10px', backgroundColor: '#edf2f7', color: '#2d3748', borderRadius: '6px', fontSize: '12px', fontWeight: '500' }}>{label}</span>
                                ))}
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ padding: '40px', textAlign: 'center', backgroundColor: '#f7fafc', borderRadius: '8px', color: '#718096' }}>
              <p style={{ fontSize: '16px', margin: 0 }}>No query results available</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VideoAnalyzer;
