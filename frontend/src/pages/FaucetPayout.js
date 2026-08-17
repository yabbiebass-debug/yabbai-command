import React, { useCallback, useEffect, useState } from 'react';

/**
 * Faucet payout — director only.
 *
 * Claims arrive as signed intent (see backend/faucet.py); nothing has moved
 * when a claim is queued. This is where value actually leaves, and it leaves
 * through the operator's own wallet, not through the server.
 *
 * v1 is deliberately a worksheet rather than a one-click payout. Building a
 * batch SPL transfer in the browser needs @solana/spl-token, which this app
 * does not currently ship, and adding a dependency in order to move real tokens
 * is not a change to make casually at the end of a long night. So: read the
 * batch, copy it into whatever tool you already trust to send, paste the
 * resulting signature back. The ledger stays accurate either way, and no claim
 * is marked paid without a signature that can be checked on chain.
 *
 * Marking paid does not move anything. It records that something already did.
 */

const API = process.env.REACT_APP_BACKEND_URL || '';

// credentials:'include' — these are director routes and need the session cookie.
const req = async (path, options = {}) => {
  const r = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
  return body;
};

export default function FaucetPayout() {
  const [pending, setPending] = useState(null);
  const [status, setStatus] = useState(null);
  const [signature, setSignature] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, s] = await Promise.all([
        req('/api/faucet/pending?limit=500'),
        fetch(`${API}/api/faucet/status`, { credentials: 'omit' }).then((r) => r.json()),
      ]);
      setPending(p);
      setStatus(s);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const rows = pending?.claims || [];

  // address,amount — one per line. Deliberately dumb and universally pasteable.
  const csv = rows.map((r) => `${r.address},${r.tokens}`).join('\n');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(csv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('clipboard blocked — select the list and copy manually');
    }
  };

  const markPaid = async () => {
    const sig = signature.trim();
    if (sig.length < 32) {
      setError('paste the transaction signature first');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await req('/api/faucet/paid', {
        method: 'POST',
        body: JSON.stringify({ addresses: rows.map((r) => r.address), signature: sig }),
      });
      setSignature('');
      await load();
      setError(null);
      alert(`Marked ${res.marked_paid} claims paid.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const S = {
    page: { padding: '28px 32px', color: '#c8d6e8', fontFamily: 'JetBrains Mono, DM Mono, monospace' },
    h1: { fontSize: 22, margin: '0 0 6px', letterSpacing: '0.01em' },
    sub: { fontSize: 13, color: '#6b8199', margin: '0 0 26px', maxWidth: '70ch', lineHeight: 1.6 },
    grid: { display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 24 },
    card: { flex: '1 1 150px', padding: '14px 16px', background: '#0f1721', border: '1px solid #1e2a3a', borderRadius: 6 },
    k: { fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#4d6076', marginBottom: 6 },
    v: { fontSize: 20, fontVariantNumeric: 'tabular-nums' },
    box: { background: '#0b1119', border: '1px solid #1e2a3a', borderRadius: 6, padding: 16, marginBottom: 20 },
    list: { maxHeight: 300, overflowY: 'auto', fontSize: 12, lineHeight: 1.8, margin: 0, whiteSpace: 'pre', color: '#8fa4bb' },
    btn: (disabled) => ({
      padding: '9px 16px', borderRadius: 6, fontSize: 13, fontFamily: 'inherit',
      border: '1px solid #2a3a4f', background: disabled ? '#141c26' : '#16202d',
      color: disabled ? '#4d6076' : '#c8d6e8', cursor: disabled ? 'not-allowed' : 'pointer',
    }),
    input: {
      flex: 1, minWidth: 260, padding: '9px 12px', borderRadius: 6, fontSize: 13,
      fontFamily: 'inherit', background: '#0b1119', border: '1px solid #2a3a4f', color: '#c8d6e8',
    },
    err: { color: '#e0736b', fontSize: 12.5, marginTop: 12, wordBreak: 'break-word' },
    note: { fontSize: 11.5, color: '#4d6076', lineHeight: 1.6, marginTop: 14 },
  };

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Faucet payout</h1>
      <p style={S.sub}>
        Claims below are signed and verified but unpaid. Nothing here has moved
        tokens. Send the batch from your own wallet, then record the signature so
        the ledger matches the chain.
      </p>

      <div style={S.grid}>
        <div style={S.card}>
          <div style={S.k}>Pending</div>
          <div style={S.v}>{pending ? pending.count : '—'}</div>
        </div>
        <div style={S.card}>
          <div style={S.k}>Tokens owed</div>
          <div style={S.v}>{pending ? Number(pending.total_tokens).toLocaleString() : '—'}</div>
        </div>
        <div style={S.card}>
          <div style={S.k}>Already paid</div>
          <div style={S.v}>{status ? status.claims_paid : '—'}</div>
        </div>
        <div style={S.card}>
          <div style={S.k}>Faucet</div>
          <div style={{ ...S.v, fontSize: 14, color: status?.enabled ? '#5fd39a' : '#6b8199' }}>
            {status ? (status.enabled ? 'OPEN' : 'CLOSED') : '—'}
          </div>
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={S.box}>
          <div style={{ fontSize: 13, color: '#6b8199' }}>
            No unpaid claims.{' '}
            {status && !status.enabled && 'The faucet is closed, so none will arrive.'}
          </div>
        </div>
      ) : (
        <>
          <div style={S.box}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
              <div style={S.k}>Batch — address,amount</div>
              <button style={S.btn(false)} onClick={copy}>
                {copied ? 'copied' : `copy ${rows.length} rows`}
              </button>
            </div>
            <pre style={S.list}>{csv}</pre>
          </div>

          <div style={S.box}>
            <div style={S.k}>Record the payout</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 10 }}>
              <input
                style={S.input}
                placeholder="transaction signature"
                value={signature}
                onChange={(e) => setSignature(e.target.value)}
                spellCheck={false}
              />
              <button style={S.btn(busy || !signature.trim())} onClick={markPaid} disabled={busy || !signature.trim()}>
                {busy ? 'recording...' : `mark ${rows.length} paid`}
              </button>
            </div>
            <div style={S.note}>
              Send first, record second. This writes history — it moves nothing,
              and a wrong signature here means the ledger disagrees with the chain.
            </div>
          </div>
        </>
      )}

      {error && <div style={S.err}>{error}</div>}
    </div>
  );
}
