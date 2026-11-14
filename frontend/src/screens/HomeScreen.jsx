// Customer Home: the dashboard built from /api/customers/<id>/overview/.

import { useEffect, useState } from 'react'
import { getOverview, peekOverview } from '../api.js'
import { fullDate } from '../format.js'
import AppBar from '../components/AppBar.jsx'
import BalanceHeader from '../components/home/BalanceHeader.jsx'
import BasketsCard from '../components/home/BasketsCard.jsx'
import CashflowCard from '../components/home/CashflowCard.jsx'
import HomeReadinessCard from '../components/home/HomeReadinessCard.jsx'
import InsightsCard from '../components/home/InsightsCard.jsx'
import PersonaCard from '../components/home/PersonaCard.jsx'
import SafeToSpendCard from '../components/home/SafeToSpendCard.jsx'
import { ErrorState, ProviderBadge, Skeleton } from '../components/ui.jsx'

function HomeSkeleton() {
  return (
    <div className="home-skeleton" aria-hidden="true">
      <section className="balance-header">
        <Skeleton width={140} height={12} className="on-dark" />
        <Skeleton width={200} height={36} className="on-dark" />
        <Skeleton width="100%" height={44} className="on-dark" />
      </section>
      <div className="cards">
        {[220, 260, 240].map((h, i) => (
          <div key={i} className="card">
            <Skeleton width="40%" height={14} />
            <Skeleton width="60%" height={32} />
            <Skeleton width="100%" height={h - 90} radius={8} />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function HomeScreen({ customer, mode, onBack, onAsk }) {
  const id = customer.customer_id
  const [state, setState] = useState(() => {
    const cached = peekOverview(id)
    return cached
      ? { id, data: cached, error: null }
      : { id: null, data: null, error: null }
  })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let live = true
    getOverview(id)
      .then((data) => live && setState({ id, data, error: null }))
      .catch((error) => live && setState({ id, data: null, error }))
    return () => {
      live = false
    }
  }, [id, attempt])

  const ready = state.id === id
  const o = ready ? state.data : null

  return (
    <main className="screen home" id="main">
      <AppBar
        title="Money Coach"
        subtitle={`Customer ${id}`}
        onBack={onBack}
        backLabel="Back to customers"
        right={
          <ProviderBadge
            demo={mode?.demo}
            provider={mode?.health?.llm?.provider}
            tiny
          />
        }
      />
      <div className="screen-scroll" aria-busy={!ready}>
        {!ready && <HomeSkeleton />}
        {ready && state.error && (
          <ErrorState
            title="Couldn't load this customer"
            message={state.error.message}
            onRetry={() => {
              setState({ id: null, data: null, error: null })
              setAttempt((n) => n + 1)
            }}
          />
        )}
        {o && (
          <>
            <BalanceHeader overview={o} />
            <div className="cards">
              <SafeToSpendCard data={o.safe_to_spend} onAsk={onAsk} />
              <InsightsCard insights={o.insights} onAsk={onAsk} />
              <BasketsCard baskets={o.baskets} lastMonth={o.last_month} onAsk={onAsk} />
              <CashflowCard data={o.monthly_cashflow} onAsk={onAsk} />
              <PersonaCard persona={o.persona} onAsk={onAsk} />
              <HomeReadinessCard data={o.home_readiness} onAsk={onAsk} />
              <p className="as-of">
                Figures as of {fullDate(o.as_of)}. Estimates only, not financial
                advice.
              </p>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
