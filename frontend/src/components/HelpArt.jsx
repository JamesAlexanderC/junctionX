// Small schematic pictures for the help page: shapes only, never numbers, so
// they illustrate a card without inventing data (CLAUDE.md: no demo data).

import Icon from './Icon.jsx'

const Art = ({ children, label }) => (
  <svg className="help-art" viewBox="0 0 120 64" role="img" aria-label={label}>
    {children}
  </svg>
)

const Stub = ({ x, y, w = 14 }) => (
  <rect className="ink-soft" x={x} y={y} width={w} height={4} rx={2} />
)

export function HBarsArt() {
  return (
    <Art label="Horizontal bars">
      {[28, 62, 44].map((w, i) => (
        <g key={i}>
          <Stub x={8} y={13 + i * 16} />
          <rect className="ink" x={28} y={10 + i * 16} width={w} height={10} rx={3} />
        </g>
      ))}
    </Art>
  )
}

export function ColumnsArt() {
  return (
    <Art label="Columns">
      <line className="axis" x1={10} x2={110} y1={54} y2={54} />
      {[22, 28, 26, 34, 40].map((h, i) => (
        <rect
          key={i}
          className="ink"
          x={16 + i * 19}
          y={54 - h}
          width={11}
          height={h}
          rx={3}
        />
      ))}
    </Art>
  )
}

export function LineArt() {
  const d = 'M10,16 L30,20 L46,30 L64,28 L82,40 L106,46'
  return (
    <Art label="Line">
      <line className="axis" x1={10} x2={110} y1={54} y2={54} />
      <path className="wash" d={`${d} L106,54 L10,54 Z`} />
      <path className="stroke" d={d} />
      <circle className="dot" cx={106} cy={46} r={4} />
    </Art>
  )
}

export function NumberArt() {
  return (
    <Art label="A single amount">
      <Stub x={14} y={14} w={40} />
      <text className="glyph" x={14} y={48}>
        €
      </text>
      <rect className="ink" x={36} y={30} width={56} height={16} rx={4} />
    </Art>
  )
}

export function BasketArt() {
  const parts = [
    ['b1', 44],
    ['b2', 14],
    ['b3', 24],
    ['ink', 18],
  ]
  let x = 10
  return (
    <Art label="Spending split into four baskets">
      {parts.map(([cls, w]) => {
        const el = (
          <rect
            key={cls}
            className={cls}
            x={x}
            y={22}
            width={w - 2}
            height={18}
            rx={3}
          />
        )
        x += w
        return el
      })}
    </Art>
  )
}

export function SliderArt() {
  return (
    <Art label="A slider">
      <Stub x={10} y={14} w={50} />
      <rect className="track" x={10} y={36} width={100} height={6} rx={3} />
      <rect className="ink" x={10} y={36} width={46} height={6} rx={3} />
      <circle className="thumb" cx={56} cy={39} r={8} />
    </Art>
  )
}

export function LevelArt() {
  return (
    <Art label="Level ladder and progress">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <circle
          key={i}
          className={i < 2 ? 'ink' : i === 2 ? 'ring' : 'ring-soft'}
          cx={16 + i * 18}
          cy={20}
          r={6}
        />
      ))}
      <rect className="track" x={10} y={40} width={100} height={6} rx={3} />
      <rect className="ink" x={10} y={40} width={55} height={6} rx={3} />
    </Art>
  )
}

export function GoalArt() {
  return (
    <Art label="A savings goal">
      <path className="stroke" d="M16,48 V14" />
      <path className="flag" d="M16,14 H34 L30,20 L34,26 H16 Z" />
      <Stub x={44} y={16} w={46} />
      <rect className="track" x={44} y={34} width={66} height={6} rx={3} />
      <rect className="ink" x={44} y={34} width={30} height={6} rx={3} />
    </Art>
  )
}

export function QuestionArt() {
  return (
    <Art label="A question with answers to tap">
      <Stub x={10} y={10} w={70} />
      {[10, 46, 82].map((x) => (
        <rect key={x} className="chip" x={x} y={30} width={30} height={14} rx={7} />
      ))}
    </Art>
  )
}

export function AlertArt() {
  return (
    <Art label="An alert">
      <rect className="panel" x={8} y={12} width={104} height={40} rx={6} />
      <rect className="b3" x={8} y={12} width={5} height={40} rx={2} />
      <Stub x={22} y={22} w={54} />
      <rect className="ink-soft" x={22} y={34} width={76} height={4} rx={2} />
    </Art>
  )
}

export function PlanArt() {
  return (
    <Art label="A plan with steps">
      {[0, 1, 2].map((i) => (
        <g key={i}>
          <circle className="ink" cx={16} cy={14 + i * 16} r={5} />
          <path className="tick-mark" d={`M13.5,${14 + i * 16} l2,2 l3.5,-4`} />
          <rect
            className="ink-soft"
            x={28}
            y={12 + i * 16}
            width={60 - i * 10}
            height={4}
            rx={2}
          />
        </g>
      ))}
    </Art>
  )
}

export function BeforeAfterArt() {
  return (
    <Art label="Before and after">
      <rect className="ring-soft-fill" x={14} y={30} width={22} height={24} rx={3} />
      <path className="stroke" d="M48,38 H70 M64,32 L70,38 L64,44" />
      <rect className="ink" x={82} y={14} width={22} height={40} rx={3} />
    </Art>
  )
}

// Icons for "How it works".
export function StepIcon({ kind }) {
  return <Icon name={kind} size={28} className="help-icon" />
}
