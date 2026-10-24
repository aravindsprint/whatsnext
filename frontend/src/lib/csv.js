// Parses pasted/uploaded CSV text into recipient objects.
// Supports an optional header row:
//   "name,phone,1,2"  -> contact_name + to_number + numbered variables
//   "phone,1,2"       -> to_number + numbered variables
//   (no header)       -> auto-detected: whichever of the first two columns
//                        looks like a phone number is treated as the phone;
//                        the other (if any) becomes contact_name.
export function looksLikePhone(value) {
  const digits = (value || '').replace(/[\s\-()]/g, '')
  return /^\+?\d{7,15}$/.test(digits)
}

export function parseRecipientsCsv(text) {
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  if (!lines.length) return []

  const first = lines[0].split(',').map((c) => c.trim())
  const hasNameCol = /^name$/i.test(first[0])
  const hasPhoneHeader = /^(phone|to|number)$/i.test(first[0])
  const isHeader = hasNameCol || hasPhoneHeader

  const dataLines = isHeader ? lines.slice(1) : lines
  // Header names for the variable columns: "1", "2", "header_1",
  // "button_0" target those template inputs directly; anything else falls
  // back to positional numbering.
  const varHeaders = isHeader ? first.slice(hasNameCol ? 2 : 1) : []
  const keyFor = (i) => {
    const h = (varHeaders[i] || '').trim()
    return /^(\d+|header_1|button_\d+)$/.test(h) ? h : String(i + 1)
  }

  return dataLines
    .map((line) => {
      const cells = line.split(',').map((c) => c.trim())
      let contact_name = ''
      let rest
      let to_number

      if (hasNameCol) {
        // Explicit header told us the order: name,phone,...
        contact_name = cells[0] || ''
        to_number = cells[1]
        rest = cells.slice(2)
      } else if (isHeader) {
        // Explicit phone/to/number header: phone,...
        to_number = cells[0]
        rest = cells.slice(1)
      } else {
        // No header — auto-detect which of the first two columns is the
        // phone number rather than assuming column order, so a manually
        // typed "Aravind,9894088422" row doesn't get sent to WhatsApp with
        // the contact's name as the destination number.
        const col0Phone = looksLikePhone(cells[0])
        const col1Phone = cells.length > 1 && looksLikePhone(cells[1])
        if (!col0Phone && col1Phone) {
          contact_name = cells[0] || ''
          to_number = cells[1]
          rest = cells.slice(2)
        } else {
          to_number = cells[0]
          rest = cells.slice(1)
        }
      }

      const parameters = {}
      rest.forEach((val, i) => {
        parameters[keyFor(i)] = val
      })
      return { contact_name, to_number, parameters, valid: looksLikePhone(to_number) }
    })
    .filter((r) => r.to_number)
}

// Inverse — used to prefill the CSV textarea when editing a saved list.
export function recipientsToCsv(recipients) {
  const hasNames = recipients.some((r) => r.contact_name)
  const header = hasNames ? ['name', 'phone'] : ['phone']
  // Every parameter key used by any recipient, body variables first in
  // numeric order, then header/button keys.
  const keys = [...new Set(recipients.flatMap((r) => Object.keys(r.parameters || {})))]
  keys.sort((a, b) => {
    const na = /^\d+$/.test(a), nb = /^\d+$/.test(b)
    if (na && nb) return Number(a) - Number(b)
    if (na !== nb) return na ? -1 : 1
    return a.localeCompare(b)
  })
  header.push(...keys)

  const rows = recipients.map((r) => {
    const cells = hasNames ? [r.contact_name || '', r.to_number] : [r.to_number]
    for (const k of keys) cells.push((r.parameters || {})[k] || '')
    return cells.join(',')
  })

  return [header.join(','), ...rows].join('\n')
}
