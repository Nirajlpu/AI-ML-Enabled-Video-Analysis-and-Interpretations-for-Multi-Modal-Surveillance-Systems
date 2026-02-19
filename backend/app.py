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

# Load environment variables
load_dotenv()

# Configure logging
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
# Reduce Flask's werkzeug logging noise
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Initialize Flask app
app = Flask(__name__)

# Get allowed origins from env or use default localhosts
allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5001,http://127.0.0.1:5001,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001').split(',')

CORS(app, 
     origins=allowed_origins,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
)

@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    # Allow all configured origins
    if origin and origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response

# Database configuration
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
        # Create users table
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
        # Create detections table (optional, for logging)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS detections (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                image_url TEXT,
                results JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create visitors table
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

# Initialize DB
init_db()

# Load YOLO model
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

# Initialize Face Analysis (ArcFace)
face_app = None
try:
    logger.info("Initializing FaceAnalysis (ArcFace)...")
    face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
    face_app.prepare(ctx_id=0, det_size=(640, 640))
    logger.info("✅ FaceAnalysis initialized successfully.")
except Exception as e:
    logger.error(f"❌ Failed to initialize FaceAnalysis: {e}")

# FAISS Index setup
EMBEDDING_DIM = 512 # ArcFace buffalo_l produces 512-d embeddings
faiss_index = faiss.IndexFlatL2(EMBEDDING_DIM) if faiss else None
visitor_ids = [] # To map FAISS index to visitor DB IDs

# Video analytics configuration
VIDEO_SAMPLE_EVERY_N_FRAMES = int(os.environ.get('VIDEO_SAMPLE_EVERY_N_FRAMES', 5))
LOITERING_SECONDS = int(os.environ.get('LOITERING_SECONDS', 12))
SUSPICIOUS_SPEED_PX = float(os.environ.get('SUSPICIOUS_SPEED_PX', 60.0))
FACE_MATCH_THRESHOLD = float(os.environ.get('FACE_MATCH_THRESHOLD', 0.6))
HEATMAP_GRID_SIZE = int(os.environ.get('HEATMAP_GRID_SIZE', 20))
MAX_QUERY_IMAGES = int(os.environ.get('MAX_QUERY_IMAGES', 20))

SUSPICIOUS_OBJECT_KEYWORDS = {
    'knife', 'gun', 'firearm', 'pistol', 'rifle', 'weapon'
}

