// Demo-mode stand-in for the Django backend. Every number here is made up,
// but each mock customer is generated from one consistent profile so the
// dashboard, the search list and the chat answers all agree with each other.
// Shapes follow the API contract in docs/design.md exactly.

const AS_OF = '2026-09-30'
const MONTHS = [
  '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03',
  '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09',
]

const round = (n) => Math.round(n * 100) / 100

// Small deterministic PRNG so a customer always gets the same numbers.
function rng(seedText) {
  let seed = 0
  for (const ch of seedText) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0
  return () => {
    seed = (seed + 0x6d2b79f5) >>> 0
    let t = seed
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const PERSONAS = {
  steady_saver: {
    label: 'Steady Saver',
    description:
      'You keep a healthy gap between what comes in and what goes out, ' +
      'month after month. Your bills are predictable and leakage is small.',
    traits: ['Saves every month', 'Low leakage', 'Predictable bills'],
    shares: [0.62, 0.16, 0.22],
    spendRatio: 0.72,
  },
  weekend_spender: {
    label: 'Weekend Spender',
    description:
      'Weekdays are calm, but Fridays and Saturdays add up: restaurants, ' +
      'taxis and nights out are a big slice of your spending.',
    traits: ['Big weekends', 'High restaurant spend', 'Frequent taxis'],
    shares: [0.44, 0.12, 0.44],
    spendRatio: 0.91,
  },
  paycheck_to_paycheck: {
    label: 'Paycheck-to-Paycheck',
    description:
      'Most of your income is gone before the next salary lands, so a ' +
      'surprise bill can hurt. A small buffer would change a lot.',
    traits: ['Tight month-end', 'Low buffer', 'Volatile balance'],
    shares: [0.58, 0.14, 0.28],
    spendRatio: 0.99,
  },
  investor: {
    label: 'Investor',
    description:
      'You move money into investments regularly. Your spending is ' +
      'deliberate and your savings work for you.',
    traits: ['Invests monthly', 'Long-term mindset', 'Low leakage'],
    shares: [0.6, 0.2, 0.2],
    spendRatio: 0.64,
  },
  comfortable: {
    label: 'Comfortable',
    description:
      'Your income comfortably covers your lifestyle. You spend freely ' +
      'but still end most months ahead.',
    traits: ['Strong income', 'Travels often', 'Healthy balance'],
    shares: [0.5, 0.24, 0.26],
    spendRatio: 0.8,
  },
}

const BASKETS = [
  {
    key: 'mandatory_regular',
    label: 'Must-pay bills',
    cats: [['Housing', 0.55], ['Groceries', 0.3], ['Utilities', 0.15]],
  },
  {
    key: 'mandatory_irregular',
    label: 'Surprise essentials',
    cats: [['Health', 0.4], ['Home & Tech', 0.35], ['Travel', 0.25]],
  },
  {
    key: 'leakage',
    label: 'Everyday leakage',
    cats: [['Restaurants', 0.46], ['Entertainment', 0.22], ['Transportation', 0.2],
      ['Lifestyle', 0.12]],
  },
]

// Hand-picked demo customers: one per persona plus a mortgage approval and a
// rejection, mirroring what /api/customers/featured/ returns.
const FEATURED = [
  { id: 'CUST04457', age: 34, postal: '00530', persona: 'steady_saver',
    income: 4210, balance: 3240, mortgage: 'approved' },
  { id: 'CUST01873', age: 27, postal: '00150', persona: 'weekend_spender',
    income: 3120, balance: 1690 },
  { id: 'CUST03092', age: 23, postal: '33100', persona: 'paycheck_to_paycheck',
    income: 1940, balance: 312 },
  { id: 'CUST02648', age: 45, postal: '02100', persona: 'investor',
    income: 5650, balance: 5420 },
  { id: 'CUST00412', age: 58, postal: '00990', persona: 'comfortable',
    income: 4870, balance: 4950 },
  { id: 'CUST00296', age: 31, postal: '40100', persona: 'weekend_spender',
    income: 3380, balance: 1870, mortgage: 'rejected' },
  { id: 'CUST04415', age: 39, postal: '00200', persona: 'investor',
    income: 7980, balance: 6320, mortgage: 'approved' },
]

const POSTALS = ['00100', '00180', '00530', '02150', '33100', '40100', '20100',
  '90100', '15110', '70100', '65100', '04400']
const PERSONA_KEYS = Object.keys(PERSONAS)

function makeRandomProfile(n) {
  const r = rng(`cust-${n}`)
  const persona = PERSONA_KEYS[Math.floor(r() * PERSONA_KEYS.length)]
  const income = Math.round(1700 + r() * 4800)
  return {
    id: `CUST${String(n).padStart(5, '0')}`,
    age: 19 + Math.floor(r() * 55),
    postal: POSTALS[Math.floor(r() * POSTALS.length)],
    persona,
    income,
    balance: Math.round(income * (persona === 'paycheck_to_paycheck'
      ? 0.1 + r() * 0.3
      : 0.6 + r() * 1.2)),
  }
}

const PROFILES = [
  ...FEATURED,
  ...Array.from({ length: 64 }, (_, i) => makeRandomProfile(101 + i * 73)),
]
const BY_ID = new Map(PROFILES.map((p) => [p.id, p]))

function spendFor(p) {
  return p.income * PERSONAS[p.persona].spendRatio
}

function summary(p) {
  const spend = spendFor(p)
  return {
    customer_id: p.id,
    customer_age: p.age,
    customer_postal_code: p.postal,
    persona: { key: p.persona, label: PERSONAS[p.persona].label },
    monthly_income: round(p.income),
    monthly_spend: round(spend),
    savings_rate: round((p.income - spend) / p.income),
    balance: round(p.balance),
    has_mortgage_application: Boolean(p.mortgage),
    mortgage_decision: p.mortgage ?? null,
  }
}

function homeReadiness(p, net) {
  // Finnish rules of thumb: payment <= 35% of net income, stress-tested at
  // 6% over 25 years, 10% deposit for a first home.
  const r = 0.06 / 12
  const perEuro = r / (1 - (1 + r) ** -300)
  const maxLoan = (0.35 * p.income) / perEuro
  const price = Math.round(maxLoan / 0.9 / 500) * 500
  const needed = round(price * 0.1)
  const saved = round(Math.min(needed, p.balance * 0.6 + Math.max(0, net) * 4))
  let months = null
  if (saved >= needed) months = 0
  else if (net > 0) months = Math.ceil((needed - saved) / net)
  let verdict
  if (p.mortgage === 'approved') {
    verdict = 'Your mortgage was approved. Keep a buffer for moving costs.'
  } else if (p.mortgage === 'rejected') {
    verdict =
      'Your last application was declined for insufficient income. ' +
      'A smaller property or a co-borrower would bring it within reach.'
  } else if (months === 0) {
    verdict = 'You already have the 10% deposit for a home in this range.'
  } else if (months === null) {
    verdict = 'Build a monthly surplus first; a deposit is out of reach for now.'
  } else if (months <= 24) {
    verdict = `On track: about ${months} months to a 10% deposit at your pace.`
  } else {
    verdict = `A stretch: about ${months} months to save the deposit at your pace.`
  }
  return {
    has_application: Boolean(p.mortgage),
    decision: p.mortgage ?? null,
    max_property_price: price,
    deposit_needed: needed,
    deposit_saved_estimate: saved,
    months_to_deposit: months,
    verdict,
  }
}

const eur = (n) =>
  `€${Number(n).toLocaleString('en-IE', { maximumFractionDigits: 0 })}`

function insightsFor(p, ctx) {
  const { leakage, savingsRate, topLeak, safe, lastSpend, avgSpend } = ctx
  const list = []
  if (savingsRate >= 0.2) {
    list.push({ title: 'Strong savings rate', tone: 'good',
      text: `You keep ${Math.round(savingsRate * 100)}% of your income. ` +
        'That is well above the 10–15% many people aim for.' })
  } else if (savingsRate < 0.05) {
    list.push({ title: 'Almost nothing left over', tone: 'warn',
      text: `Only ${Math.round(savingsRate * 100)}% of income is left at month ` +
        'end. Even €50 a month into a buffer account helps.' })
  } else {
    list.push({ title: 'Room to save more', tone: 'info',
      text: `You save ${Math.round(savingsRate * 100)}% of income. ` +
        'Nudging that to 15% would add up fast.' })
  }
  list.push({
    title: `${topLeak.category} is your biggest leak`,
    tone: leakage.share > 0.3 ? 'warn' : 'info',
    text: `About ${eur(topLeak.monthly_avg)} a month. Cutting it by 20% ` +
      `frees ${eur(topLeak.monthly_avg * 0.2)} a month, ` +
      `${eur(topLeak.monthly_avg * 0.2 * 12)} a year.`,
  })
  if (lastSpend > avgSpend * 1.05) {
    list.push({ title: 'September ran hot', tone: 'warn',
      text: `You spent ${eur(lastSpend)} last month, ` +
        `${Math.round((lastSpend / avgSpend - 1) * 100)}% above your average.` })
  } else {
    list.push({ title: 'Spending under control', tone: 'good',
      text: `September spend of ${eur(lastSpend)} was at or below your ` +
        '12-month average.' })
  }
  list.push({ title: 'Bills before payday', tone: 'info',
    text: `${safe.upcoming_bills.length} bills totalling ` +
      `${eur(safe.upcoming_bills.reduce((s, b) => s + b.amount, 0))} are due ` +
      `before payday on ${Number(safe.next_payday.slice(8))} Oct.` })
  if (p.persona === 'investor') {
    list.push({ title: 'Investing habit', tone: 'good',
      text: 'You moved money into investments in 11 of the last 12 months.' })
  }
  return list
}

function overview(p) {
  const r = rng(p.id)
  const persona = PERSONAS[p.persona]
  const avgSpend = spendFor(p)

  const monthly = MONTHS.map((month, i) => {
    const bonus = month === '2025-12' || month === '2026-06' ? 0.12 : 0
    const income = p.income * (0.97 + r() * 0.06 + bonus)
    const seasonal = month === '2025-12' ? 0.22 : month === '2026-07' ? 0.14 : 0
    const late = i === 11 && p.persona !== 'steady_saver' ? 0.06 : 0
    const spend = avgSpend * (0.9 + r() * 0.16 + seasonal + late)
    return { month, income: round(income), spend: round(spend),
      net: round(income - spend) }
  })
  const income = monthly.reduce((s, m) => s + m.income, 0) / 12
  const spend = monthly.reduce((s, m) => s + m.spend, 0) / 12
  const last = monthly.at(-1)

  const baskets = BASKETS.map((b, i) => {
    const avg = spend * persona.shares[i]
    return {
      key: b.key,
      label: b.label,
      monthly_avg: round(avg),
      share: round(persona.shares[i]),
      top_categories: b.cats
        .map(([category, w]) => ({ category,
          monthly_avg: round(avg * w * (0.85 + r() * 0.3)) }))
        .sort((a, b2) => b2.monthly_avg - a.monthly_avg)
        .slice(0, 3),
    }
  })

  const bills = [
    { label: 'Rent', amount: round(baskets[0].top_categories
      .find((c) => c.category === 'Housing')?.monthly_avg ?? 700), due: '2026-10-01' },
    { label: 'Helen electricity', amount: round(38 + r() * 40), due: '2026-10-06' },
    { label: 'Elisa mobile', amount: 24.9, due: '2026-10-09' },
    { label: 'Spotify', amount: 11.99, due: '2026-10-12' },
  ]
  const reserve = round(Math.max(50, p.income * 0.04))
  const billsTotal = bills.reduce((s, b) => s + b.amount, 0)
  const amount = round(Math.max(0, p.balance - billsTotal - reserve))
  const days = 15
  const safe = {
    amount,
    per_day: round(amount / days),
    days_until_payday: days,
    next_payday: '2026-10-15',
    reserve,
    upcoming_bills: bills,
  }

  const savingsRate = round((income - spend) / income)
  const leakage = baskets[2]
  return {
    customer: summary(p),
    as_of: AS_OF,
    balance: round(p.balance),
    income_monthly_avg: round(income),
    spend_monthly_avg: round(spend),
    savings_rate: savingsRate,
    baskets,
    last_month: {
      month: last.month,
      income: last.income,
      spend: last.spend,
      baskets: Object.fromEntries(baskets.map((b, i) =>
        [b.key, round(last.spend * persona.shares[i])])),
    },
    monthly_cashflow: monthly,
    safe_to_spend: safe,
    persona: { key: p.persona, label: persona.label,
      description: persona.description, traits: persona.traits },
    insights: insightsFor(p, {
      leakage, savingsRate, safe, lastSpend: last.spend, avgSpend: spend,
      topLeak: leakage.top_categories[0],
    }),
    home_readiness: homeReadiness(p, income - spend),
  }
}

// ---------- Endpoint stand-ins ----------------------------------------------

const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'))
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })

