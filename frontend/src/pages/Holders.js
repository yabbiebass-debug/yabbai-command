import React, { useEffect, useState, useCallback } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// This page is public. It calls only /api/public/* and never sends credentials:
// the SSO cookie is scoped to .yabbai.network and would otherwise ride along on
// every request from this subdomain. `credentials: 'omit'` keeps the session off
// the public surface entirely.
const PUBLIC_FETCH = { credentials: 'omit', headers: { Accept: 'application/json' } };

const GAP = 'DATA GAP';

function num(v, opts = {}) {
  if (v === null || v === undefined) return GAP;
  return v.toLocaleString(undefined, opts);
}

function usd(v) {
  if (v === null || v === undefined) return GAP;
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function short(addr) {
  if (!addr) return GAP;
  return `${addr.slice(0, 4)}…${addr.slice(-4)}`;
}

/** Sparkline over the recorded price series. Pure SVG, no chart library. */
function PriceChart({ points }) {
  if (!points || points.length < 2) {
    return (
      <div style={{
        height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: '1px dashed rgba(58,80,112,0.35)', borderRadius: 8, color: '#3a5070',
        fontFamily: 'var(--font-mono)', fontSize: 12,
      }}>
        NOT ENOUGH PRICE HISTORY YET
      </div>
    );
  }

  const values = points.map(p => p.price);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const W = 600;
  const H = 160;

  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * W;
      const y = H - ((p.price - min) / span) * (H - 20) - 10;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? '#14F195' : '#ff6060';

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', minWidth: 280, height: H }}
           role="img" aria-label="Recorded price history">
        <defs>
          <linearGradient id="pfade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${d} L${W},${H} L0,${H} Z`} fill="url(#pfade)" />
        <path d={d} fill="none" stroke={stroke} strokeWidth="2" />
      </svg>
    </div>
  );
}

function Stat({ label, value, tone }) {
  const isGap = value === GAP;
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 900,
        color: isGap ? '#3a5070' : (tone || '#e8f0ff'),
        overflow: 'hidden', textOverflow: 'ellipsis',
      }}>
        {value}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 0.6,
        color: '#3a5070', marginTop: 4,
      }}>
        {label}
      </div>
    </div>
  );
}

