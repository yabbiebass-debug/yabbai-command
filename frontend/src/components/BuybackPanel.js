import React, { useCallback, useEffect, useState } from 'react';
import { detectWallets, connectWallet, signAndSendTransaction } from '../lib/wallets';

/**
 * Treasury buyback: quote, review, sign in your own wallet, submit.
 *
 * Buying the token with treasury SOL is the only lever here that moves market
 * cap using funds already under the operator's control. The quote comes from
 * Jupiter, so price impact is real rather than derived from a spot price.
 *
 * This page cannot execute anything. The transaction is built unsigned by
 * Jupiter, and the wallet extension displays the amounts before the operator
 * accepts. That prompt is the protection; nothing here holds a key.
 */
export default function BuybackPanel({ api }) {
  const [amount, setAmount] = useState('');
  const [quote, setQuote] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const loadQuote = useCallback(async (sol) => {
    if (!sol || parseFloat(sol) <= 0) { setQuote(null); return; }
    setBusy('quote');
    setError(null);
    try {
      const res = await fetch(`${api}/buyback/quote`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount_sol: parseFloat(sol) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setQuote(data);
    } catch (e) {
      setError(e.message);
      setQuote(null);
    }
    setBusy(null);
  }, [api]);

  // Prefill with the spendable balance so the first quote is meaningful.
  useEffect(() => {
    let cancelled = false;
    fetch(`${api}/buyback/quote`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (cancelled || !d) return;
        setQuote(d);
        if (d.amount_sol) setAmount(String(d.amount_sol));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [api]);

  const ensureWallet = async () => {
    if (wallet) return wallet;
    const found = detectWallets();
    if (!found.length) throw new Error('No Solana wallet detected');
    const w = await connectWallet(found[0]);
    const next = { ...w, entry: found[0] };
    setWallet(next);
    return next;
  };

  const execute = async () => {
    setBusy('execute');
    setError(null);
    setResult(null);
    try {
      const w = await ensureWallet();

      const res = await fetch(`${api}/buyback/transaction`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet: w.address, amount_sol: parseFloat(amount) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

      // The wallet displays the amounts here. Read that prompt before approving.
      const signature = await signAndSendTransaction(w.entry, data.swap_transaction);

      await fetch(`${api}/buyback/confirm`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signature, wallet: w.address,
          amount_sol: parseFloat(amount),
          tokens_out: quote?.tokens_out,
        }),
      });

      setResult({ signature });
    } catch (e) {
      setError(e.message);
    }
    setBusy(null);
  };

  const impact = quote?.price_impact_pct;
  const impactColor = impact == null ? '#8fa3bf'
    : impact >= 10 ? '#ff6060' : impact >= 3 ? '#F5A623' : '#14F195';

  return (
    <div className="card">
      <p className="section-label" style={{ marginBottom: 14 }}>TREASURY BUYBACK</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <input
          className="field"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={() => loadQuote(amount)}
          placeholder="0.00"
          inputMode="decimal"
          style={{ flex: 1, minWidth: 120 }}
        />
        <span className="badge badge-purple" style={{ alignSelf: 'center' }}>SOL</span>
        <button
          className="btn btn-outline btn-sm"
          onClick={() => loadQuote(amount)}
          disabled={busy === 'quote'}
        >
          {busy === 'quote' ? 'Quoting…' : 'Quote'}
        </button>
      </div>

      {quote?.available && (
        <div style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: 14 }}>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: '#9945FF' }}>
                {quote.tokens_out?.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="stat-label">YABBAI OUT</div>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: impactColor }}>
                {impact != null ? `${impact.toFixed(2)}%` : '—'}
              </div>
              <div className="stat-label">PRICE IMPACT</div>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 900, color: '#e8f0ff' }}>
                {quote.treasury_sol_after?.toFixed(4)}
              </div>
              <div className="stat-label">SOL AFTER</div>
            </div>
          </div>

          {quote.warning && (
            <div style={{
              fontSize: 12, color: '#e8d5b0', background: 'rgba(245,166,35,0.08)',
              border: '1px solid rgba(245,166,35,0.3)', borderRadius: 6, padding: '8px 10px',
            }}>
              {quote.warning}
            </div>
          )}
        </div>
      )}

      {quote && !quote.available && (
        <div style={{ fontSize: 12, color: '#F5A623', marginBottom: 12 }}>
          {quote.reason}
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

      {result && (
        <div style={{
          fontSize: 12, color: '#14F195', background: 'rgba(20,241,149,0.08)',
          border: '1px solid rgba(20,241,149,0.3)', borderRadius: 6,
          padding: '8px 10px', marginBottom: 12,
        }}>
          Buyback submitted.{' '}
          <a href={`https://solscan.io/tx/${result.signature}`} target="_blank"
             rel="noopener noreferrer" style={{ color: '#14F195' }}>
            view on Solscan ↗
          </a>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          className="btn btn-green"
          style={{ flex: 1, minWidth: 160 }}
          onClick={execute}
          disabled={busy === 'execute' || !quote?.available}
        >
          {busy === 'execute' ? 'Awaiting wallet…'
            : wallet ? `Buy with ${wallet.name}` : 'Connect & buy'}
        </button>
        {quote?.jupiter_url && (
          <a className="btn btn-outline" href={quote.jupiter_url}
             target="_blank" rel="noopener noreferrer"
             style={{ textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
            Jupiter ↗
          </a>
        )}
      </div>

      <p style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6, marginTop: 12 }}>
        The transaction is built unsigned and signed by your own wallet, which
        shows the amounts before you approve — read that prompt, it is what
        protects you. This service holds no keys and cannot execute anything on
        its own. A buyback converts SOL into tokens: it changes your position,
        it is not income.
      </p>
    </div>
  );
}
