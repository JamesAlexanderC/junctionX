import { createContext, useContext } from 'react'

// Shared app state for screens and cards:
//   profile           the customer's profile JSON
//   ask(text, opts)   open chat with `text`; opts {depth, send: true} sends it
//   go(route)         navigate, e.g. go('explore/baskets')
//   actions           API mutations (createGoal, snooze, saveLoan, ...)
export const AppContext = createContext({
  profile: null,
  demo: false,
  ask: () => {},
  go: () => {},
  actions: {},
})

export const useApp = () => useContext(AppContext)
