// Question discovery: "Try asking" strip, "See all questions" sheet,
// chat placeholders and suggestions for tapped numbers. All built from the
// user's own profile so examples feel personal.

import { eur } from './format.js'

function topLeaky(profile) {
  return profile?.baskets?.leaky_categories?.[0]?.category ?? 'takeaway'
}

function topGoal(profile) {
  return profile?.goals?.active?.[0]?.name ?? 'my goal'
}

// One example per depth (Quick, Explain, What-if, Plan).
export function tryAsking(profile) {
  const leaky = topLeaky(profile)
  const safe = profile?.forecast?.safe_to_spend_week
  return [
    { depth: 1, text: `How much did I spend on ${leaky} last month?` },
    {
      depth: 2,
      text:
        safe != null
          ? `Why is my safe to spend ${eur(safe)}?`
          : 'Why is my safe to spend so low?',
    },
    { depth: 3, text: `What if I cut ${leaky} by 20%?` },
    { depth: 4, text: `Help me reach ${topGoal(profile)} sooner` },
  ]
}

export function allQuestions(profile) {
  const leaky = topLeaky(profile)
  const goal = topGoal(profile)
  const sub = profile?.income?.subscriptions?.[0]?.name ?? 'Netflix'
  return [
    {
      topic: 'Spending',
      items: [
        { depth: 1, text: `How much did I spend on ${leaky} last month?` },
        { depth: 1, text: 'How much did I spend on taxis last month?' },
        { depth: 2, text: "What's my leaky spending?" },
        { depth: 2, text: 'What kind of spender am I?' },
      ],
    },
    {
      topic: 'Safe to spend',
      items: [
        { depth: 1, text: 'What is safe for me to spend this week?' },
        { depth: 1, text: 'When is payday?' },
        { depth: 2, text: 'Why is my safe to spend so low?' },
        { depth: 4, text: "I'm always broke before payday, what do I do?" },
      ],
    },
    {
      topic: 'What-ifs',
      items: [
        { depth: 3, text: `What if I cut ${leaky} by 20%?` },
        { depth: 3, text: 'What if I cut dining out by 20%?' },
        { depth: 3, text: `What if I cancel ${sub}?` },
        { depth: 3, text: `Can I reach ${goal} sooner?` },
      ],
    },
    {
      topic: 'Goals and levels',
      items: [
        { depth: 1, text: 'What level am I on?' },
        { depth: 4, text: 'Help me get my money sorted' },
        { depth: 4, text: 'I want EUR 1,500 for Japan by June' },
      ],
    },
    {
      topic: 'Mortgage',
      items: [
        { depth: 2, text: 'How ready am I for a mortgage?' },
        { depth: 4, text: 'Help me buy a flat' },
        { depth: 2, text: 'Can I afford my mortgage if rates go up?' },
      ],
    },
    {
      topic: 'Alerts',
      items: [
        { depth: 4, text: 'Help me clear my alerts' },
        { depth: 2, text: 'Why did I get this alert?' },
      ],
    },
  ]
}

export function placeholders(profile) {
  return [
    'Ask about your money…',
    ...tryAsking(profile).map((q) => `Try: “${q.text}”`),
  ]
}

// "Tap any number for three suggested questions about it."
export function numberQuestions(label) {
  return [
    { depth: 2, text: `Why is my ${label.toLowerCase()} this number?` },
    { depth: 3, text: `What if I spent less on my top leak?` },
    { depth: 4, text: `Help me improve my ${label.toLowerCase()}` },
  ]
}
