import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from fastapi import WebSocket

class Player:
    def __init__(self, player_id: str, username: str, websocket: WebSocket):
        self.player_id = player_id
        self.username = username
        self.websocket = websocket
        self.score = 0
        self.streak = 0
        self.has_answered = False
        self.last_answer_time = 0.0

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "username": self.username,
            "score": self.score,
            "streak": self.streak,
            "has_answered": self.has_answered,
        }

class QuizRoom:
    def __init__(self, room_code: str, session_id: str, difficulty: str, quiz_data: Dict[str, Any], owner_id: Optional[str] = None):
        self.room_code = room_code
        self.session_id = session_id
        self.difficulty = difficulty
        self.quiz_data = quiz_data
        self.owner_id = owner_id
        self.questions: List[Dict[str, Any]] = quiz_data.get("questions", [])
        self.players: Dict[str, Player] = {}
        self.status = "waiting"  # waiting, question_active, question_result, finished
        self.current_question_index = -1
        self.question_start_time = 0.0
        self.question_duration = 15  # 15 seconds per question

    async def broadcast(self, message: Dict[str, Any]):
        dead_players = []
        payload = json.dumps(message)
        for pid, player in self.players.items():
            try:
                await player.websocket.send_text(payload)
            except Exception:
                dead_players.append(pid)
        for pid in dead_players:
            self.remove_player(pid)

    def add_player(self, player_id: str, username: str, websocket: WebSocket) -> Player:
        player = Player(player_id, username, websocket)
        self.players[player_id] = player
        return player

    def remove_player(self, player_id: str):
        if player_id in self.players:
            del self.players[player_id]

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        sorted_players = sorted(self.players.values(), key=lambda p: p.score, reverse=True)
        return [
            {
                "rank": i + 1,
                "player_id": p.player_id,
                "username": p.username,
                "score": p.score,
                "streak": p.streak,
            }
            for i, p in enumerate(sorted_players)
        ]

    def submit_answer(self, player_id: str, option_index: int) -> Dict[str, Any]:
        if self.status != "question_active":
            return {"error": "No question currently active"}
        player = self.players.get(player_id)
        if not player or player.has_answered:
            return {"error": "Already answered or player not found"}

        now = time.time()
        elapsed = now - self.question_start_time
        remaining = max(0.0, self.question_duration - elapsed)
        
        current_q = self.questions[self.current_question_index]
        correct_index = current_q.get("correct_option_index", 0)
        is_correct = (option_index == correct_index)

        player.has_answered = True
        player.last_answer_time = elapsed

        points = 0
        if is_correct:
            # Base 500 + speed bonus up to 500 points
            speed_ratio = remaining / self.question_duration
            points = int(500 + (500 * speed_ratio))
            player.streak += 1
            if player.streak > 1:
                points += min(player.streak * 50, 200) # streak bonus
            player.score += points
        else:
            player.streak = 0

        return {
            "player_id": player_id,
            "is_correct": is_correct,
            "points_earned": points,
            "total_score": player.score,
            "correct_option_index": correct_index if self.status == "question_result" else None,
        }

class GameManager:
    def __init__(self):
        self.rooms: Dict[str, QuizRoom] = {}

    def create_room(self, room_code: str, session_id: str, difficulty: str, quiz_data: Dict[str, Any], owner_id: Optional[str] = None) -> QuizRoom:
        room = QuizRoom(room_code, session_id, difficulty, quiz_data, owner_id=owner_id)
        self.rooms[room_code] = room
        return room

    def get_room(self, room_code: str) -> Optional[QuizRoom]:
        return self.rooms.get(room_code)

    def remove_room(self, room_code: str):
        if room_code in self.rooms:
            del self.rooms[room_code]

game_manager = GameManager()
