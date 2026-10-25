import { describe, expect, it } from 'vitest'
import { parseRecipientsCsv, recipientsToCsv, looksLikePhone } from '../csv'
import { parseFrappeDate } from '../date'
import { templateInputs, needsHeaderMedia, toFrappeDatetime } from '../templateVars'

describe('csv', () => {
  it('detects phone numbers', () => {
    expect(looksLikePhone('+91 98765 43210')).toBe(true)
    expect(looksLikePhone('Aravind')).toBe(false)
  })

  it('auto-detects a name column without a header', () => {
    const [r] = parseRecipientsCsv('Aravind,9894088422,INV-1')
    expect(r.contact_name).toBe('Aravind')
    expect(r.to_number).toBe('9894088422')
    expect(r.parameters).toEqual({ 1: 'INV-1' })
  })

  it('uses named header columns for header/button variables', () => {
    const [r] = parseRecipientsCsv('name,phone,1,button_0\nRavi,+919876543210,SO-1,abc')
    expect(r.parameters).toEqual({ 1: 'SO-1', button_0: 'abc' })
  })

  it('flags invalid numbers', () => {
    const [r] = parseRecipientsCsv('phone\nnot-a-number')
    expect(r.valid).toBe(false)
  })

  it('round-trips through recipientsToCsv', () => {
    const text = 'name,phone,1,2,header_1\nRavi,+919876543210,a,b,h'
    expect(parseRecipientsCsv(recipientsToCsv(parseRecipientsCsv(text)))).toEqual(parseRecipientsCsv(text))
  })
})

describe('parseFrappeDate', () => {
  it('parses Frappe datetimes with microseconds (Safari-safe form)', () => {
    const d = parseFrappeDate('2026-10-24 12:34:56.123456')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getHours()).toBe(12)
    expect(d.getMilliseconds()).toBe(123)
  })

  it('reads a bare date as local midnight', () => {
    const d = parseFrappeDate('2026-10-24')
    expect([d.getDate(), d.getHours()]).toEqual([24, 0])
  })

  it('returns an invalid date for empty input', () => {
    expect(isNaN(parseFrappeDate(null))).toBe(true)
  })
})

describe('templateInputs', () => {
  const tpl = {
    body: 'Hi {{1}}, order {{2}} ships {{3}}',
    header_type: 'Text',
    header_text: 'Order {{1}}',
    variables_sample: '{"1":"Ravi"}',
    buttons: [
      { index: 0, type: 'Quick Reply', text: 'Thanks' },
      { index: 1, type: 'URL', text: 'Track', value: 'https://x.in/t/{{1}}' },
    ],
  }

  it('lists header, body and URL-button inputs with backend keys', () => {
    expect(templateInputs(tpl).map((i) => i.key)).toEqual(['header_1', '1', '2', '3', 'button_1'])
  })

  it('uses saved samples as placeholders', () => {
    expect(templateInputs(tpl).find((i) => i.key === '1').placeholder).toBe('Ravi')
  })

  it('knows which headers need media', () => {
    expect(needsHeaderMedia({ header_type: 'Image' })).toBe(true)
    expect(needsHeaderMedia({ header_type: 'Text' })).toBe(false)
  })

  it('converts datetime-local values to Frappe format', () => {
    expect(toFrappeDatetime('2026-10-24T18:30')).toBe('2026-10-24 18:30:00')
    expect(toFrappeDatetime('')).toBe(null)
  })
})
