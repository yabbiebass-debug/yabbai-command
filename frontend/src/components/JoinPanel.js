import React, { useCallback, useEffect, useState } from 'react';

/**
 * The next step, for someone who just read the numbers.
 *
 * Before this, the public page ended at the data. A visitor arriving from search
 * could verify everything and then had nowhere to go — no way to buy, no way to
 * find anyone, no way to pass it on. Discoverability without a next step just
 * means more people bouncing.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 *
 * No urgency, no countdown, no "don't miss out", no projected price. The page it
 * sits on shows 3 holders and 100% concentration, and this block sits directly
 * underneath that without contradicting it. A visitor who buys should do it
 * having read the bad numbers, or they are not the holder worth having.
 *
 * The share text is generated from live values, including the unflattering ones.
 * That is the only genuinely uncopyable thing here: anyone can post a chart, and
 * almost nobody will post their real holder count next to it.
 *
 * Social links come from environment variables and render only when set. No
 * placeholder handles — a dead link on a token page reads as abandonment, which
 * is worse than no link at all.
 */

const API = process.env.REACT_APP_BACKEND_URL || '';

const SOCIALS = [
  { key: 'REACT_APP_TELEGRAM', label: 'Telegram' },
  { key: 'REACT_APP_X', label: 'X' },
  { key: 'REACT_APP_DISCORD', label: 'Discord' },
  { key: 'REACT_APP_GITHUB', label: 'GitHub' },
].map((s) => ({ ...s, url: process.env[s.key] })).filter((s) => s.url);

export default function JoinPanel() {
  const [stats, setStats] = useState(null);
  const [copied, setCopied] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/public/token`, { credentials: 'omit' })
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const mint = stats?.mint;

  const copy = useCallback(async (text, tag) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(tag);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      /* clipboard blocked; the address is on screen and selectable anyway */
    }
  }, []);

  // Built from what was actually read. Unreadable fields are omitted rather than
  // guessed, so the post never claims a number the page could not verify.
  const shareText = (() => {
    if (!stats) return '';
    const lines = ['YABBAI — every number read live from Solana mainnet.', ''];
    if (stats.price != null) lines.push(`Price: $${Number(stats.price).toFixed(8)}`);
    if (stats.market_cap != null) lines.push(`Market cap: $${Number(stats.market_cap).toLocaleString()}`);
    if (stats.holder_count != null) lines.push(`Holders: ${stats.holder_count}`);
    if (stats.mint_authority_revoked && stats.freeze_authority_revoked) {
      lines.push('Mint + freeze authority: REVOKED');
    }
    lines.push(
      '',
      'Values that cannot be read show DATA GAP instead of a made-up number.',
      'Check any of it yourself:',
      'https://holders.yabbai.network'
    );
    return lines.join('\n');
  })();

  const c = {
    ink: '#c8d6e8', dim: '#6b8199', faint: '#4d6076',
    line: '#1e2a3a', surface: '#0f1721', ground: '#0b1119', gold: '#d4a017',
  };

  const btn = {
    padding: '10px 16px', borderRadius: 6, fontSize: 13,
    fontFamily: 'JetBrains Mono, DM Mono, monospace',
    border: `1px solid ${c.line}`, background: '#16202d', color: c.ink,
    cursor: 'pointer', textDecoration: 'none', display: 'inline-block',
  };

  return (
    <section
      style={{
        maxWidth: 900, margin: '8px auto 40px', padding: '22px 24px',
        background: c.surface, border: `1px solid ${c.line}`, borderRadius: 10,
        fontFamily: 'JetBrains Mono, DM Mono, monospace', color: c.ink,
      }}
    >
      <h2 style={{ margin: '0 0 6px', fontSize: 16, letterSpacing: '0.02em' }}>
        Check it yourself
      </h2>
      <p style={{ margin: '0 0 20px', fontSize: 12.5, color: c.dim, lineHeight: 1.65, maxWidth: '62ch' }}>
        Nothing above needs to be taken on trust. The mint address is below —
        every figure on this page can be read straight from chain with it, by you,
        without this site.
      </p>

      {mint && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: c.faint, marginBottom: 7 }}>
            Token mint
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <code
              style={{
                fontSize: 12, padding: '8px 11px', background: c.ground,
                border: `1px solid ${c.line}`, borderRadius: 5,
                color: c.dim, wordBreak: 'break-all', flex: '1 1 320px',
              }}
            >
              {mint}
            </code>
            <button style={btn} onClick={() => copy(mint, 'mint')}>
              {copied === 'mint' ? 'copied' : 'copy'}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 20 }}>
        {mint && (
          <>
            <a style={btn} href={`https://jup.ag/swap/SOL-${mint}`} target="_blank" rel="noopener noreferrer">
              Trade on Jupiter ↗
            </a>
            <a style={btn} href={`https://solscan.io/token/${mint}`} target="_blank" rel="noopener noreferrer">
              Verify on Solscan ↗
            </a>
          </>
        )}
        {shareText && (
          <button style={btn} onClick={() => copy(shareText, 'share')}>
            {copied === 'share' ? 'copied — paste anywhere' : 'copy the numbers'}
          </button>
        )}
      </div>

      {SOCIALS.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: c.faint, marginBottom: 8 }}>
            Where people talk
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {SOCIALS.map((s) => (
              <a key={s.key} style={btn} href={s.url} target="_blank" rel="noopener noreferrer">
                {s.label} ↗
              </a>
            ))}
          </div>
        </div>
      )}

      <p
        style={{
          margin: 0, paddingTop: 16, borderTop: `1px solid ${c.line}`,
          fontSize: 11.5, color: c.faint, lineHeight: 1.65, maxWidth: '68ch',
        }}
      >
        Read the numbers above before doing anything, including the unflattering
        ones — holder count and concentration are on this page for that reason.
        This is not financial advice, not an offer and not a solicitation. Token
        values can fall to zero, and most do.
      </p>
    </section>
  );
}
