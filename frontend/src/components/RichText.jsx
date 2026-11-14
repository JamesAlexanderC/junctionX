// Renders the coach's markdown subset safely (no innerHTML):
// paragraphs, **bold**, *italic*, `code`, "- " / "* " bullets, "1. " lists
// and "#"-style headings (shown as bold lines).

const BULLET = /^\s*[-*•]\s+/
const NUMBERED = /^\s*\d+[.)]\s+/
const HEADING = /^\s*#{1,6}\s+/

function Inline({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g)
  return parts.map((part, i) => {
    if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
      return <code key={i}>{part.slice(1, -1)}</code>
    }
    if (part.length > 2 && part.startsWith('*') && part.endsWith('*')) {
      return <em key={i}>{part.slice(1, -1)}</em>
    }
    return part
  })
}

function parseBlocks(text) {
  const blocks = []
  let current = null
  const flush = () => {
    if (current) blocks.push(current)
    current = null
  }
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    if (!line.trim()) {
      flush()
      continue
    }
    const type = BULLET.test(line)
      ? 'ul'
      : NUMBERED.test(line)
        ? 'ol'
        : HEADING.test(line)
          ? 'h'
          : 'p'
    if (type === 'h') {
      flush()
      blocks.push({ type, lines: [line.replace(HEADING, '')] })
      continue
    }
    // A plain line right after a list item continues that item.
    if (type === 'p' && current && current.type !== 'p') {
      current.lines[current.lines.length - 1] += ` ${line.trim()}`
      continue
    }
    if (!current || current.type !== type) {
      flush()
      current = { type, lines: [], start: 1 }
      if (type === 'ol') current.start = parseInt(line, 10) || 1
    }
    current.lines.push(line.replace(type === 'ul' ? BULLET : NUMBERED, ''))
    if (type === 'p') current.lines[current.lines.length - 1] = line
  }
  flush()
  return blocks
}

export default function RichText({ text }) {
  return parseBlocks(text.trim()).map((block, i) => {
    if (block.type === 'ul' || block.type === 'ol') {
      const List = block.type
      return (
        <List key={i} start={block.type === 'ol' ? block.start : undefined}>
          {block.lines.map((l, j) => (
            <li key={j}>
              <Inline text={l} />
            </li>
          ))}
        </List>
      )
    }
    if (block.type === 'h') {
      return (
        <p key={i} className="rt-heading">
          <strong>
            <Inline text={block.lines[0].replace(/\*\*/g, '')} />
          </strong>
        </p>
      )
    }
    return (
      <p key={i}>
        {block.lines.map((l, j) => (
          <span key={j}>
            {j > 0 && <br />}
            <Inline text={l} />
          </span>
        ))}
      </p>
    )
  })
}
