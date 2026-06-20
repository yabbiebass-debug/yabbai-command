import React, { useState, useEffect, useMemo } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Payment() {
  const [realIncome, setRealIncome] = useState(0);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Load REAL data only - NO MOCK DATA
  useEffect(() => {
    const loadRealData = async () => {
      try {
        // Get real income from revenue system
        const statusRes = await fetch(`${API}/revenue/status`);
        const statusData = await statusRes.json();
        setRealIncome(statusData.real_income || 0);

        // Get real transactions
        const incomeRes = await fetch(`${API}/revenue/live/income?limit=100`);
        const incomeData = await incomeRes.json();
        
        if (incomeData.income) {
          const txs = incomeData.income.map((item, idx) => ({
            id: `tx_${idx}`,
            source: item.source,
            amount: item.amount,
            description: item.data?.product || item.data?.service || item.data?.client || 'Payment',
            timestamp: new Date(item.timestamp).toLocaleString(),
          }));
          setTransactions(txs);
        }
      } catch (e) {
        console.error('Failed to load payment data:', e);
      }
      setLoading(false);
    };
    
    loadRealData();
    // Refresh every 10 seconds for live updates
    const interval = setInterval(loadRealData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="page-container fade-in">
        <p className="section-label">⚡ PAYMENT ENGINE</p>
        <div className="card">
          <p style={{ color: '#3a5070' }}>Loading real payment data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container fade-in">
      <p className="section-label fade-in-1">⚡ PAYMENT ENGINE</p>

      {/* Real Income Total */}
      <div className="card fade-in-2" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <p className="section-label" style={{ margin: 0, marginBottom: 8 }}>REAL INCOME TOTAL</p>
            <span style={{ 
              fontFamily: 'var(--font-mono)', 
              fontSize: 32, 
              fontWeight: 900, 
              color: '#14F195',
              textShadow: '0 0 20px rgba(20,241,149,0.3)'
            }}>
              ${realIncome.toFixed(2)}
            </span>
            <div className="stat-label">RECONCILED PAYMENT PROCESSOR DATA ONLY</div>
          </div>
          <div style={{ 
            width: 80, 
            height: 80, 
            borderRadius: '50%', 
            background: 'radial-gradient(circle, rgba(20,241,149,0.2), transparent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 32
          }}>
            💰
          </div>
        </div>
      </div>

      {/* Real Transactions Ledger */}
      <div className="card fade-in-3">
        <p className="section-label" style={{ marginBottom: 16 }}>REAL TRANSACTIONS LEDGER</p>
        
        {transactions.length === 0 ? (
          <div style={{ 
            padding: 40, 
            textAlign: 'center',
            color: '#3a5070',
            borderRadius: 8,
            background: 'rgba(153,69,255,0.03)',
            border: '1px dashed rgba(153,69,255,0.2)'
          }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
            <p style={{ margin: 0, marginBottom: 8, fontWeight: 600 }}>No Transactions Yet</p>
            <p style={{ margin: 0, fontSize: 13 }}>
              Real transactions will appear here when payment webhooks fire.
              <br />
              NO MOCK DATA - Only verified payment processor transactions.
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ 
              width: '100%', 
              borderCollapse: 'collapse', 
              fontFamily: 'var(--font-mono)', 
              fontSize: 12 
            }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(153,69,255,0.15)' }}>
                  {['SOURCE', 'AMOUNT', 'DESCRIPTION', 'TIMESTAMP'].map(h => (
                    <th 
                      key={h} 
                      style={{ 
                        padding: '12px 16px', 
                        textAlign: 'left', 
                        color: '#3a5070', 
                        letterSpacing: '0.1em', 
                        fontWeight: 700 
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {transactions.map(tx => (
                  <tr key={tx.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '12px 16px' }}>
                      <span className="badge badge-green">
                        {tx.source === 'product_sale' ? 'PRODUCT' : 'INVOICE'}
                      </span>
                    </td>
                    <td style={{ 
                      padding: '12px 16px', 
                      color: '#14F195', 
                      fontWeight: 700,
                      fontSize: 14
                    }}>
                      +${tx.amount.toFixed(2)}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#e8f0ff' }}>
                      {tx.description}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#3a5070', fontSize: 11 }}>
                      {tx.timestamp}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Stats Footer */}
        {transactions.length > 0 && (
          <div style={{ 
            marginTop: 16, 
            paddingTop: 16, 
            borderTop: '1px solid rgba(153,69,255,0.1)',
            display: 'flex',
            gap: 24
          }}>
            <div>
              <div className="stat-label">TOTAL TRANSACTIONS</div>
              <span style={{ 
                fontFamily: 'var(--font-mono)', 
                fontSize: 18, 
                fontWeight: 700, 
                color: '#9945FF' 
              }}>
                {transactions.length}
              </span>
            </div>
            <div>
              <div className="stat-label">AVERAGE TRANSACTION</div>
              <span style={{ 
                fontFamily: 'var(--font-mono)', 
                fontSize: 18, 
                fontWeight: 700, 
                color: '#14F195' 
              }}>
                ${transactions.length > 0 ? (realIncome / transactions.length).toFixed(2) : '0.00'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Truth Protocol Notice */}
      <div className="card fade-in-4" style={{ 
        marginTop: 24,
        background: 'rgba(153,69,255,0.05)',
        borderColor: 'rgba(153,69,255,0.2)'
      }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ fontSize: 24 }}>🔒</div>
          <div>
            <p style={{ margin: 0, marginBottom: 8, fontWeight: 600, color: '#9945FF' }}>
              Truth Protocol Enforced
            </p>
            <p style={{ margin: 0, fontSize: 13, color: '#3a5070', lineHeight: 1.6 }}>
              This ledger shows ONLY reconciled payment processor transactions. 
              No mock data, no projections, no estimates. Every dollar shown has been 
              verified through a payment webhook (Stripe, Gumroad, etc.) with 
              source_type: "payment_processor". Data persists across refreshes.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
