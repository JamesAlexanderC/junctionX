// MB-8: simulated PSD2 multi-bank UI (MULTIBANK_PLAN.md §7).
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Accounts, { PartialViewBanner } from '../components/Accounts.jsx'
import { ReplyCard } from '../components/Cards.jsx'
import Chat from '../components/Chat.jsx'
import ConnectBank from '../components/ConnectBank.jsx'

const json = (data, status = 200) => new Response(JSON.stringify(data), { status })
afterEach(() => vi.unstubAllGlobals())

const NORDEA = {
  bank: 'Nordea',
  consent_id: 7,
  name: 'Car loan account',
  type: 'current',
  iban_masked: 'FI•• •••• •••• 4821',
  balance_eur: 57.79,
  balance_date: '2026-09-30',
  consent_expires_at: '2027-03-29T12:00:00+00:00',
  simulated: true,
}
const SBANK = {
  bank: 'S-Bank',
  name: 'S-Bank account',
  type: 'current',
  balance_eur: 1085.77,
  simulated: false,
}
const DELTA = {
  safe_to_spend: { before: 18.7, after: 0 },
  dsti: { before: null, after: 0.16 },
  buffer_months: { before: -0.18, after: -0.12 },
  level: { before: 2, after: 2 },
  monthly_income: { before: 2041.11, after: 2041.11 },
}

function connectFetch() {
  return vi.fn(async (url, init = {}) => {
    if (url.startsWith('/api/banks/')) {
      return json([
        { code: 'NDEAFIHH', name: 'Nordea' },
        { code: 'OKOYFIHH', name: 'OP' },
      ])
    }
    if (url === '/api/consents/' && init.method === 'POST') {
      return json({ consent_id: 7, status: 'pending' }, 201)
    }
    if (url === '/api/consents/7/authorise/') {
      return json({ consent_id: 7, status: 'active', bank_name: 'Nordea', accounts_found: 1 })
    }
    if (url.startsWith('/api/accounts/')) {
      return json({ accounts: [SBANK, NORDEA], coverage: 'full', delta: DELTA })
    }
    return json({}, 404)
  })
}

describe('connect flow', () => {
  it('goes bank -> consent -> connected without any credential field', async () => {
    const fetch = connectFetch()
    vi.stubGlobal('fetch', fetch)
    const onConnected = vi.fn()
    const { container } = render(
      <ConnectBank customerId="CUST03369" onClose={() => {}} onConnected={onConnected} />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Nordea' }))
    expect(screen.getByText(/It cannot move money/)).toBeTruthy()
    expect(container.querySelector('input')).toBeNull()
    expect(screen.queryByLabelText(/password|username|pin/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Allow' }))
    expect(await screen.findByText(/Connected to Nordea/)).toBeTruthy()
    expect(container.querySelector('input')).toBeNull()
    expect(screen.getByText('Safe to spend')).toBeTruthy()
    expect(screen.getByText('DSTI')).toBeTruthy()
    expect(onConnected).toHaveBeenCalled()
    const posted = fetch.mock.calls.filter(([, init]) => init?.body)
    for (const [, init] of posted) {
      expect(Object.keys(JSON.parse(init.body))).toEqual(['customer_id', 'bank_code'])
    }
  })

  it('cancel on the consent screen connects nothing', async () => {
    const fetch = connectFetch()
    vi.stubGlobal('fetch', fetch)
    const onClose = vi.fn()
    render(<ConnectBank customerId="CUST03369" onClose={onClose} onConnected={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'OP' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    expect(fetch.mock.calls.some(([url]) => url.includes('/consents/'))).toBe(false)
  })
})

describe('accounts', () => {
  it('shows a source badge on other-bank numbers only', () => {
    render(<ReplyCard card={{ type: 'accounts', accounts: [
      { bank: 'S-Bank', name: 'S-Bank account', type: 'current', balance: 1085.77 },
      { bank: 'Nordea', name: 'Car loan account', type: 'current', balance: 57.79,
        simulated: true },
    ] }} onSend={() => {}} />)
    expect(screen.getAllByText('Nordea · simulated')).toHaveLength(1)
    expect(screen.queryByText('S-Bank · simulated')).toBeNull()
  })

  it('disconnect asks for confirmation first', () => {
    const onDisconnect = vi.fn()
    render(<Accounts data={{ accounts: [SBANK, NORDEA], coverage: 'full' }}
      onDisconnect={onDisconnect} onConnect={() => {}} />)
    expect(screen.getByText('FI•• •••• •••• 4821')).toBeTruthy()
    expect(screen.getByText('Nordea · simulated')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Disconnect Nordea' }))
    expect(onDisconnect).not.toHaveBeenCalled()
    expect(screen.getByText(/deletes the accounts and transactions/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, disconnect' }))
    expect(onDisconnect).toHaveBeenCalledWith(7)
  })

  it('the partial-view banner offers to connect', () => {
    const onConnect = vi.fn()
    render(<PartialViewBanner coverage="partial" onConnect={onConnect} />)
    expect(screen.getByText(/I only see your S-Bank account/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Connect another bank' }))
    expect(onConnect).toHaveBeenCalled()
  })

  it('no banner when the view is not partial', () => {
    const { container } = render(<PartialViewBanner coverage="full" onConnect={() => {}} />)
    expect(container.textContent).toBe('')
  })
})

describe('chat', () => {
  it('the Connect another bank chip opens the flow instead of sending', () => {
    const onSend = vi.fn()
    const onConnect = vi.fn()
    const reply = { text: 'I only see your S-Bank account.', depth: 1,
      chips: ['Connect another bank', 'What is safe to spend?'] }
    render(<Chat messages={[{ role: 'assistant', reply }]} onSend={onSend}
      onConnect={onConnect} />)
    fireEvent.click(screen.getByRole('button', { name: 'Connect another bank' }))
    expect(onConnect).toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'What is safe to spend?' }))
    expect(onSend).toHaveBeenCalled()
  })
})
