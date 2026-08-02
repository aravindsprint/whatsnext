// Parses pasted/uploaded CSV text into recipient objects.
// Supports an optional header row:
//   "name,phone,1,2"  -> contact_name + to_number + numbered variables
//   "phone,1,2"       -> to_number + numbered variables
//   (no header)       -> first column is the phone number, rest are variables
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

  return dataLines
    .map((line) => {
      const cells = line.split(',').map((c) => c.trim())
      let contact_name = ''
      let rest
      if (hasNameCol) {
        contact_name = cells[0] || ''
        rest = cells.slice(2)
      } else {
        rest = cells.slice(1)
      }
      const to_number = hasNameCol ? cells[1] : cells[0]
      const parameters = {}
      rest.forEach((val, i) => {
        parameters[String(i + 1)] = val
      })
      return { contact_name, to_number, parameters }
    })
    .filter((r) => r.to_number)
}

// Inverse — used to prefill the CSV textarea when editing a saved list.
export function recipientsToCsv(recipients) {
  const hasNames = recipients.some((r) => r.contact_name)
  const header = hasNames ? ['name', 'phone'] : ['phone']
  const maxVars = Math.max(0, ...recipients.map((r) => Object.keys(r.parameters || {}).length))
  for (let i = 1; i <= maxVars; i++) header.push(String(i))

  const rows = recipients.map((r) => {
    const cells = hasNames ? [r.contact_name || '', r.to_number] : [r.to_number]
    for (let i = 1; i <= maxVars; i++) cells.push((r.parameters || {})[String(i)] || '')
    return cells.join(',')
  })

  return [header.join(','), ...rows].join('\n')
}
