<script setup>
import { ref, onMounted, computed } from 'vue'

// Dynamic server configuration from Vite environment variables with automatic fallback
const getApiBase = () => {
  if (import.meta.env.VITE_API_BASE !== undefined && import.meta.env.VITE_API_BASE !== '') {
    return import.meta.env.VITE_API_BASE
  }
  // If running in browser and served from the same host (e.g. Cloud Run), use relative path
  if (typeof window !== 'undefined' && window.location.port !== '5173') {
    return window.location.origin
  }
  return 'http://localhost:8000'
}

const getWsBase = () => {
  if (import.meta.env.VITE_WS_BASE !== undefined && import.meta.env.VITE_WS_BASE !== '') {
    return import.meta.env.VITE_WS_BASE
  }
  if (typeof window !== 'undefined' && window.location.port !== '5173') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}`
  }
  return 'ws://localhost:8000'
}

const API_BASE = getApiBase()
const WS_BASE = getWsBase()


// --- Navigation & Views ---
const currentTab = ref('home') // 'home' | 'sessions' | 'detail' | 'lobby' | 'game'

// --- Sessions State ---
const sessions = ref([])
const activeSession = ref(null)
const isLoading = ref(false)
const statusMessage = ref('')

// --- Rename Session Modal State ---
const showRenameModal = ref(false)
const renameSessionId = ref('')
const renameSessionTitle = ref('')
const renameSessionDesc = ref('')
const isRenaming = ref(false)

// --- Create Session Modal/Inputs ---
const newSessionTitle = ref('')
const newSessionDesc = ref('')
const showCreateModal = ref(false)

// --- File Upload State ---
const selectedFile = ref(null)
const uploadProgress = ref(false)

// --- Global Blocking Loading Overlay State ---
const overlayLoadingTitle = ref('')
const overlayLoadingSubtitle = ref('')
const isOverlayLoading = computed(() => {
  return uploadProgress.value || isGeneratingQuiz.value || (isLoading.value && showCreateModal.value)
})

// --- Quiz Generation State ---
const selectedDifficulty = ref('medium')
const isGeneratingQuiz = ref(false)

// --- Multiplayer State ---
const username = ref('Player_' + Math.floor(1000 + Math.random() * 9000))
const roomCodeInput = ref('')
const activeRoom = ref(null)
const isHost = ref(false)
const socket = ref(null)

// Game Round State
const gameStatus = ref('waiting') // waiting | question_active | question_result | finished
const currentQuestion = ref(null)
const selectedOption = ref(null)
const answerResult = ref(null)
const correctOptionIndex = ref(null)
const explanationText = ref('')
const leaderboard = ref([])
const playersList = ref([])
const winnerData = ref(null)
const timeLeft = ref(15)
let timerInterval = null

// --- User Authentication State (Firestore User Management) ---
const currentUser = ref(null)
const showAuthModal = ref(false)
const authMode = ref('login') // 'login' | 'register'
const authIdentifier = ref('') // username or email for login
const authUsername = ref('')   // username for register
const authEmail = ref('')      // email for register
const authPassword = ref('')
const authDisplayName = ref('')
const authError = ref('')
const isAuthSubmitting = ref(false)
const googleClientId = ref('') // optional custom OAuth client ID
const showGooglePrompt = ref(false)

// Load user from localStorage if saved
try {
  const savedUser = localStorage.getItem('sessioniq_user')
  if (savedUser) {
    currentUser.value = JSON.parse(savedUser)
  }
} catch (e) {
  console.warn('Failed reading user from storage', e)
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' }
  if (currentUser.value && currentUser.value.token) {
    headers['Authorization'] = `Bearer ${currentUser.value.token}`
  }
  return headers
}

async function handleAuthSubmit() {
  authError.value = ''
  isAuthSubmitting.value = true

  try {
    if (authMode.value === 'register') {
      if (!authUsername.value.trim() && !authEmail.value.trim()) {
        throw new Error('Please enter a username or email address')
      }
      if (!authPassword.value || authPassword.value.length < 6) {
        throw new Error('Password must be at least 6 characters')
      }

      const payload = {
        username: authUsername.value.trim() || undefined,
        email: authEmail.value.trim() || undefined,
        password: authPassword.value,
        display_name: authDisplayName.value.trim() || undefined
      }

      const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed')
      }
      currentUser.value = data.user
      localStorage.setItem('sessioniq_user', JSON.stringify(data.user))
      username.value = data.user.display_name || data.user.username || data.user.email.split('@')[0]
      showAuthModal.value = false
      statusMessage.value = `Welcome, ${username.value}! Your account is registered.`
    } else {
      // Login mode
      if (!authIdentifier.value.trim() || !authPassword.value) {
        throw new Error('Please enter your username/email and password')
      }

      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: authIdentifier.value.trim(),
          password: authPassword.value
        })
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Invalid username/email or password')
      }
      currentUser.value = data.user
      localStorage.setItem('sessioniq_user', JSON.stringify(data.user))
      username.value = data.user.display_name || data.user.username || data.user.email.split('@')[0]
      showAuthModal.value = false
      statusMessage.value = `Welcome back, ${username.value}!`
    }
  } catch (err) {
    authError.value = err.message
  } finally {
    isAuthSubmitting.value = false
  }
}

// Google Sign-In with Google Identity Services (One-Tap / GSI button) or Direct Google Login
async function handleGoogleLoginSuccess(response) {
  authError.value = ''
  isAuthSubmitting.value = true
  try {
    const res = await fetch(`${API_BASE}/api/auth/google`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: response.credential })
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Google authentication failed')
    }
    currentUser.value = data.user
    localStorage.setItem('sessioniq_user', JSON.stringify(data.user))
    username.value = data.user.display_name || data.user.username || data.user.email.split('@')[0]
    showAuthModal.value = false
    statusMessage.value = `Signed in with Google as ${username.value}!`
  } catch (err) {
    authError.value = err.message
  } finally {
    isAuthSubmitting.value = false
  }
}

// Fallback Quick Google Sign-In prompt (allows entering Google email if client ID not configured)
async function handleQuickGoogleSignIn() {
  const userGoogleEmail = prompt('Enter your Google Account email:')
  if (!userGoogleEmail || !userGoogleEmail.includes('@')) return

  authError.value = ''
  isAuthSubmitting.value = true
  try {
    const res = await fetch(`${API_BASE}/api/auth/google`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: userGoogleEmail.trim(),
        name: userGoogleEmail.split('@')[0].replace('.', ' ').toUpperCase()
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Google sign-in failed')
    currentUser.value = data.user
    localStorage.setItem('sessioniq_user', JSON.stringify(data.user))
    username.value = data.user.display_name || data.user.username || data.user.email.split('@')[0]
    showAuthModal.value = false
    statusMessage.value = `Signed in with Google as ${username.value}!`
  } catch (err) {
    authError.value = err.message
  } finally {
    isAuthSubmitting.value = false
  }
}

function initGoogleSignIn() {
  if (window.google && window.google.accounts && window.google.accounts.id) {
    // If user or app provides a client id or default
    const cid = googleClientId.value || '1029384756-sessioniq.apps.googleusercontent.com'
    try {
      window.google.accounts.id.initialize({
        client_id: cid,
        callback: handleGoogleLoginSuccess,
        auto_select: false,
      })
      const btnContainer = document.getElementById('gsi-button-container')
      if (btnContainer) {
        window.google.accounts.id.renderButton(btnContainer, {
          theme: 'outline',
          size: 'large',
          width: 320,
          text: 'signin_with',
          shape: 'rectangular',
        })
      }
    } catch (e) {
      console.warn('GSI init note:', e)
    }
  }
}

watch(showAuthModal, (val) => {
  if (val) {
    setTimeout(() => {
      initGoogleSignIn()
    }, 200)
  }
})

function logoutUser() {
  currentUser.value = null
  localStorage.removeItem('sessioniq_user')
  statusMessage.value = 'Logged out. You are now playing as a guest.'
}

const isSessionOwner = computed(() => {
  if (!activeSession.value) return false
  // If session has no owner_id, allow current user or host
  if (!activeSession.value.owner_id) return true
  return currentUser.value && currentUser.value.user_id === activeSession.value.owner_id
})

// Filter sessions owned by current logged-in user
const myOwnedSessions = computed(() => {
  if (!currentUser.value) return []
  return sessions.value.filter(s => s.owner_id === currentUser.value.user_id)
})

function openRenameModal(session) {
  renameSessionId.value = session.session_id
  renameSessionTitle.value = session.title || ''
  renameSessionDesc.value = session.description || ''
  showRenameModal.value = true
}

async function submitRenameSession() {
  if (!renameSessionTitle.value.trim() || !renameSessionId.value) return
  isRenaming.value = true
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${renameSessionId.value}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        title: renameSessionTitle.value.trim(),
        description: renameSessionDesc.value.trim()
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to rename session')
    
    // Update local list
    const idx = sessions.value.findIndex(s => s.session_id === renameSessionId.value)
    if (idx !== -1 && data.session) {
      sessions.value[idx] = { ...sessions.value[idx], ...data.session }
    }
    if (activeSession.value && activeSession.value.session_id === renameSessionId.value) {
      activeSession.value.title = data.session.title
      activeSession.value.description = data.session.description
    }
    showRenameModal.value = false
    statusMessage.value = `Session "${data.session.title}" renamed successfully!`
  } catch (err) {
    statusMessage.value = 'Rename failed: ' + err.message
  } finally {
    isRenaming.value = false
  }
}

async function deleteSession(sessionId, sessionTitle) {
  const confirmMsg = `Are you sure you want to delete session "${sessionTitle || sessionId}"? All uploaded materials and quizzes will be permanently deleted.`
  if (!confirm(confirmMsg)) return

  isLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to delete session')

    // Remove from local list
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    if (activeSession.value && activeSession.value.session_id === sessionId) {
      activeSession.value = null
      currentTab.value = 'sessions'
    }
    statusMessage.value = `Session "${sessionTitle || sessionId}" was deleted.`
  } catch (err) {
    statusMessage.value = 'Delete failed: ' + err.message
  } finally {
    isLoading.value = false
  }
}

// --- API Calls ---
async function fetchSessions() {
  isLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/sessions`)
    const data = await res.json()
    sessions.value = data.sessions || []
  } catch (e) {
    statusMessage.value = 'Failed to load sessions: ' + e.message
  } finally {
    isLoading.value = false
  }
}

