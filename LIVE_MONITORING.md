# Live Webcam Monitoring - Real-Time Video Analysis

## Overview
Live webcam monitoring with real-time object detection, behavioral analysis, and query image matching. Perfect for testing and demonstration purposes.

## Features

### 🎥 **Real-Time Video Processing**
- **Webcam Access** - Uses browser's `getUserMedia` API
- **Live Feed** - Displays video at 1280x720 resolution
- **2 FPS Processing** - Analyzes frames every 500ms for optimal performance
- **Bounding Box Overlay** - Real-time object detection visualization

### 🎯 **Object Detection**
- **YOLO11n Model** - Fast, accurate object detection
- **80+ Classes** - Detects people, vehicles, animals, objects
- **Confidence Scores** - Shows detection confidence percentage
- **Green Overlays** - Visual bounding boxes on video feed

### ⚠️ **Real-Time Alerts**
- **Suspicious Objects** - Flags weapons (knife, gun, etc.)
- **Face Matches** - Alerts when query faces are detected
- **Behavioral Analysis** - Real-time unusual activity detection
- **Alert History** - Keeps last 50 alerts with timestamps

### 🖼️ **Query Image Matching**
- **Upload Multiple Images** - Drag & drop or select query images
- **Face Recognition** - Matches faces using ArcFace embeddings
- **Object Matching** - Finds similar objects in live feed
- **Visual Preview** - Shows uploaded query images as thumbnails

### 📊 **Live Statistics**
- **Processing Speed** - Current FPS (frames per second)
- **Object Count** - Number of objects in current frame
- **Alert Counter** - Total active alerts
- **Detection List** - Real-time list of detected objects

## User Interface

### Layout

```
┌─────────────────────────────────────────────────────────┐
│              📹 Live Webcam Monitor                     │
│      Real-time object detection & behavioral analysis   │
├────────────────────────────┬────────────────────────────┤
│                            │        📊 Live Stats       │
│     Live Video Feed        │  ┌────────────────────┐   │
│  ┌──────────────────┐      │  │ FPS: 2             │   │
│  │                  │ LIVE │  │ Objects: 3         │   │
│  │   [Video]        │      │  │ Alerts: 1          │   │
│  │                  │      │  └────────────────────┘   │
│  └──────────────────┘      │                            │
│                            │  Current Detections:       │
│  🎥 Start  ⏹️ Stop        │  • person (95%)            │
│                            │  • car (88%)               │
│ ─────────────────────      │  • backpack (75%)          │
│  🖼️ Query Images          │                            │
│  [Upload Images]           │  ⚠️ Live Alerts           │
│  [□] [□] [□] Previews      │  • Face match detected!   │
│                            │  • Suspicious object       │
└────────────────────────────┴────────────────────────────┘
```

