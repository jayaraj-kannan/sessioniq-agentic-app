from typing import List, Optional
from pydantic import BaseModel, Field

class QuizQuestion(BaseModel):
    id: int = Field(description="Question sequential identifier starting from 1")
    question: str = Field(description="The quiz question text")
    options: List[str] = Field(description="List of 4 candidate answer choices")
    correct_option_index: int = Field(description="0-based index of the correct option (0, 1, 2, or 3)")
    explanation: str = Field(description="Explanation of why this answer is correct")
    timestamp_reference: Optional[str] = Field(default=None, description="Timestamp or segment reference from the session (e.g. '04:15')")

class QuizSchema(BaseModel):
    session_id: str = Field(description="Unique session identifier")
    title: str = Field(description="Title of the session or quiz")
    difficulty: str = Field(description="Difficulty level: simple, medium, or hard")
    summary: str = Field(description="Executive summary of the session content covered in this quiz")
    topics: List[str] = Field(description="Key topics covered")
    questions: List[QuizQuestion] = Field(description="List of generated quiz questions")
