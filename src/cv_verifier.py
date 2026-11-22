import hashlib
import os
import urllib.request
import uuid
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
import pyodbc
from db_connection import get_sql_connection


MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

COSINE_THRESHOLD = 0.363


def ensure_models() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if not YUNET_PATH.exists():
        print("Downloading YuNet face detection model...")
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
    if not SFACE_PATH.exists():
        print("Downloading SFace recognition model...")
        urllib.request.urlretrieve(SFACE_URL, SFACE_PATH)


def capture_frame(image_path: Optional[str] = None) -> np.ndarray:
    if image_path:
        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Could not read image at {image_path}")
        return frame

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Webcam unavailable. Pass image_path for offline testing.")

    print("Position face in front of camera. Press SPACE to capture or ESC to cancel.")
    captured = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow("Nova Biometric Gate", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 32:
            captured = frame.copy()
            break
        if key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    if captured is None:
        raise RuntimeError("Capture cancelled or failed.")
    return captured


def extract_face_embedding(frame: np.ndarray) -> tuple[np.ndarray, str]:
    ensure_models()
    h, w = frame.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_PATH), "", (w, h), score_threshold=0.7, nms_threshold=0.3
    )
    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        raise ValueError("No face detected in frame.")

    primary_face = max(faces, key=lambda f: f[2] * f[3])
    recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
    aligned_face = recognizer.alignCrop(frame, primary_face)
    feature = recognizer.feature(aligned_face).astype(np.float32).flatten()

    _, encoded_img = cv2.imencode(".png", frame)
    frame_sha256 = hashlib.sha256(encoded_img.tobytes()).hexdigest()
    return feature, frame_sha256


def compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    ensure_models()
    recognizer = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
    score = float(
        recognizer.match(
            vec_a.reshape(1, -1),
            vec_b.reshape(1, -1),
            cv2.FaceRecognizerSF_FR_COSINE,
        )
    )
    return round(max(0.0, min(1.0, score)), 4)


def enroll_operative(employee_id: str, image_path: Optional[str] = None) -> None:
    frame = capture_frame(image_path)
    embedding, _ = extract_face_embedding(frame)
    payload_bytes = embedding.tobytes()
    reference_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    biometric_id = f"BIO-{uuid.uuid4().hex[:12].upper()}"

    with get_sql_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "{CALL api.usp_enroll_operative_biometric (?, ?, ?, ?, ?)}",
            (
                biometric_id,
                employee_id,
                "OPENCV_SFACE_V1",
                reference_sha256,
                pyodbc.Binary(payload_bytes),
            ),
        )
        conn.commit()
    print(f"Enrolled biometric profile {biometric_id} for {employee_id}.")


def verify_operative_scan(
    employee_id: str,
    asset_id: str,
    source_batch: Optional[str] = None,
    anomaly_id: Optional[str] = None,
    image_path: Optional[str] = None,
) -> dict:
    with get_sql_connection() as conn:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT e.username, r.role_name, b.encoding_payload, b.reference_sha256
            FROM dim.employee e
            JOIN dim.role r ON e.role_id = r.role_id
            LEFT JOIN dim.employee_biometric b
                ON e.employee_id = b.employee_id AND b.is_active = 1
            WHERE e.employee_id = ?
            """,
            (employee_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"Employee {employee_id} not found.")

        username, role_name, stored_payload, stored_sha256 = row
        frame = capture_frame(image_path)
        live_embedding, frame_sha256 = extract_face_embedding(frame)
        verification_id = f"VER-{uuid.uuid4().hex[:12].upper()}"

        if role_name != "Operative" or stored_payload is None:
            confidence = 0.0000
            auth_status = "DENIED_ROLE"
        else:
            stored_bytes = bytes(stored_payload)
            if hashlib.sha256(stored_bytes).hexdigest() != stored_sha256:
                raise RuntimeError("Biometric template integrity check failed (SHA-256 mismatch).")

            ref_embedding = np.frombuffer(stored_bytes, dtype=np.float32)
            confidence = compute_cosine_similarity(ref_embedding, live_embedding)
            auth_status = "VERIFIED" if confidence >= COSINE_THRESHOLD else "REJECTED"

        cursor.execute(
            "{CALL api.usp_record_operative_verification (?, ?, ?, ?, ?, ?, ?, ?)}",
            (
                verification_id,
                employee_id,
                asset_id,
                anomaly_id,
                source_batch,
                confidence,
                auth_status,
                frame_sha256,
            ),
        )

        event_id = f"EVT-{uuid.uuid4().hex[:12].upper()}"
        action_desc = f"CV_VERIFICATION_{auth_status} asset={asset_id} conf={confidence:.4f}"
        query_hash = hashlib.sha256(
            f"{verification_id}:{employee_id}:{frame_sha256}".encode("utf-8")
        ).hexdigest()

        cursor.execute(
            "{CALL api.usp_append_audit_log (?, ?, ?, ?, ?, ?)}",
            (event_id, employee_id, username, role_name, action_desc, query_hash),
        )
        conn.commit()

    return {
        "verification_id": verification_id,
        "employee_id": employee_id,
        "auth_status": auth_status,
        "confidence": confidence,
        "frame_sha256": frame_sha256,
    }


if __name__ == "__main__":
    enroll_operative("EMP-003")
    result = verify_operative_scan("EMP-003", "ASSET-CMP-01", source_batch="BATCH-TEST-001")
    print(result)