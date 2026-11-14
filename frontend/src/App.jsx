// App shell: picks between the customer picker and a customer's Home/Coach
// tabs, inside a phone frame on desktop.

import { useCallback, useEffect, useState } from 'react'
import { getMode } from './api.js'
import TabBar from './components/TabBar.jsx'
import useConversations from './hooks/useConversations.js'
import ChatScreen from './screens/ChatScreen.jsx'
import HomeScreen from './screens/HomeScreen.jsx'
import PickerScreen from './screens/PickerScreen.jsx'
import './App.css'

export default function App() {
  const [mode, setMode] = useState(null)
  const [customer, setCustomer] = useState(null)
  const [tab, setTab] = useState('home')
  const conversations = useConversations()

  useEffect(() => {
    getMode().then(setMode)
  }, [])

  const pick = useCallback((c) => {
    setCustomer(c)
    setTab('home')
  }, [])

  const back = useCallback(() => setCustomer(null), [])

  const { setDraft } = conversations
  const ask = useCallback(
    (question) => {
      if (customer && question) setDraft(customer.customer_id, question)
      setTab('chat')
    },
    [customer, setDraft],
  )

  // Return to the top of each new screen.
  useEffect(() => {
    document.querySelector('.screen-scroll, .picker')?.scrollTo?.(0, 0)
  }, [customer, tab])

  const convo = customer ? conversations.get(customer.customer_id) : null

  return (
    <div className="stage">
      <aside className="stage-caption" aria-hidden="true">
        <span className="logo-mark">S</span>
        <h2>Money Coach</h2>
        <p>
          A chat coach that talks to your own S-Pankki banking data. Three
          baskets, safe-to-spend, what-ifs and home readiness, grounded in
          real transactions.
        </p>
      </aside>
      <div className="device">
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {customer ? (
          <>
            {tab === 'home' ? (
              <HomeScreen customer={customer} mode={mode} onBack={back} onAsk={ask} />
            ) : (
              <ChatScreen
                key={customer.customer_id}
                customer={customer}
                mode={mode}
                convo={convo}
                actions={conversations}
                onBack={back}
              />
            )}
            <TabBar tab={tab} onChange={setTab} busy={convo?.busy} />
          </>
        ) : (
          <PickerScreen mode={mode} onPick={pick} />
        )}
      </div>
    </div>
  )
}
