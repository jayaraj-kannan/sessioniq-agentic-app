# ruff: noqa
# Copyright 2026 Google LLC
# SessionIQ: Multi-agent coordination for session media breakdown, input material upload & quiz generation

import os
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import (
    upload_session_material_to_gcs,
    read_session_material_from_gcs,
    list_session_files,
    store_quiz_schema_in_firestore,
    get_session_quiz_from_firestore,
)

MODEL = "gemini-2.5-flash"

# 1. Sub-agent: Breakdown video / audio / transcript content into structured text
media_breakdown_agent = Agent(
    name="media_breakdown_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Media & Transcript Breakdown Specialist for SessionIQ.
Your role:
1. Receive raw input files (transcripts, video/audio logs, lecture notes, or session text).
2. Clean, segment, and structure the content into chronological sections with key concepts.
3. Whenever new input files/materials are provided for a session, upload ONLY these input files to the Google Cloud Storage bucket using `upload_session_material_to_gcs(session_id=..., file_name=..., content=..., category='input_materials')`.
4. If asked to inspect existing materials, invoke `list_session_files(session_id=...)` or `read_session_material_from_gcs(...)`.
5. Return the structured breakdown text to the coordinator for quiz generation.""",
    tools=[
        upload_session_material_to_gcs,
        read_session_material_from_gcs,
        list_session_files,
    ],
)

# 2. Sub-agent: Break down the extracted text content into quiz schema
quiz_generator_agent = Agent(
    name="quiz_generator_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Quiz Schema Architect for SessionIQ.
Your role:
1. Take structured session text or uploaded input materials and generate engaging, multiple-choice quiz questions based on the requested difficulty:
   - "simple": Straightforward factual recall, direct definitions, easy options.
   - "medium": Conceptual understanding, identifying examples, distinguishing between related ideas.
   - "hard": Deep analytical scenarios, multi-step reasoning, tricky distractors, edge-case mechanics.
2. Structure the output strictly matching this schema:
   {
     "session_id": "<session_id>",
     "title": "<session or quiz title>",
     "difficulty": "simple" | "medium" | "hard",
     "summary": "<short 2-sentence summary of covered topics>",
     "topics": ["<topic1>", "<topic2>"],
     "questions": [
       {
         "id": 1,
         "question": "<question text>",
         "options": ["<A>", "<B>", "<C>", "<D>"],
         "correct_option_index": 0,
         "explanation": "<why this answer is correct>",
         "timestamp_reference": "<optional timestamp or segment name>"
       }
     ]
   }
3. Always validate that exactly 4 distinct options are provided for each question, with the correct index properly mapped (0 to 3).
4. Persist the generated quiz collection object ONLY in Firestore database by invoking `store_quiz_schema_in_firestore(session_id=..., quiz_data_json=...)`. DO NOT upload the quiz collection or quiz questions to the Cloud Storage bucket.
5. Return a friendly summary and the generated quiz structure to the coordinator.""",
    tools=[
        store_quiz_schema_in_firestore,
        get_session_quiz_from_firestore,
        read_session_material_from_gcs,
    ],
)

# 3. Coordinator Agent: Orchestrates the workflow between breakdown, input material uploads, and quiz creation
coordinator_agent = Agent(
    name="coordinator_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the SessionIQ Lead Coordinator.
Your mission is to orchestrate the end-to-end transformation of recorded and live session content and input materials into multiplayer quiz games.

Storage Policy:
- Input files (videos, audio transcripts, source notes) are stored ONLY in Google Cloud Storage bucket partitioned by `sessions/{session_id}/input_materials/`.
- Quiz collection objects, questions, answers, and schemas are stored ONLY in the Firestore database (`/sessions/{session_id}/quizzes/{difficulty}`). Never upload the quiz schema to GCS.

Your Workflow:
1. When a user uploads or supplies session input files (transcripts, notes, media logs):
   - Identify or create the `session_id`.
   - Ensure the raw input file is uploaded to the Google Cloud Storage bucket using `upload_session_material_to_gcs` under `sessions/{session_id}/input_materials/`.
2. When the user requests quiz generation:
   - Identify the requested difficulty level ('simple', 'medium', 'hard').
   - Delegate breakdown of the input files to `media_breakdown_agent`.
   - Delegate quiz generation to `quiz_generator_agent`, which saves the quiz object exclusively into Firestore database.
3. Provide the user with:
   - Confirmation of input file saved to GCS bucket (`gs://<bucket>/sessions/<session_id>/...`).
   - Confirmation of quiz collection saved to Firestore database.
   - Preview of the quiz questions.
   - Ready-to-play invitation for the multiplayer quiz lobby.""",
    sub_agents=[media_breakdown_agent, quiz_generator_agent],
    tools=[
        upload_session_material_to_gcs,
        read_session_material_from_gcs,
        list_session_files,
        store_quiz_schema_in_firestore,
        get_session_quiz_from_firestore,
    ],
)

app = App(
    root_agent=coordinator_agent,
    name="sessioniq",
)
