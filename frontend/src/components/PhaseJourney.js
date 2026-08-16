import React from 'react';

/**
 * The yabby journey: PUMP -> ESKY -> MISSION -> SCALE -> WITHDRAW.
 *
 * The artwork is decorative; the numbers are not. Agent counts and cycle totals
 * come from /api/agents/status. Nothing here implies completion or progress,
 * because the pool does not progress — every agent walks all five phases and
 * starts again. A station lights up when agents are currently in it, and goes
 * dim when none are. That is a live state, not a milestone.
 */

const PHASES = [
  { id: 'pump', label: 'PUMP', blurb: 'pumped up' },
  { id: 'esky', label: 'ESKY', blurb: 'in the esky' },
  { id: 'mission', label: 'MISSION', blurb: 'on mission' },
  { id: 'scale', label: 'SCALE', blurb: 'scaling up' },
  { id: 'withdraw', label: 'WITHDRAW', blurb: 'setting sail' },
];

const LIVE = '#14F195';
const IDLE = '#2a4060';
const ACCENT = '#9945FF';
const SHELL = '#E8542A';
const SHELL_DARK = '#B33A16';

/** A yabby, facing right. Scales with `s`. */
function Yabby({ x, y, s = 1, opacity = 1, glow = false }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
      {glow && <ellipse cx="0" cy="0" rx="17" ry="11" fill={LIVE} opacity="0.16" />}
      {/* antennae */}
      <path d="M6 -5 L20 -13" stroke={SHELL_DARK} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <path d="M6 -1 L21 -6" stroke={SHELL_DARK} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      {/* claws */}
      <path d="M5 -6 L14 -11 L11 -6 Z" fill={SHELL} />
      <path d="M5 2 L14 7 L11 2 Z" fill={SHELL} />
      {/* body */}
      <ellipse cx="0" cy="-2" rx="8" ry="6" fill={SHELL} />
      {/* tail segments */}
      <ellipse cx="-8" cy="-1" rx="4.5" ry="4" fill={SHELL} opacity="0.95" />
      <ellipse cx="-13" cy="0" rx="3.6" ry="3.2" fill={SHELL} opacity="0.9" />
      <path d="M-17 0 l-6 -4 l1.5 4 l-1.5 4 z" fill={SHELL_DARK} />
      {/* eyes */}
      <circle cx="3" cy="-5" r="1.5" fill="#C6F24E" />
      <circle cx="3" cy="0" r="1.5" fill="#C6F24E" />
    </g>
  );
}

/** Per-phase station glyph. */
function Station({ phase, active }) {
  const c = active ? LIVE : IDLE;
  switch (phase) {
    case 'pump': // upward pressure
      return (
        <g stroke={c} strokeWidth="2" fill="none" strokeLinecap="round">
          <path d="M0 8 L0 -8" />
          <path d="M-5 -3 L0 -8 L5 -3" />
          <path d="M-7 10 L7 10" />
        </g>
      );
    case 'esky': // the cooler
      return (
        <g stroke={c} strokeWidth="1.8" fill="none">
          <rect x="-9" y="-4" width="18" height="12" rx="2" />
          <path d="M-10 -4 L10 -4" />
          <path d="M-6 -4 L-6 -7 L6 -7 L6 -4" />
        </g>
      );
    case 'mission': // target
      return (
        <g stroke={c} strokeWidth="1.8" fill="none">
          <circle cx="0" cy="0" r="8" />
          <circle cx="0" cy="0" r="3.5" />
          <path d="M0 -11 L0 -8 M0 8 L0 11 M-11 0 L-8 0 M8 0 L11 0" strokeLinecap="round" />
        </g>
      );
    case 'scale': // stacked bars
      return (
        <g fill={c}>
          <rect x="-9" y="2" width="4" height="7" rx="1" />
          <rect x="-2" y="-2" width="4" height="11" rx="1" />
          <rect x="5" y="-7" width="4" height="16" rx="1" />
        </g>
      );
    case 'withdraw': // setting sail
      return (
        <g stroke={c} strokeWidth="1.8" fill="none" strokeLinecap="round">
          <path d="M-9 7 L9 7 L6 11 L-6 11 Z" fill={c} fillOpacity="0.25" />
          <path d="M0 6 L0 -9" />
          <path d="M1 -8 L8 2 L1 2 Z" fill={c} fillOpacity="0.35" />
        </g>
      );
    default:
      return null;
  }
}

