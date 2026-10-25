import { describe, expect, it } from 'vitest'
import { errorMessage } from '../errors'

const serverMessages = (...msgs) => JSON.stringify(msgs.map((m) => JSON.stringify({ message: m })))

describe('errorMessage', () => {
  it('prefers the user-facing server message', () => {
    expect(errorMessage({
      exception: 'frappe.exceptions.ValidationError: The <b>24-hour</b> window is closed',
      _server_messages: serverMessages('The <b>24-hour</b> window is closed'),
    })).toBe('The 24-hour window is closed')
  })

  it('uses the last server message when there are several', () => {
    expect(errorMessage({ _server_messages: serverMessages('First', 'Second') })).toBe('Second')
  })

  it('strips the class path from a raw exception', () => {
    expect(errorMessage({
      exception: 'whatsnext_ai.whatsnext_ai.client.AIServiceError: The AI service is busy right now. Please try again in a minute.',
    })).toBe('The AI service is busy right now. Please try again in a minute.')
  })

  it('keeps messages that merely contain a colon', () => {
    expect(errorMessage({ exception: 'Note: retry later' })).toBe('Note: retry later')
  })

  it('falls back to message, then the status code', () => {
    expect(errorMessage({ message: 'Plain message' })).toBe('Plain message')
    expect(errorMessage({}, 502)).toBe('Request failed (502)')
    expect(errorMessage(null)).toBe('Request failed')
  })

  it('survives malformed server messages', () => {
    expect(errorMessage({ _server_messages: 'not json', exception: 'frappe.exceptions.PermissionError: Not permitted' }))
      .toBe('Not permitted')
  })
})
