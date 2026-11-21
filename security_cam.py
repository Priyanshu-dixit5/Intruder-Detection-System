import cv2
import time
import os
import sqlite3
from datetime import datetime

# --- CONFIGURATION ---
SAVE_DIR = "static/captures"
DB_NAME = "intruder_logs.db"
MIN_AREA = 5000  # Sensitivity: Lower number = more sensitive
COOLDOWN = 3     # Seconds to wait between photos

# Ensure directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            image_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- MAIN CAMERA LOOP ---
def start_surveillance():
    cap = cv2.VideoCapture(0) # 0 is usually the default webcam
    
    # Read the first frame for baseline
    _, first_frame = cap.read()
    if first_frame is None:
        print("Error: Could not open camera.")
        return

    first_frame = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    first_frame = cv2.GaussianBlur(first_frame, (21, 21), 0)

    last_capture_time = 0

    print("--- Security System Active ---")
    print("Press 'q' to quit.")

    while True:
        check, frame = cap.read()
        if not check: break

        # Image Processing for Motion Detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # Calculate difference between baseline and current frame
        delta_frame = cv2.absdiff(first_frame, gray)
        thresh_frame = cv2.threshold(delta_frame, 30, 255, cv2.THRESH_BINARY)[1]
        thresh_frame = cv2.dilate(thresh_frame, None, iterations=2)

        # Find Contours
        contours, _ = cv2.findContours(thresh_frame.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_detected = False
        for contour in contours:
            if cv2.contourArea(contour) < MIN_AREA:
                continue
            motion_detected = True
            # Draw rectangle around intruder (Optional visual)
            (x, y, w, h) = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)

        # --- TRIGGER ACTION ---
        current_time = time.time()
        if motion_detected and (current_time - last_capture_time > COOLDOWN):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            print_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 1. Generate Filename
            filename = f"intruder_{timestamp}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            
            # 2. Save Image
            cv2.imwrite(filepath, frame)
            
            # 3. Log to Database
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO logs (timestamp, event_type, image_path) VALUES (?, ?, ?)",
                           (print_time, "Intruder Detected", filename))
            conn.commit()
            conn.close()
            
            print(f"[{print_time}] Motion Detected! Photo saved: {filename}")
            last_capture_time = current_time

        # Show the feed
        cv2.imshow("Security Feed", frame)

        # Update baseline frame occasionally (optional, helps with lighting changes)
        # first_frame = gray 

        key = cv2.waitKey(1)
        if key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    init_db()
    start_surveillance()