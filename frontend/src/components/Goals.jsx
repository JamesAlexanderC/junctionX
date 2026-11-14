// The customer's goals at the top of the Overview, from GET /api/goals/.
// Every number is the backend's (#26, #49 to #53, #65, #66, #70): this file
// only formats them. Tapping a goal asks the coach about it.

import { eur, longDate } from '../lib/format.js'
import { Bar } from './Cards.jsx'
import Icon from './Icon.jsx'

const share = (num, den) => (den ? (num ?? 0) / den : 0)

function GoalRow({ goal, onAsk }) {
  const name = goal.name || 'Goal'
  const status = goal.paused ? 'paused' : goal.on_track ? 'on track' : 'behind'
  return (
    <li>
      <button
        type="button"
        className="row goal-row"
        onClick={() => onAsk(`Tell me about my ${name} goal`, 2)}
      >
        <span className="row-main">
          <span className="ins-title goal-head">
            {goal.emoji && <span aria-hidden="true">{goal.emoji}</span>}
            {name}
            {goal.paused ? (
              <span className="tag">
                <Icon name="paused" size={12} />
                Paused
              </span>
            ) : (
              goal.difficulty && <span className="tag">{goal.difficulty}</span>
            )}
          </span>
          <Bar
            value={share(goal.saved, goal.target)}
            marker={goal.paused ? null : share(goal.expected_pct, 100)}
          />
          <small className="ins-text">
            {eur(goal.saved)} of {eur(goal.target)}
            {goal.target_date && ` · by ${longDate(goal.target_date)}`}
          </small>
          <small className={`ins-text goal-status ${status.replace(' ', '-')}`}>
            {!goal.paused && (
              <Icon name={goal.on_track ? 'check' : 'behind'} size={14} />
            )}
            {goal.monthly_needed > 0 && `${eur(goal.monthly_needed)} a month needed · `}
            {status}
          </small>
          {goal.realistic === false && goal.suggested_monthly != null && (
            <small className="ins-text">
              Realistic: {eur(goal.suggested_monthly)} a month
              {goal.suggested_date && `, done by ${longDate(goal.suggested_date)}`}
            </small>
          )}
          {goal.tip?.text && <small className="ins-text goal-tip">{goal.tip.text}</small>}
        </span>
        {goal.progress_pct != null && (
          <strong className="ins-value">{Math.round(goal.progress_pct)}%</strong>
        )}
        <Icon name="chevron" className="chevron" />
      </button>
    </li>
  )
}

export default function Goals({ goals, onAsk }) {
  const active = goals?.active ?? []
  const completed = goals?.completed ?? []
  const clash = goals?.clash
  return (
    <div className="section goals" aria-label="Goals">
      <h2 className="section-title">
        <Icon name="goals" size={16} />
        Your goals
      </h2>
      <ul className="panel rows">
        {active.map((g) => (
          <GoalRow key={g.id} goal={g} onAsk={onAsk} />
        ))}
        {!active.length && (
          <li>
            <button
              type="button"
              className="row"
              onClick={() => onAsk('Help me set a goal', 2)}
            >
              <span className="row-main">
                <span className="ins-title">No goals yet</span>
                <small className="ins-text">Ask the coach to help you set one.</small>
              </span>
              <Icon name="chevron" className="chevron" />
            </button>
          </li>
        )}
      </ul>
      {clash?.clash && (
        <p className="ins-text goal-note">
          Together your goals need {eur(clash.total_needed)} a month, but you can
          safely save about {eur(clash.safe_to_save_monthly)}.
        </p>
      )}
      {completed.length > 0 && (
        <details className="goal-note">
          <summary>Completed ({completed.length})</summary>
          <ul>
            {completed.map((g) => (
              <li key={g.id}>{g.name}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