export const MOCK_HEALTH = {
  status: 'ok',
  llm: { provider: 'offline', model: null, configured: false },
  data: { customers: 5100, transactions: 3_612_480 },
}

export async function mockFeatured() {
  await wait(250)
  return FEATURED.map((p) => summary(BY_ID.get(p.id)))
}

export async function mockCustomers({ search = '', limit = 20, offset = 0 } = {}) {
  await wait(200)
  const q = search.trim().toLowerCase()
  const hits = PROFILES.filter((p) => !q || [p.id, p.postal,
    PERSONAS[p.persona].label, String(p.age)]
    .some((v) => v.toLowerCase().includes(q)))
  return {
    count: hits.length,
    results: hits.slice(offset, offset + limit).map(summary),
  }
}

export async function mockOverview(customerId) {
  await wait(450)
  const p = BY_ID.get(customerId)
  if (!p) throw new Error('Customer not found')
  return overview(p)
}

// ---------- Chat ------------------------------------------------------------

const pct = (n) => `${Math.round(n * 100)}%`

function answerFor(question, o) {
  const leak = o.baskets[2]
  const top = leak.top_categories[0]
  const s = o.safe_to_spend
  const h = o.home_readiness

  if (/safe|afford|this week|spend today/i.test(question)) {
    return {
      tools: [['safe_to_spend', 'Checking your balance and upcoming bills…']],
      text:
        `You can safely spend about **${eur(s.per_day)} a day** until payday ` +
        `on ${Number(s.next_payday.slice(8))} Oct, ` +
        `${s.days_until_payday} days away.\n\n` +
        `That already sets aside:\n` +
        s.upcoming_bills.map((b) => `- **${b.label}** ${eur(b.amount)}`)
          .join('\n') +
        `\n- a **${eur(s.reserve)}** reserve for surprises\n\n` +
        `In total that leaves **${eur(s.amount)}** to play with.`,
      concept: {
        title: 'What is "safe to spend"?',
        text:
          'Your balance minus bills due before your next income, minus a ' +
          'small reserve for surprise costs, spread over the days left.',
      },
      suggestions: ['What if I cut dining out by 20%?', 'Show my spending by basket'],
    }
  }
  if (/basket|where.*money|breakdown|spending by/i.test(question)) {
    const lm = o.last_month
    return {
      tools: [['basket_breakdown', 'Sorting your spending into baskets…']],
      text:
        `You spent **${eur(lm.spend)}** last month:\n\n` +
        o.baskets.map((b) => `- **${b.label}** ${eur(lm.baskets[b.key])}`)
          .join('\n') +
        `\n\nEveryday leakage is the basket you control most. ` +
        `Trimming it by a quarter frees up about ` +
        `**${eur(lm.baskets.leakage * 0.25)} a month**.`,
      chart: {
        kind: 'pie', title: 'Last month by basket', unit: '€',
        data: o.baskets.map((b) => ({ label: b.label,
          value: lm.baskets[b.key] })),
      },
      suggestions: [`How much do I spend on ${top.category.toLowerCase()}?`,
        'What is safe to spend this week?'],
    }
  }
  if (/what if|cut|save more|reduce/i.test(question)) {
    const monthly = top.monthly_avg * 0.2
    const years = [1, 2, 3, 4, 5].map((y) => {
      let total = 0
      for (let m = 0; m < y * 12; m++) total = total * (1 + 0.03 / 12) + monthly
      return { label: `Year ${y}`, value: round(total) }
    })
    return {
      tools: [['what_if', 'Running a what-if projection…']],
      text:
        `Cutting **${top.category.toLowerCase()}** by 20% would save you ` +
        `**${eur(monthly)} a month**. With 3% interest that grows to ` +
        `**${eur(years[0].value)}** after a year and ` +
        `**${eur(years[4].value)}** after 5 years.\n\n` +
        `**Tip:** set a weekly limit for ${top.category.toLowerCase()} ` +
        'in the app and check in on Sundays.',
      chart: { kind: 'line', title: `Savings from cutting ${top.category}`,
        unit: '€', data: years },
      concept: { title: 'Compound interest',
        text: 'Interest earned on your savings also earns interest, so ' +
          'small monthly amounts snowball over time.' },
      suggestions: ['Am I ready to buy a home?', 'What kind of spender am I?'],
    }
  }
  if (/persona|kind of spender|type of|who am i/i.test(question)) {
    return {
      tools: [['spender_persona', 'Looking at your spending habits…']],
      text:
        `You're a **${o.persona.label}**. ${o.persona.description}\n\n` +
        o.persona.traits.map((t) => `- ${t}`).join('\n') +
        `\n\nYou save **${pct(o.savings_rate)}** of your income, and ` +
        `everyday leakage is **${pct(leak.share)}** of your spending.`,
      suggestions: ['What if I cut dining out by 20%?', 'Am I ready to buy a home?'],
    }
  }
  if (/home|house|mortgage|flat|apartment|property/i.test(question)) {
    const progress = h.deposit_needed
      ? h.deposit_saved_estimate / h.deposit_needed : 0
    return {
      tools: [['home_readiness', 'Checking your home-buying readiness…']],
      text:
        (h.has_application
          ? `Your mortgage application was **${h.decision}**.\n\n` : '') +
        `Based on your income you could afford a home up to about ` +
        `**${eur(h.max_property_price)}**. For that you'd need a ` +
        `**${eur(h.deposit_needed)}** deposit (10%), and you have roughly ` +
        `**${pct(progress)}** of it.\n\n${h.verdict}`,
      concept: { title: 'Loan-to-value (LTV)',
        text: 'The share of the home price covered by the loan. First-time ' +
          'buyers in Finland can borrow up to 90%, so you need 10% yourself.' },
      suggestions: ['How can I save the deposit faster?',
        'What is safe to spend this week?'],
    }
  }
  const cat = ['taxi', 'restaurant', 'grocer', 'entertainment', 'travel']
    .find((c) => question.toLowerCase().includes(c))
  if (cat || /how much.*spend/i.test(question)) {
    const name = cat === 'taxi' ? 'taxis' : cat ? `${cat}s` : top.category
    const base = cat === 'taxi' ? 64 : top.monthly_avg
    const data = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'].map((label, i) => ({
      label, value: round(base * (0.75 + ((i * 37) % 10) / 20)) }))
    const lastVal = data.at(-1).value
    return {
      tools: [['spend_by_category', 'Checking your transactions…']],
      text:
        `You spent **${eur(lastVal)}** on ${name.toLowerCase()} last month, ` +
        `against a 6-month average of ` +
        `**${eur(data.reduce((a, d) => a + d.value, 0) / 6)}**.\n\n` +
        `That counts as everyday leakage: small, frequent and optional.`,
      chart: { kind: 'bar', title: `${name} by month`, unit: '€', data },
      suggestions: ['What if I cut dining out by 20%?', 'Show my spending by basket'],
    }
  }
  return {
    tools: [],
    text:
      "I'm running in **demo mode** with sample data. I can help with:\n\n" +
      '- what is **safe to spend** before payday\n' +
      '- your spending **by basket**\n' +
      '- **what-if** savings, like cutting dining out\n' +
      '- your **spender persona** and **home readiness**',
    suggestions: ['What is safe to spend this week?', 'Show my spending by basket',
      'Am I ready to buy a home?'],
  }
}

export async function mockChat({ customerId, messages, onEvent, signal }) {
  const question = messages.at(-1)?.content ?? ''
  const p = BY_ID.get(customerId) ?? FEATURED[0]
  const answer = answerFor(question, overview(p))
  onEvent({ type: 'meta', provider: 'offline', model: null })
  await wait(350, signal)
  for (const [name, label] of answer.tools) {
    onEvent({ type: 'tool', name, label })
    await wait(700, signal)
  }
  for (const word of answer.text.split(/(?<=[ \n])/)) {
    onEvent({ type: 'token', text: word })
    await wait(16, signal)
  }
  if (answer.chart) onEvent({ type: 'chart', chart: answer.chart })
  if (answer.concept) onEvent({ type: 'concept', ...answer.concept })
  if (answer.suggestions) {
    onEvent({ type: 'suggestions', items: answer.suggestions })
  }
  onEvent({ type: 'done' })
}
