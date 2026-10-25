import { ref } from 'vue'

// Whether the slide-out menu is open on phones (the header's ☰ button
// toggles it; any navigation closes it).
export const navOpen = ref(false)

// Width breakpoints used across the app. Keep in sync with style.css.
export const PHONE_MAX = 768 // phones and small tablets in portrait: slide-out menu
export const RAIL_MAX = 1199 // tablets and small laptops: icon-only sidebar by default
