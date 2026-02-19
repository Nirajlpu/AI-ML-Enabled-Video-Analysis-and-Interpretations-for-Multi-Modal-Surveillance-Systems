import React, { useState, useRef, useEffect, useCallback } from 'react';

interface Detection {
  label: string;
  confidence: number;
  box: { x: number; y: number; width: number; height: number };
}

interface Alert {
  type: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  timestamp: string;
}

const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:5001';

const styles = {
  container: {
    padding: '32px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    minHeight: '100vh',
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
  },
  header: {
    marginBottom: '32px',
    textAlign: 'center' as const,
    color: 'white'
  },
  title: {
    fontSize: '42px',
    fontWeight: '700',
    marginBottom: '8px',
    textShadow: '2px 2px 4px rgba(0,0,0,0.3)'
  },
  subtitle: {
    fontSize: '16px',
    opacity: 0.9
  },
  mainGrid: {
    display: 'grid',
    gridTemplateColumns: '2fr 1fr',
    gap: '24px',
    marginBottom: '24px'
  },
  section: {
    background: 'white',
    borderRadius: '12px',
    padding: '24px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
  },
  videoContainer: {
    position: 'relative' as const,
    backgroundColor: '#000',
    borderRadius: '8px',
    overflow: 'hidden',
    aspectRatio: '16/9'
  },
  video: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const
  },
  canvas: {
    position: 'absolute' as const,
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    pointerEvents: 'none' as const
  },
  statusBadge: (isActive: boolean) => ({
    position: 'absolute' as const,
    top: '16px',
    right: '16px',
    padding: '8px 16px',
    borderRadius: '20px',
    backgroundColor: isActive ? '#48bb78' : '#e53e3e',
    color: 'white',
    fontWeight: '600',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  }),
  button: (variant: 'primary' | 'danger' | 'secondary', disabled: boolean) => {
    const colors = {
      primary: '#4c51bf',
      danger: '#e53e3e',
      secondary: '#718096'
    };
    return {
      padding: '12px 24px',
      fontSize: '15px',
      fontWeight: '600',
      border: 'none',
      borderRadius: '8px',
      cursor: disabled ? 'not-allowed' : 'pointer',
      backgroundColor: disabled ? '#cbd5e0' : colors[variant],
      color: 'white',
      opacity: disabled ? 0.6 : 1,
      boxShadow: disabled ? 'none' : `0 4px 12px ${colors[variant]}40`,
      transition: 'all 0.3s ease',
      flex: 1,
      minWidth: '140px'
    };
  },
  buttonContainer: {
    display: 'flex',
    gap: '12px',
    marginTop: '16px',
    flexWrap: 'wrap' as const
  },
  alertsContainer: {
    maxHeight: '400px',
    overflowY: 'auto' as const
  },
  alert: (severity: string) => {
    const colors: any = {
      high: { bg: '#fff5f5', border: '#fc8181', text: '#c53030' },
      medium: { bg: '#fffaf0', border: '#f6ad55', text: '#c05621' },
      low: { bg: '#edf2f7', border: '#90cdf4', text: '#2c5282' }
    };
    const color = colors[severity] || colors.low;
    return {
      padding: '12px',
      marginBottom: '12px',
      borderLeft: `4px solid ${color.border}`,
      backgroundColor: color.bg,
      borderRadius: '6px'
    };
  },
  detectionsList: {
    maxHeight: '300px',
    overflowY: 'auto' as const
  },
  detectionItem: {
    padding: '10px',
    marginBottom: '8px',
    backgroundColor: '#f7fafc',
    borderRadius: '6px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  queryImageUpload: {
    marginBottom: '16px',
    padding: '12px',
    backgroundColor: '#edf2f7',
    borderRadius: '8px'
  },
  queryImagePreview: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '8px',
    marginTop: '12px'
  },
  queryImageThumb: {
    width: '60px',
    height: '60px',
    objectFit: 'cover' as const,
    borderRadius: '6px',
    border: '2px solid #cbd5e0'
  },
  statCard: {
    padding: '16px',
    backgroundColor: '#e6f7ff',
    borderRadius: '8px',
    marginBottom: '12px'
  },
  statLabel: {
    fontSize: '12px',
    fontWeight: '600',
    color: '#4a5568',
    textTransform: 'uppercase' as const,
    marginBottom: '4px'
  },
  statValue: {
    fontSize: '28px',
    fontWeight: '700',
    color: '#2d3748'
  }
};

