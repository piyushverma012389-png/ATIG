"""
ATIG YOLOv12 Detection Engine — High-Performance Edition
Real-time object detection with optimized inference resolution and multi-threading.
"""

from ultralytics import YOLO
import cv2
import time
import os
import torch

# Optimize PyTorch CPU inference threads
try:
    torch.set_num_threads(max(2, min(os.cpu_count() or 4, 6)))
except Exception:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class YOLODetector:
    """High-performance YOLOv12 object detector for ATIG surveillance nodes."""

    def __init__(self, model_path=None):
        if model_path is None:
            local_model = os.path.join(PROJECT_ROOT, "yolo12n.pt")
            model_path = local_model if os.path.exists(local_model) else "yolo12n.pt"

        print(f"[AI] Loading YOLOv12 Model ({model_path})...")
        self.model = YOLO(model_path)
        print("[AI] YOLOv12 Model loaded.")

        # Target tactical classes (Humans, Vehicles, Drones, Animals only)
        self.target_classes = {
            0: "Human",
            2: "Vehicle", 3: "Vehicle", 5: "Vehicle", 6: "Vehicle", 7: "Vehicle", 8: "Vehicle",
            4: "Drone",
            14: "Animal", 15: "Animal", 16: "Animal", 17: "Animal", 18: "Animal",
            19: "Animal", 20: "Animal", 21: "Animal", 22: "Animal", 23: "Animal",
        }

        # Colors (BGR)
        self.colors = {
            "Human":  (0, 165, 255),   # Amber/Orange
            "Vehicle": (0, 0, 255),    # Red
            "Drone":   (255, 0, 255),  # Magenta
            "Animal":  (255, 180, 0),  # Cyan
        }

        self.total_detections = 0
        self.frame_count = 0
        self.start_time = time.time()

    def detect(self, frame, confidence_threshold=0.45):
        """
        Run ultra-fast inference with optimal imgsz.
        """
        self.frame_count += 1
        
        # imgsz=384 provides an ideal speed/accuracy sweet spot on CPU (~3x-4x faster than 640)
        with torch.inference_mode():
            results = self.model(frame, imgsz=384, conf=confidence_threshold, verbose=False)[0]

        detections = []
        for box in results.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if class_id in self.target_classes and confidence >= confidence_threshold:
                object_type = self.target_classes[class_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                detections.append({
                    "class": object_type,
                    "confidence": confidence,
                    "bbox": (x1, y1, x2, y2),
                })

        self.total_detections += len(detections)
        return detections

    def draw_boxes(self, frame, detections):
        """Draw crisp tactical bounding boxes."""
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            label = f"{det['class']} ({det['confidence']:.0%})"
            color = self.colors.get(det['class'], (0, 229, 255))

            # Box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Label badge
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(frame, (x1, y1 - text_h - 6), (x1 + text_w + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

            # Tactical corner markers
            c_len = 10
            cv2.line(frame, (x1, y1), (x1 + c_len, y1), (255, 255, 255), 2)
            cv2.line(frame, (x1, y1), (x1, y1 + c_len), (255, 255, 255), 2)
            cv2.line(frame, (x2, y1), (x2 - c_len, y1), (255, 255, 255), 2)
            cv2.line(frame, (x2, y1), (x2, y1 + c_len), (255, 255, 255), 2)
            cv2.line(frame, (x1, y2), (x1 + c_len, y2), (255, 255, 255), 2)
            cv2.line(frame, (x1, y2), (x1, y2 - c_len), (255, 255, 255), 2)
            cv2.line(frame, (x2, y2), (x2 - c_len, y2), (255, 255, 255), 2)
            cv2.line(frame, (x2, y2), (x2, y2 - c_len), (255, 255, 255), 2)

        return frame
