import os

# Reduce TensorFlow console noise (DeepFace imports TF internally)
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


def load_local_env(env_path):
    """Minimal .env loader to avoid extra dependency."""
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f".env load warning: {e}")

import warnings
warnings.filterwarnings("ignore", message=r".*oneDNN custom operations are on.*")
warnings.filterwarnings("ignore", message=r".*deprecated.*sparse_softmax_cross_entropy.*")

import logging
logging.getLogger("tensorflow").setLevel(logging.ERROR)

import serial
import sqlite3
import threading
import time
import queue
import cv2
import numpy as np
import json
import re
import shutil
import subprocess
import tempfile
import mimetypes
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, abort, Response, send_file)
from werkzeug.middleware.proxy_fix import ProxyFix
from deepface import DeepFace
from test_gmail import send_dual_alert

app = Flask(__name__)
TYPE_SAFE_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_local_env(os.path.join(TYPE_SAFE_BASE_DIR, ".env"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_me_secret_key")
# Render (and other HTTPS proxies) terminate TLS in front of the app.
if os.getenv("RENDER"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

# --- CONFIGURATION ---
SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3").strip()
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200").strip() or "115200")
_db_name = os.getenv("DB_NAME", "radar.db").strip() or "radar.db"
DB_NAME = _db_name if os.path.isabs(_db_name) else os.path.join(TYPE_SAFE_BASE_DIR, _db_name)
SAVE_DIR = os.path.join(TYPE_SAFE_BASE_DIR, "static", "captures")
RECORDINGS_DIR = os.path.join(TYPE_SAFE_BASE_DIR, "static", "recordings")
KNOWN_FACES_DIR = os.path.join(TYPE_SAFE_BASE_DIR, "known_faces")
MIN_DIST_TRIGGER = 20  # cm
COOLDOWN = 5  # Seconds between captures
RECORDING_DURATION = 3  # Seconds for each recording clip
INTRUDER_ALERT_COOLDOWN = 60  # Seconds between alerts for same user
# Recognition: Facenet512 is fast; ArcFace is stronger but heavier (override via .env).
FACE_MODEL_NAME = os.getenv("FACE_MODEL_NAME", "Facenet512").strip() or "Facenet512"
FACE_DISTANCE_METRIC = os.getenv("FACE_DISTANCE_METRIC", "cosine").strip() or "cosine"
try:
    from deepface.modules import verification as _verif_mod

    _MODEL_THRESHOLD_DEFAULT = float(
        _verif_mod.find_threshold(FACE_MODEL_NAME, FACE_DISTANCE_METRIC)
    )
except Exception:
    _MODEL_THRESHOLD_DEFAULT = 0.30
FACE_ACCEPT_THRESHOLD = float(
    os.getenv("FACE_ACCEPT_THRESHOLD", str(_MODEL_THRESHOLD_DEFAULT)).strip()
    or str(_MODEL_THRESHOLD_DEFAULT)
)
# Ambiguity: only reject when the two closest identities are different people.
FACE_MARGIN_THRESHOLD = float(os.getenv("FACE_MARGIN_THRESHOLD", "0.02").strip() or "0.02")
# Order: fast detectors first for live recognition (override via .env for max accuracy).
_det_chain = os.getenv("FACE_DETECTOR_CHAIN", "opencv,mtcnn,retinaface").strip()
FACE_DETECTOR_CHAIN = [b.strip() for b in _det_chain.split(",") if b.strip()]
if not FACE_DETECTOR_CHAIN:
    FACE_DETECTOR_CHAIN = ["opencv", "mtcnn", "retinaface"]
FACE_DETECTOR_BACKEND = FACE_DETECTOR_CHAIN[0]
# Downscale large captures before DeepFace (major CPU win).
MAX_FACE_INFER_EDGE = int(os.getenv("MAX_FACE_INFER_EDGE", "640").strip() or "640")
FACE_ENFORCE_DETECTION = os.getenv("FACE_ENFORCE_DETECTION", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
FACE_ALIGN = os.getenv("FACE_ALIGN", "1").strip().lower() not in ("0", "false", "no")
FACE_MIN_CONFIDENCE = float(os.getenv("FACE_MIN_CONFIDENCE", "0.75").strip() or "0.75")
FACE_MIN_AREA_RATIO = float(os.getenv("FACE_MIN_AREA_RATIO", "0.012").strip() or "0.012")
FACE_RETRY_COUNT = int(os.getenv("FACE_RETRY_COUNT", "2").strip() or "2")
FACE_RETRY_DELAY_SEC = float(os.getenv("FACE_RETRY_DELAY_SEC", "0.08").strip() or "0.08")
FACE_ANALYZE_STRIDE = 2
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "").strip()
ALERT_PHONE_TO = os.getenv("ALERT_PHONE_TO", "").strip()
# Safety net if the recognition worker crashes (keep > typical DeepFace latency on your PC).
PROCESSING_STALE_SECONDS = int(os.getenv("PROCESSING_STALE_SECONDS", "120").strip() or "120")

# Ensure directories exist
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

# Global variables
current_data = {'angle': 90, 'distance': 0}
last_capture_time = 0
latest_frame = None
camera_active = False
camera_cap = None  # Store camera capture object globally
current_user_id = None
user_lock = threading.Lock()
db_lock = threading.Lock()
serial_last_update = 0.0  # last time we received real radar data
last_frame_time = 0.0  # last time we received a camera frame
last_alert_time_by_user = {}
capture_queue = queue.Queue(maxsize=16)
recognition_queue = queue.Queue(maxsize=24)


# --- DATABASE HELPER ---
_db_init_lock = threading.Lock()
_db_initialized = False


def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30, check_same_thread=False)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except sqlite3.Error:
        conn.execute('PRAGMA journal_mode=DELETE')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def valid_password(password):
    """Login/register policy: 8–12 characters inclusive."""
    if not password:
        return False
    return 8 <= len(password) <= 12


def normalize_gmail_address(value):
    email = (value or "").strip().lower()
    if not email:
        return ""
    if not re.fullmatch(r"[a-z0-9._%+\-]+@gmail\.com", email):
        return ""
    return email


def parse_history_date(arg):
    """Return YYYY-MM-DD if valid, else None."""
    if not arg:
        return None
    s = arg.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        return s
    return None


def _ffmpeg_encode_h264_mp4(frames, out_path, fps=20):
    """Encode frames to H.264 MP4 using ffmpeg (browser-playable). Returns True on success."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not frames:
        return False
    try:
        tmp = tempfile.mkdtemp(prefix='rec_clip_')
        try:
            for i, frame in enumerate(frames):
                p = os.path.join(tmp, f'f{i:05d}.jpg')
                cv2.imwrite(p, frame)
            # yuv420p + faststart: reliable in Chrome/Edge/Firefox
            cmd = [
                ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
                '-framerate', str(fps), '-i', os.path.join(tmp, 'f%05d.jpg'),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                out_path,
            ]
            run_kw = {'check': True, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
            if os.name == 'nt':
                run_kw['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.run(cmd, **run_kw)
            return os.path.exists(out_path) and os.path.getsize(out_path) > 1000
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        print(f"ffmpeg encode failed: {e}")
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except OSError:
            pass
    return False

# --- DATABASE SETUP ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Ensure user ids are never reused (AUTOINCREMENT guarantees monotonic rowid)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            alert_gmail TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            person_name TEXT,
            image_path TEXT,
            recording_path TEXT,
            angle INTEGER,
            distance INTEGER,
            user_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS face_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            person_name TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, person_name),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    # Migration for old databases
    for col, ctype in {'angle': 'INTEGER', 'distance': 'INTEGER', 'person_name': 'TEXT',
                        'user_id': 'INTEGER', 'recording_path': 'TEXT', 'model_distance': 'REAL',
                        'model_threshold': 'REAL', 'review_status': 'INTEGER DEFAULT 0',
                        'review_comment': 'TEXT'}.items():
        try:
            c.execute(f"ALTER TABLE logs ADD COLUMN {col} {ctype}")
            print(f"  Migrated: added '{col}'")
        except sqlite3.OperationalError:
            pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN alert_gmail TEXT")
        print("  Migrated: added users.alert_gmail")
    except sqlite3.OperationalError:
        pass
    conn.commit()

    # Migration: upgrade legacy `users` table (without AUTOINCREMENT) to guarantee non-reuse of ids
    try:
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        row = c.fetchone()
        users_sql = (row[0] or "") if row else ""
        if "AUTOINCREMENT" not in users_sql.upper():
            c.execute("BEGIN")
            c.execute("ALTER TABLE users RENAME TO users_old")
            c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, alert_gmail TEXT)")
            old_cols = [r[1] for r in c.execute("PRAGMA table_info(users_old)").fetchall()]
            if "alert_gmail" in old_cols:
                c.execute("""INSERT INTO users (id, username, password, alert_gmail)
                             SELECT id, username, password, alert_gmail FROM users_old""")
            else:
                c.execute("""INSERT INTO users (id, username, password, alert_gmail)
                             SELECT id, username, password, '' FROM users_old""")
            c.execute("DROP TABLE users_old")
            c.execute("COMMIT")
            conn.commit()
            print("  Migrated: upgraded users.id to AUTOINCREMENT")
    except Exception as e:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        print(f"  Migration warning (users AUTOINCREMENT): {e}")

    conn.close()
    print("Database initialized")


def ensure_db():
    """Create tables on first use. Required for gunicorn (skips `if __name__ == '__main__'`)."""
    global _db_initialized
    if _db_initialized:
        return
    with _db_init_lock:
        if _db_initialized:
            return
        init_db()
        _db_initialized = True


def get_user_alert_gmail(user_id):
    try:
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT alert_gmail FROM users WHERE id=?", (user_id,))
            row = c.fetchone()
            conn.close()
        return normalize_gmail_address(row[0] if row else "")
    except Exception:
        return ""


def reconcile_stale_processing_logs():
    """Mark stale Processing rows to avoid permanent 'Analyzing...' status."""
    try:
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                """
                UPDATE logs
                SET event_type='Intruder Detected',
                    person_name='Intruder',
                    model_threshold=?
                WHERE (event_type='Processing' OR person_name='Analyzing...')
                  AND created_at <= datetime('now', ?)
                """,
                (FACE_ACCEPT_THRESHOLD, f"-{int(PROCESSING_STALE_SECONDS)} seconds")
            )
            changed = c.rowcount
            conn.commit()
            conn.close()
        if changed:
            print(f"Recovered {changed} stale processing log(s).")
    except Exception as e:
        print(f"Stale log reconciliation warning: {e}")


def stale_processing_sweeper():
    while True:
        reconcile_stale_processing_logs()
        time.sleep(30)


def invalidate_user_face_cache(user_id):
    user_known_dir = os.path.join(KNOWN_FACES_DIR, str(user_id))
    if not os.path.isdir(user_known_dir):
        return
    for fn in os.listdir(user_known_dir):
        if fn.lower().startswith("representations_") and fn.lower().endswith(".pkl"):
            try:
                os.remove(os.path.join(user_known_dir, fn))
            except OSError:
                pass


def warm_user_face_index(user_id):
    """Rebuild embeddings cache in background so first live detection is faster."""

    def _run():
        try:
            root = os.path.join(KNOWN_FACES_DIR, str(user_id))
            if not os.path.isdir(root):
                return
            sample = None
            for dirpath, _, files in os.walk(root):
                for fn in files:
                    if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                        sample = os.path.join(dirpath, fn)
                        break
                if sample:
                    break
            if not sample:
                return
            DeepFace.find(
                img_path=sample,
                db_path=root,
                model_name=FACE_MODEL_NAME,
                distance_metric=FACE_DISTANCE_METRIC,
                detector_backend=FACE_DETECTOR_CHAIN[0],
                enforce_detection=FACE_ENFORCE_DETECTION,
                align=FACE_ALIGN,
                silent=True,
            )
        except Exception as e:
            print(f"Face index warmup warning: {e}")

    threading.Thread(target=_run, daemon=True).start()


def count_enrolled_profiles(user_id):
    """Number of trained identities with at least one face image on disk."""
    return len(list_known_people(user_id))


def sanitize_person_name(name):
    clean = (name or "").strip().replace("/", "").replace("\\", "").replace("..", "")
    return clean


def list_known_people(user_id):
    user_root = os.path.join(KNOWN_FACES_DIR, str(user_id))
    people = []
    if not os.path.isdir(user_root):
        return people
    try:
        for person in sorted(os.listdir(user_root)):
            person_dir = os.path.join(user_root, person)
            if not os.path.isdir(person_dir):
                continue
            images = []
            for fn in sorted(os.listdir(person_dir)):
                if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    rel = f"{user_id}/{person}/{fn}"
                    images.append({"file": fn, "path": rel})
            if not images:
                continue
            people.append({"name": person, "count": len(images), "images": images})
    except Exception as e:
        print(f"Known people listing warning: {e}")
    return people


def get_person_adaptive_threshold(user_id, person_name):
    """
    Adaptive threshold per identity:
    - More dislikes => tighten threshold (reduce false accepts)
    - More likes => allow slightly easier match
    """
    person_name = (person_name or "").strip()
    if not person_name:
        return FACE_ACCEPT_THRESHOLD
    likes = dislikes = 0
    try:
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT likes, dislikes FROM face_feedback WHERE user_id=? AND person_name=?",
                      (user_id, person_name))
            row = c.fetchone()
            conn.close()
        if row:
            likes, dislikes = int(row[0] or 0), int(row[1] or 0)
    except Exception:
        pass
    th = float(FACE_ACCEPT_THRESHOLD)
    adjusted = th + (likes * 0.012) - (dislikes * 0.028)
    lo = max(0.04, th * 0.82)
    hi = min(0.95, th * 1.14)
    return float(min(hi, max(lo, adjusted)))


# --- CAMERA THREAD ---
def camera_loop():
    global latest_frame, camera_active, camera_cap, last_frame_time
    print("Initializing Camera...")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera Error: Could not open camera.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    camera_cap = cap
    camera_active = True
    print("Camera Active")

    while True:
        try:
            ret, frame = cap.read()
            if ret:
                latest_frame = frame.copy()
                last_frame_time = time.time()
            else:
                time.sleep(0.5)
            time.sleep(0.03)
        except Exception as e:
            print(f"Camera Error: {e}")
            break


# --- FACE RECOGNITION ---
def identify_person(img_path, user_id):
    result = {
        "name": None,
        "distance": None,
        "threshold": FACE_ACCEPT_THRESHOLD,
        "reason": "no_match",
    }
    tmp_scaled = None
    try:
        user_dir = os.path.join(KNOWN_FACES_DIR, str(user_id))
        if not os.path.exists(user_dir) or not os.listdir(user_dir):
            result["reason"] = "empty_db"
            return result
        img = cv2.imread(img_path)
        if img is None:
            result["reason"] = "bad_image"
            return result
        work_path = img_path
        if MAX_FACE_INFER_EDGE > 0:
            h0, w0 = img.shape[:2]
            m0 = max(h0, w0)
            if m0 > MAX_FACE_INFER_EDGE:
                scale = MAX_FACE_INFER_EDGE / float(m0)
                img = cv2.resize(img, (int(w0 * scale), int(h0 * scale)))
                fd, tmp_scaled = tempfile.mkstemp(prefix="infer_", suffix=".jpg")
                os.close(fd)
                cv2.imwrite(tmp_scaled, img)
                work_path = tmp_scaled
        img_area = float(img.shape[0] * img.shape[1])
        dedup_backends = []
        for backend in FACE_DETECTOR_CHAIN:
            if backend not in dedup_backends:
                dedup_backends.append(backend)

        faces = None
        active_backend = dedup_backends[0]
        for backend in dedup_backends:
            try:
                current_faces = DeepFace.extract_faces(
                    img_path=work_path,
                    detector_backend=backend,
                    enforce_detection=FACE_ENFORCE_DETECTION,
                    align=FACE_ALIGN,
                )
                if current_faces:
                    faces = current_faces
                    active_backend = backend
                    break
            except Exception:
                continue

        if not faces:
            result["reason"] = "no_face"
            return result

        def _face_ok(fdict):
            conf_raw = fdict.get("confidence")
            if conf_raw is None:
                conf = 1.0
            else:
                try:
                    conf = float(conf_raw)
                except (TypeError, ValueError):
                    conf = 1.0
            if conf > 1.0:
                conf = conf / 100.0
            area = fdict.get("facial_area") or {}
            w = float(area.get("w", 0.0) or 0.0)
            h = float(area.get("h", 0.0) or 0.0)
            area_ratio = ((w * h) / img_area) if img_area > 0 else 1.0
            area_ratio_ok = area_ratio >= FACE_MIN_AREA_RATIO
            if not area_ratio_ok:
                return False
            if len(faces) == 1:
                return True
            return conf >= FACE_MIN_CONFIDENCE

        accepted_faces = [f for f in faces if _face_ok(f)]
        if not accepted_faces:
            result["reason"] = "low_face_confidence"
            return result

        dfs = DeepFace.find(
            img_path=work_path,
            db_path=user_dir,
            model_name=FACE_MODEL_NAME,
            distance_metric=FACE_DISTANCE_METRIC,
            detector_backend=active_backend,
            enforce_detection=FACE_ENFORCE_DETECTION,
            align=FACE_ALIGN,
            silent=True
        )
        if len(dfs) == 0 or dfs[0].empty:
            result["reason"] = "empty_results"
            return result

        results = dfs[0].sort_values(by="distance", ascending=True).reset_index(drop=True)
        best = results.iloc[0]
        best_dist = float(best["distance"])
        person_name = os.path.basename(os.path.dirname(best["identity"]))
        adaptive_threshold = get_person_adaptive_threshold(user_id, person_name)
        result["distance"] = best_dist
        result["threshold"] = adaptive_threshold

        # Only treat as ambiguous when two different identities are similarly close.
        if len(results) > 1:
            second_dist = float(results.iloc[1]["distance"])
            second_name = os.path.basename(os.path.dirname(results.iloc[1]["identity"]))
            if (
                second_name != person_name
                and abs(second_dist - best_dist) < FACE_MARGIN_THRESHOLD
            ):
                result["reason"] = "low_margin"
                return result

        if best_dist <= adaptive_threshold:
            result["name"] = person_name
            result["reason"] = "matched"
            return result
    except Exception as e:
        print(f"DeepFace Error: {e}")
        result["reason"] = "exception"
    finally:
        if tmp_scaled and os.path.isfile(tmp_scaled):
            try:
                os.remove(tmp_scaled)
            except OSError:
                pass
    return result


def identify_person_with_retries(frame_for_inference, user_id, user_caps, ts):
    """
    Improves recognition reliability while keeping latency low:
    - Try the current frame first
    - Retry quickly with a fresh frame if first pass misses
    """
    attempts = max(1, int(FACE_RETRY_COUNT))
    best_unknown = {"name": None, "distance": None, "threshold": FACE_ACCEPT_THRESHOLD, "reason": "no_match"}

    for attempt in range(attempts):
        attempt_frame = frame_for_inference
        if attempt > 0 and latest_frame is not None:
            try:
                attempt_frame = latest_frame.copy()
            except Exception:
                attempt_frame = frame_for_inference

        scale = 0.92 if attempt == 0 else 1.0
        infer_frame = cv2.resize(attempt_frame, (0, 0), fx=scale, fy=scale)
        tmp_infer = os.path.join(user_caps, f"infer_{ts}_{attempt}.jpg")
        cv2.imwrite(tmp_infer, infer_frame)
        ident = identify_person(tmp_infer, user_id)
        try:
            os.remove(tmp_infer)
        except OSError:
            pass

        if ident.get("name"):
            return ident

        dist = ident.get("distance")
        best_dist = best_unknown.get("distance")
        if dist is not None and (best_dist is None or dist < best_dist):
            best_unknown = ident

        if attempt < (attempts - 1):
            time.sleep(max(0.0, FACE_RETRY_DELAY_SEC))

    return best_unknown


def maybe_send_intruder_alert(user_id, trigger_angle, trigger_dist, image_path):
    now = time.time()
    last_sent = last_alert_time_by_user.get(user_id, 0.0)
    if (now - last_sent) < INTRUDER_ALERT_COOLDOWN:
        return

    user_alert_email = get_user_alert_gmail(user_id)
    target_email = user_alert_email or ALERT_EMAIL_TO
    if not target_email and not ALERT_PHONE_TO:
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_text = (
        f"INTRUDER ALERT!\n"
        f"Time: {ts}\n"
        f"User ID: {user_id}\n"
        f"Angle: {trigger_angle} deg\n"
        f"Distance: {trigger_dist} cm\n"
        f"Captured image: {image_path}"
    )
    try:
        result = send_dual_alert(
            target_email,
            ALERT_PHONE_TO,
            message_text,
            subject="Intruder Detected - Immediate Action Required",
        )
        print(f"Alert status: {result}")
        # Apply cooldown only when at least one channel succeeds.
        if bool(result.get("email_ok")) or bool(result.get("sms_ok")):
            last_alert_time_by_user[user_id] = now
        else:
            print("Alert warning: both email and SMS failed; cooldown not applied.")
    except Exception as e:
        print(f"Alert dispatch failed: {e}")


# --- VIDEO RECORDING (3-second clip: prefer H.264 MP4 via ffmpeg for browser playback) ---
def record_clip(user_id, timestamp_str):
    """Record ~3s clip: try ffmpeg H.264 MP4 first, then MJPEG AVI, then frame-sequence player."""
    try:
        user_rec_dir = os.path.join(RECORDINGS_DIR, str(user_id))
        os.makedirs(user_rec_dir, exist_ok=True)

        # Collect frames for 3 seconds
        frames = []
        print("Recording started...")
        start = time.time()
        while time.time() - start < RECORDING_DURATION:
            if latest_frame is not None:
                frames.append(latest_frame.copy())
            time.sleep(0.05)  # ~20 fps

        if not frames:
            print("Recording error: no frames captured")
            return None

        print(f"Captured {len(frames)} frames, saving video...")

        # Get actual frame dimensions from first frame
        h, w = frames[0].shape[:2]
        writer_fps = max(int(round(len(frames) / RECORDING_DURATION)), 10)

        # 1) Browser-friendly H.264 MP4 (requires ffmpeg in PATH)
        h264_name = f"rec_{timestamp_str}_h264.mp4"
        h264_path = os.path.join(user_rec_dir, h264_name)
        if _ffmpeg_encode_h264_mp4(frames, h264_path, fps=writer_fps):
            print(f"Recording saved (H.264): {h264_name}")
            return f"{user_id}/{h264_name}"

        # If ffmpeg isn't available, browser playback of OpenCV-created AVI/MP4 is unreliable.
        # Prefer the frame-sequence fallback, which the UI can always play.
        if not shutil.which('ffmpeg'):
            print("ℹ️  ffmpeg not found: saving frame-sequence for reliable browser playback.")
            raise RuntimeError("ffmpeg_missing_use_frames")

        # 2) OpenCV fallbacks (should be rare when ffmpeg is installed)
        codec_attempts = [
            ('MJPG', '.avi'),
            ('XVID', '.avi'),
            ('mp4v', '.mp4'),
        ]

        for codec_name, ext in codec_attempts:
            filename = f"rec_{timestamp_str}{ext}"
            filepath = os.path.join(user_rec_dir, filename)
            db_path = f"{user_id}/{filename}"

            try:
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                out = cv2.VideoWriter(filepath, fourcc, float(writer_fps), (w, h))

                if not out.isOpened():
                    continue

                for frame in frames:
                    resized = cv2.resize(frame, (w, h)) if frame.shape[:2] != (h, w) else frame
                    out.write(resized)

                out.release()

                # Verify the file was actually written
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                    print(f"Recording saved: {filename} ({len(frames)} frames, codec={codec_name})")
                    return db_path
                else:
                    # File too small, codec didn't work
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    continue

            except Exception as e:
                print(f"  Codec {codec_name} failed: {e}")
                if os.path.exists(filepath):
                    os.remove(filepath)
                continue

        # Last resort: save individual frames as JPEG sequence for JS playback
        print("Saving frame sequence as fallback...")
        frames_dir = os.path.join(user_rec_dir, f"rec_{timestamp_str}_frames")
        os.makedirs(frames_dir, exist_ok=True)

        # Save every 2nd frame for smoother playback vs every 3rd
        saved_frames = []
        for i, frame in enumerate(frames):
            if i % 2 == 0:
                fname = f"frame_{i:04d}.jpg"
                cv2.imwrite(os.path.join(frames_dir, fname), frame)
                saved_frames.append(fname)

        # Create a manifest JSON for the JS player
        manifest = {
            'type': 'frame_sequence',
            'frames': saved_frames,
            'fps': (len(saved_frames) / RECORDING_DURATION) if saved_frames else 10,
            'duration': RECORDING_DURATION
        }
        manifest_path = os.path.join(frames_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f)

        db_path = f"{user_id}/rec_{timestamp_str}_frames/manifest.json"
        print(f"Frame sequence saved: {len(saved_frames)} frames")
        return db_path

    except Exception as e:
        # If we intentionally forced the frame-sequence path, do it here.
        if str(e) == "ffmpeg_missing_use_frames":
            try:
                user_rec_dir = os.path.join(RECORDINGS_DIR, str(user_id))
                frames_dir = os.path.join(user_rec_dir, f"rec_{timestamp_str}_frames")
                os.makedirs(frames_dir, exist_ok=True)

                saved_frames = []
                for i, frame in enumerate(frames):
                    if i % 2 == 0:
                        fname = f"frame_{i:04d}.jpg"
                        cv2.imwrite(os.path.join(frames_dir, fname), frame)
                        saved_frames.append(fname)

                manifest = {
                    'type': 'frame_sequence',
                    'frames': saved_frames,
                    'fps': (len(saved_frames) / RECORDING_DURATION) if saved_frames else 10,
                    'duration': RECORDING_DURATION
                }
                with open(os.path.join(frames_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
                    json.dump(manifest, f)

                print(f"Frame sequence saved: {len(saved_frames)} frames")
                return f"{user_id}/rec_{timestamp_str}_frames/manifest.json"
            except Exception as e2:
                print(f"Recording fallback error: {e2}")
                return None

        print(f"Recording error: {e}")
        return None


# --- RECORDING FALLBACK: generate frame-sequence manifest for any recording ---
def _video_to_frame_manifest(video_fp, out_dir, duration_s=RECORDING_DURATION):
    """
    Convert a recording file to a frame-sequence manifest for reliable browser playback.
    Returns absolute path to manifest.json on success, else None.
    """
    try:
        if not os.path.isfile(video_fp):
            return None

        os.makedirs(out_dir, exist_ok=True)
        manifest_fp = os.path.join(out_dir, "manifest.json")
        # Cache: if manifest already exists and is newer than the video, reuse it.
        try:
            if os.path.isfile(manifest_fp) and os.path.getmtime(manifest_fp) >= os.path.getmtime(video_fp):
                return manifest_fp
        except OSError:
            pass

        cap = cv2.VideoCapture(video_fp)
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if fps <= 0 or fps > 240:
            fps = 20.0

        # Save ~20fps equivalent by skipping frames if needed
        target_fps = 20.0
        stride = max(int(round(fps / target_fps)), 1)

        saved_frames = []
        frame_idx = 0
        saved_idx = 0
        t_start = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame_idx % stride) == 0:
                fname = f"frame_{saved_idx:04d}.jpg"
                out_fp = os.path.join(out_dir, fname)
                cv2.imwrite(out_fp, frame)
                saved_frames.append(fname)
                saved_idx += 1
            frame_idx += 1

            # Safety: recordings are expected to be ~3 seconds; stop early if we exceed that.
            if (time.time() - t_start) > max(float(duration_s) + 1.0, 4.0):
                break

        cap.release()

        if not saved_frames:
            return None

        manifest = {
            "type": "frame_sequence",
            "frames": saved_frames,
            "fps": min(target_fps, len(saved_frames) / max(float(duration_s), 0.1)),
            "duration": float(duration_s),
        }
        with open(manifest_fp, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        return manifest_fp
    except Exception as e:
        print(f"Manifest generation error: {e}")
        return None


# --- CAPTURE & DETECT LOGIC ---
def _finalize_log_row(
    log_id,
    user_id,
    event_type,
    person_name,
    model_distance=None,
    model_threshold=None,
    only_if_processing=True,
):
    """
    If only_if_processing is True, only update rows still in 'Processing' state.
    This avoids racing the stale-log sweeper or double-finalize.
    """
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        if only_if_processing:
            c.execute(
                """UPDATE logs
                   SET event_type=?, person_name=?, model_distance=?, model_threshold=?
                   WHERE id=? AND user_id=? AND event_type='Processing'""",
                (event_type, person_name, model_distance, model_threshold, log_id, user_id),
            )
        else:
            c.execute(
                """UPDATE logs
                   SET event_type=?, person_name=?, model_distance=?, model_threshold=?
                   WHERE id=? AND user_id=?""",
                (event_type, person_name, model_distance, model_threshold, log_id, user_id),
            )
        changed = c.rowcount
        conn.commit()
        conn.close()
    return changed > 0


def _set_log_recording_path(log_id, user_id, recording_path):
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE logs SET recording_path=? WHERE id=? AND user_id=?",
            (recording_path, log_id, user_id),
        )
        conn.commit()
        conn.close()


def _run_recognition_job(job):
    """Runs DeepFace in the background so capture/record is never blocked for minutes."""
    log_id, user_id, img_path, user_caps, ts, trigger_angle, trigger_dist, db_img = job
    try:
        frame = cv2.imread(img_path)
        if frame is None:
            if _finalize_log_row(
                log_id,
                user_id,
                "Intruder Detected",
                "Intruder",
                None,
                FACE_ACCEPT_THRESHOLD,
            ):
                maybe_send_intruder_alert(user_id, trigger_angle, trigger_dist, db_img)
            return
        try:
            ident = identify_person_with_retries(frame, user_id, user_caps, ts)
        except Exception as e:
            print(f"Recognition error: {e}")
            ident = {"name": None, "distance": None, "threshold": FACE_ACCEPT_THRESHOLD}

        name = ident.get("name")
        event_type = "Known Person" if name else "Intruder Detected"
        if not name:
            name = "Intruder"
        if not _finalize_log_row(
            log_id,
            user_id,
            event_type,
            name,
            ident.get("distance"),
            ident.get("threshold"),
        ):
            return
        print(f"Log #{log_id}: {event_type} - {name}")
        if event_type == "Intruder Detected":
            maybe_send_intruder_alert(user_id, trigger_angle, trigger_dist, db_img)
    except Exception as e:
        print(f"Recognition job failed: {e}")


def recognition_worker():
    while True:
        try:
            job = recognition_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            _run_recognition_job(job)
        except Exception as e:
            print(f"recognition_worker: {e}")
        finally:
            try:
                recognition_queue.task_done()
            except Exception:
                pass


def capture_logic(trigger_angle, trigger_dist):
    global last_capture_time

    # Wait for camera frame
    wait_start = time.time()
    while latest_frame is None and (time.time() - wait_start) < 2:
        time.sleep(0.1)

    if latest_frame is None:
        print("No camera frame available.")
        return

    with user_lock:
        active_user_id = current_user_id

    if active_user_id is None:
        print("No active user.")
        return

    log_id = None
    try:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        display_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        user_caps = os.path.join(SAVE_DIR, str(active_user_id))
        os.makedirs(user_caps, exist_ok=True)

        # 1. Save image
        img_name = f"scan_{ts}.jpg"
        img_path = os.path.join(user_caps, img_name)
        db_img = f"{active_user_id}/{img_name}"
        frame_for_inference = latest_frame.copy()
        cv2.imwrite(img_path, frame_for_inference)
        print(f"Image captured: {db_img}")

        # 2. Insert log immediately (fast UI feedback)
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO logs (timestamp, event_type, person_name, image_path,
                         recording_path, angle, distance, user_id) VALUES (?,?,?,?,?,?,?,?)""",
                      (display_time, "Processing", "Analyzing...", db_img, None,
                       trigger_angle, trigger_dist, active_user_id))
            log_id = c.lastrowid
            conn.commit()
            conn.close()
        print(f"Log #{log_id} created")

        # 3. Record clip BEFORE recognition so every event gets media even if DeepFace is slow.
        rec_path = record_clip(active_user_id, ts)
        if rec_path:
            _set_log_recording_path(log_id, active_user_id, rec_path)

        # 4. Queue recognition (non-blocking; avoids "Analyzing" for minutes in one thread)
        job = (
            log_id,
            active_user_id,
            img_path,
            user_caps,
            ts,
            trigger_angle,
            trigger_dist,
            db_img,
        )
        try:
            recognition_queue.put_nowait(job)
        except queue.Full:
            print("Recognition queue full; running recognition inline.")
            _run_recognition_job(job)

    except Exception as e:
        print(f"Capture Error: {e}")
        if log_id is not None:
            try:
                _finalize_log_row(
                    log_id,
                    active_user_id,
                    "Intruder Detected",
                    "Intruder",
                    None,
                    FACE_ACCEPT_THRESHOLD,
                    only_if_processing=True,
                )
            except Exception as inner:
                print(f"Finalize recovery error for log #{log_id}: {inner}")


def capture_worker():
    """Single worker keeps recognition pipeline stable and non-freezing."""
    while True:
        try:
            angle, dist = capture_queue.get()
            capture_logic(angle, dist)
        except Exception as e:
            print(f"Capture worker error: {e}")
        finally:
            try:
                capture_queue.task_done()
            except Exception:
                pass


def enqueue_capture(trigger_angle, trigger_dist):
    global last_capture_time
    now = time.time()
    if now - last_capture_time <= COOLDOWN:
        return
    last_capture_time = now
    try:
        capture_queue.put_nowait((trigger_angle, trigger_dist))
    except queue.Full:
        print("Capture queue full: dropping frame to keep UI responsive.")


# --- SERIAL READER ---
def read_serial():
    global current_data, last_capture_time, serial_last_update
    print(f"Connecting to {SERIAL_PORT}...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"Serial Connected: {SERIAL_PORT}")
    except Exception as e:
        print(f"Serial Error: {e} - Web UI still works without radar.")
        return

    while True:
        try:
            if ser.is_open and ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if ',' in line:
                    parts = line.split(',')
                    if len(parts) == 2:
                        try:
                            angle, dist = int(parts[0]), int(parts[1])
                            current_data = {'angle': angle, 'distance': dist}
                            serial_last_update = time.time()
                            # Only trigger capture when a user is logged in
                            with user_lock:
                                has_user = current_user_id is not None
                            if has_user and 0 < dist < MIN_DIST_TRIGGER:
                                enqueue_capture(angle, dist)
                        except ValueError:
                            pass
            else:
                time.sleep(0.05)
        except Exception as e:
            print(f"Serial Error: {e}")
            time.sleep(1)


def demo_radar_loop():
    """Keeps radar UI animated when no valid serial packets are arriving."""
    global current_data
    while True:
        try:
            now = time.time()
            # If no valid serial update recently, generate demo sweep
            if serial_last_update == 0 or (now - serial_last_update) > 1.5:
                angle = int((now * 45) % 180)  # sweep speed
                # Smooth-ish distance wave: 6..18 cm
                dist = int(12 + 6 * np.sin(now * 2.2))
                dist = max(0, dist)
                current_data = {'angle': angle, 'distance': dist}
        except Exception:
            pass
        time.sleep(0.05)


# --- VIDEO FEED ---
def generate_frames():
    while True:
        try:
            frame = latest_frame
            # If camera hasn't produced frames recently, serve a placeholder image
            if frame is None or (last_frame_time and (time.time() - last_frame_time) > 2.0):
                ph = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(ph, "Camera feed not available", (60, 230),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(ph, "Check permissions / other apps using camera", (30, 270),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2, cv2.LINE_AA)
                frame = ph

            ret, buf = cv2.imencode('.jpg', frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
        except Exception:
            pass
        time.sleep(0.04)


# ========================================
# ROUTES
# ========================================

@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    global current_user_id
    ensure_db()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not valid_password(password):
            flash("Password must be between 8 and 12 characters.")
            return render_template('login.html')
        try:
            with db_lock:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id, username FROM users WHERE username=? AND password=?", (username, password))
                user = c.fetchone()
                conn.close()
        except sqlite3.Error as e:
            print(f"Login DB error: {e}")
            flash("Login failed. Please try again.")
            return render_template('login.html')
        if user:
            session['user'] = user[1]
            session['user_id'] = user[0]
            with user_lock:
                current_user_id = user[0]
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password!")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    ensure_db()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        alert_gmail = normalize_gmail_address(request.form.get('alert_gmail', ''))
        if request.form.get('alert_gmail', '').strip() and not alert_gmail:
            flash("Please enter a valid Gmail address (example@gmail.com).")
            return redirect(url_for('register'))
        if not valid_password(password):
            flash("Password must be between 8 and 12 characters.")
            return redirect(url_for('register'))
        try:
            with db_lock:
                conn = get_db_connection()
                conn.cursor().execute(
                    "INSERT INTO users (username, password, alert_gmail) VALUES (?,?,?)",
                    (username, password, alert_gmail),
                )
                conn.commit()
                conn.close()
            flash("Registration successful! Please log in.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists!")
        except sqlite3.Error as e:
            print(f"Register DB error: {e}")
            flash("Registration failed. Please try again.")
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    global current_user_id
    if 'user' not in session:
        return redirect(url_for('login'))
    if 'user_id' not in session:
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE username=?", (session['user'],))
            u = c.fetchone()
            conn.close()
        if u:
            session['user_id'] = u[0]
            with user_lock:
                current_user_id = u[0]
    return render_template('dashboard.html', username=session['user'])


@app.route('/history')
def history():
    if 'user' not in session or 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    date_arg = request.args.get('date')
    date_filter = parse_history_date(date_arg) if date_arg else None
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        if date_filter:
            c.execute("""SELECT id, timestamp, event_type, person_name, image_path,
                         recording_path, angle, distance, review_status FROM logs
                         WHERE user_id=? AND timestamp LIKE ? ORDER BY id DESC""",
                      (user_id, f"{date_filter}%"))
        else:
            c.execute("""SELECT id, timestamp, event_type, person_name, image_path,
                         recording_path, angle, distance, review_status FROM logs
                         WHERE user_id=? ORDER BY id DESC""", (user_id,))
        logs = c.fetchall()
        conn.close()
    return render_template('history.html', username=session['user'], logs=logs,
                            date_filter=date_filter or '')


@app.route('/reset_my_data', methods=['POST'])
def reset_my_data():
    """Clear this user's logs and their capture/recording files (keeps DB schema and user account)."""
    if 'user' not in session or 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    uid_str = str(user_id)
    with db_lock:
        conn = get_db_connection()
        conn.execute('DELETE FROM logs WHERE user_id=?', (user_id,))
        conn.commit()
        conn.close()
    cap_u = os.path.join(SAVE_DIR, uid_str)
    rec_u = os.path.join(RECORDINGS_DIR, uid_str)
    shutil.rmtree(cap_u, ignore_errors=True)
    shutil.rmtree(rec_u, ignore_errors=True)
    os.makedirs(cap_u, exist_ok=True)
    os.makedirs(rec_u, exist_ok=True)
    flash('Your detection logs, photos, and recordings were cleared. You can start fresh.')
    return redirect(url_for('history'))


@app.route('/train_face', methods=['GET', 'POST'])
def train_face():
    if 'user' not in session or 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    if request.method == 'POST':
        name = sanitize_person_name(request.form.get('name', ''))
        if not name:
            flash("Please enter a valid name.")
            return redirect(url_for('train_face'))

        person_dir = os.path.join(KNOWN_FACES_DIR, str(user_id), name)
        os.makedirs(person_dir, exist_ok=True)
        saved = 0
        for i, f in enumerate(request.files.getlist('photos')):
            if f and f.filename and f.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                f.save(os.path.join(person_dir, f"{name}_{i}_{int(time.time())}.jpg"))
                saved += 1
        if saved:
            flash(f"Successfully trained {saved} images for {name}!")
            invalidate_user_face_cache(user_id)
            warm_user_face_index(user_id)
        else:
            flash("No valid images uploaded.")
        return redirect(url_for('train_face'))
    people = list_known_people(user_id)
    return render_template('train_face.html', people=people)


@app.route('/known_faces/<path:filename>')
def serve_known_face(filename):
    if 'user_id' not in session:
        abort(403)
    user_id = str(session['user_id'])
    try:
        parts = filename.split('/')
        if len(parts) != 3 or parts[0] != user_id:
            abort(403)
        fp = os.path.join(KNOWN_FACES_DIR, parts[0], parts[1], parts[2])
        if os.path.isfile(fp):
            mt = mimetypes.guess_type(fp)[0] or 'image/jpeg'
            return send_file(fp, mimetype=mt)
    except Exception:
        pass
    abort(404)


@app.route('/delete_known_image', methods=['POST'])
def delete_known_image():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = str(session['user_id'])
    person = sanitize_person_name(request.form.get('person'))
    file_name = os.path.basename((request.form.get('file_name') or "").strip())
    if not person or not file_name:
        flash("Invalid image delete request.")
        return redirect(url_for('train_face'))
    fp = os.path.join(KNOWN_FACES_DIR, user_id, person, file_name)
    try:
        if os.path.isfile(fp):
            os.remove(fp)
            invalidate_user_face_cache(user_id)
            person_dir = os.path.join(KNOWN_FACES_DIR, user_id, person)
            remaining = [
                f for f in os.listdir(person_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            if not remaining:
                shutil.rmtree(person_dir, ignore_errors=True)
                try:
                    with db_lock:
                        conn = get_db_connection()
                        conn.execute(
                            "DELETE FROM face_feedback WHERE user_id=? AND person_name=?",
                            (int(user_id), person),
                        )
                        conn.commit()
                        conn.close()
                except Exception as ex:
                    print(f"face_feedback cleanup: {ex}")
            flash(f"Removed image '{file_name}' from {person}.")
        else:
            flash("Image not found.")
    except Exception as e:
        flash(f"Could not remove image: {e}")
    return redirect(url_for('train_face'))


@app.route('/delete_known_person', methods=['POST'])
def delete_known_person():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = str(session['user_id'])
    person = sanitize_person_name(request.form.get('person'))
    if not person:
        flash("Invalid person delete request.")
        return redirect(url_for('train_face'))
    person_dir = os.path.join(KNOWN_FACES_DIR, user_id, person)
    try:
        if os.path.isdir(person_dir):
            shutil.rmtree(person_dir, ignore_errors=True)
            invalidate_user_face_cache(user_id)
            try:
                with db_lock:
                    conn = get_db_connection()
                    conn.execute(
                        "DELETE FROM face_feedback WHERE user_id=? AND person_name=?",
                        (int(user_id), person),
                    )
                    conn.commit()
                    conn.close()
            except Exception as e:
                print(f"face_feedback cleanup: {e}")
            flash(f"Deleted known person '{person}' and all training images.")
        else:
            flash("Person not found.")
    except Exception as e:
        flash(f"Could not delete person: {e}")
    return redirect(url_for('train_face'))


@app.route('/logout')
def logout():
    global current_user_id
    session.clear()
    with user_lock:
        current_user_id = None
    return redirect(url_for('login'))


@app.route('/get_scan')
def get_scan():
    return jsonify(current_data)


@app.route('/video_feed')
def video_feed():
    if 'user' not in session:
        return redirect(url_for('login'))
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/favicon.ico')
def favicon():
    # Avoid noisy 404s during demos if no favicon is provided.
    return ("", 204)


@app.route('/api/status')
def api_status():
    """Quick diagnostic endpoint for demo/debug."""
    with user_lock:
        uid = current_user_id
    return jsonify({
        'camera_active': bool(camera_active),
        'has_frame': latest_frame is not None,
        'last_frame_age_s': (time.time() - last_frame_time) if last_frame_time else None,
        'serial_last_update_age_s': (time.time() - serial_last_update) if serial_last_update else None,
        'current_data': current_data,
        'active_user_id': uid
    })


@app.route('/api/alert_config_status')
def api_alert_config_status():
    if 'user' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_email = get_user_alert_gmail(session['user_id'])
    return jsonify({
        "user_alert_gmail_set": bool(user_email),
        "user_alert_gmail": user_email,
        "fallback_email_to_set": bool(ALERT_EMAIL_TO),
        "phone_to_set": bool(ALERT_PHONE_TO),
        "sender_email_set": bool(os.getenv("ALERT_SENDER_EMAIL", "").strip()),
        "gmail_app_password_set": bool(os.getenv("ALERT_GMAIL_APP_PASSWORD", "").strip()),
        "twilio_sid_set": bool(os.getenv("TWILIO_ACCOUNT_SID", "").strip()),
        "twilio_token_set": bool(os.getenv("TWILIO_AUTH_TOKEN", "").strip()),
        "twilio_phone_set": bool(os.getenv("TWILIO_PHONE_NUMBER", "").strip()),
    })


@app.route('/api/test_alert', methods=['POST'])
def api_test_alert():
    if 'user' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    uid = session['user_id']
    target_email = get_user_alert_gmail(uid) or ALERT_EMAIL_TO
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = (
        "Manual Alert Test\n"
        f"Time: {ts}\n"
        f"User ID: {uid}\n"
        "If you received this, email/SMS alert setup is working."
    )
    try:
        result = send_dual_alert(target_email, ALERT_PHONE_TO, msg, subject="Intruder Alert Test")
        return jsonify({"ok": bool(result.get("email_ok") or result.get("sms_ok")), "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/captures/<path:filename>')
def serve_capture(filename):
    if 'user_id' not in session:
        abort(403)
    user_id = str(session['user_id'])
    try:
        if '/' in filename:
            parts = filename.split('/', 1)
            if parts[0] != user_id:
                abort(403)
            d = os.path.join(SAVE_DIR, parts[0])
            fp = os.path.join(d, parts[1])
            if os.path.isfile(fp):
                mt = mimetypes.guess_type(fp)[0] or 'image/jpeg'
                return send_file(fp, mimetype=mt)
        else:
            d = os.path.join(SAVE_DIR, user_id)
            fp = os.path.join(d, filename)
            if os.path.isfile(fp):
                mt = mimetypes.guess_type(fp)[0] or 'image/jpeg'
                return send_file(fp, mimetype=mt)
    except Exception:
        pass
    abort(404)


@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    if 'user_id' not in session:
        abort(403)
    user_id = str(session['user_id'])
    try:
        if '/' in filename:
            parts = filename.split('/', 1)
            if parts[0] != user_id:
                abort(403)
            fp = os.path.join(RECORDINGS_DIR, parts[0], parts[1])
            if os.path.isfile(fp):
                # Auto-transcode old AVI recordings to browser-playable H.264 MP4 when ffmpeg is available.
                # This fixes "Play" not working for legacy .avi clips.
                if fp.lower().endswith('.avi') and shutil.which('ffmpeg'):
                    mp4_fp = fp[:-4] + "_h264.mp4"
                    if (not os.path.exists(mp4_fp)) or (os.path.getmtime(mp4_fp) < os.path.getmtime(fp)):
                        try:
                            ffmpeg = shutil.which('ffmpeg')
                            cmd = [
                                ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
                                '-i', fp,
                                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                                mp4_fp
                            ]
                            run_kw = {'check': True, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
                            if os.name == 'nt':
                                run_kw['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                            subprocess.run(cmd, **run_kw)
                        except Exception as e:
                            print(f"ffmpeg transcode failed: {e}")
                    if os.path.exists(mp4_fp) and os.path.getsize(mp4_fp) > 1000:
                        fp = mp4_fp
                mt = mimetypes.guess_type(fp)[0]
                if fp.lower().endswith('.mp4'):
                    mt = mt or 'video/mp4'
                elif fp.lower().endswith('.avi'):
                    mt = mt or 'video/x-msvideo'
                elif fp.lower().endswith('.webm'):
                    mt = mt or 'video/webm'
                elif fp.lower().endswith('.json'):
                    mt = 'application/json; charset=utf-8'
                return send_file(fp, mimetype=mt or 'application/octet-stream', conditional=True)
        else:
            fp = os.path.join(RECORDINGS_DIR, user_id, filename)
            if os.path.isfile(fp):
                mt = mimetypes.guess_type(fp)[0]
                if fp.lower().endswith('.mp4'):
                    mt = mt or 'video/mp4'
                elif fp.lower().endswith('.avi'):
                    mt = mt or 'video/x-msvideo'
                return send_file(fp, mimetype=mt or 'application/octet-stream', conditional=True)
    except Exception:
        pass
    abort(404)


@app.route('/recordings_manifest/<path:filename>')
def recordings_manifest(filename):
    """
    Always-playable fallback: returns a manifest.json for frame-sequence playback
    derived from any recording (mp4/avi/etc). Used when browser can't decode the video.
    """
    if 'user_id' not in session:
        abort(403)
    user_id = str(session['user_id'])
    try:
        if '/' not in filename:
            abort(404)
        parts = filename.split('/', 1)
        if parts[0] != user_id:
            abort(403)

        video_fp = os.path.join(RECORDINGS_DIR, parts[0], parts[1])
        if not os.path.isfile(video_fp):
            abort(404)

        base = os.path.splitext(os.path.basename(video_fp))[0]
        out_dir = os.path.join(RECORDINGS_DIR, parts[0], f"{base}_frames")
        manifest_fp = _video_to_frame_manifest(video_fp, out_dir, duration_s=RECORDING_DURATION)
        if not manifest_fp:
            abort(404)

        return send_file(manifest_fp, mimetype='application/json; charset=utf-8', conditional=True)
    except Exception:
        pass
    abort(404)


@app.route('/api/logs')
def api_logs():
    if 'user' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    date_filter = parse_history_date(request.args.get('date', ''))
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        if date_filter:
            c.execute("""SELECT id, timestamp, event_type, person_name, image_path,
                         recording_path, angle, distance, review_status, model_distance, model_threshold FROM logs
                         WHERE user_id=? AND timestamp LIKE ?
                         ORDER BY id DESC LIMIT 500""",
                      (user_id, f"{date_filter}%"))
        else:
            c.execute("""SELECT id, timestamp, event_type, person_name, image_path,
                         recording_path, angle, distance, review_status, model_distance, model_threshold FROM logs
                         WHERE user_id=? ORDER BY id DESC LIMIT 500""", (user_id,))
        rows = c.fetchall()
        conn.close()
    return jsonify([{
        'id': r[0], 'timestamp': r[1] or '', 'event_type': r[2] or '',
        'person_name': r[3] or 'Unknown', 'image_path': r[4] or '',
        'recording_path': r[5] or '', 'angle': r[6] or 0, 'distance': r[7] or 0,
        'review_status': r[8] or 0, 'model_distance': r[9], 'model_threshold': r[10]
    } for r in rows])


@app.route('/api/review', methods=['POST'])
def api_review():
    if 'user' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}
    log_id = int(payload.get('log_id', 0) or 0)
    action = (payload.get('action') or '').strip().lower()
    if log_id <= 0 or action not in ('like', 'dislike'):
        return jsonify({'error': 'Invalid payload'}), 400
    review_status = 1 if action == 'like' else -1

    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""SELECT person_name, image_path, review_status
                     FROM logs WHERE id=? AND user_id=?""", (log_id, user_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Log not found'}), 404

        person_name, image_path, current_review = row
        if current_review == review_status:
            conn.close()
            return jsonify({'ok': True, 'status': review_status, 'unchanged': True})

        c.execute("UPDATE logs SET review_status=?, review_comment=? WHERE id=? AND user_id=?",
                  (review_status, action, log_id, user_id))

        # Online adaptation: update per-person feedback profile.
        if person_name and person_name not in ('Intruder', 'Unknown', 'Analyzing...'):
            c.execute("""INSERT INTO face_feedback (user_id, person_name, likes, dislikes, updated_at)
                         VALUES (?, ?, 0, 0, CURRENT_TIMESTAMP)
                         ON CONFLICT(user_id, person_name) DO NOTHING""", (user_id, person_name))
            if action == 'like':
                c.execute("""UPDATE face_feedback
                             SET likes=likes+1, updated_at=CURRENT_TIMESTAMP
                             WHERE user_id=? AND person_name=?""", (user_id, person_name))
            else:
                c.execute("""UPDATE face_feedback
                             SET dislikes=dislikes+1, updated_at=CURRENT_TIMESTAMP
                             WHERE user_id=? AND person_name=?""", (user_id, person_name))
        conn.commit()
        conn.close()

    # Incremental training from verified-positive samples.
    if action == 'like' and person_name and person_name not in ('Intruder', 'Unknown', 'Analyzing...') and image_path:
        try:
            src = os.path.join(SAVE_DIR, image_path)
            if os.path.isfile(src):
                person_dir = os.path.join(KNOWN_FACES_DIR, str(user_id), person_name)
                os.makedirs(person_dir, exist_ok=True)
                dst = os.path.join(person_dir, f"review_{log_id}_{int(time.time())}.jpg")
                shutil.copy2(src, dst)
                invalidate_user_face_cache(user_id)
                warm_user_face_index(user_id)
        except Exception as e:
            print(f"Review training warning: {e}")
    return jsonify({'ok': True, 'status': review_status})


@app.route('/api/stats')
def api_stats():
    """Get dashboard statistics"""
    if 'user' not in session or 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    enrolled = count_enrolled_profiles(user_id)
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM logs WHERE user_id=?", (user_id,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM logs WHERE user_id=? AND event_type='Intruder Detected'", (user_id,))
        intruders = c.fetchone()[0]
        c.execute(
            "SELECT COUNT(*) FROM logs WHERE user_id=? AND event_type='Known Person'",
            (user_id,),
        )
        known_events = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM logs WHERE user_id=? AND recording_path IS NOT NULL AND recording_path != ''", (user_id,))
        recordings = c.fetchone()[0]
        conn.close()
    return jsonify({
        'total': total,
        'intruders': intruders,
        'known': enrolled,
        'known_events': known_events,
        'recordings': recordings,
    })


# ========================================
# START
# ========================================
# Gunicorn imports this module and never runs `__main__`. Create tables at import.
try:
    ensure_db()
except Exception as e:
    print(f"Database init at import failed: {e}")

if __name__ == '__main__':
    ensure_db()
    reconcile_stale_processing_logs()
    if not shutil.which('ffmpeg'):
        print("Tip: Install ffmpeg and add it to PATH for browser-playable H.264 recordings (.mp4).")

    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=read_serial, daemon=True).start()
    threading.Thread(target=demo_radar_loop, daemon=True).start()
    threading.Thread(target=capture_worker, daemon=True).start()
    threading.Thread(target=recognition_worker, daemon=True).start()
    threading.Thread(target=stale_processing_sweeper, daemon=True).start()

    port = int(os.environ.get("PORT", "5000") or "5000")
    on_render = bool(os.environ.get("RENDER"))
    print("=" * 50)
    print("  Intruder Detection System")
    print(f"  Face model: {FACE_MODEL_NAME} ({FACE_DISTANCE_METRIC} ≤ {FACE_ACCEPT_THRESHOLD})")
    print(f"  Detectors: {', '.join(FACE_DETECTOR_CHAIN)} (async recognition queue)")
    print(f"  http://127.0.0.1:{port}")
    print("=" * 50)
    app.run(debug=not on_render, host="0.0.0.0", port=port, use_reloader=False)