def load_visitors_into_faiss():
    global visitor_ids
    if not faiss or not faiss_index:
        return
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, embedding FROM visitors WHERE embedding IS NOT NULL")
        rows = cur.fetchall()
        if rows:
            embeddings = []
            visitor_ids = []
            for row in rows:
                embedding = np.frombuffer(row[1], dtype=np.float32)
                embeddings.append(embedding)
                visitor_ids.append(row[0])
            
            if embeddings:
                faiss_index.reset()
                faiss_index.add(np.array(embeddings).astype('float32'))
                logger.info(f"Loaded {len(visitor_ids)} visitors into FAISS index.")
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
    if not face_app:
        return []

    try:
        faces = face_app.get(frame)
        parsed = []
        for face in faces:
            fx1, fy1, fx2, fy2 = face.bbox.tolist()
            parsed.append({
                'bbox': [fx1, fy1, fx2, fy2],
                'embedding': face.embedding.astype('float32') if hasattr(face, 'embedding') else None
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

        label_overlap = set(signature['labels']).intersection(frame_labels)
        if label_overlap:
            signature['matched'] = True
            signature['first_match_time_sec'] = round(float(timestamp_sec), 2)
            signature['match_reason'] = f"Object match: {', '.join(sorted(label_overlap))}"
            continue

        for query_embedding in signature['face_embeddings']:
            for frame_embedding in frame_face_embeddings:
                dist = float(np.linalg.norm(query_embedding - frame_embedding))
                if dist < FACE_MATCH_THRESHOLD:
                    signature['matched'] = True
                    signature['first_match_time_sec'] = round(float(timestamp_sec), 2)
                    signature['match_reason'] = f"Face match (distance={dist:.3f})"
                    break
            if signature['matched']:
                break

def analyze_video_stream(video_capture, fps, query_signatures=None, restricted_zones=None):
    frame_index = 0
    object_counts = defaultdict(int)
    alerts = []
    alert_keys = set()
    track_state = {}
    heatmap_grid = np.zeros((HEATMAP_GRID_SIZE, HEATMAP_GRID_SIZE), dtype=np.int32)
    processed_frames = 0
    video_duration_sec = 0.0
    object_timeline = defaultdict(list)  # Track when each object type appears

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
                object_counts[label] += 1

                # Track timestamp for this object detection
                if not object_timeline[label] or abs(object_timeline[label][-1] - timestamp_sec) > 0.5:
                    # Only record if first occurrence or >0.5s since last
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

        if query_signatures:
            _match_queries_in_frame(query_signatures, frame_labels, frame_face_embeddings, timestamp_sec)

    # Clean query signatures for JSON serialization (remove numpy arrays)
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

    # Prepare object detections with timestamps
    object_detections = []
    for label, timestamps in sorted(object_timeline.items()):
        object_detections.append({
            'label': label,
            'count': object_counts[label],
            'timestamps': timestamps[:20],  # Limit to first 20 occurrences
            'first_seen': timestamps[0] if timestamps else None,
            'last_seen': timestamps[-1] if timestamps else None
        })

    return {
        'processed_frames': processed_frames,
        'video_duration_sec': round(float(video_duration_sec), 2),
        'object_counts': dict(sorted(object_counts.items(), key=lambda item: item[1], reverse=True)),
        'object_detections': object_detections,
        'alerts': alerts,
        'alert_count': len(alerts),
        'heatmap': _compute_heatmap_points(heatmap_grid, HEATMAP_GRID_SIZE),
        'queries': clean_queries
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

    # Use werkzeug for password hashing
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
        
        # Use tracking if requested or by default for video
        # model.track returns results with .boxes.id
        results = model.track(img, persist=True, conf=0.25, verbose=False)
        
        detections = []
        
        # For Face Recognition, we'll also run FaceAnalysis on the whole frame
        # (Optimally we'd only run it on person crops, but insightface prefers the full frame context for detection)
        faces = []
        if face_app:
            faces = face_app.get(img)

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
                
                # If it's a person, try to match with detected faces
                if label == 'person' and faces:
                    # Find face that falls within this person's bounding box
                    for face in faces:
                        fx1, fy1, fx2, fy2 = face.bbox.tolist()
                        # Simple overlap check
                        if fx1 >= x1 and fx2 <= x2 and fy1 >= y1 and fy2 <= y2:
                            embedding = face.embedding.astype('float32')
                            
                            # Search in FAISS
                            if faiss and faiss_index and faiss_index.ntotal > 0:
                                D, I = faiss_index.search(np.array([embedding]), 1)
                                if D[0][0] < 0.6: # Threshold for L2 distance (adjust as needed)
                                    v_id = visitor_ids[I[0][0]]
                                    visitor_status = "Returning Visitor"
                                    # Update last seen in DB
                                    conn = get_db_connection()
                                    if conn:
                                        cur = conn.cursor(cursor_factory=RealDictCursor)
                                        cur.execute("UPDATE visitors SET last_seen = NOW(), visit_count = visit_count + 1 WHERE id = %s RETURNING name", (v_id,))
                                        v_row = cur.fetchone()
                                        visitor_name = v_row['name'] if v_row else "Visitor"
                                        conn.commit()
                                        conn.close()
                                else:
                                    visitor_status = "New Visitor"
                                    # Add to DB
                                    conn = get_db_connection()
                                    if conn:
                                        cur = conn.cursor()
                                        cur.execute("INSERT INTO visitors (embedding) VALUES (%s) RETURNING id", (psycopg2.Binary(embedding.tobytes()),))
                                        new_id = cur.fetchone()[0]
                                        conn.commit()
                                        conn.close()
                                        # Refresh FAISS
                                        load_visitors_into_faiss()
                            else:
                                visitor_status = "New Visitor"
                                # First or no faiss
                                conn = get_db_connection()
                                if conn:
                                    cur = conn.cursor()
                                    cur.execute("INSERT INTO visitors (embedding) VALUES (%s) RETURNING id", (psycopg2.Binary(embedding.tobytes()),))
                                    new_id = cur.fetchone()[0]
                                    conn.commit()
                                    conn.close()
                                    load_visitors_into_faiss()
                            break # One face per person for now

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
        # Read frame
        img_bytes = frame_file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'error': 'Invalid frame format'}), 400

        frame_h, frame_w = frame.shape[:2]
        
        # Run YOLO detection
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
                
                # Normalized coordinates
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
                
                # Check for suspicious objects
                if label.lower() in SUSPICIOUS_OBJECT_KEYWORDS:
                    alerts.append({
                        'type': 'suspicious_object',
                        'severity': 'high',
                        'message': f"Suspicious object detected: {label}"
                    })
                    alert_count += 1

        # Face detection and matching (if query images provided)
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
                
                # Check object label overlap
                label_overlap = set(signature['labels']).intersection(frame_labels)
                if label_overlap:
                    matched = True
                    match_reason = f"Object match: {', '.join(sorted(label_overlap))}"
                
                # Check face matching
                if not matched:
                    for query_embedding in signature['face_embeddings']:
                        for frame_embedding in frame_face_embeddings:
                            dist = float(np.linalg.norm(query_embedding - frame_embedding))
                            if dist < FACE_MATCH_THRESHOLD:
                                matched = True
                                match_reason = f"Face match (distance={dist:.3f})"
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
    # Use environment variable for debug mode, default to False for production safety
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Configure timeouts and limits
    import socket
    socket.setdefaulttimeout(600)  # 10 minute timeout for video processing
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)