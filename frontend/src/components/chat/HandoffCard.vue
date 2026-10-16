<template>
  <div class="handoff-card" :class="'is-' + state">
    <div class="hc-head">
      <span class="hc-icon"><XoIcon :name="state === 'saved' ? 'check' : 'headset'" :size="18" /></span>
      <div class="hc-title">
        <strong>{{ state === 'saved' ? tr('handoff_saved') : tr('handoff_review_title') }}</strong>
        <small v-if="state === 'saved' && draft.ticket_id">{{ tr('ticket') }}: {{ draft.ticket_id }}</small>
      </div>
    </div>

    <dl v-if="!editing" class="hc-rows">
      <div><dt>{{ tr('handoff_name') }}</dt><dd>{{ draft.name }}</dd></div>
      <div><dt>{{ tr('handoff_phone') }}</dt><dd dir="ltr">{{ draft.phone }}</dd></div>
      <div v-if="draft.preferred_language"><dt>{{ tr('handoff_language') }}</dt><dd>{{ languageLabel(draft.preferred_language) }}</dd></div>
      <div><dt>{{ tr('handoff_team') }}</dt><dd>{{ teamLabel(draft.team) }}</dd></div>
    </dl>

    <form v-else class="hc-form" @submit.prevent="submit" novalidate>
      <label>
        <span>{{ tr('handoff_name') }}</span>
        <input v-model="form.name" type="text" autocomplete="name" maxlength="120" dir="auto" :aria-invalid="errorField === 'name'" ref="nameInput" />
      </label>
      <label>
        <span>{{ tr('handoff_phone') }}</span>
        <input v-model="form.phone" type="tel" inputmode="tel" autocomplete="tel" dir="ltr" maxlength="24" placeholder="+971 50 123 4567"
               :aria-invalid="errorField === 'phone'" ref="phoneInput" />
        <small>{{ tr('handoff_phone_hint') }}</small>
      </label>
      <div class="hc-form-row">
        <label>
          <span>{{ tr('handoff_language') }}</span>
          <select v-model="form.preferred_language">
            <option v-for="lang in languages" :key="lang.code" :value="lang.code">{{ lang.native }}</option>
          </select>
        </label>
        <label>
          <span>{{ tr('handoff_team') }}</span>
          <select v-model="form.team">
            <option v-for="team in TEAMS" :key="team" :value="team">{{ tr('team_' + team) }}</option>
          </select>
        </label>
      </div>
      <button type="submit" class="visually-hidden" tabindex="-1">{{ tr('handoff_submit') }}</button>
    </form>

    <p v-if="error" class="hc-error" role="alert">{{ error }}</p>
    <p v-if="state === 'review'" class="hc-note">{{ tr('handoff_consent_note') }}</p>
    <p v-else-if="state === 'saved'" class="hc-note">{{ tr('handoff_saved_note') }}</p>
    <p v-else-if="state === 'expired'" class="hc-note">{{ tr('handoff_err_expired') }}</p>

    <div v-if="state === 'review'" class="hc-actions">
      <template v-if="!editing">
        <button type="button" class="hc-btn ghost" @click="startEdit" :disabled="saving">
          <XoIcon name="edit" :size="15" />{{ tr('handoff_edit') }}
        </button>
        <button type="button" class="hc-btn primary" @click="submit" :disabled="saving">
          <XoIcon name="check" :size="15" />{{ saving ? tr('handoff_saving') : tr('handoff_confirm') }}
        </button>
      </template>
      <template v-else>
        <button type="button" class="hc-btn ghost" @click="cancelEdit" :disabled="saving">{{ tr('cancel') }}</button>
        <button type="button" class="hc-btn primary" @click="submit" :disabled="saving">
          {{ saving ? tr('handoff_saving') : tr('handoff_submit') }}
        </button>
      </template>
    </div>
  </div>
</template>

<script setup>
// Advisor callback review card (PRD FR-5): nothing is saved until the user taps Confirm (or edits and submits).
// The card's state is kept on the message (draft object), so it survives a page refresh.
import { computed, inject, nextTick, reactive, ref } from 'vue'
import XoIcon from '../shared/XoIcon.vue'
import { languages, languageInfo, t } from '../../i18n'

const TEAMS = ['mortgage', 'sales', 'support']
const ERRORS = { invalid_phone: 'handoff_err_phone', invalid_name: 'handoff_err_name', save_failed: 'handoff_err_save' }

const props = defineProps({
  draft: { type: Object, required: true },
  language: { type: String, default: 'en' }
})
const submitHandoff = inject('submitHandoff', null)

const tr = (key, vars) => t(props.language, key, vars)
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const errorField = ref('')
const nameInput = ref(null)
const phoneInput = ref(null)
const form = reactive({ name: '', phone: '', preferred_language: '', team: '' })

const state = computed(() => props.draft.status || 'review')
const languageLabel = (code) => languageInfo(code)?.native || code
const teamLabel = (team) => (TEAMS.includes(team) ? tr('team_' + team) : team)

function fillForm() {
  form.name = props.draft.name || ''
  form.phone = props.draft.phone || ''
  form.preferred_language = props.draft.preferred_language || props.language
  form.team = TEAMS.includes(props.draft.team) ? props.draft.team : 'support'
}

