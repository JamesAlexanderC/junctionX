import { PersonaAvatar } from '../CustomerCard.jsx'
import Card from './Card.jsx'

export default function PersonaCard({ persona, onAsk }) {
  if (!persona) return null
  return (
    <Card
      className="persona-card"
      title="Your spender persona"
      icon="user"
      question="What kind of spender am I?"
      onAsk={onAsk}
    >
      <div className="persona-main">
        <PersonaAvatar persona={persona} size={52} />
        <div>
          <p className="persona-label">{persona.label}</p>
          <p className="persona-desc">{persona.description}</p>
        </div>
      </div>
      {persona.traits?.length > 0 && (
        <ul className="trait-chips">
          {persona.traits.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </Card>
  )
}
