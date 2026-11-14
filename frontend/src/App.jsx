// Saldo: log in, then a demo landing page where you pick a real customer,
// then that customer's chat-first view. No demo data, no fallbacks.

import './App.css'
import CustomerView from './components/CustomerView.jsx'
import Landing from './components/Landing.jsx'
import Login from './components/Login.jsx'
import { useLoggedIn } from './lib/auth.js'
import { enterCustomer, exitToDemo, useHashRoute } from './lib/route.js'

export default function App() {
  const loggedIn = useLoggedIn()
  const customerId = useHashRoute()
  // A #/c/<id> link survives the login screen and opens once logged in.
  if (!loggedIn) return <Login />
  return customerId ? (
    // Keyed so switching customer starts with fresh insights and chat.
    <CustomerView key={customerId} customerId={customerId} onExit={exitToDemo} />
  ) : (
    <Landing onEnter={enterCustomer} />
  )
}
