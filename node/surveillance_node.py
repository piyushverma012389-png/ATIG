"""
ATIG Surveillance Node — High-Performance Edition
Multi-threaded video capture, asynchronous YOLOv12 inference,
smooth 30 FPS MJPEG streaming, and real-time C2 telemetry push.
"""

import sys
import os
import cv2
import time
import json
import signal
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
import requests
import paho.mqtt.client as mqtt
from flask import Flask, Response

# Ensure node directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yolo_detector import YOLODetector
from sensor_fusion import SensorFusion

# ─── Configuration ───────────────────────────────────────────
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPICS = {
    "alerts": "atig/alerts",
    "heartbeat": "atig/heartbeat",
    "rover_command": "atig/rover/command",
}
NODE_ID = "Node_Alpha"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_config = {"dashboard_url": "http://localhost:8502"}
_http_pool = ThreadPoolExecutor(max_workers=4)

# ─── Flask App for MJPEG Streaming ──────────────────────────
flask_app = Flask(__name__)
current_frame_bytes = None
frame_lock = threading.Lock()
shutdown_event = threading.Event()


def generate_frames():
    """Yield MJPEG frames for the web client with non-blocking generator."""
    last_sent_time = 0
    while not shutdown_event.is_set():
        with frame_lock:
            frame_data = current_frame_bytes
        if frame_data is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(0.03)  # ~33 FPS cap
        else:
            time.sleep(0.02)


@flask_app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@flask_app.route('/health')
def health():
    return "OK", 200


# ─── Async HTTP Ingest Push ──────────────────────────────────
def _post_alert_worker(url, payload):
    try:
        requests.post(f"{url}/api/ingest/alert", json=payload, timeout=1.5)
    except Exception:
        pass


def _post_heartbeat_worker(url, payload):
    try:
        requests.post(f"{url}/api/ingest/heartbeat", json=payload, timeout=1.5)
    except Exception:
        pass


def push_alert_to_dashboard(payload):
    _http_pool.submit(_post_alert_worker, _config['dashboard_url'], payload)


def push_heartbeat_to_dashboard(payload):
    _http_pool.submit(_post_heartbeat_worker, _config['dashboard_url'], payload)


