import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useToast } from '../context/ToastContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function CommandCentre() {
  const { error: toastError } = useToast();
  const [stats, setStats] = useState({
    real_income: 0,
    net_profit: 0,
    agents_active: 0,
    cycles_completed: 0,
    pending_approvals: 0,
    kill_switch: false,
  });
  const [liveStatus, setLiveStatus] = useState(null);
  const [agentStatus, setAgentStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState([]);
  const canvasRef = useRef(null);
  const neuralRef = useRef(null);
  const frameRef = useRef(0);
  const offsets = useRef([0, Math.PI / 3, (2 * Math.PI) / 3]);

  // Load real data from APIs
  useEffect(() => {
    const loadRealData = async () => {
      try {
        // Fetch revenue status
        const revenueRes = await fetch(`${API}/revenue/status`);
        const revenueData = await revenueRes.json();

        // Fetch agent pool status
        const agentRes = await fetch(`${API}/agents/status`);
        const agentData = await agentRes.json();

        // Fetch live tracking status
        const liveRes = await fetch(`${API}/revenue/live/status`);
        const liveData = await liveRes.json();

        // Update stats with REAL data
        setStats({
          real_income: revenueData.real_income || 0,
          net_profit: revenueData.net_profit || 0,
          agents_active: agentData.total_agents || 0,
          cycles_completed: agentData.total_cycles || 0,
          pending_approvals: revenueData.gates?.pending || 0,
          kill_switch: revenueData.gates?.kill_switch || false,
        });

        setLiveStatus(liveData);
        setAgentStatus(agentData);

        // Generate live events from real data
        const newEvents = [];
        const timestamp = Date.now();
        if (agentData.total_revenue > 0) {
          newEvents.push({
            type: 'revenue',
            message: `Revenue: $${agentData.total_revenue.toFixed(2)}`,
            time: new Date().toLocaleTimeString(),
            ts: timestamp,
          });
        }
        if (agentData.total_agents > 0) {
          newEvents.push({
            type: 'agent',
            message: `${agentData.total_agents} agents active`,
            time: new Date().toLocaleTimeString(),
            ts: timestamp + 1, // Ensure unique timestamp
          });
        }
        if (agentData.total_cycles > 0) {
          newEvents.push({
            type: 'cycle',
            message: `${agentData.total_cycles} cycles completed`,
            time: new Date().toLocaleTimeString(),
            ts: timestamp + 2, // Ensure unique timestamp
          });
        }

        setEvents(prev => [...newEvents, ...prev].slice(0, 10));

      } catch (e) {
        console.error('Failed to load command centre data:', e);
        toastError('Failed to load dashboard data');
      }
      setLoading(false);
    };

    loadRealData();
    // Refresh every 5 seconds
    const interval = setInterval(loadRealData, 5000);
    return () => clearInterval(interval);
  }, [toastError]);

  // Waveform canvas (visual only)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let raf;
    const draw = () => {
      const W = canvas.width = canvas.offsetWidth;
      const H = canvas.height = canvas.offsetHeight || 72;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(6,14,32,0.75)';
      ctx.fillRect(0, 0, W, H);
      const layers = [
        { col: 'rgba(153,69,255,0.25)', amp: 14, freq: 0.018, speed: 0.022 },
        { col: 'rgba(20,241,149,0.5)', amp: 10, freq: 0.025, speed: 0.035 },
        { col: 'rgba(20,241,149,0.9)', amp: 6, freq: 0.034, speed: 0.05 },
      ];
      const t = (frameRef.current += 1);
      layers.forEach(({ col, amp, freq, speed }, li) => {
        ctx.beginPath();
        ctx.strokeStyle = col;
        ctx.lineWidth = li === 2 ? 1.5 : 1;
        for (let x = 0; x <= W; x++) {
          const y = H / 2 + Math.sin(x * freq + t * speed + offsets.current[li]) * amp
            + Math.sin(x * freq * 1.7 + t * speed * 0.7) * (amp * 0.4);
          x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      });
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    // Animation loop intentionally runs once - re-running would create duplicate RAF loops
  }, []);

  // Neural network canvas animation (VISUAL ONLY - NOT DISPLAYING METRICS)
  // This animation uses Math.random() only for particle positioning and movement
  // All actual metrics are fetched from real backend APIs above
  useEffect(() => {
    const canvas = neuralRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const N = 40;
    // Random particle positions for visual effect only
    const nodes = Array.from({ length: N }, () => ({
      x: Math.random() * 100,
      y: Math.random() * 100,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
    }));
    let raf;
    const draw = () => {
      const W = canvas.width = canvas.offsetWidth;
      const H = canvas.height = canvas.offsetHeight || 200;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(6,14,32,0.9)';
      ctx.fillRect(0, 0, W, H);
      nodes.forEach(n => {
        n.x = (n.x + n.vx + 100) % 100;
        n.y = (n.y + n.vy + 100) % 100;
      });
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const d = Math.sqrt(dx * dx + dy * dy);
          if (d < 15) {
            ctx.strokeStyle = `rgba(153,69,255,${0.5 * (1 - d / 15)})`;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo((a.x / 100) * W, (a.y / 100) * H);
            ctx.lineTo((b.x / 100) * W, (b.y / 100) * H);
            ctx.stroke();
          }
        }
      }
      nodes.forEach(n => {
        ctx.fillStyle = '#14F195';
        ctx.beginPath();
        ctx.arc((n.x / 100) * W, (n.y / 100) * H, 2, 0, Math.PI * 2);
        ctx.fill();
      });
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    // Animation loop intentionally runs once - re-running would create duplicate RAF loops
  }, []);

  if (loading) {
    return (
      <div className="page-container fade-in">
        <p className="section-label">⚡ COMMAND CENTRE</p>
        <div className="card">
          <p style={{ color: '#3a5070' }}>Loading command centre...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ YABBAI COMMAND CENTRE</p>

      {/* Live Status Banner */}
      <div className="card fade-in-2" style={{ 
        marginBottom: 24,
        background: stats.kill_switch ? 'rgba(255,69,69,0.1)' : 'rgba(20,241,149,0.05)',
        borderColor: stats.kill_switch ? '#ff4545' : '#14F195'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ 
              fontSize: 11, 
              fontWeight: 700, 
              letterSpacing: '0.1em', 
              color: stats.kill_switch ? '#ff4545' : '#14F195',
              marginBottom: 4
            }}>
              {stats.kill_switch ? '🔴 SYSTEM HALTED' : '🟢 SYSTEM OPERATIONAL'}
            </div>
            <p style={{ margin: 0, fontSize: 13, color: '#3a5070' }}>
              {stats.agents_active} agents running • {stats.cycles_completed} cycles completed
              {stats.pending_approvals > 0 && ` • ${stats.pending_approvals} pending approvals`}
            </p>
          </div>
          <div style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: 11, 
            color: '#3a5070' 
          }}>
            Live Refresh: 5s
          </div>
        </div>
      </div>

      {/* Real Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        <div className="card fade-in-3">
          <div className="stat-label">REAL INCOME</div>
          <div style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: 28, 
            fontWeight: 900, 
            color: '#14F195',
            textShadow: '0 0 20px rgba(20,241,149,0.3)'
          }}>
            ${stats.real_income.toFixed(2)}
          </div>
        </div>

        <div className="card fade-in-3">
          <div className="stat-label">NET PROFIT</div>
          <div style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: 28, 
            fontWeight: 900, 
            color: stats.net_profit >= 0 ? '#14F195' : '#ff4545'
          }}>
            ${stats.net_profit.toFixed(2)}
          </div>
        </div>

        <div className="card fade-in-3">
          <div className="stat-label">ACTIVE AGENTS</div>
          <div style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: 28, 
            fontWeight: 900, 
            color: '#9945FF'
          }}>
            {stats.agents_active}
          </div>
        </div>

        <div className="card fade-in-3">
          <div className="stat-label">TOTAL CYCLES</div>
          <div style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: 28, 
            fontWeight: 900, 
            color: '#9945FF'
          }}>
            {stats.cycles_completed}
          </div>
        </div>
      </div>

      {/* Agent Phase Breakdown */}
      {agentStatus && agentStatus.phase_breakdown && (
        <div className="card fade-in-4" style={{ marginBottom: 24 }}>
          <p className="section-label" style={{ marginBottom: 16 }}>AGENT PHASE DISTRIBUTION</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
            {Object.entries(agentStatus.phase_breakdown).map(([phase, data]) => (
              <div key={phase} style={{ textAlign: 'center' }}>
                <div style={{ 
                  fontSize: 24, 
                  fontWeight: 900, 
                  color: '#14F195',
                  marginBottom: 4
                }}>
                  {data.active_agents}
                </div>
                <div style={{ 
                  fontSize: 10, 
                  fontWeight: 700, 
                  letterSpacing: '0.1em', 
                  color: '#3a5070',
                  textTransform: 'uppercase'
                }}>
                  {phase}
                </div>
                <div style={{ fontSize: 9, color: '#3a5070', marginTop: 4 }}>
                  {data.total_cycles} cycles
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Events Feed */}
      <div className="card fade-in-5" style={{ marginBottom: 24 }}>
        <p className="section-label" style={{ marginBottom: 12 }}>LIVE EVENTS</p>
        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
          {events.length === 0 ? (
            <p style={{ color: '#3a5070', fontSize: 13, margin: 0 }}>
              Waiting for events...
            </p>
          ) : (
            events.map((evt) => (
              <div 
                key={`${evt.type}-${evt.ts}-${evt.agent || evt.channel || evt.message}`} 
                style={{ 
                  padding: '8px 12px',
                  background: 'rgba(153,69,255,0.03)',
                  borderRadius: 4,
                  marginBottom: 8,
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <span style={{ color: '#e8f0ff' }}>{evt.message}</span>
                <span style={{ color: '#3a5070', fontSize: 10 }}>{evt.time}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Visual Elements */}
      <div className="card fade-in-6" style={{ marginBottom: 16, padding: 0, overflow: 'hidden' }}>
        <canvas ref={canvasRef} style={{ width: '100%', height: 72, display: 'block' }} />
      </div>

      <div className="card fade-in-7" style={{ padding: 0, overflow: 'hidden' }}>
        <canvas ref={neuralRef} style={{ width: '100%', height: 200, display: 'block' }} />
      </div>
    </div>
  );
}
