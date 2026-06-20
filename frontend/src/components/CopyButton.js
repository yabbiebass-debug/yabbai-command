import React, { useState, useCallback } from 'react';

export default function CopyButton({ text, label, style }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async (e) => {
    e.stopPropagation();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      title={copied ? 'Copied!' : `Copy ${label || ''}`}
      style={{
        background: 'none',
        border: '1px solid ' + (copied ? 'rgba(20,241,149,0.4)' : 'rgba(153,69,255,0.2)'),
        borderRadius: 3,
        padding: '2px 7px',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        fontWeight: 700,
        color: copied ? '#14F195' : '#3a5070',
        transition: 'all 0.2s',
        letterSpacing: '0.08em',
        ...style,
      }}
    >
      {copied ? '✓ COPIED' : label || 'COPY'}
    </button>
  );
}
