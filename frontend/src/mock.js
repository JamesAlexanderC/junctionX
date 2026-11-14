// Demo-mode stand-in for POST /api/chat/. Returns send_reply JSON built only
// from numbers already in the profile, so the UI can be clicked through
// with the backend off. The real coach is Gemini in Django.

import { sortAlerts } from './lib/alerts.js'
import { eur } from './lib/format.js'

export const MOCK_CUSTOMERS = [
  { customer_id: 'demo-aino', customer_age: 24, customer_postal_code: '00510' },
]

// Same keyword rules as the backend router (context.md "Request flow").
export function routeDepth(message) {
  const m = message.toLowerCase()
  if (/help me|\bplan\b|what do i do|sorted/.test(m)) return 4
  if (/what if|cancel|sooner|cut /.test(m)) return 3
  if (/\bwhy\b|what kind|leaky|ready/.test(m)) return 2
  return 1
}

const reply = (text, depth, cards = [], chips = []) => ({
  text,
  depth,
  cards,
  chips: chips.slice(0, 3),
})

function basketCard(p) {
  const t = p.baskets?.totals ?? {}
  return {
    type: 'basket_bar',
    essential: t.essential ?? 0,
    surprise: t.surprise ?? 0,
    leaky: t.leaky ?? 0,
    saver: t.saver ?? 0,
  }
}

function findCategory(p, message) {
  const means = p.whatif?.category_means ?? {}
  const m = message.toLowerCase()
  return Object.keys(means).find((c) => m.includes(c.toLowerCase())) ?? null
}

function clearAlertsReply(p) {
  const alerts = sortAlerts(p.alerts, p.today)
  if (!alerts.length) {
    return reply('You have no open alerts right now. Nice work.', 4, [], [
      'What is safe to spend?',
    ])
  }
  const cut = p.levels?.easiest_next_step
  const sub = p.income?.possibly_unused?.[0]
  const steps = []
  if (cut) {
    steps.push({
      text: `Cut ${cut.category} by ${Math.round(cut.cut_pct * 100)}%`,
      monthly_impact: cut.monthly_saving,
      clears: alerts.filter((a) => a.inference !== 92).map((a) => a.id),
    })
  }
  if (sub) {
    steps.push({
      text: `Keep only one video service (drop ${sub.name})`,
      monthly_impact: sub.amount,
      clears: alerts.filter((a) => a.inference === 92).map((a) => a.id),
    })
  }
  const safe = p.forecast?.safe_to_spend_week
  return reply(
    `You have ${alerts.length} alerts. Here is a plan with ` +
      `${steps.length} easy steps. Nothing changes until you accept.`,
    4,
    [
      ...alerts.slice(0, 3).map((a) => ({
        type: 'alert',
        id: a.id,
        severity: a.severity,
        title: a.title,
        text: a.text,
      })),
      { type: 'plan', steps },
      {
        type: 'before_after',
        before: {
          safe_to_spend: safe,
          buffer_months: p.levels?.buffer_months,
          goal_date: p.goals?.active?.[0]?.target_date ?? null,
        },
        after: {
          safe_to_spend: safe,
          buffer_months: p.levels?.buffer_months,
          goal_date: p.goals?.active?.[0]?.target_date ?? null,
        },
      },
    ],
    ['Accept plan', 'Only step 1', 'Other ideas'],
  )
}

