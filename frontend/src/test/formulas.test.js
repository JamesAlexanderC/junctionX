import { describe, expect, it } from 'vitest'
import { addMonths, cutSaving, goalMonths, goalWithCut } from '../lib/formulas.js'

// Test Aino numbers from context.md "Inference unit tests".
describe('#24 cut a category', () => {
  it('cut takeaway (90 a month) by 20% saves 18 a month, 216 a year', () => {
    expect(cutSaving(90, 0.2)).toEqual({ monthly: 18, yearly: 216 })
  })
  it('never goes negative', () => {
    expect(cutSaving(-5, 0.2)).toEqual({ monthly: 0, yearly: 0 })
  })
})

describe('#26 goal date', () => {
  it('1,500 target, 640 saved, 150 a month = 6 months', () => {
    expect(goalMonths(1500, 640, 150)).toBe(6)
  })
  it('rate 0 is not reachable', () => {
    expect(goalMonths(1500, 640, 0)).toBeNull()
  })
  it('already reached is 0 months', () => {
    expect(goalMonths(500, 600, 100)).toBe(0)
  })
  it('a cut moves the goal date earlier', () => {
    const r = goalWithCut({ target: 1500, saved: 640, monthlyRate: 150 }, 18, '2026-10-18')
    expect(r.before).toBe(6)
    expect(r.after).toBe(6) // 860 / 168 = 5.12 -> 6
    const big = goalWithCut({ target: 1500, saved: 640, monthlyRate: 150 }, 70, '2026-10-18')
    expect(big.after).toBe(4)
    expect(big.monthsSooner).toBe(2)
  })
  it('addMonths clamps to month end', () => {
    expect(addMonths('2026-01-31', 1)).toBe('2026-02-28')
    expect(addMonths('2026-10-18', 6)).toBe('2027-04-18')
  })
})
