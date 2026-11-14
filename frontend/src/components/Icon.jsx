// Every icon in the app comes from this one map (Lucide, ISC licence), so
// size, stroke and accessibility stay the same everywhere. Icons are always
// decorative: the button or heading next to them carries the accessible name.
// Swap an icon here and it changes across the site.

import {
  ArrowLeft,
  Building2,
  ChartColumn,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Clock,
  House,
  Landmark,
  LayoutGrid,
  LogIn,
  LogOut,
  MessageCircle,
  Pause,
  Repeat,
  SendHorizontal,
  ShoppingBag,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
  Trophy,
  UserRound,
  Users,
  Wallet,
  Wrench,
  X,
} from 'lucide-react'

const ICONS = {
  // Actions and navigation
  back: ArrowLeft,
  chevron: ChevronRight,
  close: X,
  help: CircleHelp,
  login: LogIn,
  logout: LogOut,
  send: SendHorizontal,
  fix: Wrench,
  check: CircleCheck,
  // Tabs
  overview: House,
  coach: MessageCircle,
  // Status
  error: CircleAlert,
  alert: TriangleAlert,
  behind: Clock,
  paused: Pause,
  // Help page steps
  ask: MessageCircle,
  numbers: ChartColumn,
  cards: LayoutGrid,
  // People
  customer: UserRound,
  suggest: Sparkles,
  // Insight sections (Insights.jsx section keys)
  alerts: TriangleAlert,
  forecast: TrendingUp,
  income: Wallet,
  baskets: ShoppingBag,
  habits: Repeat,
  goals: Target,
  levels: Trophy,
  mortgage: Landmark,
  benchmarks: Users,
  multibank: Building2,
}

export default function Icon({ name, size = 18, className = '' }) {
  const Glyph = ICONS[name]
  if (!Glyph) return null
  return (
    <Glyph
      className={`icon ${className}`.trim()}
      size={size}
      strokeWidth={2}
      aria-hidden="true"
      focusable="false"
    />
  )
}
