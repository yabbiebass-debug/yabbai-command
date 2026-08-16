import React, { useState, useEffect, useRef } from 'react';
import { useToast } from '../context/ToastContext';

const TEMPLATES = [
  { id: 't1', name: 'Cyberpunk Banner', aspect: '1200x630', type: 'social' },
  { id: 't2', name: 'Token Launch Card', aspect: '1080x1080', type: 'social' },
  { id: 't3', name: 'YABBAI Hero', aspect: '1920x1080', type: 'web' },
  { id: 't4', name: 'BASHAM Gold Card', aspect: '800x500', type: 'print' },
  { id: 't5', name: 'Mission Report', aspect: '1200x800', type: 'report' },
];

// Copy shipped here must not assert yields, holder counts, or earnings — those are
// public investment claims and nothing in this codebase measures them. Removed:
// "847% APY — AI-powered treasury management" and "Join 1,337 holders earning
// passive income"; both numbers were invented and neither was ever computed.
const COPY_LINES = [
  'YABBAI — Autonomous Treasury on Solana',
  'BASHAM: The business wealth protocol',
  'From Side Hustle to Autonomous Income Machine',
];

// Mirrors backend/revenue/gates/compliance_gate.py BANNED_CLAIM_PATTERNS. Promo art is
// generated and exported entirely client-side, so it never reaches the backend gate —
// without this check the gate is unenforced on the one surface that faces the public.
const BANNED_CLAIM_PATTERNS = [
  [/guaranteed (returns?|profit|income|results?)/i, 'Guaranteed-returns claim'],
  [/(make|earn) \$?\d+.{0,15}(per|a|each) (day|week|month)/i, 'Income/earnings claim'],
  [/risk[- ]?free/i, "'Risk-free' claim"],
  [/limited spots|only \d+ left|act now|expires (today|soon)/i, 'Fake scarcity'],
  [/\d[\d,.]* ?% ?(apy|apr|returns?|gains?)/i, 'Unsubstantiated yield claim'],
  [/\d[\d,.]* (holders|investors|members|customers|users)/i, 'Unverified count claim'],
  [/as seen (on|in)/i, "'As seen on' claim"],
];

function checkClaims(text) {
  return BANNED_CLAIM_PATTERNS.filter(([re]) => re.test(text || '')).map(([, label]) => label);
}

