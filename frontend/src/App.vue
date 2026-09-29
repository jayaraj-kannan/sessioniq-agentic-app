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
const currentTab = ref('sessions') // 'sessions' | 'detail' | 'lobby' | 'game'

// --- Sessions State ---
const sessions = ref([])
const activeSession = ref(null)
const isLoading = ref(false)
const statusMessage = ref('')

// --- Create Session Modal/Inputs ---
const newSessionTitle = ref('')
const newSessionDesc = ref('')
const showCreateModal = ref(false)

// --- File Upload State ---
const selectedFile = ref(null)
const uploadProgress = ref(false)

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
  isLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newSessionTitle.value,
        description: newSessionDesc.value
      })
    })
    const data = await res.json()
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
  uploadProgress.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('category', 'input_materials')

    const res = await fetch(`${API_BASE}/api/sessions/${activeSession.value.session_id}/upload`, {
      method: 'POST',
      body: formData
    })
    const data = await res.json()
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
  selectedDifficulty.value = difficulty
  isGeneratingQuiz.value = true
  statusMessage.value = `Agents are analyzing materials and generating ${difficulty} quiz...`
  try {
    const res = await fetch(`${API_BASE}/api/sessions/${activeSession.value.session_id}/generate-quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSession.value.session_id,
        difficulty: difficulty,
        num_questions: 4
      })
    })
    const data = await res.json()
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
  try {
    const res = await fetch(`${API_BASE}/api/rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSession.value.session_id,
        difficulty: difficulty
      })
    })
    const room = await res.json()
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
      is_host: isHost.value
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
          <button @click="currentTab = 'sessions'" class="neo-btn" :class="{ 'pink': currentTab === 'sessions' }">
            ⚡ Sessions
          </button>
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
            <h2>{{ activeSession.title || 'Session Details' }}</h2>
            <span class="neo-badge green">Firestore Synced</span>
          </div>
          <p class="hero-desc">{{ activeSession.summary || activeSession.description || 'Manage materials and quiz generators for this session.' }}</p>
        </div>

        <div class="detail-split">
          <!-- Left: Input Materials & GCS Upload -->
          <div class="split-col neo-box-static">
            <h3 class="panel-title">🗂️ Input Source Files (GCS Bucket)</h3>
            <p class="panel-desc">Raw video/audio transcripts and session notes stored in <code>sessions/{{ activeSession.session_id }}/input_materials/</code></p>

            <div class="upload-zone neo-box">
              <input type="file" @change="onFileSelected" />
              <button @click="uploadMaterial" :disabled="!selectedFile || uploadProgress" class="neo-btn cyan">
                {{ uploadProgress ? 'Uploading...' : 'Upload to Cloud Storage' }}
              </button>
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
            <h3 class="panel-title">🎯 AI Quiz Engine (Firestore DB)</h3>
            <p class="panel-desc">Trigger multi-agents to extract concepts and store schemas directly in Firestore.</p>

            <div class="quiz-gen-actions">
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

            <div v-if="isGeneratingQuiz" class="generating-box neo-box">
              <h4>🤖 Agents Collaborating...</h4>
              <p>Extracting topics, composing questions, and writing to Firestore...</p>
            </div>

            <!-- Existing Quizzes -->
            <div class="available-quizzes">
              <h4>Ready-to-Play Quizzes:</h4>
              <div v-if="!activeSession.quizzes || !Object.keys(activeSession.quizzes).length" class="empty-quizzes">
                No quizzes generated yet. Click a difficulty above!
              </div>

              <div v-for="(quiz, diff) in activeSession.quizzes" :key="diff" class="quiz-item neo-box">
                <div class="quiz-item-header">
                  <span class="neo-badge" :class="diff">{{ diff.toUpperCase() }}</span>
                  <span class="q-count">{{ (quiz.questions || []).length }} Questions</span>
                </div>
                <h5>{{ quiz.title }}</h5>
                <p>{{ quiz.summary }}</p>
                <button @click="hostMultiplayerLobby(diff)" class="neo-btn purple">
                  🎮 Host Live Multiplayer
                </button>
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

@media (max-width: 768px) {
  .detail-split, .options-grid {
    grid-template-columns: 1fr;
  }
}
</style>
