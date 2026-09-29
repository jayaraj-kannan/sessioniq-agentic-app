# ⚡ SessionIQ · Agentic Multi-Player Quiz Platform

<div align="center">

![Build with Gemini](https://img.shields.io/badge/Build%20with%20Gemini-World%20Tour-4285F4?logo=google&logoColor=white)
![Track 3](https://img.shields.io/badge/Track%203-Agent--First%20Apps-EA4335)
![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Agent%20Platform-4285F4?logo=googlecloud&logoColor=white)
![Vue 3](https://img.shields.io/badge/Vue-3.x-4FC08D?logo=vuedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)

**Transform recorded and live conference sessions, transcripts, and study notes into real-time interactive multiplayer trivia games powered by Gemini Multi-Agent orchestration.**

</div>

---

## 📖 Overview

**SessionIQ** is an agentic platform designed for conference organizers, educators, and live audiences. It breaks down raw recorded video/audio transcripts and session notes into multi-difficulty quiz schemas, archives source media into Google Cloud Storage, persists game collections in Firestore, and drives real-time Kahoot-style multiplayer trivia battles via WebSockets with a bold Neo-Brutalist Vue 3 user interface.

---

## 🤖 Multi-Agent Architecture

SessionIQ utilizes Google's **Agent Development Kit (ADK)** and **Gemini 2.5 Flash** to power specialized collaborating sub-agents:

```
                            ┌──────────────────────────────────┐
                            │    SessionIQ Lead Coordinator    │
                            │      (coordinator_agent)         │
                            └────────────────┬─────────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
       ┌───────────────────────────────┐             ┌─────────────────────────────┐
       │   Media Breakdown Agent       │             │   Quiz Generator Agent      │
       │   (media_breakdown_agent)     │             │   (quiz_generator_agent)    │
       └──────────────┬────────────────┘             └──────────────┬──────────────┘
                      │                                             │
                      ▼                                             ▼
             Google Cloud Storage                           Google Cloud Firestore
        `sessions/{id}/input_materials/`            `/sessions/{id}/quizzes/{difficulty}`
```

1. **Lead Coordinator Agent (`coordinator_agent`)**:
   - Manages end-to-end workflow between input ingestion, media breakdown, and quiz schema generation.
   - Allocates unique `session_id` identifiers and coordinates cloud persistence.

2. **Media & Transcript Breakdown Sub-Agent (`media_breakdown_agent`)**:
   - Analyzes raw transcript logs, cleans timestamps, extracts key themes, definitions, and speaker takeaways.
   - Archives raw source files directly to dedicated Google Cloud Storage buckets under `sessions/{session_id}/input_materials/`.

3. **Quiz Schema Architect Sub-Agent (`quiz_generator_agent`)**:
   - Converts extracted concepts into structured 4-option multiple-choice quizzes tailored by difficulty:
     - 🟢 **Simple**: Direct definitions and core factual recall.
     - 🟡 **Medium**: Conceptual understanding and scenario differentiation.
     - 🔴 **Hard**: Deep technical reasoning, edge cases, and architectural trade-offs.
   - Enforces strict Pydantic schemas with timestamp references and explanations.
   - Stores the generated quiz collections exclusively in **Firestore Database**.

---

## 🛠️ Storage & Data Boundaries

To maintain clean separation between source media and structured quiz models:

- **Google Cloud Storage (GCS)**:
  - Bucket: `gs://<project-id>-sessioniq-assets`
  - Path: `sessions/{session_id}/input_materials/{filename}`
  - Stores: Uploaded video/audio transcripts, lecture notes, markdown files, and raw media sources.
- **Google Cloud Firestore (Native Mode)**:
  - Collection: `/sessions/{session_id}` (Session metadata, title, topics, material flags)
  - Subcollection: `/sessions/{session_id}/quizzes/{difficulty}` (Structured question objects, candidate choices, correct index, detailed explanations, and timestamps)

---

## 🎮 Real-Time Multiplayer Engine

SessionIQ includes a high-performance **FastAPI WebSocket Game Manager**:
- **Room Code Lobby**: Dynamic 6-character room codes (e.g. `#BGPC78`) allowing dozens of simultaneous participants to join.
- **Synchronized Game Loop**: Live 15-second per-question countdown broadcasted simultaneously to all clients.
- **Speed Scoring**: Base score + speed bonus (faster correct answers earn up to +1000 points) + winning streak multipliers.
- **Live Leaderboard**: Real-time standings broadcasted between questions and final podium celebration.

---

## 🎨 Neo-Brutalist Vue 3 Frontend

A high-contrast, tactile retro interface built with **Vue 3** and modern styling:
- **Session Catalog**: Real-time Firestore session dashboard showing upload states and ready-to-play quizzes.
- **Direct Asset Uploader**: Multi-part upload channel syncing input files directly into GCS.
- **One-Click AI Quiz Generators**: Difficulty-based generator triggering the ADK multi-agent workflow.
- **Live Multiplayer Arena**: Host game dashboard, player buzzer controllers, animated feedback, explanations, and ranked leaderboards.

---

## 🚀 Quickstart & Setup Guide

### 1. Prerequisites
- Python 3.11+ or 3.12 (`uv` recommended)
- Node.js 18+ and npm
- Google Cloud CLI (`gcloud`) authenticated to your project with Firestore and Storage enabled:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  gcloud services enable firestore.googleapis.com storage.googleapis.com aiplatform.googleapis.com
  ```

### 2. Backend Setup
1. Navigate to the agent workspace:
   ```bash
   cd sessioniq
   ```
2. Create virtual environment and install dependencies:
   ```bash
   uv venv -p 3.12
   source .venv/bin/activate
   uv pip install -e .
   uv pip install google-cloud-firestore google-cloud-storage
   ```
3. Start the FastAPI REST & WebSocket server:
   ```bash
   python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 --reload
   ```

### 3. Frontend Setup
1. In a new terminal, navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev -- --host 0.0.0.0 --port 5173
   ```
4. Open `http://localhost:5173` in your browser.

---

## 📁 Repository Structure

```text
├── sessioniq/
│   ├── app/
│   │   ├── agent.py            # Multi-agent coordination (coordinator, breakdown, quiz generator)
│   │   ├── fast_api_app.py     # FastAPI REST API & WebSocket multiplayer endpoints
│   │   ├── game_manager.py     # Real-time room manager, scoring loop, and leaderboard
│   │   ├── tools.py            # GCS input file upload & Firestore quiz storage tools
│   │   └── schemas.py          # Pydantic models for Quiz and Question schemas
│   ├── agents-cli-manifest.yaml
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.vue             # Complete Neo-Brutalist UI (Catalog, Detail, Lobby, Game)
│   │   ├── style.css           # Neo-Brutalist high-contrast design system
│   │   └── main.js
│   ├── package.json
│   └── vite.config.js
├── project_brief.md            # Workshop track 3 specification
└── README.md
```

---

## 📄 License
Demonstration project developed for Track 3 of the Build with Gemini World Tour.
