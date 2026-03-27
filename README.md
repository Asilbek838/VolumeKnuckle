# VolumeKnuckle

Control system volume with a closed fist and webcam tracking.

## What it does
- Runs webcam feed
- Detects a closed fist using MediaPipe Hands
- Moving the fist up increases volume
- Moving the fist down decreases volume
- Shows current volume on screen
- Works with:
  - Windows: `pycaw`
  - macOS: `osascript`
  - Linux: `pactl`

## Tech Stack
- Python
- OpenCV
- MediaPipe Hands
- pycaw (Windows)
- osascript (macOS)
- pactl (Linux)

## Hardware Concept
This project is inspired by analog-to-digital conversion:

- A potentiometer changes physical position into voltage.
- Your fist height changes physical position into a digital value.
- The program maps that motion to system volume changes.

## Setup

### Install dependencies
```bash
pip install mediapipe opencv-python numpy