<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const originalTitle = document.title
const settings = reactive({
  reminder_interval_minutes: 20,
  rest_duration_value: 5,
  rest_duration_unit: 'minutes',
  snooze_minutes: 5,
  sound_enabled: true,
  notification_enabled: true,
})

const status = ref('idle')
const pausedFrom = ref('running')
const remainingSeconds = ref(settings.reminder_interval_minutes * 60)
const settingsLoaded = ref(false)
const saving = ref(false)
const error = ref('')
const audioContext = ref(null)
const oscillator = ref(null)
const gainNode = ref(null)
const titleTimer = ref(null)
const tickTimer = ref(null)

const statusLabel = computed(() => {
  if (status.value === 'running') return '下一次提醒'
  if (status.value === 'alerting') return '需要休息'
  if (status.value === 'resting') return '休息中'
  if (status.value === 'paused') return '已暂停'
  return '未启动'
})

const primaryActionLabel = computed(() => (status.value === 'paused' ? '继续' : '启动'))
const restDurationMax = computed(() => (settings.rest_duration_unit === 'seconds' ? 3600 : 60))

const formattedRemaining = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60)
  const seconds = remainingSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

const progressPercent = computed(() => {
  const total = currentCycleSeconds()
  if (!total) return 0
  return Math.max(0, Math.min(100, 100 - (remainingSeconds.value / total) * 100))
})

watch(
  () => settings.reminder_interval_minutes,
  () => {
    if (status.value === 'idle') {
      remainingSeconds.value = settings.reminder_interval_minutes * 60
    }
  },
)

watch(
  () => settings.rest_duration_unit,
  () => {
    if (settings.rest_duration_value > restDurationMax.value) {
      settings.rest_duration_value = restDurationMax.value
    }
  },
)

watch(
  () => settings.sound_enabled,
  (enabled) => {
    if (!enabled) {
      stopSound()
    }
  },
)

onMounted(async () => {
  await loadSettings()
})

onBeforeUnmount(() => {
  stopTimers()
  stopAlertEffects()
})

async function loadSettings() {
  try {
    const response = await fetch('/api/settings')
    if (!response.ok) throw new Error('读取配置失败')
    Object.assign(settings, await response.json())
    remainingSeconds.value = settings.reminder_interval_minutes * 60
    settingsLoaded.value = true
  } catch (err) {
    error.value = err.message
  }
}

async function saveSettings() {
  saving.value = true
  error.value = ''
  try {
    const response = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    if (!response.ok) throw new Error('保存配置失败，请检查数值范围')
    Object.assign(settings, await response.json())
    await unlockAudio()
    if (status.value === 'idle') {
      remainingSeconds.value = settings.reminder_interval_minutes * 60
    }
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function recordEvent(event_type, note = '') {
  try {
    await fetch('/api/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_type, note }),
    })
  } catch {
    // Event logging is useful, but the timer should continue if the API is temporarily unavailable.
  }
}

async function createDesktopAlert() {
  try {
    await fetch('/api/desktop-alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: '该休息眼睛了',
        message: '请离开屏幕，眺望远处，给眼睛一次真正的缓冲。',
      }),
    })
  } catch {
    // The in-page alert remains active even if the desktop companion is not running.
  }
}

async function startTimer() {
  await unlockAudio()
  await requestNotificationPermission()
  stopAlertEffects()
  if (status.value === 'paused') {
    status.value = pausedFrom.value
  } else {
    status.value = 'running'
    if (remainingSeconds.value <= 0) remainingSeconds.value = settings.reminder_interval_minutes * 60
  }
  startTicking()
}

function pauseTimer() {
  pausedFrom.value = status.value === 'resting' ? 'resting' : 'running'
  status.value = 'paused'
  stopTicking()
  stopAlertEffects()
  recordEvent('paused')
}

function resetTimer() {
  status.value = 'idle'
  remainingSeconds.value = settings.reminder_interval_minutes * 60
  stopTicking()
  stopAlertEffects()
  recordEvent('reset')
}

function startTicking() {
  stopTicking()
  tickTimer.value = window.setInterval(() => {
    if (remainingSeconds.value > 0) {
      remainingSeconds.value -= 1
      if (remainingSeconds.value === 0) handleTimerComplete()
      return
    }
    handleTimerComplete()
  }, 1000)
}

function handleTimerComplete() {
  if (status.value === 'running') triggerReminder()
  if (status.value === 'resting') finishRest()
}

function currentCycleSeconds() {
  if (status.value === 'resting' || (status.value === 'paused' && pausedFrom.value === 'resting')) {
    return restDurationSeconds()
  }
  if (status.value === 'running' || status.value === 'paused') {
    return settings.reminder_interval_minutes * 60
  }
  return settings.reminder_interval_minutes * 60
}

function restDurationSeconds() {
  const value = Number(settings.rest_duration_value) || 1
  return settings.rest_duration_unit === 'seconds' ? value : value * 60
}

function stopTicking() {
  if (tickTimer.value) {
    window.clearInterval(tickTimer.value)
    tickTimer.value = null
  }
}

function stopTimers() {
  stopTicking()
  if (titleTimer.value) {
    window.clearInterval(titleTimer.value)
    titleTimer.value = null
  }
}

async function triggerReminder() {
  status.value = 'alerting'
  stopTicking()
  remainingSeconds.value = 0
  startAlertEffects()
  sendNotification('该休息眼睛了', '离开屏幕，看看远处，让眼睛缓一缓。')
  await createDesktopAlert()
  await recordEvent('reminder_triggered')
}

