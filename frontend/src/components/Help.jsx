// Help page (#/c/<id>/help), opened over the customer view: what the coach
// can do, with a picture of each chart and card. The pictures are shapes only
// (HelpArt.jsx): there is no sample data at runtime (CLAUDE.md). Tapping an
// example question closes help and asks the coach.

import {
  AlertArt,
  BasketArt,
  BeforeAfterArt,
  ColumnsArt,
  GoalArt,
  HBarsArt,
  LevelArt,
  LineArt,
  NumberArt,
  PlanArt,
  QuestionArt,
  SliderArt,
  StepIcon,
} from './HelpArt.jsx'

const STEPS = [
  ['ask', 'You ask', 'In your own words.'],
  ['numbers', 'The app works it out', 'From real transactions. No guessing.'],
  ['cards', 'You get an answer', 'A short reply, plus charts and cards.'],
]

const DEPTHS = [
  ['Quick', 'One fact'],
  ['Explain', 'The fact and why'],
  ['What-if', 'Try a change'],
  ['Plan', 'Steps to a goal'],
]

const CHARTS = [
  [HBarsArt, 'Bars', 'Compare things: baskets, categories, subscriptions.'],
  [ColumnsArt, 'Columns', 'See a value change month by month.'],
  [LineArt, 'Line', 'Your expected balance, day by day to payday.'],
]

const CARDS = [
  [NumberArt, 'Number', 'One headline amount.'],
  [BasketArt, 'Baskets', 'Essentials, surprises, leaky habits and saving.'],
  [SliderArt, 'What-if slider', 'Drag to cut a category and see the saving.'],
  [LevelArt, 'Level', 'Your level, and what gets you to the next one.'],
  [GoalArt, 'Goal', 'Target, amount saved and the date you get there.'],
  [QuestionArt, 'Question', 'Tap an answer instead of typing.'],
  [AlertArt, 'Alert', 'Something worth a look, by urgency.'],
  [PlanArt, 'Plan', 'Up to three steps and what each one saves.'],
  [BeforeAfterArt, 'Before / after', 'How a plan changes your numbers.'],
]

const LEVELS = [
  ['Getting started', 'Income and bills found'],
  ['In control', 'Spend within income for a month'],
  ['Safety net', 'One month of essentials put by'],
  ['Goal setter', 'A goal on track'],
  ['Mortgage ready', 'Readiness score of 0.75'],
  ['Wealth builder', 'Three-month buffer, saving 10 %'],
]

const TRY = [
  ['Show me a chart of where my money went this month', 2],
  ['How much can I safely spend this week?', 1],
  ['How can I save more?', 3],
  ['Help me save for a trip', 4],
]

function Section({ title, children }) {
  return (
    <section className="section">
      <h2 className="section-title">{title}</h2>
      {children}
    </section>
  )
}

function Tiles({ items, three = false }) {
  return (
    <ul className={`help-tiles${three ? ' three' : ''}`}>
      {items.map(([Picture, name, text]) => (
        <li key={name} className="panel help-tile">
          <Picture />
          <strong>{name}</strong>
          <span>{text}</span>
        </li>
      ))}
    </ul>
  )
}

export default function Help({ onBack, onAsk }) {
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="logo" aria-hidden="true">
            S
          </span>
          <h1>Help</h1>
          <div className="topbar-actions">
            <button type="button" className="logout" onClick={onBack}>
              Back
            </button>
          </div>
        </div>
      </header>

      <main className="landing help">
        <Section title="How it works">
          <ol className="help-steps">
            {STEPS.map(([icon, name, text]) => (
              <li key={icon} className="panel">
                <StepIcon kind={icon} />
                <strong>{name}</strong>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <p className="help-note">
            The coach never moves, pays or cancels anything, and it only saves a
            goal when you say yes.
          </p>
        </Section>

        {onAsk && (
          <Section title="Try asking">
            <div className="help-try">
              {TRY.map(([text, depth]) => (
                <button key={text} type="button" onClick={() => onAsk(text, depth)}>
                  {text}
                </button>
              ))}
            </div>
          </Section>
        )}

        <Section title="How deep it goes">
          <ol className="help-depths">
            {DEPTHS.map(([name, text]) => (
              <li key={name}>
                <span className="depth">{name}</span>
                <span>{text}</span>
              </li>
            ))}
          </ol>
          <p className="help-note">
            Tap a suggestion under a reply to go one step deeper.
          </p>
        </Section>

        <Section title="Charts">
          <Tiles items={CHARTS} three />
          <p className="help-note">Tap a bar or the line to see the exact amount.</p>
        </Section>

        <Section title="Cards">
          <Tiles items={CARDS} />
        </Section>

        <Section title="Levels">
          <ol className="panel help-levels">
            {LEVELS.map(([name, text], i) => (
              <li key={name}>
                <span className="help-level-num">{i + 1}</span>
                <span>
                  <strong>{name}</strong>
                  <small>{text}</small>
                </span>
              </li>
            ))}
          </ol>
          <p className="help-note">
            Ask "How can I save more?" to see your next step.
          </p>
        </Section>
      </main>
    </div>
  )
}