async function createNewSession() {
  if (!newSessionTitle.value.trim()) return
  if (!currentUser.value) {
    showAuthModal.value = true
    authError.value = 'Please sign in or register to create a new session as its owner.'
    return
  }
  isLoading.value = true
  overlayLoadingTitle.value = 'Creating New Session...'
  overlayLoadingSubtitle.value = 'Initializing session document in Google Cloud Firestore...'
  try {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        title: newSessionTitle.value,
        description: newSessionDesc.value
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to create session')
    newSessionTitle.value = ''
    newSessionDesc.value = ''
    showCreateModal.value = false
    await fetchSessions()
    viewSessionDetail(data.session_id)
  } catch (e) {
    statusMessage.value = 'Error creating session: ' + e.message
  } finally {
    isLoading.value = false
  }
}

async function viewSessionDetail(sessionId) {
  isLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`)
    activeSession.value = await res.json()
    currentTab.value = 'detail'
  } catch (e) {
    statusMessage.value = 'Failed to load session details: ' + e.message
  } finally {
    isLoading.value = false
  }
}

function onFileSelected(event) {
  selectedFile.value = event.target.files[0]
}

async function uploadMaterial() {
  if (!selectedFile.value || !activeSession.value) return
  if (!isSessionOwner.value) {
    statusMessage.value = 'Permission denied: Only the session owner can upload source materials.'
    return
  }
  uploadProgress.value = true
  overlayLoadingTitle.value = 'Uploading Material...'
  overlayLoadingSubtitle.value = `Streaming "${selectedFile.value.name}" to Cloud Storage & registering in Firestore...`
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('category', 'input_materials')

    const uploadHeaders = {}
    if (currentUser.value && currentUser.value.token) {
      uploadHeaders['Authorization'] = `Bearer ${currentUser.value.token}`
    }

    const res = await fetch(`${API_BASE}/api/sessions/${activeSession.value.session_id}/upload`, {
      method: 'POST',
      headers: uploadHeaders,
      body: formData
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Upload failed')
    statusMessage.value = `Uploaded "${data.file_name}" to GCS successfully!`
    selectedFile.value = null
    await viewSessionDetail(activeSession.value.session_id)
  } catch (e) {
    statusMessage.value = 'Upload failed: ' + e.message
  } finally {
    uploadProgress.value = false
  }
}

async function triggerQuizGeneration(difficulty) {
  if (!activeSession.value) return
  if (!isSessionOwner.value) {
    statusMessage.value = 'Permission denied: Only the session owner can build or generate quizzes.'
    return
  }
  selectedDifficulty.value = difficulty
  isGeneratingQuiz.value = true
  overlayLoadingTitle.value = `Building ${difficulty.toUpperCase()} Quiz...`
  overlayLoadingSubtitle.value = 'Gemini 2.5 Flash agents are reading materials, analyzing concepts, and structuring questions...'
  statusMessage.value = `Agents are analyzing materials and generating ${difficulty} quiz...`
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${activeSession.value.session_id}/generate-quiz`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        session_id: activeSession.value.session_id,
        difficulty: difficulty,
        num_questions: 4
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Quiz generation failed')
    statusMessage.value = `Quiz successfully created and saved to Firestore!`
    await viewSessionDetail(activeSession.value.session_id)
  } catch (e) {
    statusMessage.value = 'Quiz generation error: ' + e.message
  } finally {
    isGeneratingQuiz.value = false
  }
}

