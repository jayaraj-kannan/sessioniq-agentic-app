import asyncio
import json
import os
import random
import string
import time
import uuid
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import firestore

from app.agent import coordinator_agent
from app.tools import (
    _get_project_id,
    upload_session_material_to_gcs,
    read_session_material_from_gcs,
    list_session_files,
    store_quiz_schema_in_firestore,
    get_session_quiz_from_firestore,
)
from app.game_manager import game_manager, QuizRoom, Player

app = FastAPI(title="SessionIQ API & Multiplayer Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _generate_room_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --- Models ---
class CreateSessionRequest(BaseModel):
    title: str
    description: Optional[str] = ""

class GenerateQuizRequest(BaseModel):
    session_id: str
    difficulty: str = "medium"  # simple, medium, hard
    num_questions: Optional[int] = 5

class CreateRoomRequest(BaseModel):
    session_id: str
    difficulty: str = "medium"

# --- REST Endpoints ---

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "SessionIQ Server"}

@app.get("/api/sessions")
async def get_sessions():
    """List all sessions from Firestore."""
    try:
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        docs = db.collection("sessions").order_by("updated_at", direction=firestore.Query.DESCENDING).stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            results.append(d)
        return {"sessions": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    """Create a new session document."""
    try:
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        session_data = {
            "session_id": session_id,
            "title": req.title,
            "description": req.description,
            "created_at": now_iso,
            "updated_at": now_iso,
            "has_materials": False,
        }
        db.collection("sessions").document(session_id).set(session_data)
        return {"session_id": session_id, "session": session_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get single session with its available quizzes and materials."""
    try:
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        doc = db.collection("sessions").document(session_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session_data = doc.to_dict()
        
        # Load quizzes
        quizzes = {}
        for diff in ["simple", "medium", "hard"]:
            qdoc = db.collection("sessions").document(session_id).collection("quizzes").document(diff).get()
            if qdoc.exists:
                quizzes[diff] = qdoc.to_dict()
        
        session_data["quizzes"] = quizzes
        session_data["files"] = json.loads(list_session_files(session_id))
        return session_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/upload")
async def upload_material(
    session_id: str,
    file: UploadFile = File(...),
    category: str = Form("input_materials")
):
    """Uploads an input transcript/file to GCS for the session."""
    try:
        content_bytes = await file.read()
        try:
            content_str = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_str = f"[Binary file {file.filename} uploaded]"

        res_str = upload_session_material_to_gcs(
            session_id=session_id,
            file_name=file.filename,
            content=content_str,
            category=category,
        )
        return json.loads(res_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/generate-quiz")
async def generate_quiz(session_id: str, req: GenerateQuizRequest):
    """Invokes coordinator & sub-agents to analyze session materials and generate quiz in Firestore."""
    try:
        # Load materials from GCS for this session
        files_json = list_session_files(session_id)
        files = json.loads(files_json)
        
        material_texts = []
        for f in files:
            fname = f.get("name")
            if "input_materials" in fname or "materials" in fname:
                clean_name = fname.split("/")[-1]
                category = "input_materials" if "input_materials" in fname else "materials"
                text = read_session_material_from_gcs(session_id, clean_name, category)
                material_texts.append(f"--- File: {clean_name} ---\n{text}")

        combined_material = "\n\n".join(material_texts)
        if not combined_material.strip():
            combined_material = "Introductory session covering modern cloud and agent architectures."

        # Prompt the ADK coordinator agent
        prompt = f"""
        Action required for session_id '{session_id}':
        1. Break down the provided input materials using the media_breakdown_agent.
        2. Generate a {req.difficulty} difficulty quiz with {req.num_questions or 5} questions.
        3. Store the generated quiz object directly in Firestore database using store_quiz_schema_in_firestore.
        
        Input Materials:
        {combined_material}
        """

        # Run model inference to produce quiz
        from google.genai import Client
        project_id = _get_project_id()
        genai_client = Client(vertexai=True, project=project_id, location="us-east1")
        
        system_instruction = f"""You are the SessionIQ Quiz Schema Architect.
        Generate a multiple choice quiz strictly in JSON format based on the source text.
        Difficulty: {req.difficulty}.
        Schema:
        {{
            "session_id": "{session_id}",
            "title": "Session Quiz ({req.difficulty.capitalize()})",
            "difficulty": "{req.difficulty}",
            "summary": "Short 2-sentence summary of the content.",
            "topics": ["topic1", "topic2"],
            "questions": [
                {{
                    "id": 1,
                    "question": "question text",
                    "options": ["A", "B", "C", "D"],
                    "correct_option_index": 0,
                    "explanation": "Why correct",
                    "timestamp_reference": "01:00"
                }}
            ]
        }}
        """
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "system_instruction": system_instruction,
            }
        )
        
        quiz_json_text = response.text
        # Save exclusively into Firestore
        store_quiz_schema_in_firestore(session_id, quiz_json_text)
        
        return {
            "status": "success",
            "session_id": session_id,
            "difficulty": req.difficulty,
            "quiz": json.loads(quiz_json_text),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rooms")
async def create_multiplayer_room(req: CreateRoomRequest):
    """Creates a real-time multiplayer room based on a Firestore session quiz."""
    quiz_str = get_session_quiz_from_firestore(req.session_id, req.difficulty)
    try:
        quiz_data = json.loads(quiz_str)
    except Exception:
        raise HTTPException(status_code=404, detail="No quiz found for session/difficulty. Generate it first.")
    
    room_code = _generate_room_code()
    room = game_manager.create_room(room_code, req.session_id, req.difficulty, quiz_data)
    return {
        "room_code": room_code,
        "session_id": req.session_id,
        "difficulty": req.difficulty,
        "title": quiz_data.get("title", "SessionIQ Quiz"),
        "total_questions": len(room.questions),
    }

@app.get("/api/rooms/{room_code}/leaderboard")
async def get_room_leaderboard(room_code: str):
    """Fetches current room leaderboard."""
    room = game_manager.get_room(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"room_code": room_code, "leaderboard": room.get_leaderboard()}

# --- WebSocket Multiplayer Handler ---

@app.websocket("/ws/quiz/{room_code}")
async def quiz_websocket_endpoint(websocket: WebSocket, room_code: str):
    await websocket.accept()
    room = game_manager.get_room(room_code)
    if not room:
        await websocket.send_text(json.dumps({"type": "error", "message": "Room not found"}))
        await websocket.close()
        return

    player_id = f"player-{uuid.uuid4().hex[:6]}"
    player: Optional[Player] = None

    try:
        # 1. Handshake: wait for join message
        init_data = await websocket.receive_text()
        init_msg = json.loads(init_data)
        username = init_msg.get("username", f"Player_{player_id[-4:]}")
        is_host = init_msg.get("is_host", False)

        player = room.add_player(player_id, username, websocket)

        # Notify player of welcome
        await websocket.send_text(json.dumps({
            "type": "joined",
            "player_id": player_id,
            "username": username,
            "room_code": room_code,
            "quiz_title": room.quiz_data.get("title"),
            "difficulty": room.difficulty,
            "total_questions": len(room.questions),
            "status": room.status,
            "is_host": is_host,
        }))

        # Broadcast player joined to room
        await room.broadcast({
            "type": "player_list_updated",
            "players": [p.to_dict() for p in room.players.values()],
            "leaderboard": room.get_leaderboard(),
        })

        # Main event loop for incoming client actions
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "start_game" and is_host:
                # Host triggers game start
                room.status = "in_progress"
                room.current_question_index = 0
                await run_question_loop(room)

            elif action == "submit_answer":
                option_index = msg.get("option_index")
                result = room.submit_answer(player_id, option_index)
                await websocket.send_text(json.dumps({
                    "type": "answer_acknowledged",
                    "result": result,
                }))
                # Broadcast updated answering count
                await room.broadcast({
                    "type": "answers_progress",
                    "answered_count": sum(1 for p in room.players.values() if p.has_answered),
                    "total_players": len(room.players),
                })

    except WebSocketDisconnect:
        if player:
            room.remove_player(player_id)
            await room.broadcast({
                "type": "player_left",
                "player_id": player_id,
                "players": [p.to_dict() for p in room.players.values()],
                "leaderboard": room.get_leaderboard(),
            })
    except Exception as e:
        print(f"WS Error: {e}")

async def run_question_loop(room: QuizRoom):
    """Drives the synchronized multiplayer quiz questions timer and scoring."""
    for idx, question in enumerate(room.questions):
        room.current_question_index = idx
        room.status = "question_active"
        room.question_start_time = time.time()
        for p in room.players.values():
            p.has_answered = False

        # Broadcast question to all players without correct answer
        safe_q = {
            "id": question.get("id", idx + 1),
            "question_index": idx,
            "total_questions": len(room.questions),
            "question": question.get("question"),
            "options": question.get("options", []),
            "duration": room.question_duration,
            "timestamp_reference": question.get("timestamp_reference"),
        }
        await room.broadcast({
            "type": "new_question",
            "question": safe_q,
        })

        # Wait for duration or all players answered
        elapsed = 0
        while elapsed < room.question_duration:
            all_answered = len(room.players) > 0 and all(p.has_answered for p in room.players.values())
            if all_answered:
                break
            await asyncio.sleep(0.5)
            elapsed += 0.5

        # Show Question Results & Leaderboard
        room.status = "question_result"
        correct_index = question.get("correct_option_index", 0)
        await room.broadcast({
            "type": "question_ended",
            "correct_option_index": correct_index,
            "explanation": question.get("explanation", ""),
            "leaderboard": room.get_leaderboard(),
        })

        await asyncio.sleep(4)  # 4 seconds reveal interval

    # Game Complete
    room.status = "finished"
    leaderboard = room.get_leaderboard()
    winner = leaderboard[0] if leaderboard else None
    await room.broadcast({
        "type": "game_over",
        "leaderboard": leaderboard,
        "winner": winner,
    })
