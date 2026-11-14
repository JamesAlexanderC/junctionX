// "See all questions" sheet, grouped by topic and depth; every example taps.

import { useApp } from '../lib/context.js'
import { DEPTH_NAMES } from '../lib/format.js'
import { allQuestions } from '../lib/questions.js'

export default function QuestionsSheet({ onClose }) {
  const { profile, ask } = useApp()
  return (
    <div className="sheet-backdrop" role="presentation" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-label="All questions"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="row">
          <h2>Things you can ask</h2>
          <button type="button" className="btn ghost small" onClick={onClose}>
            Close
          </button>
        </header>
        {allQuestions(profile).map((group) => (
          <section key={group.topic}>
            <h3 className="card-title">{group.topic}</h3>
            <ul className="question-list">
              {[...group.items]
                .sort((a, b) => a.depth - b.depth)
                .map((q) => (
                  <li key={q.text}>
                    <button
                      type="button"
                      onClick={() => {
                        onClose()
                        ask(q.text, { depth: q.depth, send: true })
                      }}
                    >
                      <span className="depth-badge">{DEPTH_NAMES[q.depth]}</span>
                      {q.text}
                    </button>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
