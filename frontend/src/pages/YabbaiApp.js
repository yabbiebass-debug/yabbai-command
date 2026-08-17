import React, { useState, useEffect, useRef } from 'react';
import PhaseJourney from '../components/PhaseJourney';
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
  const [agentPool, setAgentPool] = useState(null);
  const [yieldData, setYieldData] = useState(null);
  const [settingsDoc, setSettingsDoc] = useState(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const mintRef = useRef(null);

  // Load token mint config
  useEffect(() => {
    fetch(`${API}/token-mint`, { credentials: 'include' })
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
      fetch(`${API}/price-history?mint=${mintRef.current}&limit=60`, { credentials: 'include' })
        .then(r => {
          if (r.status === 429) {
            toastError('Price history rate limited - retrying shortly');
            throw new Error('Rate limited');
          }
          return r.json();
        })
        .then(data => {
          // The endpoint returns { ok, points: [...] }, not a bare array. This
          // checked data.length, which is undefined on an object, so the guard
          // never passed and the chart sat on "Loading price history..." forever
          // even when points were available.
          const points = Array.isArray(data) ? data : (data?.points || []);
          if (points.length > 0) {
            setPriceHistory(points);
            setPrice(points[points.length - 1]?.price ?? null);
          }
          setHistoryLoaded(true);
        })
        .catch((e) => {
          console.error('Price history fetch failed:', e);
          setHistoryLoaded(true);
        });
    };

    loadPriceHistory();
    const historyInterval = setInterval(loadPriceHistory, 30000); // Refresh every 30s
    
    return () => clearInterval(historyInterval);
  }, [mintCfg, toastError]);

  // Poll live price when token is configured
  useEffect(() => {
    if (!mintRef.current) return;
    const poll = () => {
      fetch(`${API}/jupiter-price?mint=${mintRef.current}`, { credentials: 'include' })
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
      fetch(`${API}/token-stats`, { credentials: 'include' })
        .then(r => r.json())
        .then(d => { if (d.ok) setStats(d); })
        .catch(e => console.error('token-stats fetch failed:', e));
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [mintCfg]);

  // Real agent pool state. Replaces the hardcoded phase progress bars.
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch(`${API}/agents/status`, { credentials: 'include' })
        .then(r => (r.ok ? r.json() : null))
        .then(d => { if (!cancelled && d) setAgentPool(d); })
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Measured yield. Reports treasury performance, current holdings, booked
  // revenue and token movement as four separate things, because conflating them
  // is how a position gets presented as a profit.
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch(`${API}/yield?window_days=30`, { credentials: 'include' })
        .then(r => (r.ok ? r.json() : null))
        .then(d => { if (!cancelled && d?.ok) setYieldData(d); })
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // These sliders were local state only: never loaded, never saved, connected to
  // nothing. The backend has had autonomy_level, risk_appetite, reinvest_rate,
  // self_improve and auto_reinvest in settings the whole time, and the agents
  // read them. Load the real values so the controls show actual configuration.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/settings`, { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (cancelled || !d) return;
        setAiConfig({
          autonomy: d.autonomy_level ?? 75,
          risk: d.risk_appetite ?? 40,
          reinvest: d.reinvest_rate ?? 60,
        });
        setToggles({
          selfImprove: d.self_improve ?? true,
          autoReinvest: d.auto_reinvest ?? true,
        });
        setSettingsDoc(d);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const saveAiConfig = async (nextConfig, nextToggles) => {
    if (!settingsDoc) {
      toastError('Settings not loaded yet');
      return;
    }
    setSavingConfig(true);
    try {
      // Send the whole document back: the endpoint replaces rather than patches,
      // so posting only the changed keys would blank everything else.
      const body = {
        ...settingsDoc,
        autonomy_level: nextConfig.autonomy,
        risk_appetite: nextConfig.risk,
        reinvest_rate: nextConfig.reinvest,
        self_improve: nextToggles.selfImprove,
        auto_reinvest: nextToggles.autoReinvest,
      };
      delete body.updated_at;
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSettingsDoc(await res.json());
      setConfigSaved(true);
      setTimeout(() => setConfigSaved(false), 2500);
    } catch (e) {
      toastError(`Could not save configuration: ${e.message}`);
    }
    setSavingConfig(false);
  };

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
          <div style={{ fontSize: 20, lineHeight: 1 }}>âš ï¸</div>
          <div style={{ flex: 1 }}>
            {/* This never meant the data was simulated. It fires whenever the token
                config could not be read, which is usually a failed auth call rather
                than a missing mint. Saying "simulated" when the real cause is a 401
                is the same class of dishonesty as the projected-APY numbers. */}
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: '#F5A623', marginBottom: 4 }}>
              TOKEN CONFIG UNAVAILABLE
            </div>
            <div style={{ fontSize: 13, color: '#e8f0ff', lineHeight: 1.5 }}>
              The token configuration could not be read, so market data is not shown.
              No values on this page are simulated — they are simply absent.
              This usually means the session is not authenticated; sign in at the hub,
              or set the mint in Settings if none is configured.
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
          {/* This button had no onClick — it was inert. Executing a swap needs a
              connected wallet, a live route quote and signing, none of which this
              page does. Rather than fake it, hand off to Jupiter, which performs
              the actual swap with real routing and real slippage. */}
          {/* Built from live state, not hardcoded: direction follows the toggle,
              the mint comes from token config, the amount from the input, and
              slippage from the configured slippage_bps rather than a fixed
              value. Change any of them here and the Jupiter link changes with it. */}
          <a
            href={mintCfg?.configured
              ? (() => {
                  const USDC_MINT = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
                  const inMint = swapFrom === 'USDC' ? USDC_MINT : mintCfg.mint;
                  const outMint = swapFrom === 'USDC' ? mintCfg.mint : USDC_MINT;
                  const params = new URLSearchParams();
                  if (swapAmt && parseFloat(swapAmt) > 0) params.set('inAmount', swapAmt);
                  // Prefer the saved setting; fall back to the on-screen choice.
                  const bps = settingsDoc?.slippage_bps ?? Math.round(slippage * 100);
                  if (bps) params.set('slippageBps', String(bps));
                  const qs = params.toString();
                  return `https://jup.ag/swap/${inMint}-${outMint}${qs ? `?${qs}` : ''}`;
                })()
              : undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-green"
            style={{
              width: '100%', display: 'block', textAlign: 'center',
              textDecoration: 'none', boxSizing: 'border-box',
              pointerEvents: mintCfg?.configured ? 'auto' : 'none',
              opacity: mintCfg?.configured ? 1 : 0.5,
            }}
          >
            {mintCfg?.configured ? 'Open in Jupiter ↗' : 'Configure Token First'}
          </a>
          {currentPrice && (
            <div style={{ marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', lineHeight: 1.5 }}>
              Indicative only: {(1 / currentPrice).toFixed(2)} TOKEN per USDC at the
              current quoted price. The real rate depends on route, pool depth and
              slippage, and is shown by Jupiter at execution.
            </div>
          )}
        </div>

        {/* Agent pool phases, read from /api/agents/status.
            This previously rendered a hardcoded array: PUMP and ESKY permanently
            COMPLETE, MISSION permanently ACTIVE at 68%. Those values described
            nothing — no phase has a completion percentage, and the pool does not
            progress through them in sequence. Every agent walks all five phases
            each cycle. Cycle counts are real; progress bars were not. */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
            <p className="section-label" style={{ margin: 0 }}>AGENT POOL — BY PHASE</p>
            {agentPool?.total_agents != null && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
                {agentPool.total_agents} agents · {agentPool.total_cycles?.toLocaleString()} cycles
              </span>
            )}
          </div>

          {!agentPool ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070', padding: '8px 0' }}>
              DATA GAP — agent pool status unavailable
            </div>
          ) : (
            <PhaseJourney pool={agentPool} />
          )}

          <p style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.5, marginTop: 10 }}>
            Cycle counts measure activity, not income. No phase places a trade or
            collects a fee, so the pool reports $0.00 revenue by design.
          </p>
          <div className="divider" />
          {/* Was a permanently disabled button labelled "Configure Revenue
              System". Four different things get called yield, so they are
              reported apart: a position is not a profit, and a rising price is
              not income. */}
          <div>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 1, color: '#3a5070', marginBottom: 12 }}>
              YIELD &mdash; MEASURED
            </p>

            {!yieldData ? (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070' }}>
                Reading treasury and ledger...
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: 14 }}>
                  <div>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 900, color: '#14F195' }}>
                      {yieldData.treasury_now?.sol != null
                        ? `${yieldData.treasury_now.sol.toFixed(4)} SOL` : 'DATA GAP'}
                    </div>
                    <div className="stat-label">TREASURY SOL</div>
                  </div>
                  <div>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 900, color: '#9945FF' }}>
                      {yieldData.treasury_now?.token_value_usd != null
                        ? `$${yieldData.treasury_now.token_value_usd.toFixed(2)}` : 'DATA GAP'}
                    </div>
                    <div className="stat-label">TOKEN HOLDINGS</div>
                  </div>
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 900,
                      color: yieldData.booked_revenue?.real_income ? '#14F195' : '#3a5070',
                    }}>
                      {yieldData.booked_revenue?.real_income != null
                        ? `$${yieldData.booked_revenue.real_income.toFixed(2)}` : 'DATA GAP'}
                    </div>
                    <div className="stat-label">BOOKED REVENUE</div>
                  </div>
                </div>

                <div style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6 }}>
                  {yieldData.treasury_performance?.available ? (
                    <>
                      Realised treasury performance{' '}
                      <span style={{ fontFamily: 'var(--font-mono)', color: yieldData.treasury_performance.period_return_pct >= 0 ? '#14F195' : '#ff6060' }}>
                        {yieldData.treasury_performance.period_return_pct >= 0 ? '+' : ''}
                        {yieldData.treasury_performance.period_return_pct}%
                      </span>{' '}
                      over {yieldData.treasury_performance.elapsed_days}d, with{' '}
                      {yieldData.treasury_performance.net_flows_sol} SOL of deposits and
                      withdrawals backed out.
                    </>
                  ) : (
                    <>
                      <span style={{ fontFamily: 'var(--font-mono)', color: '#F5A623' }}>DATA GAP</span>
                      {' - '}{yieldData.treasury_performance?.detail
                        || 'not enough treasury history to measure a return yet.'}
                    </>
                  )}
                </div>

                <div style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6 }}>
                  Booked revenue counts reconciled payment-processor income only. It
                  stays at $0.00 until a verified webhook books a real sale - token
                  holdings rising in value is a position, not income.
                </div>

                {yieldData.token_trend?.available && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
                    {yieldData.token_trend.measurements} agent measurements in window
                  </div>
                )}
              </div>
            )}
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
