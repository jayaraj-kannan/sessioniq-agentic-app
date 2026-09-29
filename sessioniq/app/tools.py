import json
import os
import uuid
import mimetypes
from typing import Dict, Any, Optional
from google.cloud import firestore
from google.cloud import storage

def _get_project_id() -> str:
    # Explicit project ID required for Firestore on Agent Engine
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ca621c40ffa0")
    if not project_id:
        project_id = "qwiklabs-gcp-04-ca621c40ffa0"
    return project_id

def _get_or_create_bucket():
    project_id = _get_project_id()
    bucket_name = f"{project_id}-sessioniq-assets"
    client = storage.Client(project=project_id)
    try:
        bucket = client.get_bucket(bucket_name)
    except Exception:
        bucket = client.create_bucket(bucket_name, location="us-east1")
    return bucket, bucket_name

def upload_session_material_to_gcs(
    session_id: str,
    file_name: str,
    content: str,
    category: str = "materials"
) -> str:
    """Uploads quiz source material, video/audio transcripts, documents, or raw text to GCS under the specific session ID.

    Args:
        session_id: Unique session identifier for the quiz (e.g. 'session-py-101').
        file_name: Name of the file being uploaded (e.g. 'lecture_notes.txt', 'audio_transcript.json', 'quiz_reference.md').
        content: The text content, transcript, or markdown material to upload.
        category: Storage subfolder category, defaults to 'materials' (e.g. 'materials', 'transcripts', 'media').

    Returns:
        JSON string containing the status, GCS URI, bucket path, and file size.
    """
    try:
        bucket, bucket_name = _get_or_create_bucket()
        blob_path = f"sessions/{session_id}/{category}/{file_name}"
        blob = bucket.blob(blob_path)
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_name)
        if not content_type:
            content_type = "text/plain"
            
        blob.upload_from_string(content, content_type=content_type)
        
        # Also register material file in Firestore session document metadata
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        session_ref = db.collection("sessions").document(session_id)
        session_ref.set({
            "session_id": session_id,
            "has_materials": True,
            "last_material_uploaded": file_name,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        gcs_uri = f"gs://{bucket_name}/{blob_path}"
        result = {
            "status": "success",
            "session_id": session_id,
            "file_name": file_name,
            "gcs_uri": gcs_uri,
            "category": category,
            "message": f"Quiz material '{file_name}' saved to GCS under session '{session_id}' and registered in Firestore."
        }
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Failed to upload session material: {str(e)}"})

def read_session_material_from_gcs(session_id: str, file_name: str, category: str = "materials") -> str:
    """Reads back stored quiz material or transcript from Google Cloud Storage for a specific session.

    Args:
        session_id: Unique session identifier.
        file_name: Name of the file to retrieve.
        category: Storage subfolder category (defaults to 'materials').

    Returns:
        The content of the file as text.
    """
    try:
        bucket, _ = _get_or_create_bucket()
        blob_path = f"sessions/{session_id}/{category}/{file_name}"
        blob = bucket.blob(blob_path)
        if not blob.exists():
            return f"File '{blob_path}' not found in bucket."
        return blob.download_as_text()
    except Exception as e:
        return f"Error reading session material from GCS: {str(e)}"

def list_session_files(session_id: str) -> str:
    """Lists all materials, transcripts, and source files stored for a specific session in Google Cloud Storage.

    Args:
        session_id: Unique session identifier.

    Returns:
        JSON array of stored file paths and metadata.
    """
    try:
        bucket, bucket_name = _get_or_create_bucket()
        prefix = f"sessions/{session_id}/"
        blobs = bucket.list_blobs(prefix=prefix)
        file_list = []
        for b in blobs:
            file_list.append({
                "name": b.name.replace(prefix, ""),
                "full_path": b.name,
                "size_bytes": b.size,
                "gcs_uri": f"gs://{bucket_name}/{b.name}",
                "updated": b.updated.isoformat() if b.updated else None
            })
        return json.dumps(file_list)
    except Exception as e:
        return json.dumps({"error": f"Error listing session files: {str(e)}"})

def store_quiz_schema_in_firestore(
    session_id: str,
    quiz_data_json: str
) -> str:
    """Stores the structured quiz schema into Firestore for a given session.

    Args:
        session_id: The unique identifier for the recorded or live session.
        quiz_data_json: A valid JSON string containing the quiz schema (title, difficulty, summary, topics, questions).

    Returns:
        Confirmation status message with session_id.
    """
    try:
        data = json.loads(quiz_data_json) if isinstance(quiz_data_json, str) else quiz_data_json
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        
        session_ref = db.collection("sessions").document(session_id)
        difficulty = data.get("difficulty", "medium")
        
        # Store metadata under session document
        session_ref.set({
            "session_id": session_id,
            "title": data.get("title", f"Session {session_id}"),
            "latest_difficulty": difficulty,
            "summary": data.get("summary", ""),
            "topics": data.get("topics", []),
            "question_count": len(data.get("questions", [])),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        
        # Save specific quiz set in the quizzes subcollection
        session_ref.collection("quizzes").document(difficulty).set(data)
        
        return f"Successfully stored quiz schema for session '{session_id}' at difficulty '{difficulty}' in Firestore."
    except Exception as e:
        return f"Error storing quiz schema in Firestore: {str(e)}"

def get_session_quiz_from_firestore(session_id: str, difficulty: Optional[str] = "medium") -> str:
    """Retrieves the quiz schema for a session from Firestore.

    Args:
        session_id: The unique identifier for the recorded or live session.
        difficulty: The quiz difficulty level (simple, medium, or hard).

    Returns:
        JSON string of the quiz schema or not found message.
    """
    try:
        project_id = _get_project_id()
        db = firestore.Client(project=project_id)
        doc = db.collection("sessions").document(session_id).collection("quizzes").document(difficulty).get()
        if doc.exists:
            return json.dumps(doc.to_dict())
        
        parent_doc = db.collection("sessions").document(session_id).get()
        if parent_doc.exists:
            return json.dumps(parent_doc.to_dict())
        return f"No quiz found for session '{session_id}' with difficulty '{difficulty}'."
    except Exception as e:
        return f"Error retrieving quiz from Firestore: {str(e)}"
