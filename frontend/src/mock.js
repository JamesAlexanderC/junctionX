// Demo-mode stand-in for the backend. All numbers here are made up and only
// exist so the UI can be built and clicked through before the API is ready.

export const MOCK_CUSTOMERS = [
  { customer_id: 'demo-thriving', customer_age: 25, customer_postal_code: '00100' },
  { customer_id: 'demo-struggling', customer_age: 23, customer_postal_code: '33100' },
]

const ANSWERS = [
  {
    match: /basket|where.*money/i,
    text:
      'You spent **€1,840** last month. **€1,120** went on must-pay bills ' +
      '(basket 1), **€210** on one-off essentials like the dentist (basket 2), ' +
      'and **€510** leaked out on everyday stuff (basket 3).\n\n' +
      'Basket 3 is the one you control most. Trimming it by a quarter frees ' +
      'up about **€128 a month**.',
    chart: {
      kind: 'pie',
      title: 'Last month by basket',
      unit: '€',
      data: [
        { label: 'Mandatory & regular', value: 1120 },
        { label: 'Mandatory & irregular', value: 210 },
        { label: 'Everyday leakage', value: 510 },
      ],
    },
  },
  {
    match: /safe/i,
    text:
      'You can safely spend about **€24 a day** until payday on the 15th ' +
      '(6 days away).\n\nThat already sets aside your phone bill and gym ' +
      'membership due before then, plus a small cushion for surprises.\n\n' +
      '**Tip:** that\'s roughly two lunches out a day, so cooking at home a ' +
      'couple of nights gives you real breathing room.',
    concept: {
      title: 'What is "safe to spend"?',
      text:
        'Your balance minus bills due before your next income, minus a ' +
        'small reserve for surprise costs, spread over the days left.',
    },
  },
  {
    match: /what if|cut|save/i,
    text:
      'Cutting dining out by 20% would save you **€46 a month**, which is ' +
      '**€552 a year** or about **€2,950 over 5 years** with a little ' +
      'interest.\n\nThat\'s around 4 restaurant dinners a month.\n\n' +
      '**Tip:** set a weekly eating-out limit in the app and stick to it.',
    chart: {
      kind: 'line',
      title: 'Savings if you cut dining out 20%',
      unit: '€',
      data: [
        { label: 'Year 1', value: 552 },
        { label: 'Year 2', value: 1131 },
        { label: 'Year 3', value: 1739 },
        { label: 'Year 4', value: 2378 },
        { label: 'Year 5', value: 2950 },
      ],
    },
  },
  {
    match: /taxi/i,
    text:
      'You spent **€86** on taxis last month across **7 rides**, so about ' +
      '€12 a ride. That counts as everyday leakage (basket 3): small, ' +
      'frequent, and optional.\n\n**Tip:** swapping two rides a week for the ' +
      'bus would save around €40 a month.',
    chart: {
      kind: 'bar',
      title: 'Taxi spend by month',
      unit: '€',
      data: [
        { label: 'Jul', value: 42 },
        { label: 'Aug', value: 55 },
        { label: 'Sep', value: 61 },
        { label: 'Oct', value: 86 },
      ],
    },
  },
]

const FALLBACK = {
  text:
    'I\'m running in **demo mode**, so the backend isn\'t connected yet. Try ' +
    'asking about baskets, safe to spend, taxis, or a what-if like cutting ' +
    'dining out.',
}

const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })

export async function mockChat({ messages, onEvent, signal }) {
  const question = messages.at(-1)?.content ?? ''
  const answer = ANSWERS.find((a) => a.match.test(question)) ?? FALLBACK
  await wait(400, signal)
  for (const word of answer.text.split(/(?<= )/)) {
    onEvent({ type: 'token', text: word })
    await wait(18, signal)
  }
  if (answer.chart) onEvent({ type: 'chart', chart: answer.chart })
  if (answer.concept) onEvent({ type: 'concept', ...answer.concept })
  onEvent({ type: 'done' })
}
