// Two-line explainers for money words, using the user's own numbers.
// Numbers come from the profile only; nothing is calculated here.

import { eur, pct } from './format.js'

export const MONEY_WORDS = {
  safe_to_spend: (p) => [
    'Safe to spend is what is left for everyday things until payday.',
    `Bills due before payday and a buffer of ${eur(p?.forecast?.buffer)} ` +
      'are already set aside.',
  ],
  buffer: (p) => [
    'A buffer is a small cushion you never plan to spend.',
    `Yours is ${eur(p?.forecast?.buffer)}: at least €50 or 10% of your ` +
      'monthly essentials.',
  ],
  leaky: (p) => [
    'Leaky spending is small, frequent, non-essential buys under €25.',
    `Yours was ${eur(p?.baskets?.totals?.leaky)} this month.`,
  ],
  essentials: (p) => [
    'Essentials are the must-pay, regular costs like rent and groceries.',
    `Yours are about ${eur(p?.baskets?.monthly_essentials)} a month.`,
  ],
  saver: (p) => [
    'Saver is money you move to savings or investments.',
    `You put aside about ${eur(p?.baskets?.monthly_saving)} a month.`,
  ],
  surprise: (p) => [
    'Surprises are must-pay costs that come rarely, like a car repair.',
    `Setting aside ${eur(p?.forecast?.surprise_fund_monthly)} a month ` +
      'covers your usual ones.',
  ],
  safety_net: (p) => [
    'A safety net is enough savings to cover one month of essentials.',
    `You have ${p?.levels?.buffer_months ?? '–'} months covered right now.`,
  ],
  dsti: (p) => [
    'DSTI is the share of your net income that goes to loan payments.',
    p?.mortgage?.dsti != null
      ? `Yours is ${pct(p.mortgage.dsti, { fraction: true })}; Finland's ` +
        'stressed limit is 60%.'
      : 'We found no loan payments in your account.',
  ],
  subscription: (p) => [
    'A subscription is a small payment that repeats every month.',
    `You have ${p?.income?.subscriptions?.length ?? 0} of them.`,
  ],
  readiness: (p) => [
    'Readiness compares your habits with people whose mortgage was approved.',
    `Your score is ${pct(p?.mortgage?.readiness?.score, { fraction: true })}. ` +
      'It is guidance, not a loan decision.',
  ],
}

export function explain(word, profile) {
  const fn = MONEY_WORDS[word]
  return fn ? fn(profile) : null
}
