import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useToast } from '../context/ToastContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const MISSION_TYPES = [
  'Liquidity Mining Protocol',
  'MEV Arbitrage Bot',
  'Yield Aggregator Strategy',
  'Cross-DEX Arbitrage',
  'NFT Floor Sniping',
  'Token Launch Scout',
  'Funding Rate Harvester',
];

const VALUES = ['DeFi', 'Passive Income', 'Solana', 'AI Autonomy', 'Low Risk', 'High APY', 'Treasury Growth'];

const CONSOLE_LINES = [
  '> Initialising AI mission core...',
  '> Loading risk parameters...',
  '> Scanning Solana mempool...',
  '> Identifying arbitrage windows...',
  '> Calculating optimal entry points...',
  '> Validating treasury constraints...',
  '> Mission plan generated ✔',
];

function generateMissionPlan(config) {
  return `// YABBAI AUTONOMOUS MISSION PLAN\n// Generated: ${new Date().toISOString()}\n// Autonomy: ${config.autonomy}% | Risk: ${config.risk}% | Reinvest: ${config.reinvest}%\n// Type: ${config.missionType}\n\nmission.configure({\n  strategy: "${config.missionType.toLowerCase().replace(/ /g, '_')}",\n  autonomy_level: ${config.autonomy / 100},\n  risk_tolerance: ${config.risk / 100},\n  reinvest_pct: ${config.reinvest / 100},\n  self_improve: ${config.selfImprove},\n  values_locked: ${JSON.stringify(config.lockedValues)},\n});\n\nmission.deploy()\n  .then(ctx => ctx.execute_loop({ interval_ms: 5000 }))\n  .then(result => treasury.sweep(result.yield))\n  .catch(err => logger.alert(err));\n\n// Expected APY range: ${Math.round(config.risk * 8 + 200)}% — ${Math.round(config.risk * 15 + 400)}%\n// Max drawdown: ${(config.risk * 0.3).toFixed(1)}%\n// Daily yield target: $${(config.autonomy * 2.8 + 50).toFixed(2)}`;
}

