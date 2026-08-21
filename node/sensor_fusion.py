"""
ATIG Sensor Fusion System
Combines AI detection data with simulated PIR and ultrasonic sensor readings
to produce verified, distance-weighted threat assessments.
"""

import random
import time


class SensorFusion:
    """
    Fuses AI visual detections with simulated hardware sensor data.
    In a production system, these would read from real GPIO/I2C sensors.
    """

    def __init__(self):
        self.pir_history = []
        self.distance_history = []
        self.last_reading_time = 0

    def read_pir_sensor(self):
        """
        Simulate a PIR Motion Sensor.
        In production: GPIO read from ESP32/Raspberry Pi.
        Returns True if motion is detected.
        """
        # Weighted random — motion is detected ~75% of the time when AI sees something
        result = random.random() < 0.75
        self.pir_history.append({
            "value": result,
            "timestamp": time.time()
        })
        # Keep only last 20 readings
        self.pir_history = self.pir_history[-20:]
        return result

    def read_ultrasonic_sensor(self):
        """
        Simulate an Ultrasonic Sensor distance reading in meters.
        In production: HC-SR04 via ESP32 GPIO.
        Returns distance in meters (1.0 to 20.0).
        """
        distance = round(random.uniform(1.0, 20.0), 2)
        self.distance_history.append({
            "value": distance,
            "timestamp": time.time()
        })
        # Keep only last 20 readings
        self.distance_history = self.distance_history[-20:]
        return distance

    def _calculate_threat_level(self, obj_class, distance, confidence):
        """
        Determine threat level based on object type, distance, and AI confidence.
        Closer objects and higher confidence = higher threat.
        """
        # Base threat by object type
        base_threats = {
            "Drone": 3,     # Airborne threat
            "Vehicle": 3,   # Highest base threat
            "Human": 2,     # Medium base threat
            "Animal": 1,    # Lowest base threat
        }
        base = base_threats.get(obj_class, 1)

        # Distance modifier: closer = more dangerous
        if distance < 5.0:
            distance_modifier = 2    # Very close — critical
        elif distance < 10.0:
            distance_modifier = 1    # Moderate range
        else:
            distance_modifier = 0    # Far away

        # Confidence modifier
        confidence_modifier = 1 if confidence > 0.7 else 0

        # Combined score
        score = base + distance_modifier + confidence_modifier

        if score >= 5:
            return "High"
        elif score >= 3:
            return "Medium"
        else:
            return "Low"

    def evaluate_threat(self, ai_detections):
        """
        Combine AI detections with simulated sensor data
        to produce verified threat assessments.

        Returns a list of verified threats with threat levels.
        """
        motion_detected = self.read_pir_sensor()
        distance = self.read_ultrasonic_sensor()
        self.last_reading_time = time.time()

        verified_threats = []

        for det in ai_detections:
            obj_class = det['class']
            confidence = det['confidence']

            # Sensor fusion logic:
            # If AI detects AND motion is confirmed AND object is within range
            if motion_detected and distance < 18.0:
                threat_level = self._calculate_threat_level(
                    obj_class, distance, confidence
                )

                verified_threats.append({
                    "object": obj_class,
                    "threat_level": threat_level,
                    "confidence": round(confidence, 3),
                    "distance": round(distance, 2),
                    "pir_motion": motion_detected,
                })

        return verified_threats

    def get_sensor_status(self):
        """Return current sensor reading summary for the dashboard."""
        return {
            "pir_readings": len(self.pir_history),
            "distance_readings": len(self.distance_history),
            "last_pir": self.pir_history[-1] if self.pir_history else None,
            "last_distance": self.distance_history[-1] if self.distance_history else None,
            "last_reading_time": self.last_reading_time,
        }
