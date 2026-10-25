// v-table-labels: copies each column's header text onto its cells as
// data-label, so on phones a table row can be shown as a card of
// "Label: value" lines (see .wn-stack in style.css) without repeating the
// labels by hand in every template.
function apply(table) {
  const headers = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim())
  for (const row of table.querySelectorAll('tbody tr')) {
    let col = 0
    for (const cell of row.children) {
      const span = Number(cell.getAttribute('colspan') || 1)
      if (span > 1) cell.setAttribute('data-full', '')
      else if (headers[col]) cell.setAttribute('data-label', headers[col])
      col += span
    }
  }
}

export default {
  mounted: apply,
  updated: apply,
}
