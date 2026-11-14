// Chat state for every customer, kept above the screens so a conversation
// (and an in-flight answer) survives switching between Home and Coach tabs.

import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat } from '../api.js'

const EMPTY = { messages: [], busy: false, provider: null, model: null, draft: '' }

export default function useConversations() {
  const [convos, setConvos] = useState({})
  const controllers = useRef(new Map())

  useEffect(() => {
    const map = controllers.current
    return () => map.forEach((c) => c.abort())
  }, [])

  const patch = useCallback((id, fn) => {
    setConvos((prev) => {
      const current = { ...EMPTY, ...prev[id] }
      return { ...prev, [id]: { ...current, ...fn(current) } }
    })
  }, [])

  // Apply an update to the last (assistant) message of one conversation.
  const patchLast = useCallback(
    (id, fn) =>
      patch(id, (c) => ({
        messages: [...c.messages.slice(0, -1), fn(c.messages.at(-1))],
      })),
    [patch],
  )

  const get = useCallback((id) => convos[id] ?? EMPTY, [convos])

  const setDraft = useCallback((id, draft) => patch(id, () => ({ draft })), [patch])

  const stop = useCallback((id) => controllers.current.get(id)?.abort(), [])

  const send = useCallback(
    async (id, text, previous) => {
      const question = text.trim()
      if (!question || controllers.current.has(id)) return

      const history = [
        ...previous
          .filter((m) => !m.error && m.content)
          .map(({ role, content }) => ({ role, content })),
        { role: 'user', content: question },
      ]
      patch(id, (c) => ({
        busy: true,
        draft: '',
        messages: [
          ...c.messages,
          { role: 'user', content: question },
          {
            role: 'assistant',
            content: '',
            pending: true,
            tools: [],
            charts: [],
            concepts: [],
            suggestions: [],
          },
        ],
      }))

      const controller = new AbortController()
      controllers.current.set(id, controller)
      try {
        await streamChat({
          customerId: id,
          messages: history,
          signal: controller.signal,
          onEvent: (ev) => {
            switch (ev.type) {
              case 'meta':
                patch(id, () => ({ provider: ev.provider, model: ev.model ?? null }))
                break
              case 'tool':
                patchLast(id, (m) => ({
                  ...m,
                  tools: [...m.tools, { name: ev.name, label: ev.label }],
                }))
                break
              case 'token':
                patchLast(id, (m) => ({ ...m, content: m.content + (ev.text ?? '') }))
                break
              case 'chart':
                if (ev.chart) {
                  patchLast(id, (m) => ({ ...m, charts: [...m.charts, ev.chart] }))
                }
                break
              case 'concept':
                patchLast(id, (m) => ({
                  ...m,
                  concepts: [...m.concepts, { title: ev.title, text: ev.text }],
                }))
                break
              case 'suggestions':
                patchLast(id, (m) => ({ ...m, suggestions: ev.items ?? [] }))
                break
              case 'error':
                throw new Error(ev.message || 'Something went wrong')
              default:
                break
            }
          },
        })
      } catch (err) {
        if (err.name === 'AbortError') {
          patchLast(id, (m) => ({ ...m, stopped: true }))
        } else {
          patchLast(id, (m) => ({
            ...m,
            error: true,
            content: `Sorry, I couldn't answer that. ${err.message}`,
          }))
        }
      } finally {
        controllers.current.delete(id)
        patchLast(id, (m) => ({ ...m, pending: false }))
        patch(id, () => ({ busy: false }))
      }
    },
    [patch, patchLast],
  )

  return { get, send, stop, setDraft }
}
