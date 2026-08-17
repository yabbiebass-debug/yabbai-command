/**
 * Suppresses a benign DataCloneError that some browser extensions raise when
 * they try to structured-clone a PerformanceServerTiming entry. It is noise: it
 * originates outside the app, it affects nothing, and it fills the console.
 *
 * WHY THIS IS A FILE AND NOT AN INLINE SCRIPT
 *
 * It used to live inline in index.html. The CSP in netlify.toml is
 * `script-src 'self'` with no 'unsafe-inline' and no nonce, so the browser
 * refused to execute it on every deployed page — this handler has never run in
 * production since the CSP was tightened. It worked locally, where no CSP header
 * is served, which is exactly why it went unnoticed.
 *
 * Served from the same origin, it satisfies 'self' and runs. The alternative was
 * adding 'unsafe-inline' to script-src, which would re-permit every inline
 * script on the page and give up most of the value of having a CSP at all. Not
 * worth it to silence one warning.
 *
 * Loaded without defer/async so it installs before the bundle executes.
 */
window.addEventListener(
  'error',
  function (e) {
    if (
      e.error instanceof DOMException &&
      e.error.name === 'DataCloneError' &&
      e.message &&
      e.message.includes('PerformanceServerTiming')
    ) {
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  },
  true
);
