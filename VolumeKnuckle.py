import cv2
import math
import platform
import re
import subprocess
import sys
from dataclasses import dataclass

import mediapipe as mp


def clamp(value, low, high):
    return max(low, min(high, value))


class VolumeController:
    def __init__(self):
        self.os_name = platform.system().lower()
        self._win_volume = None

        if "windows" in self.os_name:
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )

                self._win_volume = cast(interface, POINTER(IAudioEndpointVolume))

            except Exception as e:
                print("Detailed error:", e)
                raise RuntimeError(
                    "Windows volume control setup failed. Try reinstalling pycaw."
                )

    def get_volume(self):
        if "windows" in self.os_name:
            return int(self._win_volume.GetMasterVolumeLevelScalar() * 100)

        if "darwin" in self.os_name:
            out = subprocess.check_output(
                ["osascript", "-e", "output volume of (get volume settings)"],
                text=True
            ).strip()
            return int(out)

        # Linux / pactl
        try:
            out = subprocess.check_output(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                text=True
            )
            match = re.search(r"(\d+)%", out)
            if match:
                return int(match.group(1))
        except Exception:
            pass

        return 50

    def set_volume(self, value):
        value = int(clamp(value, 0, 100))

        if "windows" in self.os_name:
            self._win_volume.SetMasterVolumeLevelScalar(value / 100.0, None)
            return

        if "darwin" in self.os_name:
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {value}"],
                check=False
            )
            return

        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
            check=False
        )


def is_fist(hand_landmarks):
    lm = hand_landmarks.landmark

    # Four fingers curled: tip below pip in image coordinates
    fingers_curled = 0
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        if lm[tip].y > lm[pip].y:
            fingers_curled += 1

    # Thumb is trickier, so we use a simple "close to palm" heuristic
    thumb_tip = lm[4]
    thumb_ip = lm[3]
    thumb_close = math.dist((thumb_tip.x, thumb_tip.y), (thumb_ip.x, thumb_ip.y)) < 0.08

    return fingers_curled >= 4 and thumb_close


def fist_center_y(hand_landmarks):
    lm = hand_landmarks.landmark
    points = [0, 5, 9, 13, 17]  # wrist + knuckles
    return sum(lm[i].y for i in points) / len(points)


def draw_volume_bar(frame, volume):
    h, w = frame.shape[:2]
    x1, y1 = 20, 120
    x2, y2 = 90, h - 80

    # Outline
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)

    # Fill
    fill_h = int((y2 - y1) * (volume / 100.0))
    cv2.rectangle(frame, (x1 + 5, y2 - fill_h), (x2 - 0, y2 - 0), (255, 0, 0), -1)

    cv2.putText(
        frame,
        f"{volume}%",
        (x1 - 5, y1 - 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils

    hands = mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )

    volume = VolumeController()
    current_volume = volume.get_volume()

    prev_fist_y = None
    sensitivity = 260  # higher = faster volume changes
    deadzone = 0.004   # ignore tiny hand jitter

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        status = "Show a closed fist"
        gesture = "NO HAND"

        if result.multi_hand_landmarks:
            hand_landmarks = result.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            if is_fist(hand_landmarks):
                gesture = "FIST"
                status = "Closed fist detected"

                y = fist_center_y(hand_landmarks)

                if prev_fist_y is not None:
                    # Smaller y means hand moved up on screen
                    dy = prev_fist_y - y

                    if abs(dy) > deadzone:
                        delta = int(dy * sensitivity)

                        if delta != 0:
                            current_volume = clamp(current_volume + delta, 0, 100)
                            volume.set_volume(current_volume)

                            if delta > 0:
                                status = f"Moving up -> volume up ({current_volume}%)"
                            else:
                                status = f"Moving down -> volume down ({current_volume}%)"

                prev_fist_y = y
            else:
                gesture = "OPEN HAND"
                status = "Make a closed fist"
                prev_fist_y = None
        else:
            prev_fist_y = None

        # UI
        cv2.rectangle(frame, (20, 20), (500, 70), (0, 0, 0), -1)
        cv2.putText(
            frame,
            f"{gesture} | {status}",
            (30, 52),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        draw_volume_bar(frame, current_volume)

        cv2.putText(
            frame,
            "Press Q to quit",
            (20, frame.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        frame_small = cv2.resize(frame, (960, 540))  # change size
        cv2.imshow("VolumeKnuckle", frame_small)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()