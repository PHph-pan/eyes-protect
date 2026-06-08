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

const timer = reactive({
  status: 'idle',
  remaining_seconds: 0,
  total_seconds: 0,
  paused_from_status: null,
  active_desktop_alert_id: null,
  do_not_disturb_active: false,
  do_not_disturb_until: null,
  do_not_disturb_period_name: null,
})

const desktopCompanion = reactive({
  connected: false,
  last_seen_at: null,
})

const doNotDisturb = reactive({
  periods: [],
})

const settingsLoaded = ref(false)
const saving = ref(false)
const savingDoNotDisturb = ref(false)
const error = ref('')
const audioContext = ref(null)
const oscillator = ref(null)
const gainNode = ref(null)
const titleTimer = ref(null)
const pollTimer = ref(null)
const activeAlertEffectId = ref(null)

const statusLabel = computed(() => {
  if (timer.status === 'running') return '下一次提醒'
  if (timer.status === 'alerting') return '需要休息'
  if (timer.status === 'resting') return '休息中'
  if (timer.status === 'paused') return '已暂停'
  return '未启动'
})

const primaryActionLabel = computed(() => (timer.status === 'paused' ? '继续' : '启动'))
const restDurationMax = computed(() => (settings.rest_duration_unit === 'seconds' ? 3600 : 60))
const desktopCompanionLabel = computed(() => (desktopCompanion.connected ? '已连接' : '未连接'))
const doNotDisturbLabel = computed(() => {
  if (!timer.do_not_disturb_active) return ''
  return timer.do_not_disturb_period_name ? `请勿打扰中：${timer.do_not_disturb_period_name}` : '请勿打扰中'
})
const displayTotalSeconds = computed(() => timer.total_seconds || settings.reminder_interval_minutes * 60)
const displayRemainingSeconds = computed(() => {
  if (timer.status === 'idle') return settings.reminder_interval_minutes * 60
  return timer.remaining_seconds
})

const formattedRemaining = computed(() => {
  const minutes = Math.floor(displayRemainingSeconds.value / 60)
  const seconds = displayRemainingSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

const progressPercent = computed(() => {
  if (timer.status === 'idle') return 0
  if (!displayTotalSeconds.value) return 0
  return Math.max(0, Math.min(100, 100 - (displayRemainingSeconds.value / displayTotalSeconds.value) * 100))
})

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
  await loadDoNotDisturbSettings()
  await fetchTimerState()
  await fetchDesktopCompanionStatus()
  startPollingTimer()
})

onBeforeUnmount(() => {
  stopPollingTimer()
  stopAlertEffects()
})

async function loadSettings() {
  try {
    const response = await fetch('/api/settings')
    if (!response.ok) throw new Error('读取配置失败')
    Object.assign(settings, await response.json())
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
    await fetchTimerState()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function loadDoNotDisturbSettings() {
  try {
    const response = await fetch('/api/do-not-disturb')
    if (!response.ok) throw new Error('读取请勿打扰设置失败')
    const data = await response.json()
    doNotDisturb.periods = data.periods
  } catch (err) {
    error.value = err.message
  }
}

async function saveDoNotDisturbSettings() {
  savingDoNotDisturb.value = true
  error.value = ''
  try {
    const response = await fetch('/api/do-not-disturb', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        periods: doNotDisturb.periods.map(({ name, start_time, end_time, enabled }) => ({
          name,
          start_time,
          end_time,
          enabled,
        })),
      }),
    })
    if (!response.ok) throw new Error('保存请勿打扰设置失败')
    const data = await response.json()
    doNotDisturb.periods = data.periods
    await fetchTimerState()
  } catch (err) {
    error.value = err.message
  } finally {
    savingDoNotDisturb.value = false
  }
}

function addDoNotDisturbPeriod() {
  doNotDisturb.periods.push({
    name: '请勿打扰',
    start_time: '12:00',
    end_time: '13:00',
    enabled: true,
  })
}

function removeDoNotDisturbPeriod(index) {
  doNotDisturb.periods.splice(index, 1)
}

function startPollingTimer() {
  stopPollingTimer()
  pollTimer.value = window.setInterval(fetchTimerState, 1000)
}

