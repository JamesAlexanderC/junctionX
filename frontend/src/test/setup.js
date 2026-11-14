import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())

// jsdom has no scrollIntoView.
Element.prototype.scrollIntoView ??= function () {}
