import React from 'react';

export function Skeleton({ width = '100%', height = 18, borderRadius = 4, style }) {
  return (
    <div style={{
      width, height, borderRadius,
      background: 'linear-gradient(90deg, rgba(153,69,255,0.04) 0%, rgba(153,69,255,0.1) 50%, rgba(153,69,255,0.04) 100%)',
      backgroundSize: '200% 100%',
      animation: 'skeleton-shimmer 1.5s infinite',
      ...style,
    }} />
  );
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <Skeleton height={20} width="60%" />
      {[...Array(lines)].map((_, i) => (
        <Skeleton key={`skeleton-line-${i}`} height={14} width={`${70 + i * 5}%`} />
      ))}
    </div>
  );
}