export default function PhaseJourney({ pool }) {
  const W = 720;
  const H = 190;
  const trackY = 118;
  const left = 60;
  const gap = (W - left * 2) / (PHASES.length - 1);

  const breakdown = pool?.phase_breakdown || {};
  const totalAgents = pool?.total_agents;
  const totalCycles = pool?.total_cycles;

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', minWidth: 560, height: 'auto' }}
           role="img" aria-label="Agent pool phases: pump, esky, mission, scale, withdraw">
        <defs>
          <linearGradient id="pjTrack" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={ACCENT} stopOpacity="0.45" />
            <stop offset="100%" stopColor={LIVE} stopOpacity="0.45" />
          </linearGradient>
          <style>{`
            @keyframes pjDrift {
              0%   { transform: translateX(0px);   opacity: 0; }
              12%  { opacity: 1; }
              88%  { opacity: 1; }
              100% { transform: translateX(${W - left * 2}px); opacity: 0; }
            }
            @keyframes pjBob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
            .pj-drift { animation: pjDrift 11s linear infinite; }
            .pj-bob   { animation: pjBob 2.6s ease-in-out infinite; }
            @media (prefers-reduced-motion: reduce) {
              .pj-drift, .pj-bob { animation: none; }
            }
          `}</style>
        </defs>

        {/* the track the yabbies travel */}
        <path d={`M${left} ${trackY} L${W - left} ${trackY}`}
              stroke="url(#pjTrack)" strokeWidth="2.5" strokeLinecap="round" fill="none" />

        {/* yabbies drifting left to right, purely decorative */}
        <g transform={`translate(${left} ${trackY - 16})`}>
          <g className="pj-drift"><g className="pj-bob"><Yabby x={0} y={0} s={0.85} glow /></g></g>
        </g>
        <g transform={`translate(${left} ${trackY - 16})`}>
          <g className="pj-drift" style={{ animationDelay: '3.6s' }}>
            <g className="pj-bob"><Yabby x={0} y={0} s={0.65} opacity={0.75} /></g>
          </g>
        </g>
        <g transform={`translate(${left} ${trackY - 16})`}>
          <g className="pj-drift" style={{ animationDelay: '7.2s' }}>
            <g className="pj-bob"><Yabby x={0} y={0} s={0.5} opacity={0.5} /></g>
          </g>
        </g>

        {PHASES.map((p, i) => {
          const x = left + i * gap;
          const data = breakdown[p.id] || {};
          const active = (data.active_agents ?? 0) > 0;
          const cycles = data.total_cycles ?? 0;
          const col = active ? LIVE : IDLE;

          return (
            <g key={p.id}>
              <circle cx={x} cy={trackY} r="20" fill="#060E20" stroke={col}
                      strokeWidth={active ? 2 : 1.2} opacity={active ? 1 : 0.6} />
              {active && <circle cx={x} cy={trackY} r="26" fill={LIVE} opacity="0.07" />}
              <g transform={`translate(${x} ${trackY})`}><Station phase={p.id} active={active} /></g>

              <text x={x} y={trackY + 42} textAnchor="middle"
                    fontFamily="JetBrains Mono, monospace" fontSize="11" fontWeight="700"
                    fill={active ? LIVE : '#4a6080'} letterSpacing="0.5">
                {p.label}
              </text>
              <text x={x} y={trackY + 56} textAnchor="middle"
                    fontFamily="JetBrains Mono, monospace" fontSize="9" fill="#3a5070">
                {p.blurb}
              </text>

              <text x={x} y={trackY - 34} textAnchor="middle"
                    fontFamily="Unbounded, sans-serif" fontSize="15" fontWeight="900"
                    fill={active ? '#e8f0ff' : '#2a4060'}>
                {data.active_agents ?? '—'}
              </text>
              <text x={x} y={trackY - 46} textAnchor="middle"
                    fontFamily="JetBrains Mono, monospace" fontSize="8" fill="#3a5070">
                {cycles ? `${cycles.toLocaleString()} cyc` : 'agents'}
              </text>
            </g>
          );
        })}

        {totalAgents != null && (
          <text x={W / 2} y={20} textAnchor="middle"
                fontFamily="JetBrains Mono, monospace" fontSize="10" fill="#3a5070">
            {totalAgents} AGENTS · {totalCycles?.toLocaleString()} CYCLES · LOOPS CONTINUOUSLY
          </text>
        )}
      </svg>
    </div>
  );
}
