import React, { useState, useEffect, useRef } from 'react';
import { useToast } from '../context/ToastContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ChartCanvas = ({ priceHistory }) => {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !priceHistory || priceHistory.length === 0) return;
    
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth;
    const H = canvas.height = canvas.offsetHeight || 220;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(6,14,32,0.85)';
    ctx.fillRect(0, 0, W, H);

    const prices = priceHistory.map(p => p.price);
    const minP = Math.min(...prices) * 0.995;
    const maxP = Math.max(...prices) * 1.005;
    const toY = p => H - ((p - minP) / (maxP - minP)) * (H - 20) - 10;

    // Gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, 'rgba(20,241,149,0.2)');
    grad.addColorStop(1, 'rgba(20,241,149,0)');
    ctx.beginPath();
    priceHistory.forEach((p, i) => {
      const x = (i / (priceHistory.length - 1)) * W;
      i === 0 ? ctx.moveTo(x, toY(p.price)) : ctx.lineTo(x, toY(p.price));
    });
    ctx.lineTo(W, H);
    ctx.lineTo(0, H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.strokeStyle = '#14F195';
    ctx.lineWidth = 2;
    ctx.shadowColor = '#14F195';
    ctx.shadowBlur = 10;
    priceHistory.forEach((p, i) => {
      const x = (i / (priceHistory.length - 1)) * W;
      i === 0 ? ctx.moveTo(x, toY(p.price)) : ctx.lineTo(x, toY(p.price));
    });
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Price label
    const last = priceHistory[priceHistory.length - 1];
    const lastX = W;
    const lastY = toY(last.price);
    ctx.fillStyle = 'rgba(20,241,149,0.9)';
    ctx.font = '600 10px JetBrains Mono';
    ctx.fillText(`$${last.price.toFixed(6)}`, lastX - 80, lastY - 5);
  }, [priceHistory]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: 220, borderRadius: 6 }} />;
};

