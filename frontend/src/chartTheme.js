// Shared chart colours and tooltip styling (validated for CVD separation).

// Basket colours first, so pies of the three baskets match the dashboard.
export const SERIES = [
  '#0f7a45', // must-pay bills
  '#e08a00', // surprise essentials
  '#dc4566', // everyday leakage
  '#2f6fa3',
  '#7a5bb5',
  '#5f6b66',
]

export const BASKET_COLORS = {
  mandatory_regular: SERIES[0],
  mandatory_irregular: SERIES[1],
  leakage: SERIES[2],
}

export const CASHFLOW = { income: '#00aa46', spend: '#2f6fa3', net: '#1f1f1f' }

export const tooltipStyle = {
  contentStyle: {
    border: '1px solid var(--border)',
    borderRadius: 8,
    boxShadow: 'var(--shadow-md)',
    fontSize: 13,
    padding: '6px 10px',
  },
  labelStyle: { color: 'var(--text)', fontWeight: 700, marginBottom: 2 },
  itemStyle: { color: 'var(--body)', padding: 0 },
}

export const axisProps = {
  tick: { fontSize: 11, fill: 'var(--muted)' },
  tickLine: false,
  axisLine: false,
}