export function mockReply({ message, depth, profile: p }) {
  const m = message.toLowerCase()
  const d = depth ?? routeDepth(message)

  if (/clear my alerts|fix this alert/.test(m)) return clearAlertsReply(p)

  if (/accept plan|only step/.test(m)) {
    return reply(
      'Done: I saved the plan as a checklist. I will tell you when an ' +
        'alert clears.',
      4,
      [],
      ['Show my alerts', 'What is safe to spend?'],
    )
  }

  if (/buy a flat|mortgage|home/.test(m) && d >= 2) {
    const r = p.mortgage?.readiness
    return reply(
      `Your mortgage readiness is ${Math.round((r?.score ?? 0) * 100)} out ` +
        'of 100. This is guidance, not a loan decision. What matters most to you?',
      4,
      [
        {
          type: 'question',
          question: 'When would you like to buy?',
          options: ['Within 1 year', 'In 2-3 years', 'Just exploring'],
          quick_answer: 'Show me my gaps',
        },
      ],
      ['Show me my gaps'],
    )
  }

  if (/what if|cut /.test(m)) {
    const cat =
      findCategory(p, message) ??
      p.baskets?.leaky_categories?.[0]?.category ??
      'takeaway'
    const spend = p.whatif?.category_means?.[cat]
    if (spend == null) {
      return reply(`I have no ${cat} spending in your data.`, 3, [], [
        "What's my leaky spending?",
      ])
    }
    const goal = p.goals?.active?.[0]
    return reply(
      `Move the slider to see what cutting ${cat} saves you.`,
      3,
      [
        {
          type: 'slider',
          category: cat,
          monthly_spend: spend,
          min_pct: 0,
          max_pct: 50,
          pct: 20,
          ...(goal && {
            goal: {
              target: goal.target,
              saved: goal.saved,
              monthly_rate: p.baskets?.monthly_saving ?? 0,
            },
          }),
        },
      ],
      ['Make it a goal', 'Other ideas'],
    )
  }

  if (/spender/.test(m)) {
    const st = p.habits?.spender_type
    return reply(
      `You are a **${st?.label ?? 'mix of types'}**. Your habits are ` +
        'scored against simple thresholds, like weekend and night spending.',
      2,
      [],
      ['Show my weekend spending', 'What can I do?'],
    )
  }

  if (/level/.test(m)) {
    const l = p.levels ?? {}
    return reply(
      `You are on Level ${l.current}: ${l.current_name}.`,
      1,
      [
        {
          type: 'level_progress',
          level: l.next,
          name: l.next_name,
          progress: l.progress,
          euros_to_go: l.euros_to_go,
          next_step: l.easiest_next_step?.text,
        },
      ],
      ['How do I get there faster?'],
    )
  }

  if (/safe|broke|payday/.test(m)) {
    const f = p.forecast ?? {}
    const pay = p.income?.payday
    return reply(
      `You can safely spend **${eur(f.safe_to_spend_week)}** this week. ` +
        `Payday is in ${pay?.days_to_payday ?? '?'} days.`,
      d,
      [
        { type: 'number', label: 'Safe to spend', value: f.safe_to_spend_week, unit: 'EUR' },
        ...(d >= 2 ? [basketCard(p)] : []),
      ],
      ['Show me why', 'What can I do?', 'Make it a goal'],
    )
  }

  if (/leaky|basket|where/.test(m)) {
    const cats = p.baskets?.leaky_categories ?? []
    return reply(
      `Leaky spending means small everyday buys that slip away. This month ` +
        `it was **${eur(p.baskets?.totals?.leaky)}**.`,
      2,
      [
        basketCard(p),
        {
          type: 'chart',
          kind: 'bar',
          title: 'Leaky categories per month',
          unit: '€',
          data: cats.map((c) => ({ label: c.category, value: c.monthly_total })),
        },
      ],
      [`What if I cut ${cats[0]?.category ?? 'takeaway'} by 20%?`],
    )
  }

  if (/how much|spend on|spent/.test(m)) {
    const cat = findCategory(p, message)
    if (!cat) {
      return reply(
        'I could not find that in your data, so I will not guess.',
        1,
        [],
        ["What's my leaky spending?"],
      )
    }
    return reply(
      `You spend about **${eur(p.whatif.category_means[cat])}** a month on ${cat}.`,
      1,
      [
        {
          type: 'number',
          label: `${cat} per month`,
          value: p.whatif.category_means[cat],
          unit: 'EUR',
        },
      ],
      ['Is that a lot?', `What if I cut ${cat} by 20%?`],
    )
  }

  if (/goal|sorted|help me/.test(m)) {
    const g = p.goals?.recommended
    return reply(
      'Here is the goal that gets you to your next level. Want to start it?',
      4,
      g
        ? [
            {
              type: 'goal',
              name: g.name,
              target: g.target,
              saved: 0,
              target_date: null,
              difficulty: g.difficulty,
              monthly_needed: g.monthly_needed,
            },
          ]
        : [],
      ['Yes, start it', 'Make it smaller', 'Not now'],
    )
  }

  return reply(
    'I can answer questions about your spending, bills, goals and alerts. ' +
      'Try one of these:',
    1,
    [],
    ['What is safe to spend?', "What's my leaky spending?", 'Help me clear my alerts'],
  )
}
