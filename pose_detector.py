import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np

# 33 Full-body landmarks
POSE_LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # Arms & Shoulders
    (11, 23), (12, 24), (23, 24),                      # Torso
    (23, 25), (25, 27), (27, 29), (27, 31),            # Left Leg
    (24, 26), (26, 28), (28, 30), (28, 32),            # Right Leg
    (0, 1), (1, 2), (2, 3), (3, 7),                    # Face Left
    (0, 4), (4, 5), (5, 6), (6, 8)                     # Face Right
]

# 21 Hand & finger landmarks per hand
HAND_LANDMARK_NAMES = [
    "wrist",
    "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_finger_mcp", "index_finger_pip", "index_finger_dip", "index_finger_tip",
    "middle_finger_mcp", "middle_finger_pip", "middle_finger_dip", "middle_finger_tip",
    "ring_finger_mcp", "ring_finger_pip", "ring_finger_dip", "ring_finger_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip"
]

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (0, 9), (9, 10), (10, 11), (11, 12),      # Middle
    (0, 13), (13, 14), (14, 15), (15, 16),    # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17)                 # Palm knuckles
]


class PoseDetector:
    def __init__(
        self,
        pose_model_path: str = "models/pose_landmarker_full.task",
        hand_model_path: str = "models/hand_landmarker.task",
        min_confidence: float = 0.5,
    ):
        # 1. Body Pose Landmarker
        pose_options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=pose_model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_confidence,
            min_pose_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self.pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)

        # 2. Hand & Finger Landmarker (tracks both Left and Right hands)
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=hand_model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self.hand_landmarker = vision.HandLandmarker.create_from_options(hand_options)

    def process_frame(self, frame_bgr: np.ndarray, timestamp_ms: int) -> dict:
        """
        Runs both body pose and hand/finger detection on a BGR frame.
        Returns:
          {
            "pose": {joint_name: {...}} or None,
            "hands": {"Left": {finger_joint: {...}}, "Right": {finger_joint: {...}}}
          }
        """
        height, width, _ = frame_bgr.shape
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        # --- Detect Body Pose ---
        pose_result = self.pose_landmarker.detect_for_video(mp_image, timestamp_ms)
        pose_data = None

        if pose_result.pose_landmarks:
            pose_data = {}
            for idx, lm in enumerate(pose_result.pose_landmarks[0]):
                name = POSE_LANDMARK_NAMES[idx]
                pose_data[name] = {
                    "id": idx,
                    "x_norm": lm.x,
                    "y_norm": lm.y,
                    "z_norm": lm.z,
                    "x_px": int(lm.x * width),
                    "y_px": int(lm.y * height),
                    "visibility": float(lm.visibility),
                }

        # --- Detect Hands & Fingers ---
        hand_result = self.hand_landmarker.detect_for_video(mp_image, timestamp_ms)
        hands_data = {}

        if hand_result.hand_landmarks and hand_result.handedness:
            for hand_lms, handedness_list in zip(hand_result.hand_landmarks, hand_result.handedness):
                hand_label = handedness_list[0].category_name  # "Left" or "Right"
                hand_conf = float(handedness_list[0].score)
                joints = {}

                for idx, lm in enumerate(hand_lms):
                    name = HAND_LANDMARK_NAMES[idx]
                    joints[name] = {
                        "id": idx,
                        "x_norm": lm.x,
                        "y_norm": lm.y,
                        "z_norm": lm.z,
                        "x_px": int(lm.x * width),
                        "y_px": int(lm.y * height),
                        "visibility": hand_conf,
                    }
                hands_data[hand_label] = joints

        return {"pose": pose_data, "hands": hands_data}

    def draw_skeleton(self, frame_bgr: np.ndarray, tracking_data: dict, vis_threshold: float = 0.5,
                      show_hand_labels: bool = True) -> np.ndarray:
        """
        Draws both the body skeleton and detailed finger skeletons on the frame.
        show_hand_labels: print MediaPipe's raw "Left/Right Hand" guess next to each wrist.
        The raw guess can be wrong (back of the hand, mirrored video), so the web app
        turns it off and shows the side the analyzer resolved instead.
        """
        annotated = frame_bgr.copy()
        pose_data = tracking_data.get("pose")
        hands_data = tracking_data.get("hands", {})

        # 1. Draw Body Skeleton
        if pose_data:
            by_id = {data["id"]: data for data in pose_data.values()}
            for start_idx, end_idx in POSE_CONNECTIONS:
                p1, p2 = by_id.get(start_idx), by_id.get(end_idx)
                if p1 and p2 and p1["visibility"] >= vis_threshold and p2["visibility"] >= vis_threshold:
                    cv2.line(annotated, (p1["x_px"], p1["y_px"]), (p2["x_px"], p2["y_px"]), (255, 255, 255), 2)

            for data in pose_data.values():
                color = (0, 255, 0) if data["visibility"] >= vis_threshold else (0, 0, 255)
                cv2.circle(annotated, (data["x_px"], data["y_px"]), 5, color, -1)

        # 2. Draw Hand & Finger Skeletons
        for hand_label, joints in hands_data.items():
            by_id = {data["id"]: data for data in joints.values()}

            # Finger bones (cyan lines)
            for start_idx, end_idx in HAND_CONNECTIONS:
                p1, p2 = by_id.get(start_idx), by_id.get(end_idx)
                if p1 and p2:
                    cv2.line(annotated, (p1["x_px"], p1["y_px"]), (p2["x_px"], p2["y_px"]), (255, 255, 0), 2)

            # Finger joints (yellow dots)
            for data in joints.values():
                cv2.circle(annotated, (data["x_px"], data["y_px"]), 4, (0, 255, 255), -1)

            if not show_hand_labels:
                continue

            # Label the hand near the wrist
            wrist = joints["wrist"]
            cv2.putText(
                annotated,
                f"{hand_label} Hand",
                (wrist["x_px"] - 20, wrist["y_px"] + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )

        return annotated

    def close(self):
        self.pose_landmarker.close()
        self.hand_landmarker.close()