async function startEdit(field) {
  fillForm()
  editing.value = true
  await nextTick()
  const target = field === 'phone' ? phoneInput.value : nameInput.value
  target && target.focus()
}

function cancelEdit() {
  editing.value = false
  error.value = ''
  errorField.value = ''
}

async function submit() {
  if (saving.value || !submitHandoff) return
  const values = editing.value ? { ...form } : {
    name: props.draft.name, phone: props.draft.phone, preferred_language: props.draft.preferred_language, team: props.draft.team
  }
  if (!values.name.trim()) return showError('invalid_name', 'name')
  if ((values.phone.match(/\d/g) || []).length < 7) return showError('invalid_phone', 'phone')

  saving.value = true
  error.value = ''
  const result = await submitHandoff({
    draft_id: props.draft.draft_id, full_name: values.name, phone: values.phone,
    preferred_language: values.preferred_language, team: values.team
  })
  saving.value = false
  if (result.lead_saved) {
    Object.assign(props.draft, {
      status: 'saved', ticket_id: result.ticket_id, name: result.name, phone: result.phone,
      preferred_language: result.preferred_language, team: result.team
    })
    editing.value = false
    return
  }
  if (result.error === 'draft_expired') {
    props.draft.status = 'expired'
    editing.value = false
    return
  }
  showError(result.error, result.field)
}

function showError(code, field) {
  error.value = tr(ERRORS[code] || 'handoff_err_save')
  errorField.value = field || ''
  if (field && !editing.value) startEdit(field)
}
</script>

<style scoped>
/* Colours come from the widget tokens (--w-*) defined on .xo-widget in ChatWidget.vue */
.handoff-card {
  display: flex; flex-direction: column; gap: 10px; margin-top: 8px; padding: 14px;
  background: var(--w-bg, #fff); color: var(--w-ink, #0f172a);
  border: 1px solid rgba(124, 44, 240, 0.28); border-radius: 18px;
  box-shadow: 0 10px 24px -16px rgba(38, 10, 74, 0.35);
}
.handoff-card.is-saved { border-color: rgba(34, 197, 94, 0.4); }
.handoff-card.is-expired { opacity: 0.6; }
.hc-head { display: flex; align-items: center; gap: 10px; }
.hc-icon {
  display: grid; place-items: center; flex: none; width: 34px; height: 34px; border-radius: 10px;
  background: linear-gradient(135deg, #5c039b, #7c2cf0); color: #fff;
}
.is-saved .hc-icon { background: linear-gradient(135deg, #16a34a, #22c55e); }
.hc-title { display: flex; flex-direction: column; min-width: 0; }
.hc-title strong { font-size: 0.9rem; font-weight: 650; }
.hc-title small { font-size: 0.72rem; color: var(--w-ink-2, #64748b); font-variant-numeric: tabular-nums; }

.hc-rows { display: grid; gap: 6px; margin: 0; padding: 10px 12px; border-radius: 12px; background: var(--w-feed, #f7f6fb); font-size: 0.84rem; }
.hc-rows div { display: flex; justify-content: space-between; gap: 12px; }
.hc-rows dt { color: var(--w-ink-2, #64748b); }
.hc-rows dd { margin: 0; font-weight: 600; text-align: end; overflow-wrap: anywhere; }

.hc-form { display: flex; flex-direction: column; gap: 10px; }
.hc-form label { display: flex; flex-direction: column; gap: 4px; min-width: 0; font-size: 0.74rem; color: var(--w-ink-2, #64748b); }
.hc-form-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.hc-form input, .hc-form select {
  width: 100%; padding: 9px 11px; border: 1px solid var(--w-line, rgba(15, 23, 42, 0.12)); border-radius: 10px;
  background: var(--w-bg, #fff); color: var(--w-ink, #0f172a); font: inherit; font-size: 0.9rem;
}
.hc-form input:focus, .hc-form select:focus { outline: none; border-color: rgba(124, 44, 240, 0.55); box-shadow: 0 0 0 3px var(--w-ring, rgba(124, 44, 240, 0.14)); }
.hc-form input[aria-invalid="true"] { border-color: #dc2626; }
.hc-form small { font-size: 0.7rem; }

.hc-error { margin: 0; font-size: 0.78rem; color: #dc2626; }
.hc-note { margin: 0; font-size: 0.74rem; color: var(--w-ink-2, #64748b); }
.hc-actions { display: flex; gap: 8px; }
.hc-btn {
  flex: 1 1 0; display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; padding: 8px 12px;
  border-radius: 12px; cursor: pointer; font-size: 0.84rem; font-weight: 600; transition: transform 150ms ease, background 150ms ease;
}
.hc-btn:active:not(:disabled) { transform: scale(0.97); }
.hc-btn:disabled { opacity: 0.65; cursor: default; }
.hc-btn.ghost { border: 1px solid var(--w-line, rgba(15, 23, 42, 0.12)); background: transparent; color: var(--w-ink, #0f172a); }
.hc-btn.ghost:hover:not(:disabled) { background: var(--w-chip, rgba(92, 3, 155, 0.06)); }
.hc-btn.primary { border: 0; background: linear-gradient(135deg, #5c039b, #7c2cf0); color: #fff; box-shadow: 0 6px 14px -6px rgba(92, 3, 155, 0.6); }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

@container (max-width: 340px) {
  .hc-form-row { grid-template-columns: minmax(0, 1fr); }
}
</style>
