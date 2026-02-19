#!/usr/bin/env bash

# VisionIQ - Complete API Usage Examples
# Run these commands after both backend and frontend are running

BASE_URL="http://localhost:5001"

echo "=========================================="
echo "VisionIQ API Examples"
echo "=========================================="

# 1. Health Check
echo -e "\n\n📋 1. HEALTH CHECK"
echo "Verify backend and model are ready..."
echo ""
echo "curl -X GET $BASE_URL/health | jq"
echo ""
echo "Expected response: model_loaded=true, db_connected=true"

# 2. Single Image Detection
echo -e "\n\n🖼️  2. SINGLE IMAGE DETECTION"
echo "Detect objects in a single image..."
echo ""
cat << 'EOF'
# First, convert your image to base64:
BASE64_IMAGE=$(base64 -i /path/to/image.jpg | tr -d '\n')

# Send for detection:
curl -X POST http://localhost:5001/detect \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$BASE64_IMAGE\"}" | jq
EOF

# 3. Video Full Analysis
echo -e "\n\n📹 3. FULL VIDEO ANALYSIS"
echo "Analyze video for objects, behavior, and optional query matching..."
echo ""
cat << 'EOF'
curl -X POST http://localhost:5001/analyze-video \
  -F "video=@/path/to/video.mp4" \
  -F "query_images=@/path/to/suspect.jpg" \
  -F 'restricted_zones=[{"name":"vault","x1":0.1,"y1":0.2,"x2":0.5,"y2":0.7}]' | jq
EOF

# 4. Query-Only Matching
echo -e "\n\n🔍 4. QUERY IMAGE MATCHING (FAST)"
echo "Search video for specific people/objects..."
echo ""
cat << 'EOF'
curl -X POST http://localhost:5001/match-video-queries \
  -F "video=@/path/to/surveillance.mp4" \
  -F "query_images=@/path/to/person1.jpg" \
  -F "query_images=@/path/to/person2.jpg" | jq
EOF

# 5. Statistics
echo -e "\n\n📊 5. GET STATISTICS"
echo "View available object classes and model info..."
echo ""
echo "curl -X GET $BASE_URL/stats | jq"

# 6. JSON Request Body Example
echo -e "\n\n📄 6. EXAMPLE RESPONSE - FULL ANALYSIS"
echo "This is what you'll get back from /analyze-video:"
echo ""
cat << 'EOF'
{
  "status": "success",
  "model": "yolo11n.pt",
  "analytics": {
    "processed_frames": 1250,
    "video_duration_sec": 50.0,
    
    "object_counts": {
      "person": 125,
      "car": 8,
      "backpack": 2,
      "knife": 1
    },
    
    "alert_count": 4,
    "alerts": [
      {
        "type": "loitering",
        "severity": "high",
        "time_sec": 12.5,
        "message": "Potential loitering detected for track 3 (14.2s)"
      },
      {
        "type": "suspicious_object",
        "severity": "high",
        "time_sec": 25.0,
        "message": "Suspicious object 'knife' detected"
      },
      {
        "type": "intrusion",
        "severity": "high",
        "time_sec": 18.5,
        "message": "Person entered restricted zone 'vault'"
      },
      {
        "type": "rapid_motion",
        "severity": "medium",
        "time_sec": 35.2,
        "message": "Fast movement detected for track 5"
      }
    ],
    
    "heatmap": [
      {"x": 15.5, "y": 45.2, "intensity": 0.95},
      {"x": 72.3, "y": 28.1, "intensity": 0.45},
      {"x": 48.2, "y": 52.7, "intensity": 0.78}
    ],
    
    "queries": [
      {
        "query_index": 0,
        "filename": "suspect.jpg",
        "matched": true,
        "first_match_time_sec": 18.5,
        "match_reason": "Face match (distance=0.45)",
        "labels": ["person"]
      },
      {
        "query_index": 1,
        "filename": "weapon.jpg",
        "matched": true,
        "first_match_time_sec": 25.0,
        "match_reason": "Object match: knife",
        "labels": ["knife"]
      }
    ]
  }
}
EOF

# 7. Query Response Example
echo -e "\n\n📄 7. EXAMPLE RESPONSE - QUERY MATCHING"
echo "This is what you'll get back from /match-video-queries:"
echo ""
cat << 'EOF'
{
  "status": "success",
  "results": [
    {
      "query_index": 0,
      "filename": "person_of_interest.jpg",
      "matched": true,
      "first_match_time_sec": 12.5,
      "match_reason": "Face match (distance=0.52)",
      "labels_in_query": ["person"]
    },
    {
      "query_index": 1,
      "filename": "another_person.jpg",
      "matched": false,
      "first_match_time_sec": null,
      "match_reason": null,
      "labels_in_query": ["person"]
    }
  ]
}
EOF

# 8. Configuration Examples
echo -e "\n\n⚙️  8. ENVIRONMENT CONFIGURATION EXAMPLES"
echo ""
echo "Create backend/.env with these settings:"
echo ""
cat << 'EOF'
# Configuration Example 1: FAST MODE (Real-time 30+ FPS)
DATABASE_URL=postgresql://user:pass@localhost/visioniq
JWT_SECRET=your-secret-key
PORT=5001
YOLO_MODEL_PATH=yolo11n.pt
VIDEO_SAMPLE_EVERY_N_FRAMES=10
LOITERING_SECONDS=8
FACE_MATCH_THRESHOLD=0.7

