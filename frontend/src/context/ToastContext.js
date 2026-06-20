import React, { createContext, useContext, useState, useCallback, useRef } from 'react';

const ToastContext = createContext(null);

let _id = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef({});

  const dismiss = useCallback((id) => {
    clearTimeout(timers.current[id]);
    setToasts(prev => prev.map(t => t.id === id ? { ...t, leaving: true } : t));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 300);
  }, []);

  const toast = useCallback(({ message, type = 'info', duration = 4000 }) => {
    const id = ++_id;
    setToasts(prev => [{ id, message, type, leaving: false }, ...prev].slice(0, 6));
    timers.current[id] = setTimeout(() => dismiss(id), duration);
    return id;
  }, [dismiss]);

  const success = useCallback((msg, opts) => toast({ message: msg, type: 'success', ...opts }), [toast]);
  const error = useCallback((msg, opts) => toast({ message: msg, type: 'error', duration: 6000, ...opts }), [toast]);
  const warn = useCallback((msg, opts) => toast({ message: msg, type: 'warn', ...opts }), [toast]);
  const info = useCallback((msg, opts) => toast({ message: msg, type: 'info', ...opts }), [toast]);

  return (
    <ToastContext.Provider value={{ toast, success, error, warn, info }}>
      {children}
      <ToastStack toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside ToastProvider');
  return ctx;
}

const TYPE_STYLES = {
  success: { border: 'rgba(20,241,149,0.4)', bg: 'rgba(20,241,149,0.08)', icon: '✓', color: '#14F195' },
  error:   { border: 'rgba(255,80,80,0.4)',  bg: 'rgba(255,80,80,0.08)',  icon: '✕', color: '#ff6060' },
  warn:    { border: 'rgba(245,166,35,0.4)', bg: 'rgba(245,166,35,0.08)', icon: '⚠', color: '#F5A623' },
  info:    { border: 'rgba(153,69,255,0.4)', bg: 'rgba(153,69,255,0.08)', icon: 'ℹ', color: '#9945FF' },
};

function ToastStack({ toasts, dismiss }) {
  if (!toasts.length) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
    }}>
      {toasts.map(t => {
        const s = TYPE_STYLES[t.type] || TYPE_STYLES.info;
        return (
          <div
            key={t.id}
            onClick={() => dismiss(t.id)}
            style={{
              pointerEvents: 'all',
              minWidth: 280, maxWidth: 380,
              background: 'rgba(6,14,32,0.97)',
              border: `1px solid ${s.border}`,
              borderRadius: 6,
              padding: '10px 14px',
              display: 'flex', alignItems: 'flex-start', gap: 10,
              cursor: 'pointer',
              backdropFilter: 'blur(12px)',
              boxShadow: `0 4px 24px rgba(0,0,0,0.5), 0 0 12px ${s.border}`,
              opacity: t.leaving ? 0 : 1,
              transform: t.leaving ? 'translateX(20px)' : 'translateX(0)',
              transition: 'all 0.3s ease',
              animation: 'fade-in-up 0.3s ease forwards',
            }}
          >
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 900,
              color: s.color, flexShrink: 0, marginTop: 1,
            }}>{s.icon}</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, color: '#e8f0ff',
              lineHeight: 1.5, flex: 1,
            }}>{t.message}</span>
          </div>
        );
      })}
    </div>
  );
}
