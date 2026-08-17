import React, { useCallback, useEffect, useState } from 'react';
import { detectWallets, connectWallet, disconnectWallet, signMessage } from '../lib/wallets';

/**
 * Connect Phantom, MetaMask, Solflare or Backpack and show live balances.
 *
 * Connecting exposes a public key and nothing else. The site cannot see a
 * private key or seed phrase, and does not sign here — every transaction still
 * has to be approved in the extension, and the sweep path additionally restricts
 * destinations to the server's allowlist.
 *
 * Balances are read server-side from the same RPC the rest of the dashboard
 * uses, so a connected wallet and the published treasury are measured
 * identically rather than by two different methods that could disagree.
 */
export default function WalletPanel({ api, mint }) {
  const [available, setAvailable] = useState([]);
  const [connected, setConnected] = useState([]);
  const [balances, setBalances] = useState({});
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [verified, setVerified] = useState({});

  useEffect(() => {
    // Extensions register asynchronously; re-scan briefly after mount.
    const scan = () => setAvailable(detectWallets());
    scan();
    const t1 = setTimeout(scan, 400);
    const t2 = setTimeout(scan, 1500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const loadBalance = useCallback(async (address) => {
    try {
      const res = await fetch(
        `${api}/solana-balance?owner=${encodeURIComponent(address)}`,
        { credentials: 'include' }
      );
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'balance unavailable');
      const token = mint
        ? (data.tokens || []).find((t) => t.mint === mint)
        : null;
      setBalances((b) => ({
        ...b,
        [address]: { sol: data.sol, token: token ? token.amount : 0 },
      }));
    } catch (e) {
      // A failed read stays unknown rather than being shown as zero.
      setBalances((b) => ({ ...b, [address]: { error: e.message } }));
    }
  }, [api, mint]);

  const handleConnect = async (entry) => {
    setBusy(entry.name);
    setError(null);
    try {
      const result = await connectWallet(entry);
      setConnected((c) =>
        c.some((w) => w.address === result.address)
          ? c
          : [...c, { ...result, entry }]
      );
      await loadBalance(result.address);
    } catch (e) {
      setError(`${entry.name}: ${e.message}`);
    }
    setBusy(null);
  };

  const handleDisconnect = async (wallet) => {
    await disconnectWallet(wallet.entry);
    setConnected((c) => c.filter((w) => w.address !== wallet.address));
    setVerified((v) => { const n = { ...v }; delete n[wallet.address]; return n; });
  };

  /**
   * Prove control of the wallet by signing a server-issued message.
   *
   * Signing text is not a transaction: it authorises nothing, moves nothing and
   * costs nothing. The message carries a single-use nonce and this domain, so
   * the signature cannot be replayed here or captured by another site.
   */
  const handleSign = async (wallet) => {
    setBusy(wallet.address);
    setError(null);
    try {
      const nonceRes = await fetch(`${api}/wallet/nonce`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: wallet.address }),
      });
      if (!nonceRes.ok) throw new Error(`nonce request failed (${nonceRes.status})`);
      const { message } = await nonceRes.json();

      const signature = await signMessage(wallet.entry, message);

      const verifyRes = await fetch(`${api}/wallet/verify`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address: wallet.address, message, signature, label: wallet.name,
        }),
      });
      if (!verifyRes.ok) {
        const body = await verifyRes.json().catch(() => ({}));
        throw new Error(body.detail || `verification failed (${verifyRes.status})`);
      }
      setVerified((v) => ({ ...v, [wallet.address]: true }));
    } catch (e) {
      setError(`${wallet.name}: ${e.message}`);
    }
    setBusy(null);
  };

  const short = (a) => `${a.slice(0, 4)}…${a.slice(-4)}`;

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
        <p className="section-label" style={{ margin: 0 }}>WALLETS</p>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070' }}>
          {available.length} detected
        </span>
      </div>

      {available.length === 0 && (
        <div style={{ fontSize: 12, color: '#8fa3bf', lineHeight: 1.6 }}>
          No Solana wallet detected. Phantom, MetaMask, Solflare and Backpack all
          work — install or unlock one and this will pick it up.
        </div>
      )}

      {available.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
          {available.map((w) => {
            const isConnected = connected.some((c) => c.name === w.name);
            return (
              <button
                key={w.name}
                className={`btn btn-sm ${isConnected ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => (isConnected ? null : handleConnect(w))}
                disabled={busy === w.name || isConnected}
              >
                {w.icon && (
                  <img src={w.icon} alt="" width="14" height="14"
                       style={{ verticalAlign: 'middle', marginRight: 6, borderRadius: 3 }} />
                )}
                {busy === w.name ? 'Connecting…' : isConnected ? `${w.name} ✓` : w.name}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <div style={{
          fontSize: 12, color: '#ff9090', background: 'rgba(255,80,80,0.08)',
          border: '1px solid rgba(255,80,80,0.3)', borderRadius: 6,
          padding: '8px 10px', marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {connected.map((w) => {
        const b = balances[w.address];
        return (
          <div key={w.address} style={{
            padding: '10px 12px', borderRadius: 8, marginBottom: 8,
            background: 'rgba(6,14,32,0.6)', border: '1px solid rgba(58,80,112,0.3)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#e8f0ff' }}>
                  {w.name}
                </div>
                <a href={`https://solscan.io/account/${w.address}`}
                   target="_blank" rel="noopener noreferrer"
                   style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#9945FF', textDecoration: 'none' }}>
                  {short(w.address)} ↗
                </a>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {verified[w.address] ? (
                  <span className="badge badge-green" style={{ alignSelf: 'center' }}>
                    VERIFIED
                  </span>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleSign(w)}
                    disabled={busy === w.address}
                    title="Sign a message to prove you control this wallet. No transaction, no funds moved."
                  >
                    {busy === w.address ? 'Signing…' : 'Sign in'}
                  </button>
                )}
                <button className="btn btn-outline btn-sm" onClick={() => handleDisconnect(w)}>
                  Disconnect
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 20, marginTop: 8 }}>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: b?.sol != null ? '#14F195' : '#3a5070' }}>
                  {b?.error ? 'DATA GAP' : b?.sol != null ? `${b.sol.toFixed(4)}` : '…'}
                </div>
                <div className="stat-label">SOL</div>
              </div>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: b?.token ? '#9945FF' : '#3a5070' }}>
                  {b?.error ? 'DATA GAP' : b?.token != null ? b.token.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '…'}
                </div>
                <div className="stat-label">YABBAI</div>
              </div>
            </div>
          </div>
        );
      })}

      <p style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6, marginTop: 10 }}>
        Connecting shares a public address only. This site never sees a private
        key or seed phrase and signs nothing on its own — every transaction is
        approved in your wallet, and sweeps are additionally limited to
        allowlisted destinations.
      </p>
    </div>
  );
}
