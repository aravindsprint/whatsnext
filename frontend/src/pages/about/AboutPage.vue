<script setup>
const version = '1.0.0'
</script>

<template>
  <div class="wn-about wn-card">
    <h2>Whatsnext</h2>
    <p class="wn-tagline">WhatsApp Business messaging hub for ERPNext — Meta Cloud API + Twilio, unified.</p>
    <ul>
      <li>Version {{ version }}</li>
      <li>Built by Aravind Govindaraj</li>
      <li>Independent of any third-party WhatsApp integration app</li>
    </ul>
    <h3>Features</h3>
    <ul class="wn-features">
      <li>Two-way WhatsApp chat synced with ERPNext documents</li>
      <li>Meta WhatsApp Cloud API and Twilio, side by side or either alone</li>
      <li>Reusable message templates with variable substitution</li>
      <li>Event-driven notifications — fire a WhatsApp message on any doctype's submit/update</li>
      <li>Scheduled sends with a stuck-message safety net</li>
      <li>Dashboard: message queue, delivery status, weekly trends, top templates</li>
    </ul>
  </div>
</template>

<style scoped>
.wn-about { max-width: 560px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 24px; }
.wn-tagline { color: var(--wn-text-muted); font-size: 14px; }
h2 { margin-top: 0; }
h3 { font-size: 14px; margin-top: 20px; }
ul { padding-left: 20px; font-size: 13.5px; line-height: 1.7; }
</style>