// --- Multiplayer Game Flow ---
async function hostMultiplayerLobby(difficulty) {
  if (!activeSession.value) return
  if (!isSessionOwner.value) {
    statusMessage.value = 'Permission denied: Only the session owner can host a multiplayer room for this session.'
    return
  }
  try {
    const res = await fetch(`${API_BASE}/api/rooms`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        session_id: activeSession.value.session_id,
        difficulty: difficulty
      })
    })
    const room = await res.json()
    if (!res.ok) throw new Error(room.detail || 'Failed to create room')
    activeRoom.value = room
    isHost.value = true
    connectToRoomSocket(room.room_code)
  } catch (e) {
    statusMessage.value = 'Failed to create room: ' + e.message
  }
}

function joinMultiplayerByCode() {
  if (!roomCodeInput.value.trim()) return
  const code = roomCodeInput.value.trim().toUpperCase()
  isHost.value = false
  connectToRoomSocket(code)
}

function connectToRoomSocket(roomCode) {
  if (socket.value) socket.value.close()
  const ws = new WebSocket(`${WS_BASE}/ws/quiz/${roomCode}`)

  ws.onopen = () => {
    ws.send(JSON.stringify({
      username: username.value,
      is_host: isHost.value,
      auth_token: currentUser.value ? currentUser.value.token : null,
    }))
    currentTab.value = 'lobby'
  }

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    handleSocketMessage(msg)
  }

  ws.onclose = () => {
    statusMessage.value = 'Disconnected from room.'
  }

  socket.value = ws
}

function handleSocketMessage(msg) {
  switch (msg.type) {
    case 'joined':
      activeRoom.value = msg
      gameStatus.value = msg.status || 'waiting'
      break
    case 'player_list_updated':
    case 'player_left':
      playersList.value = msg.players || []
      leaderboard.value = msg.leaderboard || []
      break
    case 'new_question':
      currentTab.value = 'game'
      gameStatus.value = 'question_active'
      currentQuestion.value = msg.question
      selectedOption.value = null
      answerResult.value = null
      correctOptionIndex.value = null
      startQuestionTimer(msg.question.duration || 15)
      break
    case 'answer_acknowledged':
      answerResult.value = msg.result
      break
    case 'question_ended':
      clearInterval(timerInterval)
      gameStatus.value = 'question_result'
      correctOptionIndex.value = msg.correct_option_index
      explanationText.value = msg.explanation
      leaderboard.value = msg.leaderboard || []
      break
    case 'game_over':
      clearInterval(timerInterval)
      gameStatus.value = 'finished'
      leaderboard.value = msg.leaderboard || []
      winnerData.value = msg.winner
      break
  }
}

function startQuestionTimer(duration) {
  clearInterval(timerInterval)
  timeLeft.value = duration
  timerInterval = setInterval(() => {
    if (timeLeft.value > 0) {
      timeLeft.value -= 1
    } else {
      clearInterval(timerInterval)
    }
  }, 1000)
}

function sendAnswer(optionIndex) {
  if (selectedOption.value !== null || gameStatus.value !== 'question_active') return
  selectedOption.value = optionIndex
  socket.value.send(JSON.stringify({
    action: 'submit_answer',
    option_index: optionIndex
  }))
}

function startGameAsHost() {
  if (!isHost.value || !socket.value) return
  socket.value.send(JSON.stringify({
    action: 'start_game'
  }))
}

onMounted(() => {
  fetchSessions()
})
</script>

