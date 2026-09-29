# My agent: SessionIQ
One-liner: A conversational multi-agent system that helps educators, conference organizers, and audience participants transform recorded audio/video sessions or transcripts into interactive, multi-difficulty multiplayer quiz games with a catalog of sessions and live trivia battles.

Tool coverage:
- Memory: Participant quiz history, performance streaks, player preferences, and session-specific learning gaps across conversations.
- Tools: 
  - `breakdown_media_to_text`: Transcribe and extract structured sections and timestamps from audio/video or transcript uploads.
  - `generate_quiz_schema`: Transform session text content into structured quiz schemas (questions, options, correct answers, explanations) customized by difficulty level (simple, medium, hard).
  - `store_quiz_to_firestore`: Persist the generated quiz schema and session metadata into Firestore collections.
  - `upload_to_gcs`: Store original media recordings, audio, and transcript source files in Google Cloud Storage with unique session identifiers.
  - `launch_multiplayer_lobby`: Initialize a real-time multiplayer trivia room powered by the Python WebSocket game server.
- Catalog/UI: Catalog of processed sessions, generated quiz sets, player leaderboard cards, and interactive quiz display rendered via Vue 3 UI and A2UI cards.
- Image gen: Badges, topic avatars, and winner victory celebration posters for top quiz performers.
- Sandbox: Real-time scoring calculation, rating/elo adjustments, and response timing analysis.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): 
- Audio/video multimodal extraction using Gemini multimodal capabilities
- FastAPI + WebSocket server for real-time live audience buzzer & multiplayer mechanics (Kahoot / Quiz style)
- Vue 3 responsive dashboard with upload zone, difficulty selector, and live game room
