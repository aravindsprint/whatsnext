// Frappe returns datetimes as "YYYY-MM-DD HH:MM:SS(.ffffff)" — a space
// separator and microseconds, which Safari/iOS's Date parser rejects with
// "Invalid Date". Normalize to the ISO "T" form and trim to milliseconds.
// A bare "YYYY-MM-DD" is read as local midnight (not UTC, as `new Date()`
// would), so weekday labels don't shift by a day west of UTC.
export function parseFrappeDate(value) {
  if (!value) return new Date(NaN)
  if (value instanceof Date) return value
  let s = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += 'T00:00:00'
  s = s.replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1')
  return new Date(s)
}