const PromoCanvas = React.forwardRef(({ template, headline, subline, theme, animating }, canvasRef) => {
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const [W, H] = (template?.aspect || '1200x630').split('x').map(Number);
    const ratio = Math.min(canvas.offsetWidth / W, 1);
    canvas.width = Math.round(W * ratio);
    canvas.height = Math.round(H * ratio);
    const CW = canvas.width;
    const CH = canvas.height;
    const sc = CW / W;
    let raf;
    const isGold = theme === 'basham';

    const draw = (t) => {
      ctx.fillStyle = isGold ? '#0a0a08' : '#060e20';
      ctx.fillRect(0, 0, CW, CH);
      ctx.strokeStyle = isGold ? 'rgba(212,160,23,0.05)' : 'rgba(153,69,255,0.05)';
      ctx.lineWidth = 1;
      for (let x = 0; x < CW; x += 40 * sc) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CH); ctx.stroke(); }
      for (let y = 0; y < CH; y += 40 * sc) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CW, y); ctx.stroke(); }
      const grad = ctx.createRadialGradient(CW * 0.3, CH * 0.5, 0, CW * 0.3, CH * 0.5, CW * 0.6);
      grad.addColorStop(0, isGold ? 'rgba(212,160,23,0.15)' : 'rgba(153,69,255,0.15)');
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, CW, CH);
      ctx.strokeStyle = isGold ? 'rgba(212,160,23,0.6)' : 'rgba(153,69,255,0.6)';
      ctx.lineWidth = 2 * sc;
      ctx.strokeRect(10 * sc, 10 * sc, CW - 20 * sc, CH - 20 * sc);
      const accentColor = isGold ? '#d4a017' : '#9945FF';
      ctx.strokeStyle = accentColor;
      ctx.lineWidth = 3 * sc;
      [0, 1, 2, 3].forEach(corner => {
        const cx = corner % 2 === 0 ? 10 * sc : CW - 10 * sc;
        const cy = corner < 2 ? 10 * sc : CH - 10 * sc;
        const dx = corner % 2 === 0 ? 1 : -1;
        const dy = corner < 2 ? 1 : -1;
        ctx.beginPath(); ctx.moveTo(cx, cy + dy * 25 * sc); ctx.lineTo(cx, cy); ctx.lineTo(cx + dx * 25 * sc, cy); ctx.stroke();
      });
      ctx.beginPath();
      ctx.strokeStyle = isGold ? 'rgba(212,160,23,0.4)' : 'rgba(20,241,149,0.4)';
      ctx.lineWidth = 1.5 * sc;
      for (let x = 0; x <= CW; x += 2) {
        const y = CH * 0.78 + Math.sin(x * 0.03 / sc + t * 0.05) * 10 * sc + Math.sin(x * 0.07 / sc + t * 0.03) * 5 * sc;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
      const fs = Math.max(16 * sc, Math.min(42 * sc, CW * 0.055));
      ctx.fillStyle = '#ffffff';
      ctx.font = `900 ${fs}px Unbounded, sans-serif`;
      ctx.textAlign = 'left';
      ctx.shadowColor = isGold ? '#d4a017' : '#9945FF';
      ctx.shadowBlur = 20 * sc;
      ctx.fillText(headline || 'YABBAI', 40 * sc, CH * 0.42);
      ctx.shadowBlur = 0;
      if (subline) {
        ctx.fillStyle = isGold ? '#d4a017' : '#14F195';
        ctx.font = `500 ${Math.max(10 * sc, fs * 0.45)}px JetBrains Mono, monospace`;
        ctx.fillText(subline, 40 * sc, CH * 0.56);
      }
      ctx.fillStyle = isGold ? 'rgba(212,160,23,0.4)' : 'rgba(153,69,255,0.4)';
      ctx.font = `700 ${Math.max(8 * sc, fs * 0.28)}px Unbounded, sans-serif`;
      ctx.textAlign = 'right';
      ctx.fillText(isGold ? 'BASHAM' : 'YABBAI', CW - 30 * sc, CH - 25 * sc);
      ctx.textAlign = 'left';
      frameRef.current = t + 1;
      if (animating) raf = requestAnimationFrame(() => draw(t + 1));
    };
    draw(frameRef.current);
    return () => { if (raf) cancelAnimationFrame(raf); };
  }, [template, headline, subline, theme, animating, canvasRef]);

  return <canvas ref={canvasRef} style={{ width: '100%', borderRadius: 8, border: '1px solid rgba(153,69,255,0.2)', display: 'block' }} />;
});

