import { useEffect, useState, useRef } from 'react';

const HUB_LOGIN = 'https://yabbai.network/login/index.html';

export function useDirectorAuth() {
  const [isAuthorized, setIsAuthorized] = useState(null);
  const [user, setUser] = useState(null);
  const hasChecked = useRef(false);

  useEffect(() => {
    // Prevent multiple auth checks (which cause redirect loops)
    if (hasChecked.current) return;
    hasChecked.current = true;

    const checkAuth = async () => {
      try {
        const response = await fetch('/api/auth/me', { credentials: 'include' });
        if (response.ok) {
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

  // If authorized, render children
  return children;
}
