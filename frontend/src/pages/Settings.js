import React, { useState, useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import CopyButton from '../components/CopyButton';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const DEFAULT_SETTINGS = {
  treasury_wallet: '7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR',
  main_wallet: '',
  rpc_url: 'https://api.mainnet-beta.solana.com',
  slippage_bps: 50,
  autopayout_threshold: 25.0,
  fee_buffer_sol: 0.005,
  auto_reinvest: true,
  autonomy_level: 75,
  risk_appetite: 40,
  reinvest_rate: 60,
  self_improve: true,
  alert_price_drop_pct: 20.0,
  alert_balance_low_sol: 0.5,
  custom_rpc_enabled: false,
  demo_mode: false,
};

const SECTION = ({ title, children }) => (
  <div className="card" style={{ marginBottom: 20 }}>
    <p className="section-label" style={{ marginBottom: 16 }}>{title}</p>
    {children}
  </div>
);

const Field = ({ label, children, hint }) => (
  <div style={{ marginBottom: 16 }}>
    <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>{label}</label>
    {children}
    {hint && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#2a4060', marginTop: 4 }}>{hint}</div>}
  </div>
);

const ToggleRow = ({ label, checked, onChange, desc }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#e8f0ff' }}>{label}</div>
      {desc && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#2a4060', marginTop: 2 }}>{desc}</div>}
    </div>
    <label className="toggle-row" style={{ cursor: 'pointer', marginLeft: 16 }}>
      <span className="toggle">
        <input type="checkbox" checked={checked} onChange={onChange} />
        <span className="toggle-slider" />
      </span>
    </label>
  </div>
);

export default function Settings() {
  const { success, error: toastError } = useToast();
  const [cfg, setCfg] = useState(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetch(`${API}/settings`)
      .then(r => r.json())
      .then(d => { setCfg(prev => ({ ...prev, ...d })); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const set = (key, val) => { setCfg(prev => ({ ...prev, [key]: val })); setDirty(true); };

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error('Save failed');
      success('Settings saved successfully');
      setDirty(false);
    } catch (e) {
      toastError('Failed to save: ' + e.message);
    }
    setSaving(false);
  };

  if (loading) return (
    <div className="page-container">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '40px 0', color: '#3a5070', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        <span className="thinking-spinner" style={{ width: 20, height: 20 }} />
        Loading settings...
      </div>
    </div>
  );

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ CONFIGURATION</p>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>SETTINGS</h1>
          {dirty && <span className="badge badge-amber">UNSAVED</span>}
        </div>
        <button
          className="btn btn-primary"
          onClick={save}
          disabled={saving || !dirty}
          data-testid="save-settings-btn"
        >
          {saving ? '⧗ Saving...' : '⚡ Save Settings'}
        </button>
      </div>

      <div className="grid-2 fade-in-2">
        {/* Left column */}
        <div>
          <SECTION title="👏 WALLET ADDRESSES">
            <Field label="TREASURY WALLET" hint="SOL sweeps accumulate here">
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="field"
                  value={cfg.treasury_wallet}
                  onChange={e => set('treasury_wallet', e.target.value)}
                  data-testid="treasury-wallet-input"
                />
                <CopyButton text={cfg.treasury_wallet} label="COPY" />
              </div>
            </Field>
            <Field label="MAIN WALLET (SAFE DESTINATION)" hint="Your primary receiving wallet">
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  className="field"
                  value={cfg.main_wallet}
                  onChange={e => set('main_wallet', e.target.value)}
                  placeholder="Your main wallet address..."
                  data-testid="main-wallet-input"
                />
                {cfg.main_wallet && <CopyButton text={cfg.main_wallet} label="COPY" />}
              </div>
            </Field>
            <Field label="FEE BUFFER (SOL)" hint="Always kept in wallet for transaction fees">
              <input
                className="field"
                type="number" step="0.001" min="0.001" max="0.1"
                value={cfg.fee_buffer_sol}
                onChange={e => set('fee_buffer_sol', parseFloat(e.target.value))}
              />
            </Field>
          </SECTION>

          <SECTION title="🌐 NETWORK">
            <ToggleRow
              label="Custom RPC Endpoint"
              desc="Use your own Solana RPC (Helius, QuickNode, etc.)"
              checked={cfg.custom_rpc_enabled}
              onChange={e => set('custom_rpc_enabled', e.target.checked)}
            />
            {cfg.custom_rpc_enabled && (
              <Field label="RPC URL" hint="Leave blank to use public mainnet-beta" style={{ marginTop: 12 }}>
                <input
                  className="field"
                  value={cfg.rpc_url}
                  onChange={e => set('rpc_url', e.target.value)}
                  placeholder="https://your-rpc.provider.com"
                />
              </Field>
            )}
            <Field label="DEFAULT SLIPPAGE (BPS)" hint="100 bps = 1%">
              <div style={{ display: 'flex', gap: 8 }}>
                {[10, 50, 100, 150].map(v => (
                  <button key={v} className={`btn btn-sm ${cfg.slippage_bps === v ? 'btn-primary' : 'btn-outline'}`} onClick={() => set('slippage_bps', v)}>
                    {v / 100}%
                  </button>
                ))}
                <input className="field" type="number" value={cfg.slippage_bps} onChange={e => set('slippage_bps', parseInt(e.target.value))} style={{ width: 70 }} />
              </div>
            </Field>
          </SECTION>

          <SECTION title="⚠ ALERTS">
            <Field label="PRICE DROP ALERT (%)" hint="Alert if YABBAI drops more than this %">
              <input
                className="field"
                type="number" step="1" min="1" max="99"
                value={cfg.alert_price_drop_pct}
                onChange={e => set('alert_price_drop_pct', parseFloat(e.target.value))}
              />
            </Field>
            <Field label="LOW BALANCE ALERT (SOL)" hint="Alert when treasury falls below this">
              <input
                className="field"
                type="number" step="0.01" min="0"
                value={cfg.alert_balance_low_sol}
                onChange={e => set('alert_balance_low_sol', parseFloat(e.target.value))}
              />
            </Field>
          </SECTION>
        </div>

        {/* Right column */}
        <div>
          <SECTION title="🤖 AI DEFAULTS">
            {[
              { key: 'autonomy_level', label: 'DEFAULT AUTONOMY LEVEL', color: '#9945FF' },
              { key: 'risk_appetite', label: 'DEFAULT RISK APPETITE', color: '#F5A623' },
              { key: 'reinvest_rate', label: 'DEFAULT REINVESTMENT RATE', color: '#14F195' },
            ].map(({ key, label, color }) => (
              <Field key={key} label={label}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <input
                    className="autonomy-slider"
                    type="range" min={0} max={100}
                    value={cfg[key]}
                    onChange={e => set(key, parseInt(e.target.value))}
                    style={{ flex: 1 }}
                  />
                  <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 900, color, minWidth: 50, textAlign: 'right' }}>
                    {cfg[key]}%
                  </span>
                </div>
              </Field>
            ))}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
              <ToggleRow label="Self-Improvement Mode" desc="AI refines strategies over time" checked={cfg.self_improve} onChange={e => set('self_improve', e.target.checked)} />
              <ToggleRow label="Auto-Reinvest LP" desc="Automatically reinvest LP yield" checked={cfg.auto_reinvest} onChange={e => set('auto_reinvest', e.target.checked)} />
            </div>
          </SECTION>

          <SECTION title="💳 PAYMENT ENGINE">
            <Field label="PAYPAL AUTOPAYOUT THRESHOLD ($)" hint="Minimum balance before auto-payout triggers">
              <input
                className="field"
                type="number" step="1" min="1"
                value={cfg.autopayout_threshold}
                onChange={e => set('autopayout_threshold', parseFloat(e.target.value))}
              />
            </Field>
          </SECTION>

          <SECTION title="🔬 DEV / DEBUG">
            <ToggleRow
              label="Demo Mode"
              desc="Use simulated data instead of live RPC calls"
              checked={cfg.demo_mode}
              onChange={e => set('demo_mode', e.target.checked)}
            />
          </SECTION>

          {/* Quick info */}
          <div className="card" style={{ borderColor: 'rgba(20,241,149,0.12)' }}>
            <p className="section-label" style={{ marginBottom: 10 }}>PLATFORM INFO</p>
            {[
              ['Version', '2.0.0'],
              ['Network', 'Solana Mainnet-Beta'],
              ['Backend', `${BACKEND_URL}`],
              ['DB', 'MongoDB (Atlas)'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.03)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                <span style={{ color: '#3a5070' }}>{k}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ color: '#e8f0ff' }}>{v}</span>
                  {k === 'Backend' && <CopyButton text={v} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Save bar */}
      {dirty && (
        <div style={{
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100,
          background: 'rgba(6,14,32,0.97)', borderTop: '1px solid rgba(153,69,255,0.2)',
          backdropFilter: 'blur(12px)', padding: '14px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#F5A623' }}>
            ⚠ You have unsaved changes
          </span>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-outline btn-sm" onClick={() => { setCfg(DEFAULT_SETTINGS); setDirty(false); }}>Reset</button>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? 'Saving...' : '⚡ Save Settings'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