export default function Mission() {
  const { success, error: toastError } = useToast();
  const [config, setConfig] = useState({
    autonomy: 75, risk: 40, reinvest: 60,
    missionType: MISSION_TYPES[0],
    selfImprove: true, lockedValues: ['DeFi', 'Passive Income'],
    name: '',
  });
  const [consoleLines, setConsoleLines] = useState([]);
  const [thinking, setThinking] = useState(false);
  const [missionPlan, setMissionPlan] = useState('');
  const [deployCount, setDeployCount] = useState(0);
  const [savedMissions, setSavedMissions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [loadingMissions, setLoadingMissions] = useState(true);
  const consoleRef = useRef(null);

  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [consoleLines]);

  const fetchMissions = useCallback(async () => {
    setLoadingMissions(true);
    try {
      const res = await fetch(`${API}/missions`);
      const data = await res.json();
      setSavedMissions(Array.isArray(data) ? data : []);
      setDeployCount(Array.isArray(data) ? data.length : 0);
    } catch (e) {
      console.error('Failed to fetch missions:', e);
    }
    setLoadingMissions(false);
  }, []);

  useEffect(() => { fetchMissions(); }, [fetchMissions]);

  const handleGenerate = async () => {
    setThinking(true);
    setConsoleLines([]);
    setMissionPlan('');
    for (let i = 0; i < CONSOLE_LINES.length; i++) {
      await new Promise(r => setTimeout(r, 300 + Math.random() * 200));
      setConsoleLines(prev => [...prev, CONSOLE_LINES[i]]);
    }
    setMissionPlan(generateMissionPlan(config));
    setThinking(false);
  };

  const handleSave = async () => {
    if (!missionPlan) { toastError('Generate a mission plan first'); return; }
    const name = config.name.trim() || `${config.missionType} #${savedMissions.length + 1}`;
    setSaving(true);
    try {
      const res = await fetch(`${API}/missions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          mission_type: config.missionType,
          autonomy: config.autonomy,
          risk: config.risk,
          reinvest: config.reinvest,
          self_improve: config.selfImprove,
          locked_values: config.lockedValues,
          plan: missionPlan,
          status: 'active',
          estimated_apy: Math.round(config.risk * 8 + 200),
        }),
      });
      if (!res.ok) throw new Error('Save failed');
      success(`Mission “${name}” saved to database`);
      fetchMissions();
    } catch (e) {
      toastError('Failed to save mission: ' + e.message);
    }
    setSaving(false);
  };

  const handleDelete = async (id, name) => {
    setDeleting(id);
    try {
      await fetch(`${API}/missions/${id}`, { method: 'DELETE' });
      success(`Mission “${name}” deleted`);
      fetchMissions();
    } catch { toastError('Delete failed'); }
    setDeleting(null);
  };

  const loadMission = (m) => {
    setConfig(prev => ({
      ...prev,
      missionType: m.mission_type,
      autonomy: m.autonomy,
      risk: m.risk,
      reinvest: m.reinvest,
      name: m.name,
    }));
    if (m.plan) setMissionPlan(m.plan);
    success(`Loaded mission: ${m.name}`);
  };

  const toggleValue = (v) => {
    setConfig(prev => ({
      ...prev,
      lockedValues: prev.lockedValues.includes(v)
        ? prev.lockedValues.filter(x => x !== v)
        : [...prev.lockedValues, v],
    }));
  };

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ MISSION BUILDER</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>MISSION BUILDER</h1>
        <span className="badge badge-green">{deployCount} SAVED</span>
      </div>

      <div className="grid-2 fade-in-2" style={{ marginBottom: 24 }}>
        <div className="card">
          <p className="section-label" style={{ marginBottom: 16 }}>MISSION CONFIGURATION</p>

          <div style={{ marginBottom: 12 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>MISSION NAME</label>
            <input
              className="field"
              placeholder="e.g. Yield Protocol Alpha..."
              value={config.name}
              onChange={e => setConfig(prev => ({ ...prev, name: e.target.value }))}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>STRATEGY TYPE</label>
            <select className="field" value={config.missionType} onChange={e => setConfig(prev => ({ ...prev, missionType: e.target.value }))}>
              {MISSION_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>

          <p className="section-label" style={{ marginBottom: 12 }}>AI PARAMETERS</p>
          {[
            { key: 'autonomy', label: 'Autonomy Level', color: '#9945FF' },
            { key: 'risk', label: 'Risk Appetite', color: '#F5A623' },
            { key: 'reinvest', label: 'Reinvestment Rate', color: '#14F195' },
          ].map(({ key, label, color }) => (
            <div key={key} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 7 }}>
                <span className="stat-label">{label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 900, color }}>{config[key]}%</span>
              </div>
              <input className="autonomy-slider" type="range" min={0} max={100} value={config[key]}
                onChange={e => setConfig(prev => ({ ...prev, [key]: Number(e.target.value) }))} />
            </div>
          ))}

          <div className="divider" />
          <p className="section-label" style={{ marginBottom: 10 }}>LOCKED VALUES</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 16 }}>
            {VALUES.map(v => (
              <button key={v} className={`value-chip ${config.lockedValues.includes(v) ? 'locked' : ''}`} onClick={() => toggleValue(v)}>
                {config.lockedValues.includes(v) ? '🔒' : '🔓'} {v}
              </button>
            ))}
          </div>

          <label className="toggle-row" style={{ cursor: 'pointer', marginBottom: 16 }}>
            <span className="toggle">
              <input type="checkbox" checked={config.selfImprove} onChange={e => setConfig(prev => ({ ...prev, selfImprove: e.target.checked }))} />
              <span className="toggle-slider" />
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: config.selfImprove ? '#9945FF' : '#3a5070' }}>Self-Improvement Mode</span>
          </label>

          <button className="btn btn-primary" style={{ width: '100%', marginBottom: 8 }} onClick={handleGenerate} disabled={thinking} data-testid="generate-mission-btn">
            {thinking ? <><span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite', marginRight: 8 }} />GENERATING...</> : '⚡ GENERATE MISSION PLAN'}
          </button>
          {missionPlan && (
            <button className="btn btn-green" style={{ width: '100%' }} onClick={handleSave} disabled={saving} data-testid="save-mission-btn">
              {saving ? 'Saving...' : '💾 SAVE TO DATABASE'}
            </button>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card" style={{ flex: '0 0 auto' }}>
            <p className="section-label" style={{ marginBottom: 10 }}>AI CONSOLE</p>
            <div ref={consoleRef} className="mission-output" style={{ minHeight: 120 }}>
              {consoleLines.map((line, i) => <div key={i}>{line}</div>)}
              {(thinking || consoleLines.length > 0) && <span className="typewriter-cursor" />}
            </div>
          </div>

          {missionPlan && (
            <div className="card">
              <p className="section-label" style={{ marginBottom: 10 }}>GENERATED MISSION PLAN</p>
              <div className="mission-output">{missionPlan}</div>
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <button className="btn btn-green btn-sm" onClick={handleSave} disabled={saving}>Save Mission</button>
                <button className="btn btn-outline btn-sm" onClick={() => navigator.clipboard?.writeText(missionPlan).then(() => {})}>Copy Plan</button>
              </div>
            </div>
          )}

          <div className="card">
            <p className="section-label" style={{ marginBottom: 12 }}>PROJECTED METRICS</p>
            <div className="grid-2">
              {[
                { l: 'EXPECTED APY', v: `${Math.round(config.risk * 8 + 200)}–${Math.round(config.risk * 15 + 400)}%`, c: '#14F195' },
                { l: 'DAILY YIELD', v: `$${(config.autonomy * 2.8 + 50).toFixed(2)}`, c: '#9945FF' },
                { l: 'MAX DRAWDOWN', v: `${(config.risk * 0.3).toFixed(1)}%`, c: '#F5A623' },
                { l: 'RISK SCORE', v: `${config.risk}/100`, c: '#F5A623' },
              ].map(({ l, v, c }) => (
                <div key={l}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, color: c }}>{v}</div>
                  <div className="stat-label">{l}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Saved Missions Library */}
      <div className="card fade-in-3">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <p className="section-label" style={{ margin: 0 }}>MISSION LIBRARY ({savedMissions.length})</p>
          <button className="btn btn-outline btn-sm" onClick={fetchMissions}>Refresh</button>
        </div>
        {loadingMissions ? (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070' }}>Loading...</div>
        ) : savedMissions.length === 0 ? (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070', padding: '20px 0', textAlign: 'center' }}>
            No saved missions. Generate and save one above.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {savedMissions.map(m => (
              <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', border: '1px solid rgba(153,69,255,0.12)', borderRadius: 6 }}>
                <div>
                  <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: '#e8f0ff' }}>{m.name}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', marginLeft: 10 }}>{m.mission_type}</span>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className={`badge ${m.status === 'active' ? 'badge-green' : 'badge-amber'}`}>{m.status}</span>
                  {m.estimated_apy && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#14F195' }}>{m.estimated_apy}% APY</span>}
                  <button className="btn btn-outline btn-sm" onClick={() => loadMission(m)}>Load</button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(m.id, m.name)} disabled={deleting === m.id}>
                    {deleting === m.id ? '...' : 'Del'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