<template>
  <div class="app-container">
    <!-- Header -->
    <header class="header neo-box-static">
      <div class="header-inner">
        <div class="brand">
          <span class="brand-badge">TRACK 3</span>
          <h1 class="logo-title">Session<span class="highlight">IQ</span></h1>
        </div>
        <div class="header-nav">
          <button @click="currentTab = 'home'" class="neo-btn" :class="{ 'yellow': currentTab === 'home' }">
            🏠 Home
          </button>
          <button @click="currentTab = 'sessions'" class="neo-btn" :class="{ 'pink': currentTab === 'sessions' }">
            ⚡ All Sessions
          </button>

          <!-- User Management & Auth Widget -->
          <div v-if="currentUser" class="user-profile-badge neo-box-static">
            <span class="user-role-tag">👑 OWNER</span>
            <span class="user-name">{{ currentUser.display_name || currentUser.email }}</span>
            <button @click="logoutUser" class="neo-btn-sm logout-btn">Logout</button>
          </div>
          <div v-else class="auth-guest-box">
            <button @click="showAuthModal = true; authMode = 'login'" class="neo-btn yellow">
              🔑 Sign In
            </button>
            <button @click="showAuthModal = true; authMode = 'register'" class="neo-btn cyan">
              Register
            </button>
          </div>

          <div class="player-tag">
            <span class="label">PLAYER:</span>
            <input v-model="username" class="username-input" />
          </div>
        </div>
      </div>
    </header>

    <!-- Global Alert Bar -->
    <div v-if="statusMessage" class="status-banner neo-box-static">
      <span>📢 {{ statusMessage }}</span>
      <button @click="statusMessage = ''" class="close-btn">✖</button>
    </div>

    <!-- MAIN VIEWS -->
    <main class="main-content">
      <!-- 0. HOME VIEW: PROMOTION, FEATURES & LOGGED-IN OWNER SESSIONS -->
      <section v-if="currentTab === 'home'" class="view-home">
        <!-- Hero Promotional Banner -->
        <div class="home-hero neo-box-static">
          <div class="hero-content">
            <div class="hero-tags">
              <span class="neo-badge yellow">GEMINI 2.5 FLASH</span>
              <span class="neo-badge cyan">VERTEX AI AGENTS</span>
              <span class="neo-badge green">FIRESTORE REAL-TIME</span>
            </div>
            <h1 class="hero-heading">Transform Any Talk, Video or Doc into a <span class="highlight">Live Multiplayer Arena</span></h1>
            <p class="hero-subheading">
              <strong>SessionIQ</strong> is the ultimate agentic learning platform. Upload your session recordings, transcripts, or notes, and our Vertex AI Agent coordinate sub-agents to synthesize knowledge, construct rich multi-level quizzes, and host live multiplayer competitions.
            </p>
            <div class="hero-cta-group">
              <button
                v-if="!currentUser"
                @click="showAuthModal = true; authMode = 'login'"
                class="neo-btn yellow hero-btn"
              >
                🔑 Sign In / Register to Host
              </button>
              <button
                v-else
                @click="showCreateModal = true"
                class="neo-btn cyan hero-btn"
              >
                ⚡ + Create New Session
              </button>
              <button @click="currentTab = 'sessions'" class="neo-btn white hero-btn">
                Browse Public Sessions ➔
              </button>
            </div>
          </div>
          <div class="hero-card-side neo-box">
            <div class="arena-preview-header">
              <span class="dot red"></span>
              <span class="dot yellow"></span>
              <span class="dot green"></span>
              <span class="arena-title">LIVE MULTIPLAYER ENGINE</span>
            </div>
            <div class="arena-preview-body">
              <div class="stat-row">
                <span class="stat-label">⚡ AI Generation:</span>
                <span class="stat-val">Sub-second Flash</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">🔒 Firestore Auth:</span>
                <span class="stat-val">Role-Based Security</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">🏆 Arena Sync:</span>
                <span class="stat-val">WebSocket Real-Time</span>
              </div>
              <div class="join-quick-box mt-3">
                <input v-model="roomCodeInput" placeholder="ENTER 4-DIGIT PIN" class="code-input full-width mb-2" />
                <button @click="joinMultiplayerByCode" class="neo-btn green full-width">Join Live Battle</button>
              </div>
            </div>
          </div>
        </div>

        <!-- LOGGED-IN OWNER SESSIONS DASHBOARD -->
        <div v-if="currentUser" class="owner-dashboard-section mt-5">
          <div class="section-title-bar">
            <div>
              <h2 class="section-title">👑 Your Owned Sessions</h2>
              <p class="section-subtitle">You are logged in as <strong>{{ currentUser.display_name || currentUser.username || currentUser.email }}</strong>. Manage, rename, or delete your sessions below.</p>
            </div>
            <button @click="showCreateModal = true" class="neo-btn cyan">+ Create Session</button>
          </div>

          <div v-if="myOwnedSessions.length === 0" class="empty-owner-box neo-box-static">
            <p>You haven't created any sessions yet! Click "+ Create Session" to upload materials and build AI quizzes.</p>
            <button @click="showCreateModal = true" class="neo-btn yellow mt-3">Launch Your First Session</button>
          </div>

          <div v-else class="sessions-grid mt-4">
            <div v-for="s in myOwnedSessions" :key="s.session_id" class="session-card owner-card neo-box">
              <div class="owner-card-top">
                <span class="neo-badge green">👑 OWNED BY YOU</span>
                <span class="card-tag">ID: {{ s.session_id }}</span>
              </div>
              <h3 class="card-title">{{ s.title || 'Untitled Session' }}</h3>
              <p class="card-desc">{{ s.summary || s.description || 'Raw input session ready for AI breakdown.' }}</p>

              <div class="card-footer owner-actions-footer">
                <button @click="viewSessionDetail(s.session_id)" class="neo-btn yellow btn-compact">
                  Inspect ➔
                </button>
                <div class="btn-group-right">
                  <button @click="openRenameModal(s)" class="neo-btn cyan btn-compact" title="Rename Session">
                    ✏️ Rename
                  </button>
                  <button @click="deleteSession(s.session_id, s.title)" class="neo-btn pink btn-compact" title="Delete Session">
                    🗑️ Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- PROMOTIONAL FEATURES GRID -->
        <div class="features-section mt-5">
          <h2 class="section-title text-center">Engineered for Interactive Learning & Retention</h2>
          <p class="section-subtitle text-center">SessionIQ combines Google Cloud Vertex AI, GCS Storage, and real-time Firestore synchronization.</p>

          <div class="features-grid mt-4">
            <div class="feature-card neo-box">
              <div class="feature-icon">🤖</div>
              <h3 class="feature-title">Vertex AI Quiz Agents</h3>
              <p class="feature-desc">Analyzes conference talks, webinars, and study materials with Gemini 2.5 Flash to automatically extract topics and build rigorous 4-choice questions.</p>
            </div>

            <div class="feature-card neo-box">
              <div class="feature-icon">⚡</div>
              <h3 class="feature-title">Real-Time Multiplayer</h3>
              <p class="feature-desc">Host high-energy live trivia battles with 4-letter room codes. Instant answer scoring, live streaks, countdown timers, and live leaderboards.</p>
            </div>

            <div class="feature-card neo-box">
              <div class="feature-icon">🔒</div>
              <h3 class="feature-title">Firestore User Management</h3>
              <p class="feature-desc">Secure account creation with username/password or Google Sign-In. Full role-based authorization: only session owners can upload media and generate tests.</p>
            </div>

            <div class="feature-card neo-box">
              <div class="feature-icon">📦</div>
              <h3 class="feature-title">Enterprise Cloud Storage</h3>
              <p class="feature-desc">Isolated per-session source buckets on Google Cloud Storage for audio, video, transcripts, and presentation decks.</p>
            </div>
          </div>
        </div>
      </section>

      <!-- 1. SESSIONS CATALOG VIEW -->
      <section v-if="currentTab === 'sessions'" class="view-sessions">
        <div class="sessions-header">
          <div>
            <h2 class="section-title">Recorded & Live Sessions</h2>
            <p class="section-subtitle">Select a session to view transcripts, generate AI quizzes, or launch trivia battles.</p>
          </div>
          <div class="actions-group">
            <button @click="showCreateModal = true" class="neo-btn cyan">+ New Session</button>
            <div class="join-lobby-box neo-box-static">
              <input v-model="roomCodeInput" placeholder="ROOM CODE" class="code-input" />
              <button @click="joinMultiplayerByCode" class="neo-btn green">Join</button>
            </div>
          </div>
        </div>

        <div v-if="isLoading" class="loading-state neo-box-static">
          <h3>⚡ Loading from Firestore...</h3>
        </div>

        <div v-else class="sessions-grid">
          <div v-for="s in sessions" :key="s.session_id" class="session-card neo-box">
            <div class="card-tag">ID: {{ s.session_id }}</div>
            <h3 class="card-title">{{ s.title || 'Untitled Session' }}</h3>
            <p class="card-desc">{{ s.summary || s.description || 'Raw input session ready for AI breakdown.' }}</p>

            <div class="card-topics" v-if="s.topics && s.topics.length">
              <span v-for="t in s.topics" :key="t" class="neo-badge">{{ t }}</span>
            </div>

            <div class="card-footer">
              <span class="badge-status" :class="s.has_materials ? 'ready' : ''">
                {{ s.has_materials ? '📂 Assets in GCS' : '📝 Pending Media' }}
              </span>
              <button @click="viewSessionDetail(s.session_id)" class="neo-btn yellow">
                Inspect ➔
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. SESSION DETAIL VIEW -->
      <section v-if="currentTab === 'detail' && activeSession" class="view-detail">
        <div class="back-nav">
          <button @click="currentTab = 'sessions'" class="neo-btn">⬅ Back to Catalog</button>
          <span class="session-id-pill">Session: {{ activeSession.session_id }}</span>
        </div>

        <div class="detail-hero neo-box-static">
          <div class="hero-header">
            <div>
              <h2>{{ activeSession.title || 'Session Details' }}</h2>
              <div class="session-owner-tag mt-1">
                <span v-if="activeSession.owner_name" class="owner-pill">
                  👤 Session Owner: <strong>{{ activeSession.owner_name }}</strong>
                </span>
                <span v-if="isSessionOwner" class="neo-badge green ml-2">YOU ARE OWNER</span>
                <span v-else class="neo-badge pink ml-2">VIEWER / GUEST MODE</span>
              </div>
            </div>
            <div class="hero-header-actions">
              <template v-if="isSessionOwner">
                <button @click="openRenameModal(activeSession)" class="neo-btn cyan btn-compact">
                  ✏️ Rename
                </button>
                <button @click="deleteSession(activeSession.session_id, activeSession.title)" class="neo-btn pink btn-compact">
                  🗑️ Delete
                </button>
              </template>
              <span class="neo-badge green">Firestore Synced</span>
            </div>
          </div>
          <p class="hero-desc">{{ activeSession.summary || activeSession.description || 'Manage materials and quiz generators for this session.' }}</p>
        </div>

        <div class="detail-split">
          <!-- Left: Input Materials & GCS Upload -->
          <div class="split-col neo-box-static">
            <div class="col-title-bar">
              <h3 class="panel-title">🗂️ Input Source Files (GCS Bucket)</h3>
              <span v-if="!isSessionOwner" class="owner-lock-badge">🔒 Owner Only</span>
            </div>
            <p class="panel-desc">Raw video/audio transcripts and session notes stored in <code>sessions/{{ activeSession.session_id }}/input_materials/</code></p>

            <div v-if="isSessionOwner" class="upload-zone neo-box">
              <input type="file" @change="onFileSelected" />
              <button @click="uploadMaterial" :disabled="!selectedFile || uploadProgress" class="neo-btn cyan">
                {{ uploadProgress ? 'Uploading...' : 'Upload to Cloud Storage' }}
              </button>
            </div>
            <div v-else class="owner-restricted-box neo-box">
              <span>🔒 Only the session owner can upload additional training or transcript materials.</span>
            </div>

            <div class="files-list">
              <h4>Archived Assets:</h4>
              <div v-if="!activeSession.files || !activeSession.files.length" class="empty-files">
                No input materials uploaded yet.
              </div>
              <ul v-else class="file-items">
                <li v-for="f in activeSession.files" :key="f.name" class="file-item">
                  <span class="file-name">📄 {{ f.name }}</span>
                  <span class="file-size">{{ Math.round(f.size_bytes / 1024) }} KB</span>
                </li>
              </ul>
            </div>
          </div>

          <!-- Right: Quiz Generators & Available Difficulties -->
          <div class="split-col neo-box-static">
            <div class="col-title-bar">
              <h3 class="panel-title">🎯 AI Quiz Engine (Firestore DB)</h3>
              <span v-if="!isSessionOwner" class="owner-lock-badge">🔒 Owner Only</span>
            </div>
            <p class="panel-desc">Trigger multi-agents to extract concepts and store schemas directly in Firestore.</p>

            <div v-if="isSessionOwner" class="quiz-gen-actions">
              <span class="gen-label">Generate By Difficulty:</span>
              <div class="btn-group">
                <button @click="triggerQuizGeneration('simple')" :disabled="isGeneratingQuiz" class="neo-btn green">
                  🟢 Simple
                </button>
                <button @click="triggerQuizGeneration('medium')" :disabled="isGeneratingQuiz" class="neo-btn yellow">
                  🟡 Medium
                </button>
                <button @click="triggerQuizGeneration('hard')" :disabled="isGeneratingQuiz" class="neo-btn pink">
                  🔴 Hard
                </button>
              </div>
            </div>
            <div v-else class="owner-restricted-box neo-box">
              <span>🔒 Only the session owner can generate or modify quizzes for this session.</span>
            </div>

            <div v-if="isGeneratingQuiz" class="generating-box neo-box">
              <h4>🤖 Agents Collaborating...</h4>
              <p>Extracting topics, composing questions, and writing to Firestore...</p>
            </div>

            <!-- Existing Quizzes -->
            <div class="available-quizzes">
              <h4>Ready-to-Play Quizzes:</h4>
              <div v-if="!activeSession.quizzes || !Object.keys(activeSession.quizzes).length" class="empty-quizzes">
                No quizzes generated yet.
              </div>

              <div v-for="(quiz, diff) in activeSession.quizzes" :key="diff" class="quiz-item neo-box">
                <div class="quiz-item-header">
                  <span class="neo-badge" :class="diff">{{ diff.toUpperCase() }}</span>
                  <span class="q-count">{{ (quiz.questions || []).length }} Questions</span>
                </div>
                <h5>{{ quiz.title }}</h5>
                <p>{{ quiz.summary }}</p>
                <button v-if="isSessionOwner" @click="hostMultiplayerLobby(diff)" class="neo-btn purple">
                  🎮 Host Live Multiplayer
                </button>
                <div v-else class="guest-info-badge neo-badge yellow">
                  🎮 Available for multiplayer when launched by session owner!
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 3. MULTIPLAYER LOBBY VIEW -->
      <section v-if="currentTab === 'lobby' && activeRoom" class="view-lobby">
        <div class="lobby-card neo-box-static">
          <div class="lobby-badge">MULTIPLAYER ROOM</div>
          <h2 class="room-code-display">{{ activeRoom.room_code }}</h2>
          <p class="lobby-title">{{ activeRoom.quiz_title }} ({{ activeRoom.difficulty }} mode)</p>

          <div class="lobby-players">
            <h3>👥 Joined Players ({{ playersList.length }}):</h3>
            <div class="players-chips">
              <div v-for="p in playersList" :key="p.player_id" class="player-chip neo-box">
                👤 {{ p.username }}
              </div>
            </div>
          </div>

          <div class="lobby-actions">
            <button v-if="isHost" @click="startGameAsHost" class="neo-btn green start-btn">
              🚀 Start Game Now
            </button>
            <div v-else class="waiting-host neo-badge yellow">
              ⏳ Waiting for host to start the game...
            </div>
          </div>
        </div>
      </section>

      <!-- 4. ACTIVE GAMEPLAY VIEW -->
      <section v-if="currentTab === 'game'" class="view-game">
        <!-- Question Active -->
        <div v-if="gameStatus === 'question_active' && currentQuestion" class="game-arena neo-box-static">
          <div class="game-meta">
            <span class="q-num">Q{{ currentQuestion.question_index + 1 }} / {{ currentQuestion.total_questions }}</span>
            <div class="timer-box neo-box" :class="{ 'warning': timeLeft <= 5 }">
              ⏳ {{ timeLeft }}s
            </div>
          </div>

          <h2 class="question-text">{{ currentQuestion.question }}</h2>

          <div class="options-grid">
            <button
              v-for="(opt, idx) in currentQuestion.options"
              :key="idx"
              @click="sendAnswer(idx)"
              class="option-btn neo-box"
              :class="{
                'selected': selectedOption === idx,
                'opt-0': idx === 0,
                'opt-1': idx === 1,
                'opt-2': idx === 2,
                'opt-3': idx === 3
              }"
              :disabled="selectedOption !== null"
            >
              <span class="opt-letter">{{ ['A', 'B', 'C', 'D'][idx] }}</span>
              <span class="opt-text">{{ opt }}</span>
            </button>
          </div>

          <div v-if="answerResult" class="feedback-toast neo-box" :class="answerResult.is_correct ? 'correct' : 'wrong'">
            {{ answerResult.is_correct ? `🎯 Correct! +${answerResult.points_earned} PTS` : '❌ Incorrect' }}
          </div>
        </div>

        <!-- Question Result Reveal -->
        <div v-if="gameStatus === 'question_result'" class="result-arena neo-box-static">
          <h3 class="reveal-title">Round Results</h3>
          <div class="explanation-box neo-box">
            <h4>💡 Explanation:</h4>
            <p>{{ explanationText }}</p>
          </div>

          <div class="leaderboard-panel">
            <h4>🏆 Standings:</h4>
            <div v-for="player in leaderboard" :key="player.player_id" class="lead-item neo-box">
              <span class="rank">#{{ player.rank }}</span>
              <span class="name">{{ player.username }}</span>
              <span class="pts">{{ player.score }} PTS</span>
            </div>
          </div>
        </div>

        <!-- Final Game Over -->
        <div v-if="gameStatus === 'finished'" class="gameover-arena neo-box-static">
          <h2 class="podium-title">🎉 GAME OVER! 🎉</h2>
          <div v-if="winnerData" class="winner-crown neo-box">
            <h3>👑 1st Place Champion: {{ winnerData.username }}</h3>
            <p class="final-score">{{ winnerData.score }} Points</p>
          </div>

          <div class="full-leaderboard">
            <h4>Final Leaderboard:</h4>
            <div v-for="p in leaderboard" :key="p.player_id" class="lead-row neo-box">
              <span class="rank">#{{ p.rank }}</span>
              <span class="name">{{ p.username }}</span>
              <span class="score">{{ p.score }} PTS</span>
            </div>
          </div>

          <button @click="currentTab = 'sessions'" class="neo-btn pink mt-4">
            Back to Sessions
          </button>
        </div>
      </section>
    </main>

    <!-- Modal: Create Session -->
    <div v-if="showCreateModal" class="modal-overlay">
      <div class="modal-content neo-box-static">
        <h3>⚡ New Session</h3>
        <input v-model="newSessionTitle" placeholder="Session Title (e.g. Docker Fundamentals)" class="neo-input mb-3" />
        <textarea v-model="newSessionDesc" placeholder="Description or speaker notes..." class="neo-input mb-3" rows="3"></textarea>
        <div class="modal-actions">
          <button @click="showCreateModal = false" class="neo-btn">Cancel</button>
          <button @click="createNewSession" class="neo-btn green">Save Session</button>
        </div>
      </div>
    </div>

    <!-- Modal: User Authentication (Login / Register) -->
    <div v-if="showAuthModal" class="modal-overlay">
      <div class="modal-content auth-modal neo-box-static">
        <div class="auth-modal-header">
          <h3>{{ authMode === 'register' ? '📝 Register Session Owner' : '🔑 Owner Sign In' }}</h3>
          <div class="auth-switch-tabs">
            <button
              @click="authMode = 'login'; authError = ''"
              class="neo-btn-sm"
              :class="{ 'yellow': authMode === 'login' }"
            >
              Sign In
            </button>
            <button
              @click="authMode = 'register'; authError = ''"
              class="neo-btn-sm"
              :class="{ 'cyan': authMode === 'register' }"
            >
              Register
            </button>
          </div>
        </div>

        <p class="auth-modal-sub">
          {{ authMode === 'register'
            ? 'Create an account to host sessions, upload training media, and generate AI quizzes.'
            : 'Sign in to access your sessions and start multiplayer quiz battles.' }}
        </p>

        <div v-if="authError" class="auth-error-banner neo-box">
          ⚠️ {{ authError }}
        </div>

        <!-- Google Sign In Quick Action -->
        <div class="google-auth-container mb-3">
          <div id="gsi-button-container" class="gsi-slot"></div>
          <button
            type="button"
            @click="handleQuickGoogleSignIn"
            class="neo-btn google-btn full-width"
          >
            <svg class="google-icon" viewBox="0 0 24 24" width="20" height="20">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            Sign in with Google
          </button>
        </div>

        <div class="auth-divider">
          <span>OR USE USERNAME & PASSWORD</span>
        </div>

        <form @submit.prevent="handleAuthSubmit" class="auth-form">
          <template v-if="authMode === 'register'">
            <div class="form-group mb-3">
              <label class="form-label">Username:</label>
              <input
                v-model="authUsername"
                required
                placeholder="e.g. jayaraj_kannan"
                class="neo-input"
              />
            </div>

            <div class="form-group mb-3">
              <label class="form-label">Display Name / Speaker Handle (Optional):</label>
              <input
                v-model="authDisplayName"
                placeholder="e.g. Jayaraj Kannan"
                class="neo-input"
              />
            </div>

            <div class="form-group mb-3">
              <label class="form-label">Email Address (Optional):</label>
              <input
                v-model="authEmail"
                type="email"
                placeholder="user@example.com"
                class="neo-input"
              />
            </div>
          </template>

          <template v-else>
            <div class="form-group mb-3">
              <label class="form-label">Username or Email Address:</label>
              <input
                v-model="authIdentifier"
                required
                placeholder="Enter your username or email"
                class="neo-input"
              />
            </div>
          </template>

          <div class="form-group mb-4">
            <label class="form-label">Password:</label>
            <input
              v-model="authPassword"
              type="password"
              required
              placeholder="••••••••"
              class="neo-input"
            />
          </div>

          <div class="modal-actions">
            <button type="button" @click="showAuthModal = false; authError = ''" class="neo-btn">
              Cancel
            </button>
            <button type="submit" :disabled="isAuthSubmitting" class="neo-btn green">
              {{ isAuthSubmitting ? 'Authenticating...' : (authMode === 'register' ? 'Register Account' : 'Sign In') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal: Rename Session -->
    <div v-if="showRenameModal" class="modal-overlay">
      <div class="modal-content neo-box-static">
        <h3>✏️ Rename Session</h3>
        <p class="modal-sub">Update the title and description for this session in Firestore.</p>

        <form @submit.prevent="submitRenameSession">
          <div class="form-group mb-3">
            <label class="form-label">Session Title:</label>
            <input
              v-model="renameSessionTitle"
              required
              placeholder="e.g. Next-Gen Vertex AI Architecture"
              class="neo-input"
            />
          </div>

          <div class="form-group mb-4">
            <label class="form-label">Session Description / Summary:</label>
            <textarea
              v-model="renameSessionDesc"
              rows="3"
              placeholder="Summary of this session's contents..."
              class="neo-input"
            ></textarea>
          </div>

          <div class="modal-actions">
            <button type="button" @click="showRenameModal = false" class="neo-btn">
              Cancel
            </button>
            <button type="submit" :disabled="isRenaming" class="neo-btn green">
              {{ isRenaming ? 'Saving...' : 'Save Changes' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Full-Screen Blocking Loading Overlay -->
    <div v-if="isOverlayLoading" class="overlay-backdrop">
      <div class="overlay-card neo-box-static">
        <div class="overlay-spinner-box">
          <div class="neo-spinner"></div>
          <span class="spinner-icon">⚡</span>
        </div>
        <h3 class="overlay-title">{{ overlayLoadingTitle || 'Processing Request...' }}</h3>
        <p class="overlay-subtitle">{{ overlayLoadingSubtitle || 'Please wait, synchronizing with Vertex AI & Google Cloud...' }}</p>
        <div class="overlay-progress-bar">
          <div class="overlay-progress-fill"></div>
        </div>
        <div class="overlay-status-tag">
          <span class="neo-badge">DO NOT REFRESH • ACTION IN PROGRESS</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.header {
  padding: 16px 24px;
  background: #fff;
  margin-bottom: 24px;
}

.header-inner {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-badge {
  background: var(--neo-pink);
  color: #fff;
  font-weight: 800;
  padding: 2px 8px;
  font-size: 0.75rem;
  border: 2px solid #000;
  box-shadow: 2px 2px 0px #000;
}

.logo-title {
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -1px;
}

.highlight {
  color: var(--neo-orange);
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 16px;
}

.player-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 2px solid #000;
  padding: 4px 8px;
  background: #f0f0f0;
}

.player-tag .label {
  font-weight: 800;
  font-size: 0.75rem;
}

.username-input {
  border: none;
  background: transparent;
  font-weight: 700;
  font-family: inherit;
  width: 120px;
  outline: none;
}

.status-banner {
  background: var(--neo-yellow);
  padding: 10px 16px;
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1rem;
  font-weight: 800;
  cursor: pointer;
}

/* SESSIONS VIEW */
.sessions-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
}

.section-title {
  font-size: 1.8rem;
  font-weight: 800;
}

.section-subtitle {
  color: #555;
  font-weight: 600;
}

.actions-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.join-lobby-box {
  display: flex;
  padding: 4px;
  background: #fff;
}

.code-input {
  border: none;
  padding: 6px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  width: 110px;
  outline: none;
  text-transform: uppercase;
}

.sessions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.session-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.card-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 700;
  color: #666;
  margin-bottom: 8px;
}

.card-title {
  font-size: 1.3rem;
  font-weight: 800;
  margin-bottom: 8px;
}

.card-desc {
  font-size: 0.95rem;
  color: #444;
  margin-bottom: 16px;
  flex-grow: 1;
}

.card-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.badge-status {
  font-weight: 700;
  font-size: 0.8rem;
  padding: 4px 8px;
  border: 2px solid #000;
  background: #eee;
}

.badge-status.ready {
  background: var(--neo-green);
}

/* DETAIL VIEW */
.back-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.session-id-pill {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  background: #000;
  color: #fff;
  padding: 6px 12px;
}

.detail-hero {
  padding: 20px;
  margin-bottom: 24px;
}

.hero-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.detail-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.split-col {
  padding: 20px;
}

.panel-title {
  font-size: 1.2rem;
  font-weight: 800;
  margin-bottom: 4px;
}

.panel-desc {
  font-size: 0.85rem;
  color: #555;
  margin-bottom: 16px;
}

.upload-zone {
  padding: 16px;
  background: #fafafa;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.files-list h4, .available-quizzes h4 {
  font-weight: 800;
  margin-bottom: 8px;
}

.file-items {
  list-style: none;
}

.file-item {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  border-bottom: 2px solid #000;
  font-weight: 600;
  font-size: 0.9rem;
}

.btn-group {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  margin-bottom: 16px;
}

.quiz-item {
  padding: 14px;
  margin-bottom: 12px;
}

.quiz-item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.quiz-item h5 {
  font-size: 1.05rem;
  font-weight: 800;
  margin-bottom: 4px;
}

.quiz-item p {
  font-size: 0.85rem;
  color: #444;
  margin-bottom: 10px;
}

/* LOBBY VIEW */
.view-lobby {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.lobby-card {
  max-width: 600px;
  width: 100%;
  padding: 32px;
  text-align: center;
}

.room-code-display {
  font-size: 3.5rem;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 6px;
  margin: 12px 0;
  color: var(--neo-pink);
  text-shadow: 3px 3px 0px #000;
}

.players-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin: 20px 0;
}

.player-chip {
  padding: 8px 14px;
  font-weight: 800;
  background: var(--neo-yellow);
}

.start-btn {
  font-size: 1.2rem;
  padding: 14px 28px;
}

/* GAMEPLAY VIEW */
.game-arena {
  padding: 30px;
}

.game-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.q-num {
  font-weight: 800;
  font-size: 1.2rem;
}

.timer-box {
  font-size: 1.4rem;
  font-weight: 800;
  padding: 6px 14px;
  background: var(--neo-cyan);
}

.timer-box.warning {
  background: var(--neo-pink);
  color: #fff;
}

.question-text {
  font-size: 1.6rem;
  font-weight: 800;
  margin-bottom: 28px;
}

.options-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.option-btn {
  padding: 20px;
  font-size: 1.1rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: pointer;
  text-align: left;
}

.opt-letter {
  background: #000;
  color: #fff;
  padding: 6px 12px;
  font-weight: 800;
}

.opt-0 { background: #ffeaa7; }
.opt-1 { background: #81ecec; }
.opt-2 { background: #fab1a0; }
.opt-3 { background: #a29bfe; }

.option-btn.selected {
  outline: 4px solid #000;
  transform: translate(2px, 2px);
}

.feedback-toast {
  margin-top: 20px;
  padding: 12px;
  font-weight: 800;
  text-align: center;
  font-size: 1.2rem;
}

.feedback-toast.correct { background: var(--neo-green); }
.feedback-toast.wrong { background: var(--neo-pink); color: #fff; }

.explanation-box {
  padding: 16px;
  background: var(--neo-yellow);
  margin-bottom: 20px;
}

.leaderboard-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lead-item {
  display: flex;
  justify-content: space-between;
  padding: 10px 16px;
  font-weight: 800;
}

.winner-crown {
  padding: 24px;
  background: var(--neo-yellow);
  margin-bottom: 20px;
  text-align: center;
}

.final-score {
  font-size: 2rem;
  font-weight: 800;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  width: 90%;
  max-width: 500px;
  padding: 24px;
}

.mb-3 { margin-bottom: 12px; }
.mt-4 { margin-top: 16px; }

/* Full-Screen Blocking Loading Overlay */
.overlay-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(18, 18, 18, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: wait;
  user-select: none;
}

.overlay-card {
  width: 90%;
  max-width: 520px;
  background: #ffffff;
  padding: 36px 28px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  border: var(--border-thicker);
  box-shadow: 10px 10px 0px var(--color-black);
  animation: popIn 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

@keyframes popIn {
  from {
    transform: scale(0.85);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

.overlay-spinner-box {
  position: relative;
  width: 84px;
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.neo-spinner {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 6px solid #f0f0f0;
  border-top: 6px solid var(--neo-pink);
  border-right: 6px solid var(--neo-yellow);
  border-bottom: 6px solid var(--neo-cyan);
  animation: spin 0.9s cubic-bezier(0.68, -0.55, 0.265, 1.55) infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.spinner-icon {
  font-size: 2.2rem;
  animation: pulse 1s infinite alternate;
}

@keyframes pulse {
  0% { transform: scale(0.9); }
  100% { transform: scale(1.15); }
}

.overlay-title {
  font-size: 1.6rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  color: var(--color-black);
}

.overlay-subtitle {
  font-size: 1rem;
  font-weight: 600;
  color: #444;
  margin-bottom: 24px;
  line-height: 1.5;
  max-width: 440px;
}

.overlay-progress-bar {
  width: 100%;
  height: 14px;
  background: #f0f0f0;
  border: var(--border-thick);
  overflow: hidden;
  margin-bottom: 18px;
  position: relative;
}

.overlay-progress-fill {
  height: 100%;
  width: 40%;
  background: repeating-linear-gradient(
    45deg,
    var(--neo-yellow),
    var(--neo-yellow) 12px,
    var(--neo-cyan) 12px,
    var(--neo-cyan) 24px
  );
  animation: progressMove 1.4s linear infinite;
}

@keyframes progressMove {
  0% { transform: translateX(-100%); width: 35%; }
  50% { width: 65%; }
  100% { transform: translateX(300%); width: 35%; }
}

.overlay-status-tag .neo-badge {
  background: var(--neo-yellow);
  font-size: 0.78rem;
  letter-spacing: 0.8px;
}

.user-profile-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--neo-yellow);
  padding: 6px 12px;
  font-size: 0.85rem;
  font-weight: 800;
}

.user-role-tag {
  background: var(--color-black);
  color: var(--neo-yellow);
  padding: 2px 6px;
  font-size: 0.7rem;
  font-weight: 900;
  letter-spacing: 0.5px;
}

.user-name {
  color: var(--color-black);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.neo-btn-sm {
  font-family: inherit;
  font-weight: 800;
  font-size: 0.75rem;
  padding: 4px 8px;
  border: var(--border-thick);
  background: var(--color-white);
  cursor: pointer;
  box-shadow: 2px 2px 0px var(--color-black);
  transition: transform 0.1s, box-shadow 0.1s;
}

.neo-btn-sm:hover {
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0px var(--color-black);
}

.logout-btn {
  background: var(--neo-pink);
  color: var(--color-white);
}

.auth-guest-box {
  display: flex;
  gap: 6px;
}

.session-owner-tag {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.owner-pill {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
}

.col-title-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.owner-lock-badge {
  background: var(--neo-pink);
  color: var(--color-white);
  font-size: 0.75rem;
  font-weight: 800;
  padding: 3px 8px;
  border: 2px solid var(--color-black);
  box-shadow: 2px 2px 0px var(--color-black);
}

.owner-restricted-box {
  background: #fdf2f4;
  border: 2px dashed #e11d48;
  padding: 16px;
  margin-bottom: 20px;
  font-size: 0.9rem;
  font-weight: 700;
  color: #9f1239;
  text-align: center;
}

.guest-info-badge {
  display: block;
  text-align: center;
  margin-top: 10px;
  font-size: 0.8rem;
  padding: 8px;
}

.auth-modal {
  max-width: 460px;
  width: 90%;
  background: var(--color-white);
}

.auth-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.auth-switch-tabs {
  display: flex;
  gap: 6px;
}

.auth-modal-sub {
  font-size: 0.9rem;
  color: #555;
  font-weight: 600;
  margin-bottom: 16px;
  line-height: 1.4;
}

.auth-error-banner {
  background: #ffe4e6;
  color: #be123c;
  padding: 10px;
  font-size: 0.85rem;
  font-weight: 800;
  margin-bottom: 16px;
  border: 2px solid #be123c;
}

.google-auth-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.gsi-slot {
  display: flex;
  justify-content: center;
  width: 100%;
}

.google-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--color-white);
  color: var(--color-black);
  border: 3px solid var(--color-black);
  font-weight: 800;
  font-size: 0.95rem;
  padding: 10px 16px;
  box-shadow: 4px 4px 0px var(--color-black);
  cursor: pointer;
  transition: transform 0.1s, box-shadow 0.1s;
}

.google-btn:hover {
  background: #f8fafc;
  transform: translate(-2px, -2px);
  box-shadow: 6px 6px 0px var(--color-black);
}

.google-icon {
  flex-shrink: 0;
}

.full-width {
  width: 100%;
}

.auth-divider {
  display: flex;
  align-items: center;
  text-align: center;
  margin: 18px 0;
  position: relative;
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  flex: 1;
  border-bottom: 2px dashed #bbb;
}

.auth-divider span {
  padding: 0 10px;
  font-size: 0.72rem;
  font-weight: 900;
  color: #666;
  letter-spacing: 0.8px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: left;
}

.form-label {
  font-size: 0.82rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Home Promotional & Dashboard Styles */
.view-home {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.home-hero {
  display: grid;
  grid-template-columns: 1.3fr 0.9fr;
  gap: 32px;
  background: var(--color-white);
  padding: 40px;
  align-items: center;
}

.hero-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.hero-heading {
  font-size: 2.4rem;
  font-weight: 900;
  line-height: 1.15;
  margin-bottom: 16px;
  color: var(--color-black);
}

.hero-subheading {
  font-size: 1.05rem;
  line-height: 1.6;
  color: #333;
  margin-bottom: 24px;
}

.hero-cta-group {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-btn {
  font-size: 1rem;
  padding: 12px 20px;
}

.hero-card-side {
  background: #fdfaf0;
  padding: 24px;
}

.arena-preview-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--color-black);
  margin-bottom: 16px;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--color-black);
}

.dot.red { background: var(--neo-pink); }
.dot.yellow { background: var(--neo-yellow); }
.dot.green { background: var(--neo-green); }

.arena-title {
  font-weight: 900;
  font-size: 0.85rem;
  margin-left: 6px;
  letter-spacing: 0.5px;
}

.arena-preview-body .stat-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-weight: 700;
  font-size: 0.9rem;
  border-bottom: 1px dashed #ccc;
}

.stat-label {
  color: #444;
}

.stat-val {
  color: var(--color-black);
  font-weight: 900;
}

.owner-dashboard-section {
  background: #f0fdf4;
  border: 3px solid var(--color-black);
  box-shadow: 6px 6px 0px var(--color-black);
  padding: 28px;
}

.owner-card {
  border-color: #15803d;
}

.owner-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.owner-actions-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-group-right {
  display: flex;
  gap: 6px;
}

.btn-compact {
  padding: 6px 10px;
  font-size: 0.8rem;
}

.empty-owner-box {
  background: var(--color-white);
  padding: 30px;
  text-align: center;
  font-size: 1.05rem;
  font-weight: 700;
}

.features-section {
  padding: 20px 0;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 20px;
}

.feature-card {
  background: var(--color-white);
  padding: 24px;
}

.feature-icon {
  font-size: 2.2rem;
  margin-bottom: 12px;
}

.feature-title {
  font-size: 1.2rem;
  font-weight: 900;
  margin-bottom: 8px;
}

.feature-desc {
  font-size: 0.9rem;
  line-height: 1.5;
  color: #444;
  font-weight: 500;
}

.text-center {
  text-align: center;
}

.hero-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 900px) {
  .home-hero {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .detail-split, .options-grid {
    grid-template-columns: 1fr;
  }
}
</style>
