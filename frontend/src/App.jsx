// Saldo: log in, then a demo landing page where you pick a real customer,
// then that customer's chat-first view (or the help page). No demo data, no
// fallbacks.

import './App.css'
import CustomerView from './components/CustomerView.jsx'
import Landing from './components/Landing.jsx'
import Login from './components/Login.jsx'
import { useLoggedIn } from './lib/auth.js'
import {
  enterCustomer,
  exitToDemo,
  openHelp,
  parseHash,
  useHash,
} from './lib/route.js'

export default function App() {
  const loggedIn = useLoggedIn()
  const { customerId, help } = parseHash(useHash())
  // A #/c/<id> link survives the login screen and opens once logged in.
  if (!loggedIn) return <Login />
  return customerId ? (
    // Keyed so switching customer starts with fresh insights and chat; the
    // help page opens over the same view, so the chat is kept.
    <CustomerView
      key={customerId}
      customerId={customerId}
      onExit={exitToDemo}
      help={help}
      onHelp={() => openHelp(customerId)}
      onCloseHelp={() => enterCustomer(customerId)}
    />
  ) : (
    <Landing onEnter={enterCustomer} />
  )
}
