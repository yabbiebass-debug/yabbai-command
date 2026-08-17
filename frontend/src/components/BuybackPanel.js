import React, { useCallback, useEffect, useState } from 'react';
import { detectWallets, connectWallet, signAndSendTransaction } from '../lib/wallets';

const fmt = (n, d = 0) =>
  typeof n === 'number' ? n.toLocaleString(undefined, { maximumFractionDigits: d }) : '—';

const ago = (iso) => {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
};

/**
 * Treasury buyback: agents propose, the operator signs.
 *
 * Buying the token with treasury SOL is the only lever here that moves market
 * cap using funds already under the operator's control. The quote comes from
 * Jupiter, so price impact is real rather than derived from a spot price.
 *
 * The agents do everything except the signature — watch the price, decide,
 * size against the risk and reinvest settings, price the route, and queue it.
 * Approving re-quotes at current pricing and hands the unsigned transaction to
 * the wallet, which displays the amounts before the operator accepts. That
 * prompt is the protection; nothing on the server holds a key, so a compromised
 * server cannot spend the treasury.
 */
export default function BuybackPanel({ api }) {
  const [amount, setAmount] = useState('');
  const [quote, setQuote] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [queue, setQueue] = useState(null);

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

  // What the agents have queued. Polled rather than pushed: a proposal that
  // appears a few seconds late costs nothing, and this page is already open.
  const loadQueue = useCallback(async () => {
    try {
      const res = await fetch(`${api}/buyback/proposals`, { credentials: 'include' });
      if (res.ok) setQueue(await res.json());
    } catch { /* leave the last known queue on screen */ }
  }, [api]);

  useEffect(() => {
    loadQueue();
    const t = setInterval(loadQueue, 30000);
    return () => clearInterval(t);
  }, [loadQueue]);

  const ensureWallet = async () => {
    if (wallet) return wallet;
    const found = detectWallets();
    if (!found.length) throw new Error('No Solana wallet detected');
    const w = await connectWallet(found[0]);
    const next = { ...w, entry: found[0] };
    setWallet(next);
    return next;
  };

  /**
   * Build, sign and record one buy. Shared by the manual box and by approving
   * an agent proposal, so both paths re-quote at current pricing and both end
   * at the same wallet prompt. A proposal's stored quote is shown for context
   * only; it is never what gets signed.
   */
  const executeBuy = async (sol, proposalId, expectedOut) => {
    const key = proposalId || 'execute';
    setBusy(key);
    setError(null);
    setResult(null);
    try {
      const w = await ensureWallet();

      const res = await fetch(`${api}/buyback/transaction`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wallet: w.address,
          amount_sol: sol,
          ...(proposalId ? { proposal_id: proposalId } : {}),
        }),
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
          signature,
          wallet: w.address,
          amount_sol: sol,
          tokens_out: expectedOut,
          ...(data.proposal_id ? { proposal_id: data.proposal_id } : {}),
        }),
      });

      setResult({ signature });
      loadQueue();
    } catch (e) {
      setError(e.message);
    }
    setBusy(null);
  };

  const execute = () => executeBuy(parseFloat(amount), null, quote?.tokens_out);

  const dismiss = async (id) => {
    setBusy(id);
    setError(null);
    try {
      const res = await fetch(`${api}/buyback/proposals/dismiss`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadQueue();
    } catch (e) {
      setError(e.message);
    }
    setBusy(null);
  };

  const impact = quote?.price_impact_pct;
  const impactColor = impact == null ? '#8fa3bf'
    : impact >= 10 ? '#ff6060' : impact >= 3 ? '#F5A623' : '#14F195';

  const pending = queue?.pending || [];
  const executed = queue?.executed || [];

  return (
    <div className="card">
      <p className="section-label" style={{ marginBottom: 14 }}>TREASURY BUYBACK</p>

      {/* Agent queue. Present whenever proposals exist; the state of the toggle
          is shown either way so an empty queue is never ambiguous. */}
      {queue && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            marginBottom: pending.length ? 10 : 0, flexWrap: 'wrap',
          }}>
            <span className="stat-label">AGENT PROPOSALS</span>
            <span className={`badge ${queue.enabled ? 'badge-green' : 'badge-purple'}`}>
              {queue.enabled ? 'ARMED' : 'OFF'}
            </span>
            {pending.length > 0 && (
              <span style={{ fontSize: 11, color: '#8fa3bf' }}>
                {pending.length} awaiting your signature
              </span>
            )}
          </div>

          {!queue.enabled && (
            <p style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6, marginTop: 6 }}>
              Agents are watching but will not queue buybacks. Enable buybacks in
              Settings to arm them; they still cannot execute without your wallet.
            </p>
          )}

          {queue.enabled && pending.length === 0 && (
            <p style={{ fontSize: 11, color: '#8fa3bf', lineHeight: 1.6, marginTop: 6 }}>
              Nothing queued. A proposal appears when the price falls past your
              trigger and the treasury has spendable SOL above the fee reserve.
            </p>
          )}

          {pending.map((p) => {
            const pImpact = p.price_impact_pct;
            const pColor = pImpact == null ? '#8fa3bf'
              : pImpact >= 10 ? '#ff6060' : pImpact >= 3 ? '#F5A623' : '#14F195';
            return (
              <div key={p.id} style={{
                border: '1px solid rgba(153,69,255,0.35)',
                background: 'rgba(153,69,255,0.06)',
                borderRadius: 8, padding: '10px 12px', marginBottom: 8,
              }}>
                <div style={{
                  display: 'flex', justifyContent: 'space-between',
                  alignItems: 'baseline', gap: 8, flexWrap: 'wrap',
                }}>
                  <span style={{
                    fontFamily: 'var(--font-display)', fontSize: 15,
                    fontWeight: 900, color: '#e8f0ff',
                  }}>
                    {fmt(p.amount_sol, 4)} SOL
                  </span>
                  <span style={{ fontSize: 11, color: pColor }}>
                    {pImpact != null ? `${pImpact.toFixed(2)}% impact` : 'impact unknown'}
                  </span>
                  <span style={{ fontSize: 11, color: '#8fa3bf' }}>
                    {p.proposed_by} · {ago(p.proposed_at)}
                  </span>
                </div>

                {(p.reasons || []).length > 0 && (
                  <div style={{ fontSize: 11, color: '#8fa3bf', marginTop: 4 }}>
                    {p.reasons.join(' · ')}
                  </div>
                )}

                {p.disclosure && (
                  <div style={{ fontSize: 11, color: '#e8d5b0', marginTop: 6, lineHeight: 1.5 }}>
                    {p.disclosure}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                  <button
                    className="btn btn-green btn-sm"
                    onClick={() => executeBuy(p.amount_sol, p.id)}
                    disabled={busy === p.id}
                  >
                    {busy === p.id ? 'Awaiting wallet…' : 'Approve & sign'}
                  </button>
                  <button
                    className="btn btn-outline btn-sm"
                    onClick={() => dismiss(p.id)}
                    disabled={busy === p.id}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            );
          })}

          {executed.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <span className="stat-label">EXECUTED</span>
              {executed.slice(0, 5).map((p) => (
                <div key={p.signature || p.id} style={{
                  fontSize: 11, color: '#8fa3bf', marginTop: 4,
                }}>
                  {fmt(p.amount_sol, 4)} SOL · {ago(p.executed_at || p.proposed_at)}
                  {p.signature && (
                    <>
                      {' · '}
                      <a href={`https://solscan.io/tx/${p.signature}`} target="_blank"
                         rel="noopener noreferrer" style={{ color: '#14F195' }}>
                        tx ↗
                      </a>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <span className="stat-label">MANUAL BUY</span>
      <div style={{ display: 'flex', gap: 8, margin: '10px 0 12px', flexWrap: 'wrap' }}>
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
        Every buy — yours or an agent's — is built unsigned and signed by your
        own wallet, which shows the amounts before you approve. Read that prompt;
        it is what protects you. This service holds no keys, so nothing here and
        nothing that compromises the server can spend the treasury. A buyback
        converts SOL into tokens: it changes your position, it is not income.
      </p>
    </div>
  );
}
