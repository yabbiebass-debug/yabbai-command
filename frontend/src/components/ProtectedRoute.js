import { useEffect, useState, useRef } from 'react';

const HUB_LOGIN = 'https://yabbai.network/login/index.html';

// Every page component resolves the API through REACT_APP_BACKEND_URL, but this
// gate used a relative '/api/auth/me'. That only works when the API is same-origin,
// which is true on command.yabbai.network and false on token.yabbai.network — where
// the relative path hits the static host, gets the SPA's index.html back with a 200,
// fails to parse as JSON, and bounces the user to the hub as if unauthenticated.
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const AUTH_URL = `${BACKEND_URL}/api/auth/me`;

// LOCAL DEVELOPMENT ONLY — skips Director verification so the UI renders without a
// hub session. Two independent guards, both of which must hold:
//
//   1. NODE_ENV !== 'production'. `craco build` hardcodes NODE_ENV=production, so
//      this whole branch is statically false in a production bundle and webpack's
//      dead-code elimination removes it. It cannot ship even if the flag below is
//      set in a deployed environment.
//   2. REACT_APP_DEV_BYPASS_AUTH === 'true', an explicit opt-in that is absent
//      unless someone deliberately sets it.
//
// This bypasses the FRONTEND gate only. Every director-only backend route still
// requires a real hub session and will keep returning 401, so no protected data is
// exposed by turning this on.
const DEV_BYPASS_AUTH =
  process.env.NODE_ENV !== 'production' &&
  process.env.REACT_APP_DEV_BYPASS_AUTH === 'true';

export function useDirectorAuth() {
  const [isAuthorized, setIsAuthorized] = useState(null);
  const [user, setUser] = useState(null);
  const hasChecked = useRef(false);

  useEffect(() => {
    // Prevent multiple auth checks (which cause redirect loops)
    if (hasChecked.current) return;
    hasChecked.current = true;

    if (DEV_BYPASS_AUTH) {
      console.warn(
        '[auth] DEV BYPASS ACTIVE — Director verification skipped. ' +
        'Local development only. Backend routes remain gated.'
      );
      setUser({ email: 'dev@localhost', dev_bypass: true });
      setIsAuthorized(true);
      document.documentElement.dataset.director = '1';
      return;
    }

    const checkAuth = async () => {
      try {
        const response = await fetch(AUTH_URL, { credentials: 'include' });
        // A static host answers unknown paths with index.html and a 200, so an ok
        // status alone does not mean this was the API. Require JSON before trusting it.
        const contentType = response.headers.get('content-type') || '';
        if (response.ok && contentType.includes('application/json')) {
          const userData = await response.json();
          setUser(userData);
          setIsAuthorized(true);
          document.documentElement.dataset.director = '1';
        } else {
          // Not authorized - redirect to hub login
          // Add a small delay to prevent rapid redirect loops
          setTimeout(() => {
            window.location.replace(
              HUB_LOGIN + '?next=' + encodeURIComponent(window.location.href)
            );
          }, 500);
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        // Fail closed - redirect to login with delay
        setTimeout(() => {
          window.location.replace(
            HUB_LOGIN + '?next=' + encodeURIComponent(window.location.href)
          );
        }, 500);
      }
    };

    checkAuth();
  }, []);

  return { isAuthorized, user };
}

export default function ProtectedRoute({ children }) {
  const { isAuthorized } = useDirectorAuth();

  // Show loading state while checking auth
  if (isAuthorized === null) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'linear-gradient(135deg, #060E20 0%, #0A1128 100%)',
        color: '#e8f0ff',
        fontFamily: 'JetBrains Mono, monospace'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>🔐</div>
          <div style={{ fontSize: 14, color: '#9945FF' }}>Verifying Director credentials...</div>
        </div>
      </div>
    );
  }

  // If authorized, render children. When the dev bypass is what authorised this
  // session, say so permanently and unmissably — an unlabelled bypass is how a
  // local-only shortcut ends up mistaken for a real login.
  if (DEV_BYPASS_AUTH) {
    return (
      <>
        <div style={{
          position: 'sticky', top: 0, zIndex: 9999,
          background: '#F5A623', color: '#1a1000',
          fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 700,
          padding: '6px 12px', textAlign: 'center', letterSpacing: 0.4,
        }}>
          ⚠ DEV AUTH BYPASS ACTIVE — NOT A VERIFIED DIRECTOR SESSION · LOCAL ONLY
        </div>
        {children}
      </>
    );
  }

  return children;
}
