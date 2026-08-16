import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';
import CopyButton from '../components/CopyButton';
import { Connection, PublicKey, Transaction, SystemProgram, LAMPORTS_PER_SOL } from '@solana/web3.js';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SOL_USD = 178.42;

function formatTs(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

const CustomTip = ({ active, payload, label, unit = '' }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'rgba(6,14,32,0.97)', border: '1px solid rgba(153,69,255,0.25)', borderRadius: 6, padding: '8px 12px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#9945FF', marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={`tooltip-${p.name}-${i}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: p.color }}>
          {p.name}: {p.value}{unit}
        </div>
      ))}
    </div>
  );
};

function EmptyChart({ height = 180 }) {
  return (
    <div style={{ height, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070' }}>No data yet</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#2a4060' }}>Data will populate as you use the platform</div>
    </div>
  );
}

export default function Analytics() {
  const [metrics, setMetrics] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [treasuryHistory, setTreasuryHistory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [missions, setMissions] = useState([]);
  const [mintCfg, setMintCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');
  
  // Treasury sweep state
  const [treasuryWallet, setTreasuryWallet] = useState('');
  const [mainWallet, setMainWallet] = useState('');
  const [treasuryBalance, setTreasuryBalance] = useState(0);
  const [sweeping, setSweeping] = useState(false);
  const [sweepResult, setSweepResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const [metricsR, txR, missionsR, mintR, settingsR] = await Promise.all([
        fetch(`${API}/analytics`, { credentials: 'include',  credentials: 'include' }).then(r => r.json()),
        fetch(`${API}/transactions?limit=100`, { credentials: 'include',  credentials: 'include' }).then(r => r.json()),
        fetch(`${API}/missions`, { credentials: 'include',  credentials: 'include' }).then(r => r.json()),
        fetch(`${API}/token-mint`, { credentials: 'include',  credentials: 'include' }).then(r => r.json()),
        fetch(`${API}/settings`, { credentials: 'include',  credentials: 'include' }).then(r => r.json()),
      ]);
      setMetrics(metricsR);
      setTransactions(Array.isArray(txR) ? txR : []);
      setMissions(Array.isArray(missionsR) ? missionsR : []);
      
      // Load treasury and main wallet from settings
      if (settingsR) {
        setTreasuryWallet(settingsR.treasury_wallet || '');
        setMainWallet(settingsR.main_wallet || '');
        
        // Load treasury balance
        if (settingsR.treasury_wallet) {
          try {
            const balRes = await fetch(`${API}/solana-balance?owner=${settingsR.treasury_wallet}`, { credentials: 'include',  credentials: 'include' });
            const balData = await balRes.json();
            if (balData.ok) {
              setTreasuryBalance(balData.sol || 0);
            }
          } catch (e) {
            console.error('Failed to load treasury balance:', e);
          }
        }
      }
      
      if (mintR.configured) {
        setMintCfg(mintR);
        const phR = await fetch(`${API}/price-history?mint=${mintR.mint}&limit=200`, { credentials: 'include',  credentials: 'include' });
        const phData = await phR.json();
        if (phData.ok) setPriceHistory(phData.points.map((p, i) => ({ ts: formatTs(p.ts), price: p.price, i })));
      }
      
      // Load treasury snapshots ONLY for current treasury wallet
      if (settingsR?.treasury_wallet) {
        const tsR = await fetch(`${API}/treasury-snapshots?limit=200`, { credentials: 'include',  credentials: 'include' });
        const tsData = await tsR.json();
        if (Array.isArray(tsData)) {
          // Filter to only show snapshots for the CURRENT treasury wallet
          const currentWalletSnapshots = tsData.filter(s => 
            s.address && s.address.toLowerCase() === settingsR.treasury_wallet.toLowerCase()
          );
          setTreasuryHistory(currentWalletSnapshots.map((s, i) => ({ 
            ts: formatTs(s.ts), 
            balance: s.balance_sol, 
            usd: (s.balance_sol * SOL_USD).toFixed(2), 
            i 
          })));
        }
      }
    } catch (e) {
      console.error('Failed to load analytics data:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // Build transaction volume by day
  const txByDay = React.useMemo(() => {
    const map = {};
    transactions.forEach(t => {
      const d = new Date(t.created_at);
      const key = `${d.getMonth()+1}/${d.getDate()}`;
      map[key] = (map[key] || 0) + (t.amount_sol || 0);
    });
    return Object.entries(map).slice(-14).map(([k, v]) => ({ day: k, volume: parseFloat(v.toFixed(4)) }));
  }, [transactions]);

  // Mission status breakdown
  const missionPie = React.useMemo(() => {
    const status = {};
    missions.forEach(m => { status[m.status || 'active'] = (status[m.status || 'active'] || 0) + 1; });
    return Object.entries(status).map(([name, value]) => ({ name, value }));
  }, [missions]);

  const PIE_COLORS = ['#9945FF', '#14F195', '#F5A623', '#ff6060'];

  const totalSweptUsd = (metrics?.total_swept_sol || 0) * SOL_USD;
  // Use LIVE treasury balance, not historical snapshots
  const currentTreasuryBalance = treasuryBalance; // This is the real live balance from blockchain
  const latestHistoricalBalance = treasuryHistory[treasuryHistory.length - 1]?.balance || 0;

  // Treasury sweep handler - connects to Phantom wallet
  const handleTreasurySweep = async () => {
    if (!treasuryWallet || !mainWallet) {
      setSweepResult({ type: 'error', message: 'Treasury or main wallet not configured in Settings' });
      return;
    }

    setSweeping(true);
    setSweepResult({ type: 'info', message: '🔐 Validating destination address...' });

    try {
      // STEP 1: Validate destination is whitelisted
      const validateResp = await fetch(`${API}/sweep/validate-destination?address=${mainWallet}`, { credentials: 'include',  credentials: 'include' });
      const validateData = await validateResp.json();
      
      if (!validateData.authorized) {
        setSweepResult({ 
          type: 'error', 
          message: `❌ SECURITY: Destination ${mainWallet.slice(0, 8)}... is NOT authorized. Funds can only be sent to whitelisted addresses.` 
        });
        setSweeping(false);
        return;
      }

      if (treasuryBalance < 50.005) {
        setSweepResult({ type: 'error', message: `Insufficient balance. Need 50.005 SOL (50 + 0.005 fee), have ${treasuryBalance.toFixed(4)} SOL` });
        setSweeping(false);
        return;
      }

      setSweepResult({ type: 'info', message: '✅ Destination authorized. Connecting to Phantom wallet...' });

      // Check if Phantom is installed
      const { solana } = window;
      if (!solana || !solana.isPhantom) {
        setSweepResult({ type: 'error', message: 'Phantom wallet not found. Please install Phantom browser extension.' });
        setSweeping(false);
        return;
      }

      setSweepResult({ type: 'info', message: '🔐 Requesting wallet connection...' });
      
      // Connect to Phantom
      const resp = await solana.connect();
      const publicKey = resp.publicKey.toString();

      // Verify connected wallet matches treasury wallet
      if (publicKey.toLowerCase() !== treasuryWallet.toLowerCase()) {
        setSweepResult({ 
          type: 'error', 
          message: `Wrong wallet connected! Expected treasury wallet ${treasuryWallet.slice(0, 8)}..., but got ${publicKey.slice(0, 8)}...` 
        });
        setSweeping(false);
        return;
      }

      setSweepResult({ type: 'info', message: '📝 Creating transfer transaction...' });

      // Create transfer transaction
      const connection = new Connection('https://api.mainnet-beta.solana.com', 'confirmed');
      const fromPubkey = new PublicKey(treasuryWallet);
      const toPubkey = new PublicKey(mainWallet);

      const transaction = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey,
          toPubkey,
          lamports: 50 * LAMPORTS_PER_SOL, // 50 SOL
        })
      );

      transaction.feePayer = fromPubkey;
      const { blockhash } = await connection.getLatestBlockhash();
      transaction.recentBlockhash = blockhash;

      setSweepResult({ type: 'info', message: '✍️ Please sign the transaction in Phantom...' });

      // Sign and send transaction
      const signed = await solana.signAndSendTransaction(transaction);
      
      setSweepResult({ type: 'info', message: '⏳ Transaction submitted, waiting for confirmation...' });

      // Wait for confirmation
      await connection.confirmTransaction(signed.signature, 'confirmed');

      setSweepResult({ 
        type: 'success', 
        message: `✅ Successfully swept 50 SOL to ${mainWallet.slice(0, 8)}...! Signature: ${signed.signature.slice(0, 16)}...` 
      });

      // Log the sweep in backend
      try {
        await fetch(`${API}/sweep`, { credentials: 'include', 
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from: treasuryWallet,
            to: mainWallet,
            amount_sol: 50,
            signature: signed.signature,
          }),
        });
      } catch (e) {
        console.error('Failed to log sweep:', e);
      }

      // Reload balances after 2 seconds
      setTimeout(() => {
        load();
      }, 2000);

    } catch (error) {
      console.error('Sweep error:', error);
      setSweepResult({ 
        type: 'error', 
        message: `Transaction failed: ${error.message || 'Unknown error'}` 
      });
    }

    setSweeping(false);
  };

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ ANALYTICS</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>ANALYTICS</h1>
        {mintCfg && <span className="badge badge-green">LIVE DATA</span>}
        {!mintCfg && <span className="badge badge-amber">AWAITING MINT CONFIG</span>}
      </div>

      {/* KPI row - REAL WALLET BALANCES */}
      <div className="grid-4 fade-in-2" style={{ marginBottom: 24 }}>
        {[
          { l: 'TREASURY BALANCE', v: `${treasuryBalance.toFixed(6)} SOL`, c: '#9945FF', sub: treasuryWallet ? `${treasuryWallet.slice(0,4)}...${treasuryWallet.slice(-4)}` : '' },
          { l: 'TOTAL TRANSACTIONS', v: metrics?.tx_count ?? '--', c: '#14F195', sub: 'All-time recorded' },
          { l: 'COMBINED WALLET VALUE', v: `${treasuryBalance.toFixed(6)} SOL`, c: '#14F195', sub: `≈ $${(treasuryBalance * SOL_USD).toFixed(2)}` },
          { l: 'SAVED MISSIONS', v: metrics?.mission_count ?? '--', c: '#F5A623', sub: 'Mission configs' },
        ].map(({ l, v, c, sub }) => (
          <div key={l} className="stat-card">
            <div className="stat-value" style={{ background: `linear-gradient(135deg, #e8f0ff 0%, ${c} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', fontSize: 22 }}>{v}</div>
            <div className="stat-label">{l}</div>
            {sub && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070', marginTop: 4 }}>{sub}</div>}
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {['overview', 'price', 'treasury', 'transactions', 'missions'].map(t => (
          <button key={t} className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-outline'}`} onClick={() => setTab(t)}>
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12, color: '#3a5070' }}>
          <span className="thinking-spinner" style={{ width: 24, height: 24, display: 'inline-block', marginBottom: 12 }} />
          <div>Loading analytics...</div>
        </div>
      ) : (
        <>
          {tab === 'overview' && (
            <div className="grid-2 fade-in">
              {/* Treasury balance */}
              <div className="card">
                <p className="section-label" style={{ marginBottom: 12 }}>TREASURY BALANCE (SOL)</p>
                {treasuryHistory.length > 1 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={treasuryHistory}>
                      <defs>
                        <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#9945FF" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#9945FF" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="ts" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} width={45} />
                      <Tooltip content={<CustomTip unit=" SOL" />} />
                      <Area type="monotone" dataKey="balance" name="Balance" stroke="#9945FF" strokeWidth={2} fill="url(#balGrad)" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : <EmptyChart />}
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#e8f0ff', marginTop: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>
                      Live Balance: <span style={{ color: '#14F195', fontWeight: 700 }}>{currentTreasuryBalance.toFixed(4)} SOL</span>
                      &nbsp;≈ <span style={{ color: '#14F195' }}>${(currentTreasuryBalance * SOL_USD).toFixed(2)}</span>
                    </span>
                    {latestHistoricalBalance > 0 && latestHistoricalBalance !== currentTreasuryBalance && (
                      <span style={{ fontSize: 9, color: '#F5A623' }}>
                        ⚠️ Chart shows history from current wallet only
                      </span>
                    )}
                  </div>
                  {treasuryHistory.length === 0 && (
                    <div style={{ fontSize: 9, color: '#3a5070', marginTop: 4 }}>
                      No historical data for this wallet yet. Snapshots will accumulate over time.
                    </div>
                  )}
                </div>
              </div>
              {/* Transaction volume */}
              <div className="card">
                <p className="section-label" style={{ marginBottom: 12 }}>TRANSACTION VOLUME (SOL/DAY)</p>
                {txByDay.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={txByDay}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="day" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} width={45} />
                      <Tooltip content={<CustomTip unit=" SOL" />} />
                      <Bar dataKey="volume" name="Volume" fill="#14F195" radius={[2, 2, 0, 0]} fillOpacity={0.8} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <EmptyChart />}
              </div>
              {/* Mission pie */}
              <div className="card">
                <p className="section-label" style={{ marginBottom: 12 }}>MISSION STATUS</p>
                {missionPie.length > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={missionPie} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
                        {missionPie.map((entry, i) => <Cell key={`cell-${entry.name}-${i}`} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Legend wrapperStyle={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }} />
                      <Tooltip content={<CustomTip />} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : <EmptyChart height={200} />}
              </div>
              {/* Treasury Sweep Action */}
              <div className="card" data-testid="treasury-sweep-widget">
                <p className="section-label" style={{ marginBottom: 14 }}>⚡ TREASURY SWEEP</p>
                
                {/* Current balances */}
                <div style={{ marginBottom: 16, padding: 12, background: 'rgba(153,69,255,0.05)', borderRadius: 6, border: '1px solid rgba(153,69,255,0.2)' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#9945FF', marginBottom: 8 }}>TREASURY WALLET</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070', marginBottom: 8, wordBreak: 'break-all' }}>
                    {treasuryWallet || 'Not configured'}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: '#14F195' }}>
                    Balance: {treasuryBalance.toFixed(4)} SOL
                    <span style={{ color: '#3a5070', fontSize: 10, marginLeft: 8 }}>
                      ≈ ${(treasuryBalance * SOL_USD).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Destination Dropdown - ONLY METAMASK_MAIN and JUPITER_MAIN */}
                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#14F195', marginBottom: 8, display: 'block' }}>
                    🔒 DESTINATION (SELECT AUTHORIZED WALLET)
                  </label>
                  <select
                    className="field"
                    value={mainWallet}
                    onChange={e => setMainWallet(e.target.value)}
                    style={{ 
                      borderColor: mainWallet ? 'rgba(20,241,149,0.3)' : 'rgba(153,69,255,0.18)',
                      cursor: 'pointer'
                    }}
                  >
                    <option value="">Select destination wallet...</option>
                    <option value="7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z">
                      METAMASK_MAIN (7ApE9...cwD7Z)
                    </option>
                    <option value="49nBAJdaTSUyNo5Uepb8HSGXxjX26Pd4x5sJp8PaNoFz">
                      JUPITER_MAIN (49nBA...aNoFz)
                    </option>
                  </select>
                  {mainWallet && (
                    <div style={{ marginTop: 8, padding: 10, background: 'rgba(20,241,149,0.05)', borderRadius: 6, border: '1px solid rgba(20,241,149,0.15)' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#14F195', wordBreak: 'break-all' }}>
                        ✓ {mainWallet}
                      </div>
                    </div>
                  )}
                </div>

                {/* Sweep button */}
                <button
                  className="btn btn-primary"
                  style={{ width: '100%', marginBottom: 12 }}
                  onClick={handleTreasurySweep}
                  disabled={sweeping || !treasuryWallet || !mainWallet || treasuryBalance < 50.005}
                  data-testid="sweep-50-sol-btn"
                >
                  {sweeping ? (
                    <>
                      <span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite', marginRight: 8 }} />
                      PROCESSING...
                    </>
                  ) : (
                    <>⚡ SWEEP 50 SOL TO MAIN WALLET</>
                  )}
                </button>

                {/* Status message */}
                {sweepResult && (
                  <div 
                    style={{ 
                      padding: 12, 
                      borderRadius: 6, 
                      background: sweepResult.type === 'success' ? 'rgba(20,241,149,0.1)' : 
                                 sweepResult.type === 'error' ? 'rgba(255,96,96,0.1)' : 
                                 'rgba(153,69,255,0.1)',
                      border: `1px solid ${sweepResult.type === 'success' ? 'rgba(20,241,149,0.3)' : 
                                          sweepResult.type === 'error' ? 'rgba(255,96,96,0.3)' : 
                                          'rgba(153,69,255,0.3)'}`,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: sweepResult.type === 'success' ? '#14F195' : 
                             sweepResult.type === 'error' ? '#ff6060' : 
                             '#9945FF',
                      lineHeight: 1.5
                    }}
                  >
                    {sweepResult.message}
                  </div>
                )}

                {/* Help text */}
                <div style={{ marginTop: 12, fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070', lineHeight: 1.5 }}>
                  💡 This will transfer 50 SOL from your treasury to your selected destination wallet. You must sign the transaction in Phantom wallet. Requires Phantom browser extension installed and connected to treasury wallet.
                  <div style={{ marginTop: 8, padding: 8, background: 'rgba(20,241,149,0.05)', borderRadius: 4, border: '1px solid rgba(20,241,149,0.1)' }}>
                    <div style={{ color: '#14F195', fontWeight: 700, marginBottom: 4 }}>🔒 SECURITY: Whitelisted Addresses Only</div>
                    <div style={{ color: '#3a5070' }}>
                      Funds can ONLY be sent to these authorized addresses:
                      <div style={{ marginTop: 4, marginLeft: 8 }}>
                        • 7ApE9...cwD7Z (METAMASK_MAIN)<br/>
                        • 49nBA...aNoFz (JUPITER_MAIN)
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === 'price' && (
            <div className="card fade-in">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
                <p className="section-label" style={{ margin: 0 }}>YABBAI PRICE HISTORY</p>
                {mintCfg && <CopyButton text={mintCfg.mint} label="COPY MINT" />}
              </div>
              {mintCfg && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', marginBottom: 12 }}>Mint: {mintCfg.mint}</div>}
              {priceHistory.length > 1 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={priceHistory}>
                    <defs>
                      <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#14F195" stopOpacity={0.2} />
                        <stop offset="100%" stopColor="#14F195" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid />
                    <XAxis dataKey="ts" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} interval={Math.floor(priceHistory.length / 8)} />
                    <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} width={80} tickFormatter={v => `$${v.toFixed(6)}`} />
                    <Tooltip content={<CustomTip />} />
                    <Line type="monotone" dataKey="price" name="Price" stroke="#14F195" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <EmptyChart height={320} />}
            </div>
          )}

          {tab === 'treasury' && (
            <div className="card fade-in">
              <p className="section-label" style={{ marginBottom: 14 }}>TREASURY BALANCE OVER TIME</p>
              {treasuryHistory.length > 1 ? (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <AreaChart data={treasuryHistory}>
                      <defs>
                        <linearGradient id="tGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#9945FF" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#9945FF" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid />
                      <XAxis dataKey="ts" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} interval={Math.floor(treasuryHistory.length / 8)} />
                      <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: '#3a5070' }} tickLine={false} axisLine={false} width={55} tickFormatter={v => v.toFixed(2)} />
                      <Tooltip content={<CustomTip unit=" SOL" />} />
                      <Area type="monotone" dataKey="balance" name="Balance" stroke="#9945FF" strokeWidth={2} fill="url(#tGrad)" />
                    </AreaChart>
                  </ResponsiveContainer>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070', marginTop: 12 }}>
                    {treasuryHistory.length} snapshots recorded
                  </div>
                </>
              ) : <EmptyChart height={280} />}
            </div>
          )}

          {tab === 'transactions' && (
            <div className="card fade-in">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
                <p className="section-label" style={{ margin: 0 }}>TRANSACTION HISTORY</p>
                <span className="badge badge-purple">{transactions.length} RECORDS</span>
              </div>
              {transactions.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(153,69,255,0.15)' }}>
                        {['TYPE', 'AMOUNT', 'FROM', 'TO', 'STATUS', 'SIG', 'TIMESTAMP'].map(h => (
                          <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: '#3a5070', letterSpacing: '0.1em', fontSize: 10 }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map(t => (
                        <tr key={t.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                          <td style={{ padding: '7px 10px' }}><span className={`badge ${t.type === 'sweep' ? 'badge-green' : 'badge-purple'}`}>{t.type}</span></td>
                          <td style={{ padding: '7px 10px', color: '#14F195', fontWeight: 700 }}>{t.amount_sol?.toFixed(4)} SOL</td>
                          <td style={{ padding: '7px 10px', color: '#3a5070' }}>{t.from_address ? t.from_address.slice(0, 8) + '...' : '--'}</td>
                          <td style={{ padding: '7px 10px', color: '#3a5070' }}>{t.to_address ? t.to_address.slice(0, 8) + '...' : '--'}</td>
                          <td style={{ padding: '7px 10px' }}><span className={`badge ${t.status === 'confirmed' ? 'badge-green' : 'badge-amber'}`}>{t.status}</span></td>
                          <td style={{ padding: '7px 10px' }}>
                            {t.sig ? (
                              <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                                <span style={{ color: '#2a4060' }}>{t.sig.slice(0, 10)}...</span>
                                <CopyButton text={t.sig} />
                              </div>
                            ) : '--'}
                          </td>
                          <td style={{ padding: '7px 10px', color: '#2a4060', fontSize: 10 }}>{formatTs(t.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ padding: '32px', textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 12, color: '#3a5070' }}>
                  No transactions recorded yet. Complete a treasury sweep to log your first transaction.
                </div>
              )}
            </div>
          )}

          {tab === 'missions' && (
            <div className="fade-in">
              <div className="grid-2">
                {missions.length > 0 ? missions.map(m => (
                  <div key={m.id} className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <span style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: '#e8f0ff' }}>{m.name}</span>
                      <span className={`badge ${m.status === 'active' ? 'badge-green' : 'badge-amber'}`}>{m.status}</span>
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', marginBottom: 8 }}>{m.mission_type}</div>
                    <div className="grid-3">
                      {[
                        { l: 'AUTONOMY', v: `${m.autonomy}%`, c: '#9945FF' },
                        { l: 'RISK', v: `${m.risk}%`, c: '#F5A623' },
                        // Was "APY EST" from risk*8+200. Missions have no measured
                        // return because nothing executes them; realised treasury
                        // performance lives on the Performance panel instead.
                        { l: 'REINVEST', v: m.reinvest != null ? `${m.reinvest}%` : '--', c: '#9945FF' },
                      ].map(({ l, v, c }) => (
                        <div key={l}>
                          <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: c }}>{v}</div>
                          <div className="stat-label">{l}</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#2a4060', marginTop: 6 }}>
                      Created: {formatTs(m.created_at)}
                    </div>
                  </div>
                )) : (
                  <div className="card" style={{ gridColumn: '1/-1', textAlign: 'center', padding: 40 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#3a5070' }}>No saved missions. Go to Mission Builder to create and save a mission.</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
