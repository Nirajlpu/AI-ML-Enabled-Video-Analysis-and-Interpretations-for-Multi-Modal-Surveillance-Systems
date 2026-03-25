// services/detectionService.ts

// Use environment variable or fallback to localhost
const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || 'http://localhost:5001';

export interface Detection {
  label: string;
  box: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  confidence?: number;
}

export interface HealthStatus {
  status: string;
  model: string;
}

export interface VideoAlert {
  type: string;
  severity: 'low' | 'medium' | 'high' | string;
  time_sec: number;
  message: string;
}

export interface HeatmapPoint {
  x: number;
  y: number;
  intensity: number;
}

export interface ObjectDetection {
  label: string;
  count: number;         // unique individuals / objects by track ID
  frame_count?: number;  // total sampled-frame detections (informational)
  timestamps: number[];
  first_seen: number | null;
  last_seen: number | null;
}

export interface TrackedPerson {
  track_id: number;
  first_seen: number;
  last_seen: number;
  confidence: number;
  image: string; // base64-encoded JPEG crop
}

export interface QueryMatchResult {
  query_index: number;
  filename: string;
  matched: boolean;
  first_match_time_sec: number | null;
  match_reason: string | null;
  labels_in_query: string[];
  error?: string;
}

export interface VideoAnalyticsResult {
  processed_frames: number;
  video_duration_sec: number;
  object_counts: Record<string, number>;
  object_detections: ObjectDetection[];
  alerts: VideoAlert[];
  alert_count: number;
  heatmap: HeatmapPoint[];
  tracked_persons?: TrackedPerson[];  // NEW: per-person snapshot gallery
  queries: Array<{
    query_index: number;
    filename: string;
    labels: string[];
    matched: boolean;
    first_match_time_sec: number | null;
    match_reason: string | null;
    error?: string;
  }>;
}

/**
 * Sends image data to the local Python backend to detect objects.
 * @param base64ImageData - The base64-encoded image string (without the data URI prefix).
 * @returns A promise that resolves to an array of detected objects.
 */
export async function detectObjects(base64ImageData: string): Promise<Detection[]> {
  try {
    const token = localStorage.getItem('token');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE_URL}/detect`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ image: base64ImageData }),
    });

    console.log(`Detection response status: ${response.status}`);

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to detect objects');
    }

    const detections: Detection[] = await response.json();
    return detections;
  } catch (error) {
    console.error('Error calling detection backend:', error);
    throw error;
  }
}

/**
 * Check if backend server is healthy and model is loaded
 * @returns Health status information
 */
export async function checkHealth(): Promise<HealthStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
    });

    if (!response.ok) {
      throw new Error(`Health check failed with status: ${response.status}`);
    }

    const health: HealthStatus = await response.json();
    return health;
  } catch (error) {
    console.error('Health check error:', error);
    throw error;
  }
}

export async function analyzeVideo(
  videoFile: File,
  queryImages: File[] = [],
  restrictedZones?: Array<{ name?: string; x1: number; y1: number; x2: number; y2: number }>
): Promise<VideoAnalyticsResult> {
  const formData = new FormData();
  formData.append('video', videoFile);
  queryImages.forEach((image) => formData.append('query_images', image));

  if (restrictedZones && restrictedZones.length > 0) {
    formData.append('restricted_zones', JSON.stringify(restrictedZones));
  }

  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 minute timeout
    
    const response = await fetch(`${API_BASE_URL}/analyze-video`, {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || `Server error: ${response.status}`);
    }

    const data = await response.json();
    
    // Validate response format
    if (!data.analytics) {
      throw new Error('Invalid response format from server');
    }
    
    return data.analytics as VideoAnalyticsResult;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Video analysis timed out. Please try a smaller video or wait longer.');
    }
    throw error;
  }
}

export async function matchVideoQueries(videoFile: File, queryImages: File[]): Promise<QueryMatchResult[]> {
  const formData = new FormData();
  formData.append('video', videoFile);
  queryImages.forEach((image) => formData.append('query_images', image));

  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 minute timeout
    
    const response = await fetch(`${API_BASE_URL}/match-video-queries`, {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || `Server error: ${response.status}`);
    }

    const data = await response.json();
    console.log('Query match response:', data);
    
    // Validate response format
    if (!data.results) {
      throw new Error('Invalid response format from server - missing results field');
    }
    
    return data.results as QueryMatchResult[];
  } catch (error) {
    console.error('Query matching error:', error);
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Query matching timed out. Please try a smaller video or wait longer.');
    }
    throw error;
  }
}

export default {
  detectObjects,
  checkHealth,
  analyzeVideo,
  matchVideoQueries,
};