# Configuration Example 2: HIGH ACCURACY (5-10 FPS)
# Change these values:
YOLO_MODEL_PATH=yolo11x.pt
VIDEO_SAMPLE_EVERY_N_FRAMES=2
LOITERING_SECONDS=15
FACE_MATCH_THRESHOLD=0.5

# Configuration Example 3: SENSITIVE SECURITY (Medium speed, strict alerts)
YOLO_MODEL_PATH=yolo11m.pt
VIDEO_SAMPLE_EVERY_N_FRAMES=5
LOITERING_SECONDS=5
SUSPICIOUS_SPEED_PX=40.0
FACE_MATCH_THRESHOLD=0.55
EOF

# 9. Frontend Usage
echo -e "\n\n🎨 9. FRONTEND USAGE"
echo ""
echo "1. Navigate to http://localhost:5173"
echo "2. Login (or register new account)"
echo "3. Click 'Video Analyzer' in sidebar"
echo "4. Upload video file (MP4, AVI, MOV, WebM)"
echo "5. Optionally add query images"
echo "6. Click 'Full Analysis' or 'Query Match'"
echo "7. View results with object counts, alerts, heatmap, and matches"

# 10. Practical NSG Use Cases
echo -e "\n\n🏢 10. PRACTICAL NSG USE CASES"
echo ""
cat << 'EOF'
==== CASE 1: Bank Robbery Investigation ====
1. Get surveillance footage from 2:00 PM - 3:00 PM
2. Get mugshot of wanted suspect
3. Upload video + suspect photo to /analyze-video
4. System returns: "Found at 2:34 PM, 2:47 PM (face match)"
5. Review those moments for positive identification

==== CASE 2: Suspicious Weapon Alert ====
1. Monitor entrance lobby (real-time or batch)
2. Knife detected at 2:30 PM (SEVERITY: HIGH)
3. Alert shows timestamp and video coordinates
4. Security team responds within 30 seconds
5. Weapon is recovered before escalation

==== CASE 3: VIP Protection - Intrusion ====
1. Define VIP lounge as restricted zone
2. Person enters without authorization
3. System alerts: "Intrusion into VIP Zone at 3:15 PM"
4. Security can respond proactively
5. Logs create audit trail

==== CASE 4: Crowd Density at Event ====
1. Monitor event hall during conference
2. Heatmap shows density concentration
3. Over 50 people in emergency exit area
4. Alert sent to event coordinator
5. Redirect crowd for safety

==== CASE 5: Known Visitor Tracking ====
1. Upload photos of known associates (first time)
2. System learns their faces (ArcFace embeddings)
3. Next event: visitor appears again
4. System: "Returning Visitor - seen 3 times before"
5. Security has prior knowledge
EOF

# 11. Troubleshooting
echo -e "\n\n🔧 11. TROUBLESHOOTING"
echo ""
cat << 'EOF'
❌ "Model not loaded" error:
   → Check YOLO model exists: cd backend && ls *.pt
   → Or re-run: python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"

❌ "No video file provided" error:
   → Use correct form field name: -F "video=@file.mp4"
   → Check file is readable: file /path/to/video.mp4

❌ "Database connection failed" error:
   → Verify DATABASE_URL in backend/.env
   → Check PostgreSQL is running: psql -U user -d visioniq

❌ "Face recognition not working" error:
   → Check insightface installed: pip list | grep insightface
   → Verify database connectivity: curl http://localhost:5001/health

❌ Video processing times out:
   → Reduce VIDEO_SAMPLE_EVERY_N_FRAMES (use value 10-20)
   → Switch to smaller model: YOLO_MODEL_PATH=yolo11n.pt
   → Reduce HEATMAP_GRID_SIZE to 10
EOF

# 12. Performance Tips
echo -e "\n\n⚡ 12. PERFORMANCE OPTIMIZATION TIPS"
echo ""
cat << 'EOF'
📌 For Production Systems:
   ✓ Use GPU (CUDA/TensorRT) for 5-10x speedup
   ✓ Use yolo11n.pt for real-time processing
   ✓ Set VIDEO_SAMPLE_EVERY_N_FRAMES=10-20 for speed
   ✓ Reduce HEATMAP_GRID_SIZE to 10
   ✓ Run behind nginx with gzip compression
   ✓ Enable model caching (inference.yaml)

📌 For Accuracy:
   ✓ Use yolo11x.pt (largest model)
   ✓ Set VIDEO_SAMPLE_EVERY_N_FRAMES=1-2
   ✓ Lower FACE_MATCH_THRESHOLD to 0.4-0.5
   ✓ Enable multi-frame temporal filtering

📌 For Memory-Constrained Systems:
   ✓ Use YOLO11n or YOLO8n model
   ✓ Reduce frame resolution (resize input)
   ✓ Batch process instead of real-time
   ✓ Clear FAISS index periodically
EOF

echo -e "\n=========================================="
echo "For more info, see:"
echo "  • SETUP_AND_DEPLOYMENT.md (full guide)"
echo "  • FEATURES.md (feature overview)"
echo "  • backend/.env.example (all settings)"
echo "=========================================="