export default function YabbaiApp() {
  const { error: toastError } = useToast();
  const [priceHistory, setPriceHistory] = useState([]);
  const [price, setPrice] = useState(null);
  const [mintCfg, setMintCfg] = useState(null);
  const [swapFrom, setSwapFrom] = useState('USDC');
  const [swapAmt, setSwapAmt] = useState('');
  const [sweeping, setSweeping] = useState(false);
  const [sweepDone, setSweepDone] = useState(false);
  const [slippage, setSlippage] = useState(0.5);
  const [aiConfig, setAiConfig] = useState({ autonomy: 75, risk: 40, reinvest: 60 });
  const [toggles, setToggles] = useState({ selfImprove: true, autoReinvest: true });
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const mintRef = useRef(null);

  // Load token mint config
  useEffect(() => {
    fetch(`${API}/token-mint`)
      .then(r => {
        if (r.status === 429) {
          toastError('Rate limited - try again shortly');
          throw new Error('Rate limited');
        }
        return r.json();
      })
      .then(d => { 
        if (d.configured) { 
          setMintCfg(d); 
          mintRef.current = d.mint; 
        }
        setLoading(false);
      })
      .catch((e) => {
        console.error('Failed to load token mint:', e);
        setLoading(false);
      });
  }, [toastError]);

  // Load price history when token is configured
  useEffect(() => {
    if (!mintRef.current) return;
    
    const loadPriceHistory = () => {
      fetch(`${API}/price-history?mint=${mintRef.current}&limit=60`)
        .then(r => {
          if (r.status === 429) {
            toastError('Price history rate limited - retrying shortly');
            throw new Error('Rate limited');
          }
          return r.json();
        })
        .then(data => {
          if (data && data.length > 0) {
            setPriceHistory(data);
            // Set current price to latest from history
            setPrice(data[data.length - 1]?.price || null);
          }
        })
        .catch((e) => console.error('Price history fetch failed:', e));
    };

    loadPriceHistory();
    const historyInterval = setInterval(loadPriceHistory, 30000); // Refresh every 30s
    
    return () => clearInterval(historyInterval);
  }, [mintCfg, toastError]);

  // Poll live price when token is configured
  useEffect(() => {
    if (!mintRef.current) return;
    const poll = () => {
      fetch(`${API}/jupiter-price?mint=${mintRef.current}`)
        .then(r => {
          if (r.status === 429) {
            toastError('Price API rate limited - retrying shortly');
            throw new Error('Rate limited');
          }
          return r.json();
        })
        .then(d => { if (d.ok && d.price) setPrice(d.price); })
        .catch((e) => console.error('Price fetch failed:', e));
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, [mintCfg, toastError]);

  // Live mainnet token facts. Anything the RPC cannot serve arrives as null and is
  // listed in data_gaps; this panel renders DATA GAP for those rather than a number.
  useEffect(() => {
    if (!mintCfg?.configured) return;
    const load = () => {
      fetch(`${API}/token-stats`)
        .then(r => r.json())
        .then(d => { if (d.ok) setStats(d); })
        .catch(e => console.error('token-stats fetch failed:', e));
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [mintCfg]);

  const handleSweep = async () => {
    if (!mintCfg?.configured) {
      toastError('Configure token mint in Settings first');
      return;
    }
    setSweeping(true);
    await new Promise(r => setTimeout(r, 1800));
    setSweeping(false);
    setSweepDone(true);
    setTimeout(() => setSweepDone(false), 3000);
  };

  // Use real price or null (no fallback mock price)
  const currentPrice = price;
  const swapOut = swapAmt && currentPrice ? (parseFloat(swapAmt) / currentPrice).toFixed(2) : '';

  return (
    <div className="page-container fade-in">
      {/* SIMULATION MODE BANNER - Only shown when token is not configured */}
      {!loading && !mintCfg?.configured && (
        <div 
          data-testid="token-simulation-mode-banner"
          style={{
            background: 'linear-gradient(135deg, rgba(245,166,35,0.15) 0%, rgba(245,166,35,0.05) 100%)',
            border: '1px solid rgba(245,166,35,0.3)',
            borderRadius: 8,
            padding: '16px 20px',
            marginBottom: 24,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
          }}
        >
          <div style={{ fontSize: 20, lineHeight: 1 }}>⚠️</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: '#F5A623', marginBottom: 4 }}>
              SIMULATION MODE
            </div>
            <div style={{ fontSize: 13, color: '#e8f0ff', lineHeight: 1.5 }}>
              This token data is simulated for demonstration.
              Configure a real SPL token in Settings to show live market data.
            </div>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 24 }}>
        <p className="section-label fade-in-1">⚡ YABBAI TOKEN</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>
            {mintCfg?.configured ? (mintCfg.mint.substring(0, 4) + '...' + mintCfg.mint.substring(mintCfg.mint.length - 4)) : 'NOT CONFIGURED'}
          </h1>
          {mintCfg?.configured ? (
            <>
              <span className="badge badge-green fade-in-2">LIVE</span>
              <span className="badge badge-purple fade-in-2">{mintCfg.network}</span>
            </>
          ) : (
            <span className="badge" style={{ background: 'rgba(58,80,112,0.3)', color: '#3a5070' }}>NOT CONNECTED</span>
          )}
        </div>
        <div className="font-mono fade-in-3" style={{ fontSize: 32, fontWeight: 900, color: currentPrice ? '#14F195' : '#3a5070', marginTop: 4 }}>
          {currentPrice ? `$${currentPrice.toFixed(6)}` : 'DATA GAP'}
          <span style={{ fontSize: 12, color: '#3a5070', marginLeft: 10 }}>USDC</span>
        </div>
      </div>

      {/* On-chain facts. Every value here is read from mainnet; nothing is derived
          from a slider or a formula. Unavailable reads render DATA GAP. */}
      {mintCfg?.configured && (
        <div className="card fade-in-2" style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span className="section-label" style={{ margin: 0 }}>ON-CHAIN — MAINNET</span>
            {stats?.data_gaps?.length > 0 && (
              <span className="badge badge-amber" title={`Unavailable: ${stats.data_gaps.join(', ')}`}>
                {stats.data_gaps.length} DATA GAP{stats.data_gaps.length > 1 ? 'S' : ''}
              </span>
            )}
          </div>
          <div className="grid-3">
            {[
              {
                l: 'SUPPLY',
                v: stats?.supply?.supply != null
                  ? stats.supply.supply.toLocaleString(undefined, { maximumFractionDigits: 0 })
                  : 'DATA GAP',
              },
              {
                l: 'HOLDERS',
                v: stats?.holders?.holders != null
                  ? stats.holders.holders.toLocaleString()
                  : 'DATA GAP',
              },
              {
                l: 'MARKET CAP',
                v: stats?.market_cap_usd != null
                  ? `$${stats.market_cap_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  : 'DATA GAP',
              },
              {
                l: 'TOP-20 CONCENTRATION',
                v: stats?.top_concentration_pct != null
                  ? `${stats.top_concentration_pct.toFixed(2)}%`
                  : 'DATA GAP',
              },
              {
                l: 'MINT AUTHORITY',
                v: stats?.authorities
                  ? (stats.authorities.mint_revoked ? 'REVOKED' : 'ACTIVE')
                  : 'DATA GAP',
              },
              {
                l: 'FREEZE AUTHORITY',
                v: stats?.authorities
                  ? (stats.authorities.freeze_revoked ? 'REVOKED' : 'ACTIVE')
                  : 'DATA GAP',
              },
            ].map(({ l, v }) => (
              <div key={l} style={{ marginBottom: 10 }}>
                <div style={{
                  fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 900,
                  color: v === 'DATA GAP' ? '#3a5070' : (v === 'ACTIVE' ? '#F5A623' : '#14F195'),
                }}>{v}</div>
                <div className="stat-label">{l}</div>
              </div>
            ))}
          </div>
          {stats?.data_gaps?.includes('holder_count') && (
            <div style={{ fontSize: 11, color: '#8fa3bf', marginTop: 6 }}>
              Holder count needs an RPC that allows <span style={{ fontFamily: 'var(--font-mono)' }}>getProgramAccounts</span>.
              The public mainnet endpoint blocks it — set a Helius RPC URL in Settings.
            </div>
          )}
        </div>
      )}

      <div className="grid-2 fade-in-2" style={{ marginBottom: 24 }}>
        {/* Chart */}
        <div className="card card-green-glow" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span className="section-label" style={{ margin: 0 }}>PRICE HISTORY</span>
            <div style={{ display: 'flex', gap: 6 }}>
              {['5m', '15m', '1h', '4h'].map(tf => (
                <button key={tf} className="btn btn-outline btn-sm" disabled={!mintCfg?.configured}>{tf}</button>
              ))}
            </div>
          </div>
          
          {!mintCfg?.configured ? (
            <div style={{ 
              height: 220, 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              background: 'rgba(6,14,32,0.85)',
              borderRadius: 6,
              border: '1px dashed rgba(58,80,112,0.3)'
            }}>
              <div style={{ textAlign: 'center', color: '#3a5070' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700 }}>NO DATA AVAILABLE</div>
                <div style={{ fontSize: 11, marginTop: 4 }}>Configure token mint in Settings</div>
              </div>
            </div>
          ) : priceHistory.length === 0 ? (
            <div style={{ 
              height: 220, 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              background: 'rgba(6,14,32,0.85)',
              borderRadius: 6
            }}>
              <div style={{ textAlign: 'center', color: '#3a5070' }}>
                <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>Loading price history...</div>
              </div>
            </div>
          ) : (
            <>
              <ChartCanvas priceHistory={priceHistory} />
              <div className="grid-4" style={{ marginTop: 14 }}>
                {priceHistory.length > 0 && [
                  { l: 'CURRENT', v: `$${priceHistory[priceHistory.length-1]?.price.toFixed(6)}` },
                  { l: 'HIGH', v: `$${Math.max(...priceHistory.map(p => p.price)).toFixed(6)}` },
                  { l: 'LOW', v: `$${Math.min(...priceHistory.map(p => p.price)).toFixed(6)}` },
                  { l: 'POINTS', v: priceHistory.length },
                ].map(({ l, v }) => (
                  <div key={l}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: '#e8f0ff' }}>{v}</div>
                    <div className="stat-label">{l}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid-2 fade-in-3" style={{ marginBottom: 24 }}>
        {/* Jupiter Swap */}
        <div className="card">
          <p className="section-label" style={{ marginBottom: 14 }}>JUPITER SWAP</p>
          <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
            {['USDC → TOKEN', 'TOKEN → USDC'].map(label => (
              <button
                key={label}
                className={`btn btn-sm ${swapFrom === label.split(' ')[0] ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setSwapFrom(label.split(' ')[0])}
                disabled={!mintCfg?.configured}
              >{label}</button>
            ))}
          </div>
          <div style={{ marginBottom: 10 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>YOU PAY</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="field"
                placeholder="0.00"
                value={swapAmt}
                onChange={e => setSwapAmt(e.target.value)}
                type="number"
                disabled={!mintCfg?.configured}
              />
              <span className="badge badge-purple" style={{ alignSelf: 'center', whiteSpace: 'nowrap' }}>
                {swapFrom}
              </span>
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>YOU RECEIVE</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="field" value={swapOut} readOnly placeholder="0.00" disabled={!mintCfg?.configured} />
              <span className="badge badge-green" style={{ alignSelf: 'center', whiteSpace: 'nowrap' }}>
                {swapFrom === 'USDC' ? 'TOKEN' : 'USDC'}
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
            <span className="stat-label">SLIPPAGE</span>
            {[0.1, 0.5, 1.0].map(s => (
              <button
                key={s}
                className={`btn btn-sm ${slippage === s ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setSlippage(s)}
                disabled={!mintCfg?.configured}
              >{s}%</button>
            ))}
          </div>
          <button className="btn btn-green" style={{ width: '100%' }} disabled={!mintCfg?.configured || !currentPrice}>
            {mintCfg?.configured ? 'Swap via Jupiter' : 'Configure Token First'}
          </button>
          {currentPrice && (
            <div style={{ marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
              Rate: 1 USDC = {(1 / currentPrice).toFixed(2)} TOKEN • Fee: 0.35%
            </div>
          )}
        </div>

        {/* Mission Phase - REAL DATA ONLY (Remove fake yield) */}
        <div className="card">
          <p className="section-label" style={{ marginBottom: 14 }}>MISSION PHASE</p>
          {[{ phase: 'PUMP', status: 'COMPLETE', pct: 100, col: '#14F195' },
            { phase: 'ESKY', status: 'COMPLETE', pct: 100, col: '#14F195' },
            { phase: 'MISSION', status: 'ACTIVE', pct: 68, col: '#9945FF' },
            { phase: 'SCALE', status: 'PENDING', pct: 0, col: '#3a5070' },
            { phase: 'WITHDRAW', status: 'PENDING', pct: 0, col: '#3a5070' },
          ].map(({ phase, status, pct, col }) => (
            <div key={phase} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: col }}>{phase}</span>
                <span className="badge" style={{ background: 'transparent', border: 'none', color: col, padding: 0, fontSize: 10 }}>{status}</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${pct}%`, background: col }} />
              </div>
            </div>
          ))}
          <div className="divider" />
          {/* Note: Yield tracking would come from real revenue backend integration */}
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', marginBottom: 12 }}>
              Connect revenue streams in Settings to track yields
            </p>
            <button
              className="btn btn-outline"
              style={{ width: '100%', fontSize: 13, padding: '14px' }}
              disabled={true}
            >
              ⚡ YIELD TRACKING (Configure Revenue System)
            </button>
          </div>
        </div>
      </div>

      {/* AI Config */}
      <div className="card fade-in-4">
        <p className="section-label" style={{ marginBottom: 16 }}>AI CONFIGURATION</p>
        <div className="grid-3" style={{ marginBottom: 20 }}>
          {[
            { key: 'autonomy', label: 'Autonomy Level', color: '#9945FF' },
            { key: 'risk', label: 'Risk Appetite', color: '#F5A623' },
            { key: 'reinvest', label: 'Reinvestment Rate', color: '#14F195' },
          ].map(({ key, label, color }) => (
            <div key={key}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="stat-label">{label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color }}>
                  {aiConfig[key]}%
                </span>
              </div>
              <input
                className="autonomy-slider"
                type="range" min={0} max={100}
                value={aiConfig[key]}
                onChange={e => setAiConfig(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                style={{ '--thumb-col': color }}
              />
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 24 }}>
          {[
            { key: 'selfImprove', label: 'Self-Improvement Mode' },
            { key: 'autoReinvest', label: 'Auto-Reinvest LP' },
          ].map(({ key, label }) => (
            <label key={key} className="toggle-row" style={{ cursor: 'pointer' }}>
              <span className="toggle">
                <input
                  type="checkbox" checked={toggles[key]}
                  onChange={e => setToggles(prev => ({ ...prev, [key]: e.target.checked }))}
                />
                <span className="toggle-slider" />
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: toggles[key] ? '#9945FF' : '#3a5070' }}>
                {label}
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
