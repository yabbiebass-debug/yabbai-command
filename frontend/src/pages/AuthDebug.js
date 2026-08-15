import React, { useState, useEffect } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function AuthDebug() {
  const [authStatus, setAuthStatus] = useState(null);
  const [cookies, setCookies] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Get all cookies
    const allCookies = document.cookie.split(';').map(c => c.trim());
    setCookies(allCookies);

    // Check auth
    fetch(`${BACKEND_URL}/api/auth/me`, { credentials: 'include' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          setAuthStatus({ status: 'authenticated', user: data });
        } else {
          setAuthStatus({ status: 'not_authenticated', code: res.status });
        }
      })
      .catch((err) => {
        setError(err.message);
      });
  }, []);

  return (
    <div style={{ padding: 40, fontFamily: 'monospace', background: '#060E20', color: '#e8f0ff', minHeight: '100vh' }}>
      <h1 style={{ color: '#9945FF' }}>🔍 Auth Debug Page</h1>
      
      <div style={{ background: '#0A1128', padding: 20, borderRadius: 8, marginTop: 20 }}>
        <h2 style={{ color: '#14F195' }}>Auth Status</h2>
        {authStatus ? (
          <pre style={{ color: authStatus.status === 'authenticated' ? '#14F195' : '#FF6B6B' }}>
            {JSON.stringify(authStatus, null, 2)}
          </pre>
        ) : (
          <p>Checking...</p>
        )}
        {error && <p style={{ color: '#FF6B6B' }}>Error: {error}</p>}
      </div>

      <div style={{ background: '#0A1128', padding: 20, borderRadius: 8, marginTop: 20 }}>
        <h2 style={{ color: '#14F195' }}>Cookies (document.cookie)</h2>
        {cookies.length > 0 ? (
          <ul>
            {cookies.map((cookie, i) => (
              <li key={i} style={{ marginBottom: 8 }}>
                <code style={{ color: '#9945FF' }}>{cookie}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: '#FF6B6B' }}>No cookies found</p>
        )}
      </div>

      <div style={{ background: '#0A1128', padding: 20, borderRadius: 8, marginTop: 20 }}>
        <h2 style={{ color: '#14F195' }}>Expected Cookie</h2>
        <p>Looking for: <code style={{ color: '#9945FF' }}>session_token</code></p>
        <p>Domain should be: <code style={{ color: '#9945FF' }}>.yabbai.network</code></p>
      </div>

      <div style={{ marginTop: 20 }}>
        <a href="/" style={{ color: '#14F195' }}>← Back to Command Centre</a>
      </div>
    </div>
  );
}