export default function Promo() {
  const { success, info, error } = useToast();
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0]);
  const [headline, setHeadline] = useState('YABBAI');
  const [subline, setSubline] = useState(COPY_LINES[0]);
  const [customSub, setCustomSub] = useState(false);
  const [theme, setTheme] = useState('yabbai');
  const [animating, setAnimating] = useState(true);
  const [generated, setGenerated] = useState([]);
  const canvasRef = useRef(null);

  const claimIssues = checkClaims(`${headline} ${subline}`);

  const handleGenerate = () => {
    if (claimIssues.length) {
      error(`Blocked — ${claimIssues.join('; ')}. Rewrite before publishing.`);
      return;
    }
    const entry = { id: Date.now(), template: selectedTemplate.name, headline, subline, theme, ts: new Date().toLocaleTimeString() };
    setGenerated(prev => [entry, ...prev].slice(0, 8));
    success(`Promo generated: ${selectedTemplate.name}`);
  };

  const handleExportPng = () => {
    if (claimIssues.length) {
      error(`Export blocked — ${claimIssues.join('; ')}. Rewrite before publishing.`);
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) { info('Canvas not ready'); return; }
    // Render at full resolution
    const [W, H] = selectedTemplate.aspect.split('x').map(Number);
    const fullCanvas = document.createElement('canvas');
    fullCanvas.width = W;
    fullCanvas.height = H;
    const ctx = fullCanvas.getContext('2d');
    // Scale and draw from the displayed canvas
    ctx.drawImage(canvas, 0, 0, W, H);
    const dataUrl = fullCanvas.toDataURL('image/png', 1.0);
    const link = document.createElement('a');
    link.href = dataUrl;
    link.download = `yabbai-promo-${selectedTemplate.id}-${Date.now()}.png`;
    link.click();
    success('PNG exported!');
  };

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ PROMO GENERATOR</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>PROMO GENERATOR</h1>
        <span className="badge badge-purple">CANVAS ENGINE</span>
      </div>

      <div className="grid-2 fade-in-2" style={{ marginBottom: 24 }}>
        {/* Controls */}
        <div className="card">
          <p className="section-label" style={{ marginBottom: 14 }}>CONFIGURE</p>
          <div style={{ marginBottom: 14 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>TEMPLATE</label>
            <select className="field" value={selectedTemplate.id} onChange={e => setSelectedTemplate(TEMPLATES.find(t => t.id === e.target.value))}>
              {TEMPLATES.map(t => <option key={t.id} value={t.id}>{t.name} ({t.aspect})</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>THEME</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {['yabbai', 'basham'].map(t => (
                <button key={t} className={`btn btn-sm ${theme === t ? 'btn-primary' : 'btn-outline'}`} onClick={() => setTheme(t)}>{t.toUpperCase()}</button>
              ))}
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>HEADLINE</label>
            <input className="field" value={headline} onChange={e => setHeadline(e.target.value)} placeholder="YABBAI" />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>COPY LINE</label>
            {!customSub ? (
              <>
                <select className="field" value={subline} onChange={e => setSubline(e.target.value)} style={{ marginBottom: 6 }}>
                  {COPY_LINES.map(c => <option key={c}>{c}</option>)}
                </select>
                <button className="btn btn-outline btn-sm" onClick={() => setCustomSub(true)}>Custom</button>
              </>
            ) : (
              <>
                <input className="field" value={subline} onChange={e => setSubline(e.target.value)} placeholder="Custom copy line..." style={{ marginBottom: 6 }} />
                <button className="btn btn-outline btn-sm" onClick={() => setCustomSub(false)}>Use presets</button>
              </>
            )}
          </div>
          <label className="toggle-row" style={{ cursor: 'pointer', marginBottom: 16 }}>
            <span className="toggle">
              <input type="checkbox" checked={animating} onChange={e => setAnimating(e.target.checked)} />
              <span className="toggle-slider" />
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: animating ? '#9945FF' : '#3a5070' }}>Live Animation</span>
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleGenerate} data-testid="generate-promo-btn">⚡ GENERATE</button>
            <button className="btn btn-green" style={{ width: '100%' }} onClick={handleExportPng} data-testid="export-png-btn">&#8595; EXPORT PNG</button>
          </div>
        </div>
        {/* Canvas */}
        <div className="card">
          <p className="section-label" style={{ marginBottom: 12 }}>PREVIEW — {selectedTemplate.aspect}</p>
          <PromoCanvas ref={canvasRef} template={selectedTemplate} headline={headline} subline={subline} theme={theme} animating={animating} />
          <div style={{ marginTop: 10, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
            Exports at full resolution: {selectedTemplate.aspect}px
          </div>
        </div>
      </div>

      {generated.length > 0 && (
        <div className="card fade-in">
          <p className="section-label" style={{ marginBottom: 12 }}>GENERATION HISTORY</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {generated.map(g => (
              <div key={g.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', border: '1px solid rgba(153,69,255,0.1)', borderRadius: 6 }}>
                <div>
                  <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: '#e8f0ff' }}>{g.headline}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', marginLeft: 8 }}>{g.template}</span>
                  <span className={`badge badge-${g.theme === 'basham' ? 'gold' : 'purple'}`} style={{ marginLeft: 6 }}>{g.theme}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070' }}>{g.ts}</span>
                  <button className="btn btn-green btn-sm" onClick={handleExportPng}>Export PNG</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
