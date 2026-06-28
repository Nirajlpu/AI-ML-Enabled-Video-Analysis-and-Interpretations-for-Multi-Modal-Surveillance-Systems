import base64
import cv2
import numpy as np
import logging
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from ultralytics import YOLO
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import tempfile
from collections import defaultdict


load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import faiss
    from insightface.app import FaceAnalysis
except ImportError:
    faiss = None
    FaceAnalysis = None
    logger.warning("⚠️ faiss or insightface not installed. Face recognition features will be disabled.")

logging.getLogger('werkzeug').setLevel(logging.ERROR)


app = Flask(__name__)


allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5001,http://127.0.0.1:5001,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001,https://ai-ml-enabled-video-analysis-and-interpretations-dj2tr2q06.vercel.app,*,https://ai-ml-enabled-video-analysis-and-in.vercel.app').split(',')

CORS(app,  
     origins=allowed_origins,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
)

@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
   
    if origin and origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response


DATABASE_URL = os.environ.get('DATABASE_URL')
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT,
                profile_picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS detections (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                image_url TEXT,
                results JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS visitors (
                id SERIAL PRIMARY KEY,
                name TEXT DEFAULT 'Unknown',
                embedding BYTEA,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                visit_count INTEGER DEFAULT 1,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    finally:
        cur.close()
        conn.close()


init_db()


MODEL_PATH = os.environ.get('YOLO_MODEL_PATH', 'yolo11n.pt')
model = None

try:
    candidate_models = [MODEL_PATH, 'yolov8m.pt', 'yolov8n.pt']
    for candidate_model in candidate_models:
        try:
            if not os.path.exists(candidate_model):
                logger.info(f"Model file '{candidate_model}' not found locally. Ultralytics will download if available...")

            logger.info(f"Loading YOLO model from {candidate_model}...")
            model = YOLO(candidate_model)
            MODEL_PATH = candidate_model
            logger.info("✅ YOLO model loaded successfully.")
            break
        except Exception as model_error:
            logger.warning(f"Failed loading model '{candidate_model}': {model_error}")

    if model is None:
        raise RuntimeError("No YOLO model could be loaded from configured candidates")
except Exception as e:
    logger.error(f"❌ Failed to load YOLO model: {e}")
    model = None


face_app = None
try:
    logger.info("Initializing FaceAnalysis (ArcFace)...")
    face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
    face_app.prepare(ctx_id=0, det_size=(640, 640))
    logger.info("✅ FaceAnalysis initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to initialize FaceAnalysis: {e}")


EMBEDDING_DIM = 512 

faiss_index = faiss.IndexFlatIP(EMBEDDING_DIM) if faiss else None
visitor_ids = [] 
VIDEO_SAMPLE_EVERY_N_FRAMES = int(os.environ.get('VIDEO_SAMPLE_EVERY_N_FRAMES', 5))
LOITERING_SECONDS = int(os.environ.get('LOITERING_SECONDS', 12))
SUSPICIOUS_SPEED_PX = float(os.environ.get('SUSPICIOUS_SPEED_PX', 60.0))


FACE_MATCH_THRESHOLD = float(os.environ.get('FACE_MATCH_THRESHOLD', 0.40))

FACE_QUALITY_THRESHOLD = float(os.environ.get('FACE_QUALITY_THRESHOLD', 0.70))

FACE_MIN_AREA_PX = int(os.environ.get('FACE_MIN_AREA_PX', 1600))  
HEATMAP_GRID_SIZE = int(os.environ.get('HEATMAP_GRID_SIZE', 20))
MAX_QUERY_IMAGES = int(os.environ.get('MAX_QUERY_IMAGES', 20))

SUSPICIOUS_OBJECT_KEYWORDS = {
    'knife', 'gun', 'firearm', 'pistol', 'rifle', 'weapon'
}

# ---------------------------------------------------------------------------

import uuid
import time as _time
import json as _json
import threading


PRESENCE_MISS_TOLERANCE = int(os.environ.get('PRESENCE_MISS_TOLERANCE', 3))


live_monitor_sessions: dict = {}
_session_lock = threading.Lock()


def _init_presence_entry():
    return {
        'is_present': False,
        'first_seen_at': None,       
        'last_seen_at': None,       
        'continuous_since': None,   
        'left_at': None,            
        'total_presence_sec': 0.0,  
        'miss_counter': 0,
        'segments': [],             
        'match_reason': None,
    }


def _now_iso():
    return datetime.datetime.now().isoformat()



def normalize_embedding(emb: np.ndarray) -> np.ndarray:
    """L2-normalize an ArcFace embedding so dot-product == cosine similarity."""
    norm = np.linalg.norm(emb)
    if norm < 1e-10:
        return emb.astype('float32')
    return (emb / norm).astype('float32')


def load_visitors_into_faiss():
    """Reload all visitor embeddings (normalized) from DB into the FAISS index."""
    global visitor_ids
    if not faiss or not faiss_index:
        return
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, embedding FROM visitors WHERE embedding IS NOT NULL")
        rows = cur.fetchall()
        if rows:
            embeddings = []
            visitor_ids = []
            for row in rows:
                raw = np.frombuffer(row[1], dtype=np.float32).copy()
                
                emb = normalize_embedding(raw)
                embeddings.append(emb)
                visitor_ids.append(row[0])

            if embeddings:
                faiss_index.reset()
                faiss_index.add(np.array(embeddings).astype('float32'))
                logger.info(f"Loaded {len(visitor_ids)} visitors into FAISS index (normalized).")
        else:
            visitor_ids = []
            faiss_index.reset()
    except Exception as e:
        logger.error(f"Error loading visitors into FAISS: {e}")
    finally:
        conn.close()

load_visitors_into_faiss()

def _open_video_capture_from_upload(video_file):
    if not video_file:
        return None, None

    suffix = os.path.splitext(video_file.filename or 'uploaded_video.mp4')[-1] or '.mp4'
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        video_file.save(temp_file.name)
        temp_file.close()
        capture = cv2.VideoCapture(temp_file.name)
        if not capture.isOpened():
            os.unlink(temp_file.name)
            return None, None
        return capture, temp_file.name
    except Exception:
        try:
            temp_file.close()
            os.unlink(temp_file.name)
        except Exception:
            pass
        raise

def _extract_faces_with_embeddings(frame):
    """Detect faces in *frame*, apply quality filters, and return L2-normalized embeddings."""
    if not face_app:
        return []

    try:
        faces = face_app.get(frame)
        parsed = []
        for face in faces:
            fx1, fy1, fx2, fy2 = face.bbox.tolist()

            det_score = getattr(face, 'det_score', 1.0) 
            if det_score < FACE_QUALITY_THRESHOLD:
                logger.debug(f"Skipping low-quality face det_score={det_score:.2f}")
                continue
            face_area = max(0, fx2 - fx1) * max(0, fy2 - fy1)
            if face_area < FACE_MIN_AREA_PX:
                logger.debug(f"Skipping tiny face area={face_area:.0f}px")
                continue

            if hasattr(face, 'pose') and face.pose is not None:
                yaw, pitch, roll = face.pose
                if abs(yaw) > 35 or abs(pitch) > 35: 
                    logger.debug(f"Skipping non-frontal face yaw={yaw:.1f} pitch={pitch:.1f}")
                    continue

            raw_emb = face.embedding if hasattr(face, 'embedding') else None
            norm_emb = normalize_embedding(raw_emb.astype('float32')) if raw_emb is not None else None

            parsed.append({
                'bbox': [fx1, fy1, fx2, fy2],
                'embedding': norm_emb,
                'pose': face.pose if hasattr(face, 'pose') else None,
                'det_score': float(det_score),
            })
        return parsed
    except Exception as e:
        logger.warning(f"Face extraction failed for frame: {e}")
        return []

def _bbox_center(x1, y1, x2, y2):
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

def _is_face_inside_person(person_box, face_box):
    px1, py1, px2, py2 = person_box
    fx1, fy1, fx2, fy2 = face_box
    return fx1 >= px1 and fx2 <= px2 and fy1 >= py1 and fy2 <= py2

def _compute_heatmap_points(heatmap_grid, grid_size):
    if heatmap_grid.sum() == 0:
        return []

    max_count = float(heatmap_grid.max())
    points = []
    for gy in range(grid_size):
        for gx in range(grid_size):
            count = heatmap_grid[gy, gx]
            if count > 0:
                points.append({
                    'x': round((gx + 0.5) * (100.0 / grid_size), 2),
                    'y': round((gy + 0.5) * (100.0 / grid_size), 2),
                    'intensity': round(float(count / max_count), 4)
                })
    return points

def _extract_query_signatures(files):
    signatures = []
    for idx, image_file in enumerate(files[:MAX_QUERY_IMAGES]):
        img_bytes = image_file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            signatures.append({
                'query_index': idx,
                'filename': image_file.filename,
                'error': 'Invalid image format'
            })
            continue

        labels = set()
        face_embeddings = []
        if model is not None:
            query_results = model.predict(img, conf=0.25, verbose=False)
            for r in query_results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    labels.add(model.names[cls])

        faces = _extract_faces_with_embeddings(img)
        for face in faces:
            if face['embedding'] is not None:
                face_embeddings.append(face['embedding'])

        signatures.append({
            'query_index': idx,
            'filename': image_file.filename,
            'labels': sorted(list(labels)),
            'face_embeddings': face_embeddings,
            'matched': False,
            'first_match_time_sec': None,
            'match_reason': None
        })
    return signatures

def _match_queries_in_frame(query_signatures, frame_labels, frame_face_embeddings, timestamp_sec):
    for signature in query_signatures:
        if signature.get('matched'):
            continue
        if signature.get('error'):
            continue


        
        has_query_face = len(signature.get('face_embeddings', [])) > 0
        
        if has_query_face:
            best_sim = None
            for query_embedding in signature['face_embeddings']:
                for frame_embedding in frame_face_embeddings:
                    sim = float(np.dot(query_embedding, frame_embedding))
                    if best_sim is None or sim > best_sim:
                        best_sim = sim
            
            if best_sim is not None and best_sim >= FACE_MATCH_THRESHOLD:
                signature['matched'] = True
                signature['first_match_time_sec'] = round(float(timestamp_sec), 2)
                signature['match_reason'] = f"Face match (sim={best_sim:.3f})"
                continue
        else:

            label_overlap = set(signature['labels']).intersection(frame_labels)
            if label_overlap:
                if label_overlap == {'person'}:
                    pass
                else:
                    signature['matched'] = True
                    signature['first_match_time_sec'] = round(float(timestamp_sec), 2)
                    signature['match_reason'] = f"Object match: {', '.join(sorted(label_overlap))}"
                    continue


        best_sim = None
        for query_embedding in signature['face_embeddings']:
            for frame_embedding in frame_face_embeddings:
                sim = float(np.dot(query_embedding, frame_embedding))
                if best_sim is None or sim > best_sim:
                    best_sim = sim
        if best_sim is not None and best_sim >= FACE_MATCH_THRESHOLD:
            signature['matched'] = True
            signature['first_match_time_sec'] = round(float(timestamp_sec), 2)
            signature['match_reason'] = f"Face match (cosine_sim={best_sim:.3f})"

MAX_PERSON_SNAPSHOT_SIZE = int(os.environ.get('MAX_PERSON_SNAPSHOT_SIZE', 20))  

def _encode_crop_as_base64(frame: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> str | None:
    """Crop a region from *frame* and encode it as a base64 JPEG string."""
    h, w = frame.shape[:2]
    cx1, cy1 = max(0, int(x1)), max(0, int(y1))
    cx2, cy2 = min(w, int(x2)), min(h, int(y2))
    if cx2 <= cx1 or cy2 <= cy1:
        return None
    crop = frame[cy1:cy2, cx1:cx2]
    ret, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not ret:
        return None
    return base64.b64encode(buf.tobytes()).decode('utf-8')

def analyze_video_stream(video_capture, fps, query_signatures=None, restricted_zones=None):
    frame_index = 0

    unique_track_ids: dict = defaultdict(set) 
    alerts = []
    alert_keys = set()
    track_state = {}
    heatmap_grid = np.zeros((HEATMAP_GRID_SIZE, HEATMAP_GRID_SIZE), dtype=np.int32)
    processed_frames = 0
    video_duration_sec = 0.0
    object_timeline = defaultdict(list)  

    person_snapshots: dict = {}

    if fps <= 0:
        fps = 25.0

    while True:
        ok, frame = video_capture.read()
        if not ok:
            break

        frame_index += 1
        if frame_index % VIDEO_SAMPLE_EVERY_N_FRAMES != 0:
            continue

        processed_frames += 1
        frame_h, frame_w = frame.shape[:2]
        timestamp_sec = frame_index / fps
        video_duration_sec = timestamp_sec

        results = model.track(frame, persist=True, conf=0.25, verbose=False) if model else []
        faces = _extract_faces_with_embeddings(frame)
        frame_face_embeddings = [face['embedding'] for face in faces if face['embedding'] is not None]
        frame_labels = set()

        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                label = model.names[cls]
                confidence = float(box.conf[0])
                track_id = int(box.id[0]) if box.id is not None else None
                frame_labels.add(label)

 
                if track_id is not None:
                    unique_track_ids[label].add(track_id)

                if not object_timeline[label] or abs(object_timeline[label][-1] - timestamp_sec) > 0.5:
                    object_timeline[label].append(round(float(timestamp_sec), 2))

                cx, cy = _bbox_center(x1, y1, x2, y2)
                gx = min(HEATMAP_GRID_SIZE - 1, max(0, int((cx / frame_w) * HEATMAP_GRID_SIZE)))
                gy = min(HEATMAP_GRID_SIZE - 1, max(0, int((cy / frame_h) * HEATMAP_GRID_SIZE)))
                heatmap_grid[gy, gx] += 1

                if track_id is not None:
                    previous = track_state.get(track_id)
                    if previous is None:
                        track_state[track_id] = {
                            'first_seen': timestamp_sec,
                            'last_seen': timestamp_sec,
                            'last_center': (cx, cy),
                            'label': label
                        }
                    else:
                        prev_cx, prev_cy = previous['last_center']
                        speed = float(np.hypot(cx - prev_cx, cy - prev_cy))
                        previous['last_seen'] = timestamp_sec
                        previous['last_center'] = (cx, cy)

                        if label == 'person' and speed > SUSPICIOUS_SPEED_PX:
                            alert_key = f"rapid_motion:{track_id}:{int(timestamp_sec)}"
                            if alert_key not in alert_keys:
                                alert_keys.add(alert_key)
                                alerts.append({
                                    'type': 'rapid_motion',
                                    'severity': 'medium',
                                    'time_sec': round(float(timestamp_sec), 2),
                                    'message': f"Fast movement detected for track {track_id}"
                                })

                    duration = track_state[track_id]['last_seen'] - track_state[track_id]['first_seen']
                    if label == 'person' and duration >= LOITERING_SECONDS:
                        alert_key = f"loitering:{track_id}"
                        if alert_key not in alert_keys:
                            alert_keys.add(alert_key)
                            alerts.append({
                                'type': 'loitering',
                                'severity': 'high',
                                'time_sec': round(float(timestamp_sec), 2),
                                'message': f"Potential loitering detected for track {track_id} ({duration:.1f}s)"
                            })

                label_lower = str(label).lower()
                if any(keyword in label_lower for keyword in SUSPICIOUS_OBJECT_KEYWORDS) and confidence > 0.3:
                    alert_key = f"suspicious_object:{label}:{int(timestamp_sec)}"
                    if alert_key not in alert_keys:
                        alert_keys.add(alert_key)
                        alerts.append({
                            'type': 'suspicious_object',
                            'severity': 'high',
                            'time_sec': round(float(timestamp_sec), 2),
                            'message': f"Suspicious object '{label}' detected"
                        })

                if restricted_zones and label == 'person':
                    for zone in restricted_zones:
                        zx1 = float(zone.get('x1', 0))
                        zy1 = float(zone.get('y1', 0))
                        zx2 = float(zone.get('x2', frame_w))
                        zy2 = float(zone.get('y2', frame_h))
                        if cx >= zx1 and cx <= zx2 and cy >= zy1 and cy <= zy2:
                            alert_key = f"intrusion:{track_id}:{zone.get('name', 'zone')}:{int(timestamp_sec)}"
                            if alert_key not in alert_keys:
                                alert_keys.add(alert_key)
                                alerts.append({
                                    'type': 'intrusion',
                                    'severity': 'high',
                                    'time_sec': round(float(timestamp_sec), 2),
                                    'message': f"Person entered restricted zone '{zone.get('name', 'zone')}'"
                                })

    
                if label == 'person' and track_id is not None and len(person_snapshots) <= MAX_PERSON_SNAPSHOT_SIZE:
                    existing = person_snapshots.get(track_id)
                    if existing is None or confidence > existing['confidence']:
                        person_snapshots[track_id] = {
                            'confidence': confidence,
                            'bbox': [x1, y1, x2, y2],
                            'frame': frame.copy(),  
                            'first_seen': track_state[track_id]['first_seen'],
                            'track_id': track_id,
                        }

        if query_signatures:
            _match_queries_in_frame(query_signatures, frame_labels, frame_face_embeddings, timestamp_sec)

    tracked_persons = []
    for track_id, snap in sorted(person_snapshots.items(), key=lambda kv: kv[1]['first_seen']):
        x1, y1, x2, y2 = snap['bbox']
        img_b64 = _encode_crop_as_base64(snap['frame'], x1, y1, x2, y2)
        if img_b64:
            tracked_persons.append({
                'track_id': track_id,
                'first_seen': round(float(snap['first_seen']), 2),
                'last_seen': round(float(track_state.get(track_id, {}).get('last_seen', snap['first_seen'])), 2),
                'confidence': round(snap['confidence'], 3),
                'image': img_b64,  # base64 JPEG
            })

    clean_queries = []
    for sig in (query_signatures or []):
        clean_sig = {
            'query_index': sig.get('query_index'),
            'filename': sig.get('filename'),
            'labels': sig.get('labels', []),
            'matched': sig.get('matched', False),
            'first_match_time_sec': sig.get('first_match_time_sec'),
            'match_reason': sig.get('match_reason'),
            'error': sig.get('error')
        }
        clean_queries.append(clean_sig)

    object_detections = []
    for label, timestamps in sorted(object_timeline.items()):
        unique_count = len(unique_track_ids[label]) if unique_track_ids[label] else len(timestamps)
        object_detections.append({
            'label': label,
            'count': unique_count,
            'frame_count': sum(            
                1 for ts in timestamps    
            ),
            'timestamps': timestamps[:20],
            'first_seen': timestamps[0] if timestamps else None,
            'last_seen': timestamps[-1] if timestamps else None
        })


    unique_object_counts = {label: len(ids) for label, ids in unique_track_ids.items()}

    return {
        'processed_frames': processed_frames,
        'video_duration_sec': round(float(video_duration_sec), 2),
        'object_counts': dict(sorted(unique_object_counts.items(), key=lambda item: item[1], reverse=True)),
        'object_detections': object_detections,
        'alerts': alerts,
        'alert_count': len(alerts),
        'heatmap': _compute_heatmap_points(heatmap_grid, HEATMAP_GRID_SIZE),
        'queries': clean_queries,
        'tracked_persons': tracked_persons,  
    }



@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify server and model status"""
    status = 'healthy' if model else 'model_not_loaded'
    return jsonify({
        'status': status,
        'model': MODEL_PATH,
        'model_loaded': model is not None,
        'db_connected': get_db_connection() is not None
    }), 200

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 204
        
    data = request.json
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', 'User')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    try:
        hashed_password = generate_password_hash(password)
    except Exception as e:
        logger.error(f"Hashing error: {e}")
        return jsonify({'error': 'Password processing failed'}), 500
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password, name) VALUES (%s, %s, %s) RETURNING id",
            (email, hashed_password, name)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        
        token = jwt.encode({
            'user_id': user_id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, JWT_SECRET, algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {
                'id': user_id,
                'email': email,
                'name': name
            }
        }), 201
    except psycopg2.IntegrityError:
        return jsonify({'error': 'Email already exists'}), 400
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 204
        
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        
        if user and check_password_hash(user['password'], password):
            token = jwt.encode({
                'user_id': user['id'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
            }, JWT_SECRET, algorithm='HS256')
            
            return jsonify({
                'token': token,
                'user': {
                    'id': user['id'],
                    'email': user['email'],
                    'name': user['name']
                }
            }), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        cur.close()
        conn.close()
@app.route('/detect', methods=['POST', 'OPTIONS'])
def detect():
    """
    Enhanced detection with tracking and visitor identification
    """
    if request.method == 'OPTIONS':
        return '', 204
        
    if model is None:
        logger.error("Model not loaded")
        return jsonify({'error': 'Model not loaded.'}), 503

    try:
        data = request.json
        if not data or 'image' not in data:
            return jsonify({'error': 'No image provided.'}), 400

        image_data = base64.b64decode(data['image'])
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'error': 'Invalid image format.'}), 400

        height, width, _ = img.shape

        results = model.track(img, persist=True, conf=0.25, verbose=False)

        detections = []

        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                label = model.names[cls]
                confidence = float(box.conf[0])
                track_id = int(box.id[0]) if box.id is not None else None
                
                visitor_status = "Unknown"
                visitor_name = None
                
                
                if label == 'person' and face_app:
                 
                    for face_data in _extract_faces_with_embeddings(img):
                        fx1, fy1, fx2, fy2 = face_data['bbox']
                      
                        if fx1 >= x1 and fx2 <= x2 and fy1 >= y1 and fy2 <= y2:
                            embedding = face_data['embedding'] 
                            if embedding is None:
                                continue

                            if faiss and faiss_index and faiss_index.ntotal > 0:
                                D, I = faiss_index.search(np.array([embedding]), 1)

                                cosine_sim = float(D[0][0])
                                logger.debug(f"FAISS cosine_sim={cosine_sim:.3f}")
                                if cosine_sim >= FACE_MATCH_THRESHOLD:
                                    v_id = visitor_ids[I[0][0]]
                                    visitor_status = "Returning Visitor"
                                    conn = get_db_connection()
                                    if conn:
                                        try:
                                            cur2 = conn.cursor(cursor_factory=RealDictCursor)
                                            cur2.execute(
                                                "UPDATE visitors SET last_seen = NOW(), visit_count = visit_count + 1 WHERE id = %s RETURNING name",
                                                (v_id,)
                                            )
                                            v_row = cur2.fetchone()
                                            visitor_name = v_row['name'] if v_row else "Visitor"
                                            conn.commit()
                                        finally:
                                            conn.close()
                                else:
                                    visitor_status = "New Visitor"
                                    conn = get_db_connection()
                                    if conn:
                                        try:
                                            cur2 = conn.cursor()
                                            cur2.execute(
                                                "INSERT INTO visitors (embedding) VALUES (%s) RETURNING id",
                                                (psycopg2.Binary(embedding.tobytes()),)
                                            )
                                            conn.commit()
                                        finally:
                                            conn.close()
                                        load_visitors_into_faiss()
                            else:
                                visitor_status = "New Visitor"
                                conn = get_db_connection()
                                if conn:
                                    try:
                                        cur2 = conn.cursor()
                                        cur2.execute(
                                            "INSERT INTO visitors (embedding) VALUES (%s) RETURNING id",
                                            (psycopg2.Binary(embedding.tobytes()),)
                                        )
                                        conn.commit()
                                    finally:
                                        conn.close()
                                    load_visitors_into_faiss()
                            break  

                detections.append({
                    'label': label,
                    'confidence': round(confidence, 2),
                    'track_id': track_id,
                    'visitor_status': visitor_status,
                    'visitor_name': visitor_name,
                    'box': {
                        'x': round(x1 / width, 4),
                        'y': round(y1 / height, 4),
                        'width': round((x2 - x1) / width, 4),
                        'height': round((y2 - y1) / height, 4)
                    }
                })

        return jsonify(detections), 200

    except Exception as e:
        logger.error(f"Detection error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
@app.route('/stats', methods=['GET'])
def get_stats():
    """Optional: Get detection statistics"""
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503
    
    return jsonify({
        'model_name': MODEL_PATH,
        'classes': list(model.names.values()),
        'total_classes': len(model.names)
    }), 200

@app.route('/analyze-video', methods=['POST', 'OPTIONS'])
def analyze_video():
    """
    Analyze uploaded video for objects, unusual behavior and optional query image matching.
    Request (multipart/form-data):
      - video: required video file
      - query_images: optional repeated image files
      - restricted_zones: optional JSON string list [{name, x1, y1, x2, y2}]
    """
    if request.method == 'OPTIONS':
        return '', 204

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503

    video_file = request.files.get('video')
    if not video_file:
        return jsonify({'error': 'No video file provided. Use form-data key "video".'}), 400

    query_images = request.files.getlist('query_images')
    restricted_zones_raw = request.form.get('restricted_zones')
    restricted_zones = None
    if restricted_zones_raw:
        try:
            import json
            restricted_zones = json.loads(restricted_zones_raw)
        except Exception:
            return jsonify({'error': 'Invalid restricted_zones JSON'}), 400

    capture = None
    temp_path = None
    try:
        capture, temp_path = _open_video_capture_from_upload(video_file)
        if capture is None:
            return jsonify({'error': 'Unable to read video file'}), 400

        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        query_signatures = _extract_query_signatures(query_images) if query_images else []
        analysis = analyze_video_stream(capture, fps, query_signatures=query_signatures, restricted_zones=restricted_zones)

        return jsonify({
            'status': 'success',
            'model': MODEL_PATH,
            'analytics': analysis
        }), 200
    except Exception as e:
        logger.error(f"Video analysis failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        if capture:
            capture.release()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
@app.route('/match-video-queries', methods=['POST', 'OPTIONS'])
def match_video_queries():
    """
    Lightweight endpoint specifically for query image matching in a video.
    Request (multipart/form-data):
      - video: required
      - query_images: required, one or many
    """
    if request.method == 'OPTIONS':
        return '', 204

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503

    video_file = request.files.get('video')
    query_images = request.files.getlist('query_images')
    if not video_file:
        return jsonify({'error': 'No video file provided'}), 400
    if not query_images:
        return jsonify({'error': 'No query_images provided'}), 400

    capture = None
    temp_path = None
    try:
        capture, temp_path = _open_video_capture_from_upload(video_file)
        if capture is None:
            return jsonify({'error': 'Unable to read video file'}), 400

        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        query_signatures = _extract_query_signatures(query_images)
        analysis = analyze_video_stream(capture, fps, query_signatures=query_signatures)

        query_result = []
        for idx, query in enumerate(analysis.get('queries', [])):
            query_result.append({
                'query_index': idx,
                'filename': query.get('filename', f'query_{idx}'),
                'matched': query.get('matched', False),
                'first_match_time_sec': query.get('first_match_time_sec'),
                'match_reason': query.get('match_reason', ''),
                'labels': query.get('labels', query.get('labels_in_query', [])),
                'labels_in_query': query.get('labels', query.get('labels_in_query', [])),
                'error': query.get('error')
            })

        return jsonify({
            'status': 'success',
            'model': MODEL_PATH,
            'results': query_result
        }), 200
    except Exception as e:
        logger.error(f"Video query matching failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        if capture:
            capture.release()
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


@app.route('/process-frame', methods=['POST', 'OPTIONS'])
def process_frame():
    """
    Process a single frame for real-time webcam monitoring.
    Request (multipart/form-data):
      - frame: required image file (JPEG/PNG)
      - query_images: optional repeated image files for matching
    Returns:
      - detections: list of detected objects with bounding boxes
      - alerts: list of behavioral alerts
      - query_matches: list of query match results
    """
    if request.method == 'OPTIONS':
        return '', 204

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503

    frame_file = request.files.get('frame')
    if not frame_file:
        return jsonify({'error': 'No frame provided'}), 400

    query_images = request.files.getlist('query_images')

    try:
        img_bytes = frame_file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'error': 'Invalid frame format'}), 400

        frame_h, frame_w = frame.shape[:2]
        
        results = model.predict(frame, conf=0.25, verbose=False)
        
        detections = []
        alerts = []
        alert_count = 0
        frame_labels = set()
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                label = model.names[cls]
                confidence = float(box.conf[0])
                frame_labels.add(label)
                
                detections.append({
                    'label': label,
                    'confidence': round(confidence, 3),
                    'box': {
                        'x': round(x1 / frame_w, 4),
                        'y': round(y1 / frame_h, 4),
                        'width': round((x2 - x1) / frame_w, 4),
                        'height': round((y2 - y1) / frame_h, 4)
                    }
                })
                
                if label.lower() in SUSPICIOUS_OBJECT_KEYWORDS:
                    alerts.append({
                        'type': 'suspicious_object',
                        'severity': 'high',
                        'message': f"Suspicious object detected: {label}"
                    })
                    alert_count += 1

        query_matches = []
        if query_images:
            query_signatures = _extract_query_signatures(query_images)
            faces = _extract_faces_with_embeddings(frame)
            frame_face_embeddings = [face['embedding'] for face in faces if face['embedding'] is not None]
            
            for signature in query_signatures:
                if signature.get('error'):
                    query_matches.append({
                        'filename': signature['filename'],
                        'matched': False,
                        'error': signature['error']
                    })
                    continue
                
                matched = False
                match_reason = None
                
                label_overlap = set(signature['labels']).intersection(frame_labels)
                if label_overlap:
                    matched = True
                    match_reason = f"Object match: {', '.join(sorted(label_overlap))}"
                
                if not matched:
                    for query_embedding in signature['face_embeddings']:
                        for frame_embedding in frame_face_embeddings:
                            sim = float(np.dot(query_embedding, frame_embedding))
                            if sim >= FACE_MATCH_THRESHOLD:
                                matched = True
                                match_reason = f"Face match (cosine_sim={sim:.3f})"
                                alerts.append({
                                    'type': 'face_match',
                                    'severity': 'high',
                                    'message': f"Query face matched: {signature['filename']}"
                                })
                                alert_count += 1
                                break
                        if matched:
                            break
                
                query_matches.append({
                    'filename': signature['filename'],
                    'matched': matched,
                    'match_reason': match_reason
                })

        return jsonify({
            'status': 'success',
            'detections': detections,
            'alerts': alerts,
            'alert_count': alert_count,
            'query_matches': query_matches,
            'frame_dimensions': {'width': frame_w, 'height': frame_h}
        }), 200

    except Exception as e:
        logger.error(f"Frame processing error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/visitors', methods=['GET'])
def get_visitors():
    """List all tracked visitors with their metadata."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id, name, visit_count, first_seen, last_seen "
            "FROM visitors ORDER BY last_seen DESC"
        )
        rows = cur.fetchall()
        visitors = []
        for row in rows:
            visitors.append({
                'id': row['id'],
                'name': row['name'],
                'visit_count': row['visit_count'],
                'first_seen': row['first_seen'].isoformat() if row['first_seen'] else None,
                'last_seen': row['last_seen'].isoformat() if row['last_seen'] else None,
            })
        return jsonify({'visitors': visitors, 'total': len(visitors)}), 200
    except Exception as e:
        logger.error(f"Get visitors error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        conn.close()


@app.route('/visitors/<int:visitor_id>', methods=['DELETE', 'OPTIONS'])
def delete_visitor(visitor_id):
    """Remove a visitor from the database and refresh the FAISS index."""
    if request.method == 'OPTIONS':
        return '', 204
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM visitors WHERE id = %s RETURNING id", (visitor_id,))
        deleted = cur.fetchone()
        if not deleted:
            return jsonify({'error': 'Visitor not found'}), 404
        conn.commit()
        load_visitors_into_faiss()  
        return jsonify({'message': f'Visitor {visitor_id} deleted successfully'}), 200
    except Exception as e:
        logger.error(f"Delete visitor error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        conn.close()


@app.route('/visitors/<int:visitor_id>/name', methods=['PUT', 'OPTIONS'])
def rename_visitor(visitor_id):
    """Assign or update the name of a known visitor."""
    if request.method == 'OPTIONS':
        return '', 204
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name field is required'}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    try:
        cur = conn.cursor()
        cur.execute("UPDATE visitors SET name = %s WHERE id = %s RETURNING id", (name, visitor_id))
        updated = cur.fetchone()
        if not updated:
            return jsonify({'error': 'Visitor not found'}), 404
        conn.commit()
        return jsonify({'message': f'Visitor {visitor_id} renamed to "{name}"'}), 200
    except Exception as e:
        logger.error(f"Rename visitor error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        conn.close()



@app.route('/live-monitor/start-session', methods=['POST', 'OPTIONS'])
def live_monitor_start_session():
    """
    Start a live-monitor session with query images.
    Request (multipart/form-data):
      - query_images: one or more image files
    Returns:
      - session_id: unique session identifier
      - queries: extracted signatures summary
    """
    if request.method == 'OPTIONS':
        return '', 204

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503

    query_images = request.files.getlist('query_images')
    if not query_images:
        return jsonify({'error': 'No query_images provided'}), 400

    try:
        query_signatures = _extract_query_signatures(query_images)
        session_id = str(uuid.uuid4())

        presence = {}
        for idx, sig in enumerate(query_signatures):
            presence[idx] = _init_presence_entry()

        with _session_lock:
            live_monitor_sessions[session_id] = {
                'query_signatures': query_signatures,
                'presence': presence,
                'alerts': [],
                'created_at': _time.time(),
            }

        logger.info(f"Session {session_id} started. Queries:")
        for i, sig in enumerate(query_signatures):
            logger.info(f"  [{i}] {sig.get('filename')} -> Labels: {sig.get('labels')}, Faces: {len(sig.get('face_embeddings', []))}")

        queries_summary = []
        for sig in query_signatures:
            queries_summary.append({
                'query_index': sig.get('query_index'),
                'filename': sig.get('filename'),
                'labels': sig.get('labels', []),
                'has_face': len(sig.get('face_embeddings', [])) > 0,
                'error': sig.get('error'),
            })

        logger.info(f"Live monitor session started: {session_id} with {len(query_signatures)} queries")

        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'queries': queries_summary,
        }), 200
    except Exception as e:
        logger.error(f"Start session error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/live-monitor/process-frame', methods=['POST', 'OPTIONS'])
def live_monitor_process_frame():
    """
    Process a single webcam frame within a live-monitor session.
    Request (multipart/form-data):
      - session_id: required (form field)
      - frame: required image file (JPEG/PNG)
    Returns:
      - detections, alerts, query_presence (per-query live status)
    """
    if request.method == 'OPTIONS':
        return '', 204

    if model is None:
        return jsonify({'error': 'Model not loaded'}), 503

    session_id = request.form.get('session_id', '').strip()
    frame_file = request.files.get('frame')

    if not frame_file:
        return jsonify({'error': 'No frame provided'}), 400

    session = None
    if session_id:
        with _session_lock:
            session = live_monitor_sessions.get(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session_id'}), 404

    try:
        img_bytes = frame_file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({'error': 'Invalid frame format'}), 400

        frame_h, frame_w = frame.shape[:2]

        results = model.predict(frame, conf=0.25, verbose=False)
        detections = []
        frame_alerts = []
        frame_labels = set()

        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                label = model.names[cls]
                confidence = float(box.conf[0])
                frame_labels.add(label)

                detections.append({
                    'label': label,
                    'confidence': round(confidence, 3),
                    'box': {
                        'x': round(x1 / frame_w, 4),
                        'y': round(y1 / frame_h, 4),
                        'width': round((x2 - x1) / frame_w, 4),
                        'height': round((y2 - y1) / frame_h, 4),
                    },
                    'is_query_match': False,
                })

                if label.lower() in SUSPICIOUS_OBJECT_KEYWORDS:
                    frame_alerts.append({
                        'type': 'suspicious_object',
                        'severity': 'high',
                        'message': f"Suspicious object detected: {label}",
                        'timestamp': _now_iso(),
                    })

        faces = _extract_faces_with_embeddings(frame)
        frame_face_embeddings = [f['embedding'] for f in faces if f['embedding'] is not None]

        query_presence = []
        session_alerts = []

        if session:
            query_signatures = session['query_signatures']
            presence_map = session['presence']
            now_str = _now_iso()
            now_ts = _time.time()

            for idx, signature in enumerate(query_signatures):
                if signature.get('error'):
                    query_presence.append({
                        'query_index': idx,
                        'filename': signature.get('filename'),
                        'error': signature.get('error'),
                        'is_present': False,
                    })
                    continue

                pstate = presence_map.get(idx, _init_presence_entry())

               
                matched = False
                match_reason = None

                
                has_query_face = len(signature.get('face_embeddings', [])) > 0
                matched = False
                match_reason = None

                if has_query_face:
                   
                    if frame_face_embeddings:
                        best_sim = None
                        for q_emb in signature['face_embeddings']:
                            for f_emb in frame_face_embeddings:
                                sim = float(np.dot(q_emb, f_emb))
                                if best_sim is None or sim > best_sim:
                                    best_sim = sim
                        
                        if best_sim is not None and best_sim >= FACE_MATCH_THRESHOLD:
                            matched = True
                            match_reason = f"Face match (sim={best_sim:.3f})"
                           
                            for det in detections:
                                if det['label'] == 'person':
                                    det['is_query_match'] = True
                else:
                   
                    label_overlap = set(signature.get('labels', [])).intersection(frame_labels)
                    if label_overlap:
                        if label_overlap == {'person'}:
                             matched = False 
                        else:
                            matched = True
                            match_reason = f"Object match: {', '.join(sorted(label_overlap))}"
                            for det in detections:
                                if det['label'] in label_overlap:
                                    det['is_query_match'] = True
                
                if matched:
                    logger.info(f"MATCH FOUND for session {session_id}, query {idx}: {match_reason}")

                
                if matched:
                    pstate['miss_counter'] = 0
                    pstate['last_seen_at'] = now_str
                    pstate['match_reason'] = match_reason

                    if not pstate['is_present']:
                        # APPEARED
                        pstate['is_present'] = True
                        pstate['continuous_since'] = now_str
                        pstate['left_at'] = None
                        if pstate['first_seen_at'] is None:
                            pstate['first_seen_at'] = now_str

                        alert_msg = {
                            'type': 'query_match',
                            'severity': 'high',
                            'message': f"🔍 MATCH: '{signature.get('filename', f'Query {idx}')}' appeared! ({match_reason})",
                            'timestamp': now_str,
                            'query_index': idx,
                            'event': 'appeared',
                        }
                        session_alerts.append(alert_msg)
                        frame_alerts.append(alert_msg)
                else:
                    pstate['miss_counter'] = pstate.get('miss_counter', 0) + 1

                    if pstate['is_present'] and pstate['miss_counter'] >= PRESENCE_MISS_TOLERANCE:
                        pstate['is_present'] = False
                        pstate['left_at'] = now_str

                        seg_start = pstate.get('continuous_since', now_str)
                        try:
                            dt_start = datetime.datetime.fromisoformat(seg_start)
                            dt_end = datetime.datetime.fromisoformat(now_str)
                            seg_duration = (dt_end - dt_start).total_seconds()
                        except Exception:
                            seg_duration = 0.0

                        pstate['total_presence_sec'] = pstate.get('total_presence_sec', 0.0) + seg_duration
                        pstate['segments'].append({
                            'start': seg_start,
                            'end': now_str,
                            'duration_sec': round(seg_duration, 1),
                        })
                        pstate['continuous_since'] = None

                        mins = int(seg_duration // 60)
                        secs = int(seg_duration % 60)
                        dur_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                        alert_msg = {
                            'type': 'query_left',
                            'severity': 'medium',
                            'message': f"👋 LEFT: '{signature.get('filename', f'Query {idx}')}' left after {dur_str}",
                            'timestamp': now_str,
                            'query_index': idx,
                            'event': 'left',
                            'duration_sec': round(seg_duration, 1),
                        }
                        session_alerts.append(alert_msg)
                        frame_alerts.append(alert_msg)

                presence_map[idx] = pstate

                current_seg_duration = 0.0
                if pstate['is_present'] and pstate.get('continuous_since'):
                    try:
                        dt_start = datetime.datetime.fromisoformat(pstate['continuous_since'])
                        dt_now = datetime.datetime.now()
                        current_seg_duration = (dt_now - dt_start).total_seconds()
                    except Exception:
                        pass

                query_presence.append({
                    'query_index': idx,
                    'filename': signature.get('filename'),
                    'is_present': pstate['is_present'],
                    'first_seen_at': pstate['first_seen_at'],
                    'last_seen_at': pstate['last_seen_at'],
                    'continuous_since': pstate['continuous_since'],
                    'left_at': pstate['left_at'],
                    'total_presence_sec': round(pstate.get('total_presence_sec', 0.0) + current_seg_duration, 1),
                    'current_segment_sec': round(current_seg_duration, 1),
                    'segments': pstate.get('segments', []),
                    'match_reason': pstate.get('match_reason'),
                })

            if session_alerts:
                session['alerts'].extend(session_alerts)

        return jsonify({
            'status': 'success',
            'detections': detections,
            'alerts': frame_alerts,
            'alert_count': len(frame_alerts),
            'query_presence': query_presence,
            'frame_dimensions': {'width': frame_w, 'height': frame_h},
        }), 200

    except Exception as e:
        logger.error(f"Live monitor frame error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/live-monitor/stop-session', methods=['POST', 'OPTIONS'])
def live_monitor_stop_session():
    """
    Stop a live-monitor session and return the final summary.
    Request (JSON or form):
      - session_id: required
    Returns:
      - Final presence summary per query with all segments
      - All alerts from the session
    """
    if request.method == 'OPTIONS':
        return '', 204

    session_id = None
    if request.is_json:
        session_id = (request.json or {}).get('session_id', '').strip()
    else:
        session_id = request.form.get('session_id', '').strip()

    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400

    with _session_lock:
        session = live_monitor_sessions.pop(session_id, None)

    if not session:
        return jsonify({'error': 'Invalid or expired session_id'}), 404

    try:
        now_str = _now_iso()
        query_summaries = []

        for idx, signature in enumerate(session['query_signatures']):
            pstate = session['presence'].get(idx, {})

            if pstate.get('is_present') and pstate.get('continuous_since'):
                try:
                    dt_start = datetime.datetime.fromisoformat(pstate['continuous_since'])
                    dt_end = datetime.datetime.now()
                    seg_duration = (dt_end - dt_start).total_seconds()
                except Exception:
                    seg_duration = 0.0

                pstate['total_presence_sec'] = pstate.get('total_presence_sec', 0.0) + seg_duration
                pstate['segments'].append({
                    'start': pstate['continuous_since'],
                    'end': now_str,
                    'duration_sec': round(seg_duration, 1),
                })
                pstate['is_present'] = False
                pstate['left_at'] = now_str

            total_sec = pstate.get('total_presence_sec', 0.0)
            mins = int(total_sec // 60)
            secs = int(total_sec % 60)
            dur_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

            query_summaries.append({
                'query_index': idx,
                'filename': signature.get('filename'),
                'labels': signature.get('labels', []),
                'was_found': pstate.get('first_seen_at') is not None,
                'first_seen_at': pstate.get('first_seen_at'),
                'last_seen_at': pstate.get('last_seen_at'),
                'total_presence_sec': round(total_sec, 1),
                'total_presence_formatted': dur_str,
                'segments': pstate.get('segments', []),
                'match_reason': pstate.get('match_reason'),
                'error': signature.get('error'),
            })

        return jsonify({
            'status': 'success',
            'session_id': session_id,
            'queries': query_summaries,
            'alerts': session.get('alerts', []),
            'total_alerts': len(session.get('alerts', [])),
        }), 200

    except Exception as e:
        logger.error(f"Stop session error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404



@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    

    import socket
    socket.setdefaulttimeout(600) 
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)