export const LiveMonitor: React.FC = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [queryImages, setQueryImages] = useState<File[]>([]);
  const [queryPreviews, setQueryPreviews] = useState<string[]>([]);
  const [stats, setStats] = useState({ fps: 0, objectCount: 0, alertCount: 0 });
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const frameCountRef = useRef(0);
  const lastFpsUpdateRef = useRef(Date.now());

  const handleQueryImagesSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setQueryImages(files);
    
    // Create preview URLs
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setQueryPreviews(prev => [...prev, e.target?.result as string]);
      };
      reader.readAsDataURL(file);
    });
  };

  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 },
        audio: false
      });
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        setIsStreaming(true);
        
        // Start processing frames
        intervalRef.current = window.setInterval(() => {
          processFrame();
        }, 500); // Process every 500ms (2 FPS)
      }
    } catch (err) {
      console.error('Error accessing webcam:', err);
      alert('Could not access webcam. Please check permissions.');
    }
  };

  const stopWebcam = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    
    setIsStreaming(false);
    setDetections([]);
    frameCountRef.current = 0;
  };

  const processFrame = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    if (!ctx || video.readyState !== video.HAVE_ENOUGH_DATA) return;
    
    // Set canvas size to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // Draw current frame
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Convert to blob and send to backend
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      
      const formData = new FormData();
      formData.append('frame', blob, 'frame.jpg');
      
      // Add query images if any
      queryImages.forEach((img, idx) => {
        formData.append('query_images', img, img.name);
      });
      
      try {
        const response = await fetch(`${API_BASE_URL}/process-frame`, {
          method: 'POST',
          body: formData
        });
        
        if (response.ok) {
          const data = await response.json();
          setDetections(data.detections || []);
          
          // Add new alerts
          if (data.alerts && data.alerts.length > 0) {
            const newAlerts = data.alerts.map((alert: any) => ({
              ...alert,
              timestamp: new Date().toLocaleTimeString()
            }));
            setAlerts(prev => [...newAlerts, ...prev].slice(0, 50)); // Keep last 50
          }
          
          // Update stats
          frameCountRef.current++;
          const now = Date.now();
          const elapsed = (now - lastFpsUpdateRef.current) / 1000;
          if (elapsed >= 1) {
            setStats(prev => ({
              fps: Math.round(frameCountRef.current / elapsed),
              objectCount: data.detections?.length || 0,
              alertCount: data.alert_count || 0
            }));
            frameCountRef.current = 0;
            lastFpsUpdateRef.current = now;
          }
          
          // Draw bounding boxes
          drawDetections(data.detections || []);
        }
      } catch (err) {
        console.error('Frame processing error:', err);
      }
    }, 'image/jpeg', 0.8);
  };

  const drawDetections = (dets: Detection[]) => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!ctx || !canvas) return;
    
    // Clear previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw each detection
    dets.forEach(det => {
      const x = det.box.x * canvas.width;
      const y = det.box.y * canvas.height;
      const w = det.box.width * canvas.width;
      const h = det.box.height * canvas.height;
      
      // Draw box
      ctx.strokeStyle = '#48bb78';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, w, h);
      
      // Draw label
      ctx.fillStyle = '#48bb78';
      ctx.fillRect(x, y - 25, w, 25);
      ctx.fillStyle = 'white';
      ctx.font = 'bold 16px Arial';
      ctx.fillText(`${det.label} ${(det.confidence * 100).toFixed(0)}%`, x + 5, y - 5);
    });
  };

  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, []);

  return (
    <div style={styles.container}>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        .pulse {
          animation: pulse 2s infinite;
        }
      `}</style>

      <div style={styles.header}>
        <h1 style={styles.title}>📹 Live Webcam Monitor</h1>
        <p style={styles.subtitle}>Real-time object detection & behavioral analysis</p>
      </div>

      <div style={styles.mainGrid}>
        <div>
          <div style={styles.section}>
            <div style={styles.videoContainer}>
              <video
                ref={videoRef}
                style={styles.video}
                autoPlay
                playsInline
                muted
              />
              <canvas ref={canvasRef} style={styles.canvas} />
              
              <div style={styles.statusBadge(isStreaming)}>
                <span className={isStreaming ? 'pulse' : ''}>●</span>
                {isStreaming ? 'LIVE' : 'OFFLINE'}
              </div>
            </div>

            <div style={styles.buttonContainer}>
              <button
                onClick={startWebcam}
                disabled={isStreaming}
                style={styles.button('primary', isStreaming)}
              >
                🎥 Start Webcam
              </button>
              <button
                onClick={stopWebcam}
                disabled={!isStreaming}
                style={styles.button('danger', !isStreaming)}
              >
                ⏹️ Stop
              </button>
            </div>
          </div>

          <div style={styles.section}>
            <h3 style={{ marginBottom: '16px', fontSize: '18px', fontWeight: '600' }}>
              🖼️ Query Images (Optional)
            </h3>
            <div style={styles.queryImageUpload}>
              <label>
                <input
                  type="file"
                  multiple
                  accept="image/*"
                  onChange={handleQueryImagesSelect}
                  style={{ display: 'block', fontSize: '14px' }}
                />
              </label>
              {queryPreviews.length > 0 && (
                <div style={styles.queryImagePreview}>
                  {queryPreviews.map((preview, idx) => (
                    <img
                      key={idx}
                      src={preview}
                      alt={`Query ${idx + 1}`}
                      style={styles.queryImageThumb}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div>
          <div style={styles.section}>
            <h3 style={{ marginBottom: '16px', fontSize: '18px', fontWeight: '600' }}>
              📊 Live Stats
            </h3>
            
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Processing Speed</div>
              <div style={styles.statValue}>{stats.fps} FPS</div>
            </div>
            
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Objects Detected</div>
              <div style={styles.statValue}>{stats.objectCount}</div>
            </div>
            
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Active Alerts</div>
              <div style={{ ...styles.statValue, color: stats.alertCount > 0 ? '#e53e3e' : '#48bb78' }}>
                {alerts.length}
              </div>
            </div>

            <h4 style={{ marginTop: '20px', marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>
              Current Detections
            </h4>
            <div style={styles.detectionsList}>
              {detections.length === 0 ? (
                <p style={{ color: '#718096', fontSize: '14px' }}>No objects detected</p>
              ) : (
                detections.map((det, idx) => (
                  <div key={idx} style={styles.detectionItem}>
                    <span style={{ fontWeight: '600' }}>{det.label}</span>
                    <span style={{ color: '#48bb78', fontWeight: '600' }}>
                      {(det.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div style={styles.section}>
            <h3 style={{ marginBottom: '16px', fontSize: '18px', fontWeight: '600' }}>
              ⚠️ Live Alerts
            </h3>
            <div style={styles.alertsContainer}>
              {alerts.length === 0 ? (
                <p style={{ color: '#718096', fontSize: '14px' }}>No alerts</p>
              ) : (
                alerts.map((alert, idx) => (
                  <div key={idx} style={styles.alert(alert.severity)}>
                    <div style={{ fontWeight: '700', fontSize: '13px', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {alert.type} • {alert.severity}
                    </div>
                    <div style={{ fontSize: '14px', marginBottom: '4px' }}>
                      {alert.message}
                    </div>
                    <div style={{ fontSize: '11px', color: '#718096' }}>
                      {alert.timestamp}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveMonitor;
