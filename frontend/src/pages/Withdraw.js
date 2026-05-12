import React, { useState, useEffect } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TREASURY = '7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR';

export default function Withdraw() {
  const [recipient, setRecipient] = useState(TREASURY);
  const [amountSol, setAmountSol] = useState('');
  const [txStatus, setTxStatus] = useState(null); // null | 'pending' | 'success' | 'error'
  const [txSig, setTxSig] = useState('');
  const [txMsg, setTxMsg] = useState('');
  const [walletAddr, setWalletAddr] = useState('');
  const [treasuryBal, setTreasuryBal] = useState(null);
  const [mintCfg, setMintCfg] = useState(null);
  const [history, setHistory] = useState([]);
  const [phantomConn, setPhantomConn] = useState(false);

  useEffect(() => {
    fetch(`${API}/token-mint`).then(r => r.json()).then(d => { if (d.configured) setMintCfg(d); }).catch(() => {});
    fetch(`${API}/solana-balance?owner=${TREASURY}`)
      .then(r => r.json())
      .then(d => { if (d.ok) setTreasuryBal(d.sol); })
      .catch(() => {});
    const solana = window.solana;
    if (solana?.isPhantom && solana.isConnected) {
      setPhantomConn(true);
      setWalletAddr(solana.publicKey?.toString() || '');
    }
  }, []);

  const connectWallet = async () => {
    try {
      const solana = window.solana;
      if (!solana?.isPhantom) { window.open('https://phantom.app/', '_blank'); return; }
      const resp = await solana.connect();
      setPhantomConn(true);
      setWalletAddr(resp.publicKey.toString());
    } catch (e) {
      setTxMsg('Wallet connection declined.');
      setTxStatus('error');
    }
  };

  const handleWithdraw = async () => {
    if (!amountSol || isNaN(parseFloat(amountSol)) || parseFloat(amountSol) <= 0) {
      setTxMsg('Enter a valid SOL amount.');
      setTxStatus('error');
      return;
    }
    if (!recipient || recipient.length < 32) {
      setTxMsg('Enter a valid recipient address.');
      setTxStatus('error');
      return;
    }
    if (!phantomConn) {
      setTxMsg('Connect Phantom wallet first.');
      setTxStatus('error');
      return;
    }
    setTxStatus('pending');
    setTxMsg('');
    try {
      // Dynamic import to avoid SSR issues
      const web3 = await import('@solana/web3.js');
      const { Connection, PublicKey, SystemProgram, Transaction, LAMPORTS_PER_SOL, ComputeBudgetProgram } = web3;
      const connection = new Connection('https://api.mainnet-beta.solana.com', 'confirmed');
      const solana = window.solana;
      const fromPubkey = solana.publicKey;
      const toPubkey = new PublicKey(recipient);
      const lamports = Math.floor(parseFloat(amountSol) * LAMPORTS_PER_SOL);

      const { blockhash } = await connection.getLatestBlockhash();
      const tx = new Transaction({ recentBlockhash: blockhash, feePayer: fromPubkey });
      tx.add(ComputeBudgetProgram.setComputeUnitPrice({ microLamports: 5000 }));
      tx.add(SystemProgram.transfer({ fromPubkey, toPubkey, lamports }));

      const signed = await solana.signTransaction(tx);
      const sig = await connection.sendRawTransaction(signed.serialize());
      await connection.confirmTransaction(sig, 'confirmed');

      setTxSig(sig);
      setTxStatus('success');
      setTxMsg(`Transaction confirmed! Sig: ${sig.slice(0, 20)}...`);
      setHistory(prev => [{ sig: sig.slice(0, 20) + '...', amt: amountSol, to: recipient.slice(0, 12) + '...', ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 10));
      setAmountSol('');
    } catch (e) {
      setTxStatus('error');
      setTxMsg('Transaction failed: ' + (e.message || 'Unknown error'));
    }
  };

  const presets = ['0.1', '0.5', '1.0', '5.0'];

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ WITHDRAW PORTAL</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <h1 className="font-display fade-in-2" style={{ fontSize: 36, fontWeight: 900, color: '#9945FF' }}>WITHDRAW PORTAL</h1>
        <span className="badge badge-purple">MAINNET-BETA</span>
        {mintCfg && <span className="badge badge-green">TOKEN LIVE</span>}
      </div>

      <div className="grid-2 fade-in-2" style={{ marginBottom: 24 }}>
        {/* Withdraw form */}
        <div className="card">
          <p className="section-label" style={{ marginBottom: 14 }}>SOL TRANSFER</p>

          {/* Wallet connect */}
          <div
            className={`wallet-option ${phantomConn ? 'connected' : ''}`}
            style={{ marginBottom: 16, padding: '12px 14px' }}
            onClick={!phantomConn ? connectWallet : undefined}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 20 }}>👻</span>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: phantomConn ? '#14F195' : '#e8f0ff' }}>
                  {phantomConn ? 'Phantom Connected' : 'Connect Phantom to Sign'}
                </div>
                {walletAddr && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: '#3a5070' }}>{walletAddr.slice(0, 20)}...</div>}
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 12 }}>
            <label className="stat-label" style={{ display: 'block', marginBottom: 5 }}>RECIPIENT ADDRESS</label>
            <input
              className="field"
              value={recipient}
              onChange={e => setRecipient(e.target.value)}
              placeholder="Solana address..."
              data-testid="withdraw-recipient"
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
              <label className="stat-label">AMOUNT (SOL)</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {presets.map(p => (
                  <button key={p} className="btn btn-outline btn-sm" onClick={() => setAmountSol(p)}>{p}</button>
                ))}
              </div>
            </div>
            <input
              className="field"
              type="number" step="0.001" min="0.001"
              placeholder="0.00"
              value={amountSol}
              onChange={e => setAmountSol(e.target.value)}
              data-testid="withdraw-amount"
            />
          </div>

          {txStatus && (
            <div style={{
              padding: '10px 14px', borderRadius: 6, marginBottom: 14,
              background: txStatus === 'success' ? 'rgba(20,241,149,0.08)' : txStatus === 'error' ? 'rgba(255,60,60,0.08)' : 'rgba(153,69,255,0.08)',
              border: `1px solid ${txStatus === 'success' ? 'rgba(20,241,149,0.25)' : txStatus === 'error' ? 'rgba(255,60,60,0.25)' : 'rgba(153,69,255,0.25)'}`,
              fontFamily: 'var(--font-mono)', fontSize: 11,
              color: txStatus === 'success' ? '#14F195' : txStatus === 'error' ? '#ff6060' : '#9945FF',
            }}>
              {txStatus === 'pending' ? '⧗ Sending transaction...' : txMsg}
              {txStatus === 'success' && txSig && (
                <a href={`https://solscan.io/tx/${txSig}`} target="_blank" rel="noopener noreferrer"
                  style={{ display: 'block', marginTop: 6, color: '#9945FF', fontSize: 10 }}>
                  View on Solscan ↗
                </a>
              )}
            </div>
          )}

          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            onClick={handleWithdraw}
            disabled={txStatus === 'pending' || !phantomConn}
            data-testid="withdraw-btn"
          >
            {txStatus === 'pending' ? (
              <><span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite', marginRight: 8 }} />Sending...</>
            ) : '⚡ SEND SOL'}
          </button>
        </div>

        {/* Treasury info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <p className="section-label" style={{ marginBottom: 12 }}>TREASURY STATUS</p>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 900, color: '#9945FF', marginBottom: 4 }}>
              {treasuryBal !== null ? `${treasuryBal.toFixed(4)} SOL` : 'Loading...'}
            </div>
            <div className="stat-label">TREASURY BALANCE</div>
            <div className="divider" />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: '#3a5070', wordBreak: 'break-all' }}>
              {TREASURY}
            </div>
            <a href={`https://solscan.io/account/${TREASURY}`} target="_blank" rel="noopener noreferrer"
              style={{ display: 'block', marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 10, color: '#9945FF' }}>
              View on Solscan ↗
            </a>
          </div>

          {history.length > 0 && (
            <div className="card">
              <p className="section-label" style={{ marginBottom: 10 }}>RECENT TRANSACTIONS</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {history.map((h, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 10, borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: 6 }}>
                    <span style={{ color: '#14F195' }}>✓ {h.amt} SOL</span>
                    <span style={{ color: '#3a5070' }}>→ {h.to}</span>
                    <span style={{ color: '#3a5070' }}>{h.ts}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card">
            <p className="section-label" style={{ marginBottom: 10 }}>INSTRUCTIONS</p>
            <ol style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#3a5070', lineHeight: 2, paddingLeft: 16 }}>
              <li>Connect your Phantom wallet</li>
              <li>Enter destination address</li>
              <li>Enter SOL amount</li>
              <li>Click SEND SOL — Phantom will prompt you to approve</li>
              <li>Transaction is broadcast to mainnet-beta</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
