<script setup>
import { onMounted, ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import ConversationList from '@/components/ConversationList.vue'
import MessageBubble from '@/components/MessageBubble.vue'

const chat = useChatStore()
const draft = ref('')
const messagesEl = ref(null)

onMounted(() => chat.loadConversations())

const activeConversation = computed(() =>
  chat.conversations.find((c) => (c.conversation_id || c.name) === chat.activeConversationId)
)

async function selectConversation(id) {
  await chat.openConversation(id)
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

watch(() => chat.activeMessages.length, scrollToBottom)

async function send() {
  const text = draft.value.trim()
  if (!text || !activeConversation.value) return
  draft.value = ''
  const to = activeConversation.value.to_number || activeConversation.value.from_number
  await chat.sendText(to, text, activeConversation.value.reference_doctype, activeConversation.value.reference_name)
}
</script>

<template>
  <div class="wn-chat-layout">
    <div class="wn-conv-pane">
      <ConversationList
        :conversations="chat.conversations"
        :active-id="chat.activeConversationId"
        @select="selectConversation"
      />
    </div>

    <div class="wn-chat-pane">
      <template v-if="activeConversation">
        <div class="wn-chat-header">
          <div class="wn-avatar">{{ (activeConversation.profile_name || '?').charAt(0).toUpperCase() }}</div>
          <div>
            <div class="wn-chat-name">{{ activeConversation.profile_name || activeConversation.to_number }}</div>
            <div class="wn-chat-phone">{{ activeConversation.to_number || activeConversation.from_number }}</div>
          </div>
        </div>

        <div class="wn-messages" ref="messagesEl">
          <MessageBubble v-for="m in chat.activeMessages" :key="m.name" :message="m" />
          <div v-if="chat.loadingMessages" class="wn-loading">Loading…</div>
        </div>

        <form class="wn-composer" @submit.prevent="send">
          <input v-model="draft" type="text" placeholder="Type a message" />
          <button type="submit">Send</button>
        </form>
      </template>

      <div v-else class="wn-chat-empty">
        <p>Select a conversation to start messaging</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-chat-layout {
  display: flex;
  height: 100%;
  background: white;
  border-radius: var(--wn-radius);
  overflow: hidden;
  box-shadow: var(--wn-shadow);
}
.wn-conv-pane { width: 320px; flex-shrink: 0; border-right: 1px solid var(--wn-border); }
.wn-chat-pane { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.wn-chat-header { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--wn-border); }
.wn-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--wn-navy); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; }
.wn-chat-name { font-weight: 600; font-size: 14px; }
.wn-chat-phone { font-size: 12px; color: var(--wn-text-muted); }
.wn-messages { flex: 1; overflow-y: auto; padding: 16px; background: var(--wn-bg); }
.wn-loading { text-align: center; font-size: 12px; color: var(--wn-text-muted); }
.wn-composer { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--wn-border); }
.wn-composer input { flex: 1; padding: 10px 14px; border-radius: 20px; border: 1px solid var(--wn-border); font-size: 14px; }
.wn-composer button { padding: 10px 18px; border-radius: 20px; border: none; background: var(--wn-teal); color: white; font-weight: 600; }
.wn-chat-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--wn-text-muted); }

@media (max-width: 768px) {
  .wn-conv-pane { width: 100%; }
  .wn-chat-pane { display: none; }
}
</style>
