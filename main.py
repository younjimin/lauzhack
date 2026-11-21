import time
import cv2
from pose_detector import PoseDetector


def next_step_placeholder(tracking_data: dict, frame_idx: int):
    """
    Placeholder for Step 2 (Joint & Finger Angle Analysis).
    Receives both 'pose' (33 body joints) and 'hands' (21 joints per hand).
    """
    pose_data = tracking_data.get("pose")
    hands_data = tracking_data.get("hands", {})

    if frame_idx % 30 == 0:
        if pose_data:
            elbow = pose_data["left_elbow"]
            print(f"[Frame {frame_idx}] Left Elbow px: ({elbow['x_px']}, {elbow['y_px']}) | conf: {elbow['visibility']:.2f}")

        for hand_label, joints in hands_data.items():
            index_tip = joints["index_finger_tip"]
            print(f"[Frame {frame_idx}] {hand_label} Index Tip px: ({index_tip['x_px']}, {index_tip['y_px']}) | conf: {index_tip['visibility']:.2f}")


def run_webcam_pose(camera_index: int = 0):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam at index {camera_index}.")

    detector = PoseDetector(
        pose_model_path="models/pose_landmarker_full.task",
        hand_model_path="models/hand_landmarker.task",
        min_confidence=0.5,
    )
    start_time_ms = int(time.time() * 1000)
    frame_idx = 0

    print("Webcam active (Body + Fingers). Press 'q' in the video window to quit.")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame from webcam.")
                break

            # Mirror webcam feed
            frame = cv2.flip(frame, 1)
            timestamp_ms = int(time.time() * 1000) - start_time_ms

            # 1. Detect body pose + hand/finger landmarks
            tracking_data = detector.process_frame(frame, timestamp_ms)

            # 2. Draw body and finger skeletons
            debug_frame = detector.draw_skeleton(frame, tracking_data, vis_threshold=0.5)

            # Status overlay
            pose_ok = tracking_data["pose"] is not None
            num_hands = len(tracking_data["hands"])
            status = f"Body: {'Detected' if pose_ok else 'None'} | Hands: {num_hands}"
            cv2.putText(debug_frame, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # 3. Show on screen
            cv2.imshow("Rehab Assistant - Body & Finger Tracking", debug_frame)

            # 4. Pass data to Step 2
            next_step_placeholder(tracking_data, frame_idx)

            frame_idx += 1

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run_webcam_pose(camera_index=0)