function startRest() {
  stopAlertEffects()
  status.value = 'resting'
  remainingSeconds.value = restDurationSeconds()
  startTicking()
  recordEvent('rest_started')
}

function snooze() {
  stopAlertEffects()
  status.value = 'running'
  remainingSeconds.value = settings.snooze_minutes * 60
  startTicking()
  recordEvent('snoozed')
}

function skipReminder() {
  stopAlertEffects()
  status.value = 'running'
  remainingSeconds.value = settings.reminder_interval_minutes * 60
  startTicking()
  recordEvent('skipped')
}

function finishRest() {
  status.value = 'running'
  remainingSeconds.value = settings.reminder_interval_minutes * 60
  startTicking()
  sendNotification('休息结束', '新的护眼计时已经开始。')
  recordEvent('rest_completed')
}

async function unlockAudio() {
  if (!settings.sound_enabled || audioContext.value) return
  const Context = window.AudioContext || window.webkitAudioContext
  if (!Context) return
  audioContext.value = new Context()
  await audioContext.value.resume()
}

function startAlertEffects() {
  startTitleFlash()
  if (settings.sound_enabled) startSound()
}

function stopAlertEffects() {
  stopTitleFlash()
  stopSound()
  document.title = originalTitle
}

function startTitleFlash() {
  stopTitleFlash()
  let visible = false
  titleTimer.value = window.setInterval(() => {
    visible = !visible
    document.title = visible ? '请休息眼睛！' : originalTitle
  }, 700)
}

function stopTitleFlash() {
  if (titleTimer.value) {
    window.clearInterval(titleTimer.value)
    titleTimer.value = null
  }
}

function startSound() {
  if (!audioContext.value) return
  stopSound()
  oscillator.value = audioContext.value.createOscillator()
  gainNode.value = audioContext.value.createGain()
  oscillator.value.type = 'sine'
  oscillator.value.frequency.value = 880
  gainNode.value.gain.value = 0.08
  oscillator.value.connect(gainNode.value)
  gainNode.value.connect(audioContext.value.destination)
  oscillator.value.start()
}

function stopSound() {
  if (oscillator.value) {
    oscillator.value.stop()
    oscillator.value.disconnect()
    oscillator.value = null
  }
  if (gainNode.value) {
    gainNode.value.disconnect()
    gainNode.value = null
  }
}

async function requestNotificationPermission() {
  if (!settings.notification_enabled || !('Notification' in window)) return
  if (Notification.permission === 'default') {
    await Notification.requestPermission()
  }
}

function sendNotification(title, body) {
  if (!settings.notification_enabled || !('Notification' in window)) return
  if (Notification.permission === 'granted') {
    new Notification(title, { body })
  }
}
</script>

<template>
  <main class="app-shell">
    <section class="timer-panel">
      <div class="timer-summary">
        <p class="eyebrow">{{ statusLabel }}</p>
        <h1>{{ formattedRemaining }}</h1>
        <div class="progress-track" aria-hidden="true">
          <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
        </div>
      </div>

      <div class="controls" aria-label="计时控制">
        <button
          class="primary"
          type="button"
          :disabled="!settingsLoaded || status === 'running' || status === 'resting' || status === 'alerting'"
          @click="startTimer"
        >
          {{ primaryActionLabel }}
        </button>
        <button type="button" :disabled="status !== 'running' && status !== 'resting'" @click="pauseTimer">暂停</button>
        <button type="button" @click="resetTimer">重置</button>
      </div>
    </section>

    <section class="settings-panel" aria-label="提醒设置">
      <div class="field-grid">
        <label>
          <span>提醒间隔（分钟）</span>
          <input v-model.number="settings.reminder_interval_minutes" min="1" max="240" type="number" />
        </label>
        <label>
          <span>休息时长</span>
          <div class="duration-input">
            <input v-model.number="settings.rest_duration_value" min="1" :max="restDurationMax" type="number" />
            <select v-model="settings.rest_duration_unit" aria-label="休息时长单位">
              <option value="minutes">分钟</option>
              <option value="seconds">秒</option>
            </select>
          </div>
        </label>
        <label>
          <span>稍后提醒（分钟）</span>
          <input v-model.number="settings.snooze_minutes" min="1" max="60" type="number" />
        </label>
      </div>

      <div class="toggle-row">
        <label class="toggle">
          <input v-model="settings.sound_enabled" type="checkbox" />
          <span>声音提醒（蜂鸣）</span>
        </label>
        <label class="toggle">
          <input v-model="settings.notification_enabled" type="checkbox" />
          <span>浏览器通知</span>
        </label>
      </div>

      <div class="save-row">
        <button type="button" :disabled="saving" @click="saveSettings">
          {{ saving ? '保存中' : '保存设置' }}
        </button>
        <p v-if="error" class="error">{{ error }}</p>
      </div>
    </section>

    <div v-if="status === 'alerting'" class="alert-overlay" role="dialog" aria-modal="true" aria-labelledby="alert-title">
      <div class="alert-content">
        <p class="eyebrow">强提醒</p>
        <h2 id="alert-title">该休息眼睛了</h2>
        <p>请离开屏幕，眺望远处，给眼睛一次真正的缓冲。</p>
        <div class="alert-actions">
          <button class="primary inverse" type="button" @click="startRest">开始休息</button>
          <button type="button" @click="snooze">稍后提醒</button>
          <button type="button" @click="skipReminder">跳过本次</button>
        </div>
      </div>
    </div>
  </main>
</template>
