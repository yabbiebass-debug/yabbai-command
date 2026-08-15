/* YABBAI COMMAND — SSO gate. Include FIRST on every Director-only page:
     <script src="/shared/sso-gate.js"></script>
   Verifies the shared .yabbai.network Director session via THIS app's own backend
   (/api/auth/me → which asks the hub's /api/auth/sso/verify). Anything not fully
   verified (Google + allowlist + Google Authenticator) bounces to the hub login,
   which returns the Director here after 2FA via the validated ?next= parameter. */
(async () => {
  const HUB_LOGIN = 'https://yabbai.network/login/index.html';
  try {
    const r = await fetch(window.location.origin + '/api/auth/me', { credentials: 'include' });
    if (r.ok) { document.documentElement.dataset.director = '1'; return; }
  } catch (e) {}
  window.location.replace(HUB_LOGIN + '?next=' + encodeURIComponent(window.location.href));
})();
