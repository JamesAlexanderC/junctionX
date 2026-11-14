// Customer picker: hero intro, featured customers and a paginated search.

import { useEffect, useState } from 'react'
import { getFeatured, searchCustomers } from '../api.js'
import { CustomerRow, FeaturedCard } from '../components/CustomerCard.jsx'
import Icon from '../components/Icon.jsx'
import { DemoBanner, ErrorState, ProviderBadge, Skeleton } from '../components/ui.jsx'

const PAGE = 20
const compactNumber = new Intl.NumberFormat('en-IE', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

function useDebounced(value, ms) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return debounced
}

function Hero({ mode }) {
  const data = mode?.health?.data
  return (
    <section className="hero">
      <div className="hero-brand">
        <span className="logo-mark" aria-hidden="true">
          S
        </span>
        <span>S-Pankki</span>
        <span className="hero-badge">
          {mode ? (
            <ProviderBadge
              demo={mode.demo}
              provider={mode.health?.llm?.provider}
              model={mode.health?.llm?.model}
              compact
            />
          ) : (
            <Skeleton width={96} height={22} radius={999} />
          )}
        </span>
      </div>
      <h1>Money Coach</h1>
      <p>
        Talk to your own banking data. Every number in every answer comes
        straight from real transactions.
      </p>
      {data && (
        <dl className="hero-stats">
          <div>
            <dt>Customers</dt>
            <dd>{compactNumber.format(data.customers)}</dd>
          </div>
          <div>
            <dt>Transactions</dt>
            <dd>{compactNumber.format(data.transactions)}</dd>
          </div>
          <div>
            <dt>Coach</dt>
            <dd>{mode.health?.llm?.provider === 'gemini' ? 'Gemini' : 'Offline'}</dd>
          </div>
        </dl>
      )}
    </section>
  )
}

function Featured({ onPick }) {
  const [state, setState] = useState({ loading: true, items: [], error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getFeatured(controller.signal)
      .then((items) => setState({ loading: false, items, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setState({ loading: false, items: [], error })
        }
      })
    return () => controller.abort()
  }, [attempt])

  const retry = () => {
    setState({ loading: true, items: [], error: null })
    setAttempt((n) => n + 1)
  }

  return (
    <section aria-labelledby="featured-title">
      <h2 className="section-title" id="featured-title">
        Featured customers
      </h2>
      {state.error ? (
        <ErrorState
          title="Couldn't load customers"
          message={state.error.message}
          onRetry={retry}
        />
      ) : (
        <div className="featured-grid" aria-busy={state.loading}>
          {state.loading
            ? Array.from({ length: 4 }, (_, i) => (
                <div key={i} className="featured-card skeleton-card">
                  <span className="featured-top">
                    <Skeleton width={44} height={44} radius="50%" />
                    <span className="featured-id">
                      <Skeleton width="60%" height={16} />
                      <Skeleton width="80%" height={12} />
                    </span>
                  </span>
                  <Skeleton width="70%" height={20} />
                  <Skeleton width="50%" height={20} radius={999} />
                </div>
              ))
            : state.items.map((c) => (
                <FeaturedCard key={c.customer_id} customer={c} onPick={onPick} />
              ))}
        </div>
      )}
    </section>
  )
}

function Search({ onPick }) {
  const [query, setQuery] = useState('')
  const search = useDebounced(query.trim(), 300)
  const [attempt, setAttempt] = useState(0)
  const key = `${search}|${attempt}`
  const [state, setState] = useState({
    key: null,
    results: [],
    count: 0,
    more: false,
    error: null,
  })
  // Loading until the response for the current query has arrived.
  const loading = state.key !== key

  // First page whenever the (debounced) query changes.
  useEffect(() => {
    const controller = new AbortController()
    searchCustomers({ search, limit: PAGE, offset: 0 }, controller.signal)
      .then(({ results, count }) =>
        setState({ key, results, count, more: false, error: null }),
      )
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setState({ key, results: [], count: 0, more: false, error })
        }
      })
    return () => controller.abort()
  }, [search, key])

  async function loadMore() {
    setState((s) => ({ ...s, more: true }))
    try {
      const { results } = await searchCustomers({
        search,
        limit: PAGE,
        offset: state.results.length,
      })
      setState((s) => ({ ...s, results: [...s.results, ...results], more: false }))
    } catch (error) {
      setState((s) => ({ ...s, more: false, error }))
    }
  }

  const remaining = state.count - state.results.length

  return (
    <section aria-labelledby="search-title">
      <h2 className="section-title" id="search-title">
        {search ? 'Search results' : 'All customers'}
      </h2>
      <div className="search-box">
        <Icon name="search" size={18} />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by ID, postal code or persona"
          aria-label="Search customers"
          autoComplete="off"
          spellCheck="false"
        />
        {query && (
          <button
            type="button"
            className="icon-btn"
            onClick={() => setQuery('')}
            aria-label="Clear search"
          >
            <Icon name="close" size={16} />
          </button>
        )}
      </div>
      <p className="result-count" aria-live="polite">
        {loading
          ? 'Searching…'
          : `${state.count.toLocaleString('en-IE')} ${
              state.count === 1 ? 'customer' : 'customers'
            }`}
      </p>
      {state.error && !state.results.length ? (
        <ErrorState
          title="Search failed"
          message={state.error.message}
          onRetry={() => setAttempt((n) => n + 1)}
        />
      ) : (
        <ul className={`customer-list${loading ? ' is-loading' : ''}`}>
          {state.results.map((c) => (
            <li key={c.customer_id}>
              <CustomerRow customer={c} onPick={onPick} />
            </li>
          ))}
          {!loading && !state.results.length && (
            <li className="empty">No customers match “{search}”.</li>
          )}
        </ul>
      )}
      {remaining > 0 && !loading && (
        <button
          type="button"
          className="btn btn-outline load-more"
          onClick={loadMore}
          disabled={state.more}
        >
          {state.more
            ? 'Loading…'
            : `Load more (${remaining.toLocaleString('en-IE')} left)`}
        </button>
      )}
    </section>
  )
}

export default function PickerScreen({ mode, onPick }) {
  return (
    <main className="screen picker" id="main">
      <Hero mode={mode} />
      {mode?.demo && <DemoBanner />}
      <Featured onPick={onPick} />
      <Search onPick={onPick} />
      <footer className="picker-footer">
        Prototype built for Junction 2026. Sample data only, not financial advice.
      </footer>
    </main>
  )
}