### Color Scheme
- **Background Gradient** - Purple gradient (#667eea → #764ba2)
- **White Cards** - Clean white sections with shadows
- **Status Badge** - Green (LIVE) / Red (OFFLINE)
- **Detection Boxes** - Green (#48bb78)
- **Alerts** - Color-coded by severity (red/orange/blue)

## Technical Architecture

### Frontend Component

**File:** [frontend/src/components/LiveMonitor.tsx](frontend/src/components/LiveMonitor.tsx)

**Key Technologies:**
- React Hooks (useState, useRef, useEffect, useCallback)
- Canvas API for frame capture
- MediaDevices API for webcam access
- Fetch API for frame upload

**Component Structure:**
```typescript
LiveMonitor
├── Video Feed (HTMLVideoElement)
├── Detection Overlay (HTMLCanvasElement)
├── Control Buttons (Start/Stop)
├── Query Image Upload
├── Live Stats Panel
├── Detections List
└── Alerts Panel
```

### Backend Endpoint

**File:** [backend/app.py](backend/app.py)

**Endpoint:** `POST /process-frame`

**Request:**
```
Content-Type: multipart/form-data

frame: [JPEG/PNG image file] (required)
query_images: [image file] (optional, multiple)
```

**Response:**
```json
{
  "status": "success",
  "detections": [
    {
      "label": "person",
      "confidence": 0.952,
      "box": {
        "x": 0.3421,
        "y": 0.2156,
        "width": 0.1234,
        "height": 0.4567
      }
    }
  ],
  "alerts": [
    {
      "type": "suspicious_object",
      "severity": "high",
      "message": "Suspicious object detected: knife"
    }
  ],
  "alert_count": 1,
  "query_matches": [
    {
      "filename": "suspect.jpg",
      "matched": true,
      "match_reason": "Face match (distance=0.382)"
    }
  ],
  "frame_dimensions": {
    "width": 1280,
    "height": 720
  }
}
```

### Processing Pipeline

1. **Frame Capture**
   ```javascript
   canvas.toBlob((blob) => {
     formData.append('frame', blob, 'frame.jpg');
     fetch('/process-frame', { method: 'POST', body: formData });
   });
   ```

2. **Backend Processing**
   ```python
   frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
   results = model.predict(frame, conf=0.25)
   detections = extract_boxes(results)
   alerts = check_behavioral_alerts(detections)
   query_matches = match_query_images(frame, queries)
   ```

3. **Result Visualization**
   ```javascript
   drawDetections(detections); // Draw bounding boxes
   setAlerts(newAlerts);       // Update alert list
   setStats({ fps, count });    // Update statistics
   ```

## Usage Instructions

### 1. Access Live Monitor
1. Open VisionIQ application
2. Click **"Live Monitor"** in the sidebar (📹 camera icon)
3. Click **"Start Webcam"** button

### 2. Grant Camera Permission
Your browser will ask for webcam access:
```
Allow [YourSite] to use your camera?
[Block] [Allow]
```
Click **Allow** to proceed.

### 3. Add Query Images (Optional)
1. Click "Choose Files" under Query Images
2. Select one or more images of people/objects to find
3. See thumbnail previews
4. Live feed will alert when matches are found

### 4. Monitor Live Feed
- **Green boxes** appear around detected objects
- **Live stats** update in real-time
- **Alerts** show up immediately when triggered
- **Status badge** shows LIVE/OFFLINE

### 5. Stop Monitoring
Click **"Stop"** button to:
- Stop webcam access
- Clear detections
- Release camera resources

## Performance Optimization

### Frame Processing Rate

**Default:** 500ms interval (2 FPS)

**Why not higher?**
- ML processing takes ~200-400ms per frame
- Network latency adds 50-100ms
- Browser rendering needs time
- Prevents overwhelming the backend

**To adjust:**
```javascript
// In LiveMonitor.tsx, line ~160
intervalRef.current = window.setInterval(() => {
  processFrame();
}, 500); // Change this value (milliseconds)
```

**Recommendations:**
- **Testing on localhost:** 300-500ms (2-3 FPS)
- **Production over network:** 500-1000ms (1-2 FPS)
- **High-performance setup:** 200-300ms (3-5 FPS)

### Frame Quality

**Default:** JPEG at 80% quality

**Why JPEG?**
- Fast encoding
- Small file size (~50-100 KB per frame)
- Sufficient for detection

**To adjust:**
```javascript
// In LiveMonitor.tsx, line ~186
canvas.toBlob(async (blob) => {
  // ... upload logic
}, 'image/jpeg', 0.8); // Quality: 0.0-1.0
```

**Trade-offs:**
- **Higher quality (0.9):** Better accuracy, slower upload
- **Lower quality (0.6):** Faster upload, may miss small objects

### Video Resolution

**Default:** 1280x720 (HD)

**To adjust:**
```javascript
// In LiveMonitor.tsx, line ~142
const stream = await navigator.mediaDevices.getUserMedia({
  video: { width: 1280, height: 720 },
  audio: false
});
```

**Options:**
- **640x480** - VGA (fastest)
- **1280x720** - HD (balanced)
- **1920x1080** - Full HD (best quality, slower)

## Alert Types

### 1. Suspicious Object Detection
```json
{
  "type": "suspicious_object",
  "severity": "high",
  "message": "Suspicious object detected: knife"
}
```
**Triggers:** knife, gun, rifle, firearm, weapon

### 2. Face Match Alert
```json
{
  "type": "face_match",
  "severity": "high",
  "message": "Query face matched: suspect.jpg"
}
```
**Triggers:** When uploaded face matches detected face

### 3. Object Match Alert
```json
{
  "type": "object_match",
  "severity": "medium",
  "message": "Object match: person, backpack"
}
```
**Triggers:** When query image objects appear in frame

## Browser Compatibility

### Required Features
- ✅ getUserMedia API (webcam access)
- ✅ Canvas API (frame capture)
- ✅ Fetch API (upload frames)
- ✅ Blob API (image encoding)

### Supported Browsers
| Browser | Version | Status |
|---------|---------|--------|
| Chrome | 90+ | ✅ Full support |
| Firefox | 88+ | ✅ Full support |
| Safari | 14+ | ✅ Full support |
| Edge | 90+ | ✅ Full support |
| Mobile Safari | 14.5+ | ⚠️ Limited (no webcam) |
| Mobile Chrome | 90+ | ⚠️ Limited (no webcam) |

**Note:** Webcam access may not work on mobile devices due to browser restrictions.

## Security & Privacy

### Camera Access
- **Permission Required** - Browser asks user for explicit consent
- **Secure Context Only** - Requires HTTPS in production
- **No Recording** - Frames processed in real-time, not stored
- **Local Processing** - Only current frame sent to server

### Data Handling
- **No Video Storage** - Frames discarded after processing
- **No Query Storage** - Query images only in memory
- **No Face Database** - Face embeddings not saved (unless explicitly added)
- **Session-Only** - All data cleared when page closes

### Best Practices
1. **HTTPS Required** - Use secure connection in production
2. **Clear Indication** - Status badge shows when camera is active
3. **Easy Stop** - Prominent stop button always available
4. **Privacy Notice** - Inform users before starting

## Troubleshooting

### Camera Not Accessible

**Error:** "Could not access webcam"

**Solutions:**
1. Check browser permissions (Settings → Privacy → Camera)
2. Ensure no other app is using the camera
3. Try refreshing the page
4. Use HTTPS (required for production)

### Low Frame Rate

**Symptom:** Processing slower than expected

**Solutions:**
1. Close other resource-intensive apps
2. Increase interval (500ms → 1000ms)
3. Lower video resolution (1280x720 → 640x480)
4. Reduce JPEG quality (0.8 → 0.6)

### No Detections Showing

**Symptom:** Video works but no objects detected

**Solutions:**
1. Check backend is running: `curl http://localhost:5001/health`
2. Verify CORS allows your frontend port
3. Check browser console for errors
4. Ensure good lighting for detection

### Alerts Not Triggering

**Symptom:** Objects detected but no alerts

**Solutions:**
1. Verify suspicious object keywords match (check SUSPICIOUS_OBJECT_KEYWORDS)
2. For face matching, ensure query images are clear
3. Adjust FACE_MATCH_THRESHOLD if needed
4. Check alert history - may be already triggered

## Use Cases

### 1. Security Testing
Test surveillance system with live feed:
- Verify detection accuracy
- Test alert triggers
- Check face recognition
- Validate response times

### 2. Demo & Presentation
Show real-time capabilities:
- Live object detection
- Instant alerts
- Query matching
- Visual feedback

### 3. Development & Debugging
Test new features:
- Quick iteration
- Immediate feedback
- No video file needed
- Easy setup

### 4. Training & Education
Demonstrate AI capabilities:
- Interactive learning
- Visual explanations
- Real-time results
- Engaging demonstrations

## Future Enhancements

### 1. Recording Capability
```
[ Record ] [ Stop Recording ]
Save processed video with bounding boxes
```

### 2. Multiple Camera Sources
```
Select Camera:
[ Front Camera ▼ ]
[ External Webcam ]
[ Screen Share ]
```

### 3. Advanced Overlays
```
• Tracking IDs
• Object trajectories
• Heatmap overlay
• Zone boundaries
```

### 4. Performance Metrics
```
• Latency graph
• Detection accuracy
• Frame drop rate
• Bandwidth usage
```

### 5. Export & Share
```
• Screenshot current frame
• Export detection logs
• Share alert history
• Generate reports
```

## Configuration

### Backend Configuration

**File:** [backend/.env](backend/.env)

```bash
# Detection confidence threshold
YOLO_CONFIDENCE=0.25

# Face matching threshold
FACE_MATCH_THRESHOLD=0.6

# Suspicious object keywords
SUSPICIOUS_OBJECT_KEYWORDS=knife,gun,rifle,firearm,weapon

# CORS allowed origins (add your frontend port)
ALLOWED_ORIGINS=http://localhost:5174
```

### Frontend Configuration

**File:** [frontend/.env.local](frontend/.env.local)

```bash
# Backend API URL
VITE_API_URL=http://localhost:5001
```

## Testing Checklist

- [ ] Camera permission prompt appears
- [ ] Video feed displays correctly
- [ ] Status badge shows "LIVE"
- [ ] Objects detected with bounding boxes
- [ ] Detection list updates in real-time
- [ ] Stats update (FPS, count)
- [ ] Query images can be uploaded
- [ ] Query image previews display
- [ ] Alerts trigger correctly
- [ ] Alert history maintains
- [ ] Stop button stops camera
- [ ] Status badge shows "OFFLINE" after stop
- [ ] No console errors
- [ ] Responsive on different screen sizes

---

**Version:** 2.3  
**Date:** February 19, 2026  
**Status:** ✅ Production Ready
**Testing:** ✅ Webcam Required