# ─── Dedicated Threaded Camera ───────────────────────────────
class ThreadedCamera:
    """
    Dedicated background capture thread that continuously drains the camera buffer.
    Guarantees 0-latency / real-time fresh frames.
    """

    def __init__(self, src=0):
        # Convert numeric string to int
        try:
            src = int(src)
        except (ValueError, TypeError):
            pass

        # Use DirectShow on Windows for instant webcam opening
        if isinstance(src, int) and os.name == 'nt':
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(src)

        # Configure camera for optimal speed
        if isinstance(src, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.is_opened = self.cap.isOpened()
        self.ret = False
        self.frame = None
        self.running = False
        self.lock = threading.Lock()

        if self.is_opened:
            self.ret, self.frame = self.cap.read()
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def _capture_loop(self):
        while self.running and not shutdown_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                # Loop video file if ended
                if self.cap.get(cv2.CAP_PROP_FRAME_COUNT) > 1:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

            with self.lock:
                self.ret = ret
                self.frame = frame
            time.sleep(0.005)

    def read(self):
        with self.lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return False, None

    def release(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()


# ─── Main Application ────────────────────────────────────────
def main():
    global current_frame_bytes

    parser = argparse.ArgumentParser(description="ATIG Surveillance Node — Fast Edition")
    parser.add_argument('--source', type=str, default="0",
                        help='Video source (URL, file path, or camera index)')
    parser.add_argument('--port', type=int, default=5000,
                        help='MJPEG stream port (default: 5000)')
    parser.add_argument('--node-id', type=str, default=NODE_ID,
                        help='Node identifier (default: Node_Alpha)')
    parser.add_argument('--dashboard', type=str, default=_config['dashboard_url'],
                        help='Dashboard URL for direct HTTP push')
    args = parser.parse_args()

    node_id = args.node_id
    _config['dashboard_url'] = args.dashboard

    print("=" * 60)
    print(f"  ATIG Surveillance Node // {node_id}")
    print(f"  AI Engine: YOLOv12 (High-Performance Real-Time)")
    print("=" * 60)

    # ── Initialize AI Engine ──
    detector = YOLODetector()
    fusion = SensorFusion()

    # ── Connect MQTT (Async Background) ──
    mqtt_client = None
    def _async_mqtt_init():
        nonlocal mqtt_client
        try:
            m = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            m.connect(MQTT_BROKER, MQTT_PORT, 5)
            m.loop_start()
            mqtt_client = m
            print(f"[Node] MQTT connected in background to {MQTT_BROKER}")
        except Exception:
            pass
    threading.Thread(target=_async_mqtt_init, daemon=True).start()

    # ── Start Threaded Camera ──
    print(f"[Node] Initializing camera source: {args.source}...")
    cam = ThreadedCamera(args.source)
    if not cam.is_opened:
        print(f"[Node] Direct source failed, trying webcam index 0...")
        cam = ThreadedCamera(0)
        if not cam.is_opened:
            print("[Node] FATAL: Could not open any camera source.")
            return

    print("[Node] ✓ Camera stream active with zero-buffer latency.")

    # ── Start MJPEG Server ──
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(host='0.0.0.0', port=args.port,
                                     debug=False, use_reloader=False, threaded=True),
        daemon=True
    )
    flask_thread.start()
    print(f"[Node] MJPEG stream: http://localhost:{args.port}/video_feed")

    # ── Shutdown Handlers ──
    def signal_handler(sig, frame):
        print("\n[Node] Shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ── Background AI Inference Worker ──
    # Decouples camera rendering (30 FPS) from YOLOv12 inference (~15-20 FPS)
    latest_detections = []
    det_lock = threading.Lock()
    total_detections = 0
    last_alert_time = 0

    def ai_inference_loop():
        nonlocal latest_detections, total_detections, last_alert_time
        while not shutdown_event.is_set():
            ret, frame = cam.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            # Run YOLOv12
            dets = detector.detect(frame, confidence_threshold=0.45)
            with det_lock:
                latest_detections = dets

            if dets:
                threats = fusion.evaluate_threat(dets)
                total_detections += len(threats)

                now = time.time()
                # Rate limit alert push to max once per 1.5s to keep UI snappy
                if threats and (now - last_alert_time) > 1.5:
                    for threat in threats:
                        payload = {
                            "node": node_id,
                            "object": threat['object'],
                            "threat_level": threat['threat_level'],
                            "confidence": threat['confidence'],
                            "distance": threat['distance'],
                            "timestamp": now
                        }
                        push_alert_to_dashboard(payload)
                        if mqtt_client:
                            try:
                                mqtt_client.publish(MQTT_TOPICS["alerts"], json.dumps(payload))
                            except Exception:
                                pass
                    last_alert_time = now

            time.sleep(0.01)

    ai_thread = threading.Thread(target=ai_inference_loop, daemon=True)
    ai_thread.start()

    # ── Rendering & Stream Encoding Loop (Smooth 30 FPS) ──
    fps_start = time.time()
    frame_counter = 0
    current_fps = 30.0
    start_time = time.time()
    last_heartbeat_time = 0

    print("[Node] Stream loop active. Ready.")
    print("-" * 60)

    while not shutdown_event.is_set():
        loop_start = time.time()
        ret, frame = cam.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        frame_counter += 1
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            current_fps = frame_counter / elapsed
            frame_counter = 0
            fps_start = time.time()

        # Get latest detections safely
        with det_lock:
            current_dets = list(latest_detections)

        # Draw tactical HUD & boxes
        display_frame = detector.draw_boxes(frame, current_dets)

        # HUD Overlay
        h, w = display_frame.shape[:2]
        cv2.putText(display_frame, f"ATIG // {node_id} // YOLOv12", (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 229, 255), 1, cv2.LINE_AA)
        cv2.putText(display_frame, f"STREAM FPS: {current_fps:.1f}", (10, 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 229, 255), 1, cv2.LINE_AA)
        cv2.putText(display_frame, f"TARGETS: {len(current_dets)}", (10, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 229, 255), 1, cv2.LINE_AA)

        # Tactical scanline / grid border
        cv2.rectangle(display_frame, (0, 0), (w - 1, h - 1), (0, 229, 255), 1)

        # Fast JPEG encoding (Quality 68 for fast compression & small payload)
        ret_enc, buffer = cv2.imencode('.jpg', display_frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, 68])
        if ret_enc:
            with frame_lock:
                current_frame_bytes = buffer.tobytes()

        # Heartbeat (every 5 seconds)
        if (time.time() - last_heartbeat_time) > 5:
            heartbeat = {
                "node_id": node_id,
                "status": "Online",
                "fps": round(current_fps, 1),
                "detections": total_detections,
                "uptime": round(time.time() - start_time, 1),
                "source": "Webcam 0",
            }
            push_heartbeat_to_dashboard(heartbeat)
            if mqtt_client:
                try:
                    mqtt_client.publish(MQTT_TOPICS["heartbeat"], json.dumps(heartbeat))
                except Exception:
                    pass
            last_heartbeat_time = time.time()

        # Regulate stream loop to ~30 FPS
        process_time = time.time() - loop_start
        sleep_time = max(0.001, (1.0 / 30.0) - process_time)
        time.sleep(sleep_time)

    # ── Cleanup ──
    print("[Node] Stopping camera and worker threads...")
    cam.release()
    _http_pool.shutdown(wait=False)
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    print("[Node] Shutdown complete.")


if __name__ == "__main__":
    main()