function stopPollingTimer() {
  if (pollTimer.value) {
    window.clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function fetchTimerState() {
  try {
    const response = await fetch('/api/timer')
    if (!response.ok) throw new Error('读取计时状态失败')
    applyTimerState(await response.json())
    await fetchDesktopCompanionStatus()
  } catch (err) {
    error.value = err.message
  }
}

async function fetchDesktopCompanionStatus() {
  try {
    const response = await fetch('/api/desktop-companion/status')
    if (!response.ok) throw new Error('读取桌面伴侣状态失败')
    Object.assign(desktopCompanion, await response.json())
  } catch {
    desktopCompanion.connected = false
    desktopCompanion.last_seen_at = null
  }
}

function applyTimerState(nextTimer) {
  Object.assign(timer, nextTimer)
  syncAlertEffects()
}

function syncAlertEffects() {
  const alertKey = timer.active_desktop_alert_id || 'web-alert'
  if (timer.status === 'alerting') {
    if (activeAlertEffectId.value !== alertKey) {
      activeAlertEffectId.value = alertKey
      startAlertEffects()
      sendNotification('该休息眼睛了', '离开屏幕，看看远处，让眼睛缓一缓。')
    }
    return
  }

  if (activeAlertEffectId.value !== null) {
    activeAlertEffectId.value = null
    stopAlertEffects()
  }
}

async function runTimerAction(action) {
  error.value = ''
  try {
    if (action === 'start' || action === 'resume') {
      await unlockAudio()
      await requestNotificationPermission()
    }
    const response = await fetch(`/api/timer/${action}`, { method: 'POST' })
    if (!response.ok) throw new Error('计时操作失败')
    applyTimerState(await response.json())
  } catch (err) {
    error.value = err.message
  }
}

function startTimer() {
  runTimerAction(timer.status === 'paused' ? 'resume' : 'start')
}

function pauseTimer() {
  runTimerAction('pause')
}

function resetTimer() {
  runTimerAction('reset')
}

function startRest() {
  runTimerAction('start-rest')
}

function snooze() {
  runTimerAction('snooze')
}

function skipReminder() {
  runTimerAction('skip')
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
          :disabled="!settingsLoaded || timer.status === 'running' || timer.status === 'resting' || timer.status === 'alerting'"
          @click="startTimer"
        >
          {{ primaryActionLabel }}
        </button>
        <button
          type="button"
          :disabled="timer.status !== 'running' && timer.status !== 'resting' && timer.status !== 'alerting'"
          @click="pauseTimer"
        >
          暂停
        </button>
        <button type="button" @click="resetTimer">重置</button>
      </div>
    </section>

    <section class="settings-panel" aria-label="提醒设置">
      <div class="companion-status" :class="{ connected: desktopCompanion.connected }">
        <span class="status-dot" aria-hidden="true"></span>
        <span>桌面伴侣：{{ desktopCompanionLabel }}</span>
      </div>

      <div v-if="timer.do_not_disturb_active" class="dnd-active">
        {{ doNotDisturbLabel }}
      </div>

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

      <div class="dnd-panel">
        <div class="section-heading">
          <h2>请勿打扰时段</h2>
          <button type="button" @click="addDoNotDisturbPeriod">新增时段</button>
        </div>

        <p v-if="doNotDisturb.periods.length === 0" class="muted">暂无请勿打扰时段。</p>

        <div v-for="(period, index) in doNotDisturb.periods" :key="period.id || index" class="dnd-row">
          <label>
            <span>名称</span>
            <input v-model.trim="period.name" maxlength="40" type="text" />
          </label>
          <label>
            <span>开始</span>
            <input v-model="period.start_time" type="time" />
          </label>
          <label>
            <span>结束</span>
            <input v-model="period.end_time" type="time" />
          </label>
          <label class="toggle dnd-toggle">
            <input v-model="period.enabled" type="checkbox" />
            <span>启用</span>
          </label>
          <button type="button" @click="removeDoNotDisturbPeriod(index)">删除</button>
        </div>

        <div class="save-row">
          <button type="button" :disabled="savingDoNotDisturb" @click="saveDoNotDisturbSettings">
            {{ savingDoNotDisturb ? '保存中' : '保存请勿打扰' }}
          </button>
        </div>
      </div>
    </section>

    <div v-if="timer.status === 'alerting'" class="alert-overlay" role="dialog" aria-modal="true" aria-labelledby="alert-title">
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
