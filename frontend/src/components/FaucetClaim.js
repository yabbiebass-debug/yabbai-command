import React, { useCallback, useEffect, useState } from 'react';
import { detectWallets, connectWallet, signMessage } from '@/lib/wallets';

/**
 * Public token claim.
 *
 * This is the only place the holders build touches a wallet, and it uses
 * signMessage only — never signAndSendTransaction. A signed message proves the
 * claimer controls the address and moves nothing; it cannot spend, approve or
 * transfer. The isolation the README describes still holds: no admin code, no
 * session, no ability to move value from this bundle.
 *
 * Renders nothing at all when the faucet is off, so shipping this to the public
 * site before opening the faucet is a no-op rather than a dead button.
 */

const API = process.env.REACT_APP_BACKEND_URL || '';

// credentials:'omit' throughout, matching the rest of the holders build — the
// .yabbai.network session cookie must never ride along to the public subdomain.
const get = (path) =>
  fetch(`${API}${path}`, { credentials: 'omit' }).then((r) =>
    r.ok ? r.json() : r.json().then((b) => Promise.reject(new Error(b.detail || `HTTP ${r.status}`)))
  );

const post = (path, body) =>
  fetch(`${API}${path}`, {
    method: 'POST',
    credentials: 'omit',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) =>
    r.ok ? r.json() : r.json().then((b) => Promise.reject(new Error(b.detail || `HTTP ${r.status}`)))
  );

export default function FaucetClaim() {
  const [status, setStatus] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    get('/api/faucet/status').then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    // Extensions inject at different moments, so one read on mount finds
    // nothing. Re-read on a bounded schedule that lines up with the
    // announcements wallets.js makes, then stop.
    //
    // Deliberately not an interval. detectWallets() drives the Wallet Standard
    // handshake, and polling it forever re-runs every installed extension's
    // registration handler once a second for as long as the tab is open.
    const scan = () => setWallets(detectWallets() || []);
    scan();
    const timers = [200, 700, 1600, 3200].map((ms) => setTimeout(scan, ms));
    return () => timers.forEach(clearTimeout);
  }, []);

  const claim = useCallback(async (entry) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const connected = await connectWallet(entry);
      const address =
        connected?.address || connected?.publicKey?.toString?.() || connected?.toString?.();
      if (!address) throw new Error('wallet did not return an address');

      // The nonce binds this signature to one claim, so a signature captured
      // elsewhere cannot be replayed here.
      const { message } = await post(`/api/faucet/nonce?address=${encodeURIComponent(address)}`);
      const signature = await signMessage(entry, message);

      setResult(await post('/api/faucet/claim', { address, message, signature }));
      get('/api/faucet/status').then(setStatus).catch(() => {});
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  // Off, unreachable, or fully claimed: render nothing rather than a dead control.
  if (!status || !status.enabled) return null;

  const box = {
    maxWidth: 560,
    margin: '32px auto',
    padding: 20,
    border: '1px solid #1e2a3a',
    borderRadius: 10,
    fontFamily: 'JetBrains Mono, DM Mono, monospace',
    color: '#c8d6e8',
    background: '#0b1119',
  };

  return (
    <section style={box}>
      <h2 style={{ margin: '0 0 4px', fontSize: 18, letterSpacing: '0.02em' }}>
        Claim {Number(status.tokens_per_claim).toLocaleString()} YABBAI
      </h2>
      <p style={{ margin: '0 0 16px', fontSize: 12, color: '#6b8199', lineHeight: 1.6 }}>
        {status.remaining.toLocaleString()} of {status.cap.toLocaleString()} claims left.
        One per wallet.
      </p>

      {result ? (
        <div style={{ fontSize: 13, lineHeight: 1.7 }}>
          <div style={{ color: '#5fd39a' }}>Claim queued — position {result.queue_position}</div>
          <div style={{ color: '#6b8199', marginTop: 6 }}>{status.note}</div>
        </div>
      ) : wallets.length === 0 ? (
        <p style={{ fontSize: 13, color: '#6b8199' }}>
          No Solana wallet detected. Install Phantom, Solflare or Backpack, then reload.
        </p>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {wallets.map((w) => (
            <button
              key={w.name}
              onClick={() => claim(w)}
              disabled={busy}
              style={{
                padding: '9px 14px',
                borderRadius: 7,
                border: '1px solid #2a3a4f',
                background: busy ? '#141c26' : '#16202d',
                color: '#c8d6e8',
                cursor: busy ? 'wait' : 'pointer',
                fontSize: 13,
                fontFamily: 'inherit',
              }}
            >
              {busy ? 'waiting for wallet...' : w.name}
            </button>
          ))}
        </div>
      )}

      {error && (
        <p style={{ marginTop: 14, fontSize: 12, color: '#e0736b', wordBreak: 'break-word' }}>
          {error}
        </p>
      )}

      <p style={{ marginTop: 16, fontSize: 11, color: '#4d6076', lineHeight: 1.6 }}>
        Signing proves you hold the address. It authorises no transfer and cannot
        move anything from your wallet.
      </p>
    </section>
  );
}