export default function Holders() {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        fetch(`${API}/public/token`, PUBLIC_FETCH).then(r => r.json()),
        fetch(`${API}/public/price-history?limit=200`, PUBLIC_FETCH).then(r => r.json()),
      ]);
      setStats(s);
      setHistory(Array.isArray(h.points) ? h.points : []);
      setError(null);
    } catch (e) {
      setError('Unable to reach the token API.');
    }
    setLoading(false);
  }, []);

  // public/index.html is shared by both builds and carries the command-app title.
  // Override it here so the holder view does not present itself as the admin tool.
  useEffect(() => {
    document.title = 'YabbAI Token (YABBAI) — Live Statistics';
    const desc = document.querySelector('meta[name="description"]');
    const text =
      'Live on-chain statistics for YabbAI Token (YABBAI) on Solana: supply, price, ' +
      'market cap, holders, authority status and treasury balance. Every figure is ' +
      'read from mainnet and independently verifiable.';
    if (desc) {
      desc.setAttribute('content', text);
    } else {
      const m = document.createElement('meta');
      m.name = 'description';
      m.content = text;
      document.head.appendChild(m);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const configured = stats?.ok && stats?.configured;
  const gaps = stats?.data_gaps || [];

  return (
    <div style={{
      minHeight: '100vh', background: '#060E20', color: '#e8f0ff',
      fontFamily: 'Inter, system-ui, sans-serif', padding: '32px 20px',
    }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>

        <header style={{ marginBottom: 28 }}>
          {/* Banner is decorative; the logo carries the accessible name. */}
          {/* JPEG rather than PNG: 152 KB vs 1.18 MB for the same 1600x640 render.
              The source PNG was 1.79 MB, which is a punishing first paint on mobile. */}
          <img
            src="/yabbai-banner.jpg"
            alt=""
            aria-hidden="true"
            width="1600"
            height="640"
            style={{
              width: '100%', height: 'auto', borderRadius: 10, marginBottom: 22,
              border: '1px solid rgba(212,160,23,0.25)', display: 'block',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
            <img
              src="/yabbai-logo.png"
              alt="YabbAI Token"
              width="52"
              height="52"
              style={{ borderRadius: '50%', flexShrink: 0 }}
            />
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 1.4,
                color: '#9945FF',
              }}>
                YABBAI · HOLDER VIEW
              </div>
              <h1 style={{ fontSize: 30, fontWeight: 900, margin: 0, letterSpacing: -0.5 }}>
                YabbAI Token
              </h1>
            </div>
          </div>
          <p style={{ color: '#8fa3bf', fontSize: 13, marginTop: 8, lineHeight: 1.6 }}>
            Every figure below is read live from Solana mainnet or from Jupiter, and is
            independently verifiable on any block explorer. Nothing here is projected or
            estimated — values that cannot be read show <strong>DATA GAP</strong> rather
            than a substituted number.
          </p>
        </header>

        {loading && (
          <div style={{ color: '#8fa3bf', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
            Reading mainnet…
          </div>
        )}

        {error && (
          <div style={{
            padding: 14, borderRadius: 8, background: 'rgba(255,80,80,0.08)',
            border: '1px solid rgba(255,80,80,0.3)', color: '#ff9090', fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {!loading && !error && !configured && (
          <div style={{
            padding: 20, borderRadius: 8, background: 'rgba(58,80,112,0.14)',
            border: '1px dashed rgba(58,80,112,0.4)', color: '#8fa3bf', fontSize: 13,
          }}>
            No token is configured yet. Statistics will appear here once the mint is live.
          </div>
        )}

        {configured && (
          <>
            {/* Headline price */}
            <section style={{
              padding: 20, borderRadius: 10, background: 'rgba(10,17,40,0.7)',
              border: '1px solid rgba(153,69,255,0.22)', marginBottom: 18,
            }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'baseline' }}>
                <div>
                  <div style={{
                    fontFamily: 'var(--font-mono)', fontSize: 34, fontWeight: 900,
                    color: stats.price_usd == null ? '#3a5070' : '#14F195',
                  }}>
                    {stats.price_usd == null ? GAP : `$${stats.price_usd.toFixed(8)}`}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
                    PRICE (USD)
                  </div>
                </div>
                <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#8fa3bf' }}>
                    {short(stats.mint)}
                  </div>
                  <a
                    href={`https://solscan.io/token/${stats.mint}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 11, color: '#9945FF', textDecoration: 'none' }}
                  >
                    verify on Solscan ↗
                  </a>
                </div>
              </div>
            </section>

            {/* Chart */}
            <section style={{
              padding: 18, borderRadius: 10, background: 'rgba(10,17,40,0.7)',
              border: '1px solid rgba(58,80,112,0.25)', marginBottom: 18,
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 1,
                color: '#3a5070', marginBottom: 12,
              }}>
                RECORDED PRICE HISTORY
              </div>
              <PriceChart points={history} />
            </section>

            {/* Core stats */}
            <section style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 20, padding: 20, borderRadius: 10, background: 'rgba(10,17,40,0.7)',
              border: '1px solid rgba(58,80,112,0.25)', marginBottom: 18,
            }}>
              <Stat label="MARKET CAP" value={usd(stats.market_cap_usd)} />
              <Stat label="CIRCULATING SUPPLY" value={num(stats.supply, { maximumFractionDigits: 0 })} />
              <Stat label="HOLDERS" value={num(stats.holders)} />
              <Stat
                label="TOP-20 CONCENTRATION"
                value={stats.top_concentration_pct == null ? GAP : `${stats.top_concentration_pct.toFixed(2)}%`}
              />
            </section>

            {/* Trust signals */}
            <section style={{
              padding: 20, borderRadius: 10, background: 'rgba(10,17,40,0.7)',
              border: '1px solid rgba(58,80,112,0.25)', marginBottom: 18,
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 1,
                color: '#3a5070', marginBottom: 14,
              }}>
                AUTHORITY STATUS
              </div>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 20,
              }}>
                <Stat
                  label="MINT AUTHORITY"
                  value={stats.mint_authority_revoked == null
                    ? GAP : (stats.mint_authority_revoked ? 'REVOKED' : 'ACTIVE')}
                  tone={stats.mint_authority_revoked ? '#14F195' : '#F5A623'}
                />
                <Stat
                  label="FREEZE AUTHORITY"
                  value={stats.freeze_authority_revoked == null
                    ? GAP : (stats.freeze_authority_revoked ? 'REVOKED' : 'ACTIVE')}
                  tone={stats.freeze_authority_revoked ? '#14F195' : '#F5A623'}
                />
              </div>
              <p style={{ color: '#8fa3bf', fontSize: 12, marginTop: 14, lineHeight: 1.6 }}>
                <strong>REVOKED</strong> means the capability is permanently gone and cannot be
                restored. An <strong>ACTIVE</strong> mint authority means new supply can still be
                created; an <strong>ACTIVE</strong> freeze authority means individual token accounts
                can still be frozen. Both are verifiable on-chain.
              </p>
            </section>

            {/* Treasury */}
            <section style={{
              padding: 20, borderRadius: 10, background: 'rgba(10,17,40,0.7)',
              border: '1px solid rgba(58,80,112,0.25)', marginBottom: 18,
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 1,
                color: '#3a5070', marginBottom: 14,
              }}>
                TREASURY
              </div>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 20,
              }}>
                <Stat
                  label="SOL BALANCE"
                  value={stats.treasury_sol == null ? GAP : `${stats.treasury_sol.toFixed(4)} SOL`}
                />
                <Stat
                  label="TOKEN BALANCE"
                  value={num(stats.treasury_token_balance, { maximumFractionDigits: 0 })}
                />
              </div>
              {stats.treasury_address && (
                <div style={{ marginTop: 14 }}>
                  <a
                    href={`https://solscan.io/account/${stats.treasury_address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontFamily: 'var(--font-mono)', fontSize: 11,
                      color: '#9945FF', textDecoration: 'none', wordBreak: 'break-all',
                    }}
                  >
                    {stats.treasury_address} ↗
                  </a>
                  <p style={{ color: '#8fa3bf', fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>
                    The treasury address is published so its balance and every transaction
                    can be audited independently. Do not take these numbers on trust —
                    check them.
                  </p>
                </div>
              )}
            </section>

            {gaps.length > 0 && (
              <section style={{
                padding: 14, borderRadius: 8, background: 'rgba(245,166,35,0.07)',
                border: '1px solid rgba(245,166,35,0.25)', fontSize: 12, color: '#e8d5b0',
              }}>
                <strong>{gaps.length} value{gaps.length > 1 ? 's' : ''} unavailable:</strong>{' '}
                {gaps.join(', ')}. These show DATA GAP rather than a guessed number.
              </section>
            )}

            <footer style={{
              marginTop: 26, paddingTop: 16, borderTop: '1px solid rgba(58,80,112,0.25)',
              color: '#3a5070', fontSize: 11, fontFamily: 'var(--font-mono)',
              display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between',
            }}>
              <span>MAINNET-BETA · REFRESHES EVERY 60s</span>
              <span>{stats.fetched_at ? `READ ${new Date(stats.fetched_at).toLocaleTimeString()}` : ''}</span>
            </footer>

            <p style={{ color: '#3a5070', fontSize: 11, marginTop: 18, lineHeight: 1.7 }}>
              This page reports on-chain data only. It is not financial advice, not an offer,
              and not a solicitation. Token values can fall to zero.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
