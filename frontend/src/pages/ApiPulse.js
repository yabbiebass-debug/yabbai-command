import React, { useState, useEffect, useRef } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Waveform visualization - VISUAL ONLY, not a metric
const WaveformCanvas = ({ cascadeMode }) => {
  const canvasRef = useRef(null);
  const frameRef = useRef(0);
  const cascadeRef = useRef(cascadeMode);
  useEffect(() => { cascadeRef.current = cascadeMode; }, [cascadeMode]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let raf;
    
    // Visual-only waveform animation (not displaying fake metrics)
    const draw = () => {
      const W = canvas.width = canvas.offsetWidth;
      const H = canvas.height = 80;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(6,14,32,0.8)';
      ctx.fillRect(0, 0, W, H);
      const t = (frameRef.current += 1);
      const layers = cascadeRef.current ? [
        { col: 'rgba(153,69,255,0.7)', amp: 18, freq: 0.012, speed: 0.06 },
        { col: 'rgba(20,241,149,0.7)', amp: 14, freq: 0.02, speed: 0.04 },
        { col: 'rgba(245,166,35,0.6)', amp: 10, freq: 0.028, speed: 0.05 },
        { col: 'rgba(255,80,200,0.5)', amp: 7, freq: 0.038, speed: 0.07 },
      ] : [
        { col: 'rgba(153,69,255,0.3)', amp: 12, freq: 0.015, speed: 0.03 },
        { col: 'rgba(20,241,149,0.6)', amp: 8, freq: 0.025, speed: 0.045 },
        { col: 'rgba(20,241,149,1)', amp: 5, freq: 0.035, speed: 0.06 },
      ];
      layers.forEach(({ col, amp, freq, speed }) => {
        ctx.beginPath();
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.5;
        ctx.shadowColor = col;
        ctx.shadowBlur = cascadeRef.current ? 8 : 0;
        for (let x = 0; x <= W; x++) {
          const y = H / 2 + Math.sin(x * freq + t * speed) * amp + Math.sin(x * freq * 2.1 + t * speed * 1.3) * (amp * 0.3);
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.shadowBlur = 0;
      });
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} style={{ width: '100%', height: 80, borderRadius: 6 }} />;
};

export default function ApiPulse() {
  const [apis, setApis] = useState([]);
  const [cascadeMode, setCascadeMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Fetch REAL health data from backend
  useEffect(() => {
    const loadHealthData = async () => {
      try {
        const response = await fetch(`${API}/health/details`, { credentials: 'include' });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        // Transform backend data to match display format
        setApis(data.services.map(service => ({
          id: service.id,
          name: service.name,
          category: service.category,
          url: service.url,
          status: service.status,
          latency: service.latency || 0,
          error: service.error || null,
          pulsing: false,
        })));
        
        setLastUpdate(new Date(data.timestamp));
        setError(null);
        setLoading(false);
      } catch (e) {
        console.error('Failed to load API health data:', e);
        setError(e.message);
        setLoading(false);
      }
    };

    loadHealthData();
    // Refresh every 10 seconds
    const interval = setInterval(loadHealthData, 10000);
    
    return () => clearInterval(interval);
  }, []);

  const liveCount = apis.filter(a => a.status === 'live').length;
  const avgLatency = apis.length > 0 
    ? Math.round(apis.reduce((sum, a) => sum + a.latency, 0) / apis.length)
    : 0;

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ API PULSE</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>API PULSE</h1>
        {!loading && !error && (
          <>
            <span className="badge badge-green" data-testid="api-pulse-live-count">
              {liveCount}/{apis.length} LIVE
            </span>
            {cascadeMode && <span className="badge badge-amber">CASCADE MODE</span>}
          </>
        )}
        {error && (
          <span className="badge" style={{ background: 'rgba(255,96,96,0.2)', color: '#ff6060' }}>
            CONNECTION ERROR
          </span>
        )}
      </div>

      {/* Waveform - VISUAL ONLY, not displaying metrics */}
      <div className="card fade-in-2" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`live-dot ${error ? '' : ''}`} style={error ? { background: '#ff6060' } : {}} />
            <span className="section-label" style={{ margin: 0 }}>PULSE WAVEFORM (Visual Only)</span>
          </div>
          <label className="toggle-row" style={{ cursor: 'pointer' }}>
            <span className="toggle">
              <input type="checkbox" checked={cascadeMode} onChange={e => setCascadeMode(e.target.checked)} />
              <span className="toggle-slider" />
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: cascadeMode ? '#F5A623' : '#3a5070' }}>CASCADE MODE</span>
          </label>
        </div>
        <WaveformCanvas cascadeMode={cascadeMode} />
        
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px', color: '#3a5070' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>Loading health data...</div>
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '20px', color: '#ff6060' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, marginBottom: 8 }}>Failed to load API health</div>
            <div style={{ fontSize: 11, color: '#3a5070' }}>{error}</div>
          </div>
        ) : (
          <div className="grid-4" style={{ marginTop: 12 }}>
            {[
              { l: 'MONITORED APIS', v: apis.length.toString(), c: '#e8f0ff' },
              { l: 'AVG LATENCY', v: avgLatency > 0 ? `${avgLatency}ms` : 'N/A', c: '#9945FF' },
              { l: 'LIVE ENDPOINTS', v: `${liveCount}/${apis.length}`, c: '#14F195' },
              { l: 'SUCCESS RATE', v: apis.length > 0 ? `${((liveCount / apis.length) * 100).toFixed(1)}%` : 'N/A', c: '#14F195' },
            ].map(({ l, v, c }) => (
              <div key={l}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, color: c }}>{v}</div>
                <div className="stat-label">{l}</div>
              </div>
            ))}
          </div>
        )}
        
        {lastUpdate && (
          <div style={{ marginTop: 12, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070' }}>
            Last updated: {lastUpdate.toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* API Cards - REAL DATA ONLY */}
      {!loading && !error && (
        <div className="grid-4 fade-in-3">
          {apis.map(api => (
            <div key={api.id} className="api-card" data-testid={`api-card-${api.id}`}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: '#e8f0ff', marginBottom: 2 }}>{api.name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070' }}>{api.category}</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                  <span className={`badge ${api.status === 'live' ? 'badge-green' : 'badge-red'}`}>{api.status}</span>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: api.latency < 100 ? '#14F195' : api.latency < 200 ? '#F5A623' : '#ff6060' }}>
                  {api.latency > 0 ? `${api.latency}ms` : 'N/A'}
                </span>
                {api.error && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#ff6060' }}>Error</span>
                )}
              </div>
              <div className="api-latency-bar">
                <div className="api-latency-fill" style={{ width: api.latency > 0 ? `${Math.min((api.latency / 300) * 100, 100)}%` : '0%', background: api.latency < 100 ? '#14F195' : api.latency < 200 ? '#F5A623' : '#ff6060' }} />
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: '#2a3a50', marginTop: 4 }} title={api.url}>
                {api.url.length > 30 ? api.url.substring(0, 30) + '...' : api.url}
              </div>
              {api.error && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: '#ff6060', marginTop: 4 }}>
                  {api.error.length > 40 ? api.error.substring(0, 40) + '...' : api.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div style={{ textAlign: 'center', padding: '40px', color: '#3a5070' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📡</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: '#ff6060', marginBottom: 8 }}>
            DATA GAP
          </div>
          <div style={{ fontSize: 12, marginBottom: 16 }}>
            Unable to fetch API health metrics from backend
          </div>
          <div style={{ fontSize: 11, color: '#3a5070' }}>
            Error: {error}
          </div>
        </div>
      )}
    </div>
  );
}
