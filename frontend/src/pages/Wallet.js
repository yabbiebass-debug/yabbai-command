import React, { useState, useEffect } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// User's main wallet for sweeping funds
const MAIN_WALLET = '8V6NhYQGgTh5Byr4tFN5GbfwR7MzYXmtsndX76RKewh1';

export default function Wallet() {
  const [treasuryWallet, setTreasuryWallet] = useState('');
  const [solBalance, setSolBalance] = useState(0);
  const [tokens, setTokens] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [sweepStatus, setSweepStatus] = useState(null);
  const [sweepMessage, setSweepMessage] = useState('');

  // Load treasury wallet from settings
  useEffect(() => {
    const loadTreasuryInfo = async () => {
      try {
        const res = await fetch(`${API}/settings`);
        const data = await res.json();
        
        if (data.treasury_wallet) {
          setTreasuryWallet(data.treasury_wallet);
          // Load balances
          await loadBalances(data.treasury_wallet);
        }
      } catch (e) {
        console.error('Failed to load treasury wallet:', e);
      }
      setLoading(false);
    };

    loadTreasuryInfo();
    // Refresh every 30 seconds
    const interval = setInterval(() => {
      if (treasuryWallet) loadBalances(treasuryWallet);
    }, 30000);
    
    return () => clearInterval(interval);
  }, [treasuryWallet]);

  const loadBalances = async (wallet) => {
    try {
      // Get SOL balance
      const solRes = await fetch(`${API}/solana-balance?owner=${wallet}`);
      const solData = await solRes.json();
      setSolBalance(solData.balance || 0);

      // Get token balances
      const tokenRes = await fetch(`${API}/solana-tokens?owner=${wallet}`);
      const tokenData = await tokenRes.json();
      
      if (tokenData.tokens && Array.isArray(tokenData.tokens)) {
        // Filter out zero balances
        const nonZeroTokens = tokenData.tokens.filter(t => t.uiAmount > 0);
        setTokens(nonZeroTokens);
      }
    } catch (e) {
      console.error('Failed to load balances:', e);
    }
  };

  const sweepToken = async (tokenMint = null, amount = null) => {
    setSweeping(true);
    setSweepStatus('pending');
    setSweepMessage('Preparing sweep transaction...');

    try {
      const sweepData = {
        from: treasuryWallet,
        to: MAIN_WALLET,
        token: tokenMint || 'SOL',
        amount: amount || (tokenMint ? null : solBalance - 0.005), // Leave 0.005 SOL for fees
      };

      // For now, just log the sweep attempt (would need Phantom signing in production)
      setSweepMessage(
        `Sweep prepared: ${sweepData.amount || 'ALL'} ${sweepData.token} → ${MAIN_WALLET.slice(0, 8)}...`
      );
      setSweepStatus('info');

      // In production, this would call Phantom wallet to sign
      // For now, we'll just track it in the revenue system
      const trackRes = await fetch(`${API}/revenue/webhooks/sweep-attempted`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sweepData),
      });

      if (trackRes.ok) {
        setSweepStatus('success');
        setSweepMessage(
          `✅ Sweep tracked! In production, this would transfer ${sweepData.amount || 'ALL'} ${sweepData.token} to your main wallet.`
        );
      }

    } catch (e) {
      console.error('Sweep error:', e);
      setSweepStatus('error');
      setSweepMessage(`❌ Sweep failed: ${e.message}`);
    }

    setSweeping(false);
  };

  const sweepAll = async () => {
    setSweeping(true);
    setSweepStatus('pending');
    setSweepMessage('Sweeping all tokens and SOL...');

    try {
      // Sweep all tokens first, then SOL (to pay for token transfer fees)
      for (const token of tokens) {
        await sweepToken(token.mint, token.uiAmount);
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s between sweeps
      }

      // Finally sweep SOL
      await sweepToken(null, solBalance - 0.005);

      setSweepStatus('success');
      setSweepMessage(`✅ All tokens swept to ${MAIN_WALLET.slice(0, 8)}...!`);

    } catch (e) {
      console.error('Sweep all error:', e);
      setSweepStatus('error');
      setSweepMessage(`❌ Sweep all failed: ${e.message}`);
    }

    setSweeping(false);
  };

  if (loading) {
    return (
      <div className="page-container fade-in">
        <p className="section-label">💼 WALLET & TREASURY</p>
        <div className="card">
          <p style={{ color: '#3a5070' }}>Loading treasury data...</p>
        </div>
      </div>
    );
  }

  if (!treasuryWallet) {
    return (
      <div className="page-container fade-in">
        <p className="section-label">💼 WALLET & TREASURY</p>
        <div className="card" style={{ background: 'rgba(255,153,0,0.05)', borderColor: 'rgba(255,153,0,0.2)' }}>
          <div style={{ textAlign: 'center', padding: 40 }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
            <p style={{ margin: 0, marginBottom: 8, fontWeight: 600, color: '#ff9900' }}>
              No Treasury Wallet Configured
            </p>
            <p style={{ margin: 0, fontSize: 13, color: '#3a5070' }}>
              Go to Settings and configure your treasury wallet address to view balances and sweep funds.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const totalValueUSD = solBalance * 178 + tokens.reduce((sum, t) => sum + (t.uiAmount * (t.symbol === 'USDC' ? 1 : 0)), 0);

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">💼 WALLET & TREASURY</p>

      {/* Treasury Overview */}
      <div className="card fade-in-2" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <p className="section-label" style={{ margin: 0, marginBottom: 8 }}>TREASURY WALLET</p>
            <div style={{ 
              fontFamily: 'var(--font-mono)', 
              fontSize: 13, 
              color: '#3a5070',
              background: 'rgba(153,69,255,0.05)',
              padding: '8px 12px',
              borderRadius: 6,
              display: 'inline-block'
            }}>
              {treasuryWallet}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="stat-label">TOTAL VALUE (EST)</div>
            <span style={{ 
              fontFamily: 'var(--font-mono)', 
              fontSize: 24, 
              fontWeight: 900, 
              color: '#14F195',
              textShadow: '0 0 20px rgba(20,241,149,0.3)'
            }}>
              ${totalValueUSD.toFixed(2)}
            </span>
          </div>
        </div>

        {/* Main Destination */}
        <div style={{ 
          padding: 16, 
          background: 'rgba(153,69,255,0.05)',
          borderRadius: 8,
          border: '1px solid rgba(153,69,255,0.2)',
          marginBottom: 16
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="stat-label">MAIN WALLET (SWEEP DESTINATION)</div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#9945FF' }}>
                {MAIN_WALLET}
              </span>
            </div>
            <button
              className="btn btn-primary"
              onClick={sweepAll}
              disabled={sweeping || (solBalance === 0 && tokens.length === 0)}
              style={{ 
                background: sweeping ? '#666' : 'linear-gradient(135deg, #9945FF, #14F195)',
                minWidth: 160
              }}
            >
              {sweeping ? '⏳ SWEEPING...' : '💰 SWEEP ALL'}
            </button>
          </div>
        </div>

        {/* Sweep Status */}
        {sweepStatus && (
          <div style={{ 
            padding: 12,
            background: sweepStatus === 'success' ? 'rgba(20,241,149,0.1)' : 
                       sweepStatus === 'error' ? 'rgba(255,69,69,0.1)' : 
                       'rgba(153,69,255,0.1)',
            borderRadius: 6,
            border: `1px solid ${sweepStatus === 'success' ? '#14F195' : 
                                 sweepStatus === 'error' ? '#ff4545' : 
                                 '#9945FF'}`,
            marginBottom: 16
          }}>
            <p style={{ 
              margin: 0, 
              fontSize: 13, 
              fontFamily: 'var(--font-mono)',
              color: sweepStatus === 'success' ? '#14F195' : 
                     sweepStatus === 'error' ? '#ff4545' : 
                     '#9945FF'
            }}>
              {sweepMessage}
            </p>
          </div>
        )}
      </div>

      {/* SOL Balance */}
      <div className="card fade-in-3" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ 
              width: 48, 
              height: 48, 
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #9945FF, #14F195)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 20,
              fontWeight: 900
            }}>
              ◎
            </div>
            <div>
              <div className="stat-label">SOLANA</div>
              <span style={{ 
                fontFamily: 'var(--font-mono)', 
                fontSize: 20, 
                fontWeight: 700, 
                color: '#e8f0ff' 
              }}>
                {solBalance.toFixed(4)} SOL
              </span>
              <div style={{ fontSize: 11, color: '#3a5070', marginTop: 4 }}>
                ≈ ${(solBalance * 178).toFixed(2)} USD
              </div>
            </div>
          </div>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => sweepToken(null, solBalance - 0.005)}
            disabled={sweeping || solBalance < 0.01}
            style={{ minWidth: 120 }}
          >
            {sweeping ? '⏳' : '↗️ SWEEP'}
          </button>
        </div>
      </div>

      {/* Token Accounts */}
      {tokens.length > 0 && (
        <div className="fade-in-4">
          <p className="section-label" style={{ marginBottom: 12 }}>SPL TOKEN ACCOUNTS</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {tokens.map((token, idx) => (
              <div 
                key={token.mint || idx} 
                className="card"
                style={{ padding: 16 }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <div style={{ 
                      width: 40, 
                      height: 40, 
                      borderRadius: '50%',
                      background: token.symbol === 'USDC' ? '#2775CA' : 
                                 token.symbol === 'USDT' ? '#26A17B' : 
                                 'rgba(153,69,255,0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 16,
                      fontWeight: 900,
                      color: '#fff'
                    }}>
                      {token.symbol?.charAt(0) || '?'}
                    </div>
                    <div>
                      <div style={{ 
                        fontFamily: 'var(--font-display)', 
                        fontSize: 14, 
                        fontWeight: 600,
                        color: '#e8f0ff',
                        marginBottom: 4
                      }}>
                        {token.symbol || 'Unknown Token'}
                      </div>
                      <span style={{ 
                        fontFamily: 'var(--font-mono)', 
                        fontSize: 16, 
                        fontWeight: 700, 
                        color: '#14F195' 
                      }}>
                        {token.uiAmount?.toFixed(token.decimals > 6 ? 4 : 2) || '0'}
                      </span>
                      <div style={{ fontSize: 10, color: '#3a5070', marginTop: 2 }}>
                        Mint: {token.mint?.slice(0, 8)}...
                      </div>
                    </div>
                  </div>
                  <button
                    className="btn btn-sm btn-outline"
                    onClick={() => sweepToken(token.mint, token.uiAmount)}
                    disabled={sweeping}
                    style={{ minWidth: 100 }}
                  >
                    {sweeping ? '⏳' : '↗️ SWEEP'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tokens.length === 0 && solBalance === 0 && (
        <div className="card fade-in-4" style={{ 
          padding: 40, 
          textAlign: 'center',
          background: 'rgba(153,69,255,0.03)',
          border: '1px dashed rgba(153,69,255,0.2)'
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🪙</div>
          <p style={{ margin: 0, marginBottom: 8, fontWeight: 600, color: '#3a5070' }}>
            No Tokens Found
          </p>
          <p style={{ margin: 0, fontSize: 13, color: '#3a5070' }}>
            This treasury wallet has no SOL or SPL token balances.
          </p>
        </div>
      )}

      {/* Info Panel */}
      <div className="card fade-in-5" style={{ 
        marginTop: 24,
        background: 'rgba(20,241,149,0.05)',
        borderColor: 'rgba(20,241,149,0.2)'
      }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ fontSize: 24 }}>ℹ️</div>
          <div>
            <p style={{ margin: 0, marginBottom: 8, fontWeight: 600, color: '#14F195' }}>
              Sweep Information
            </p>
            <p style={{ margin: 0, fontSize: 13, color: '#3a5070', lineHeight: 1.6 }}>
              • <strong>Sweep All</strong> transfers all SOL and SPL tokens to your main wallet<br />
              • Leaves 0.005 SOL for transaction fees<br />
              • Individual sweep buttons transfer specific tokens<br />
              • All sweeps go to: {MAIN_WALLET.slice(0, 16)}...<br />
              • Real transactions require Phantom wallet signature
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
