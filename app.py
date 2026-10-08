import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory
from ultralytics import YOLO

import os
import cv2
import uuid


# =========================================================
# DATABASE
# =========================================================

DATABASE = "detection.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_name TEXT NOT NULL,
            object_name TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# FLASK APPLICATION
# =========================================================

app = Flask(__name__)
init_db()


# =========================================================
# UPLOAD FOLDER
# =========================================================

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =========================================================
# LOAD AI MODELS
# =========================================================

# Object Detection Model
detection_model = YOLO("yolov8n.pt")


# Image Classification Model
classification_model = YOLO("yolov8n-cls.pt")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@app.route("/dashboard")
def dashboard():

    conn = get_db()

    # Total unique analyses
    total_analyses = conn.execute("""
        SELECT COUNT(DISTINCT image_name)
        FROM detections
    """).fetchone()[0]

    # Total detected objects
    total_objects = conn.execute("""
        SELECT COUNT(*)
        FROM detections
    """).fetchone()[0]

    # Average confidence
    avg_confidence = conn.execute("""
        SELECT AVG(confidence)
        FROM detections
    """).fetchone()[0]

    # Most detected object
    most_detected = conn.execute("""
        SELECT object_name, COUNT(*) AS count
        FROM detections
        GROUP BY object_name
        ORDER BY count DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    if most_detected:
        most_detected_name = most_detected["object_name"]
    else:
        most_detected_name = "N/A"

    return render_template(
        "dashboard.html",
        total_analyses=total_analyses,
        total_objects=total_objects,
        avg_confidence=round(avg_confidence or 0, 2),
        most_detected=most_detected_name
    )


# =========================================================
# ANALYTICS
# =========================================================

@app.route("/analytics")
def analytics():

    conn = get_db()

    # Object counts
    object_data = conn.execute("""
        SELECT object_name, COUNT(*) AS count
        FROM detections
        GROUP BY object_name
        ORDER BY count DESC
    """).fetchall()

    # Average confidence
    avg_confidence = conn.execute("""
        SELECT AVG(confidence)
        FROM detections
    """).fetchone()[0]

    # Total objects
    total_objects = conn.execute("""
        SELECT COUNT(*)
        FROM detections
    """).fetchone()[0]

    conn.close()

    return render_template(
        "analytics.html",
        object_data=object_data,
        avg_confidence=round(avg_confidence or 0, 2),
        total_objects=total_objects
    )


# =========================================================
# HISTORY
# =========================================================

@app.route("/history")
def history():

    conn = get_db()

    records = conn.execute("""
        SELECT *
        FROM detections
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "history.html",
        records=records
    )


# =========================================================
# SERVE UPLOADED / RESULT IMAGES
# =========================================================

@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# =========================================================
# OBJECT DETECTION API
# =========================================================

@app.route("/detect", methods=["POST"])
def detect():

    # -----------------------------------------------------
    # Check whether image was uploaded
    # -----------------------------------------------------

    if "image" not in request.files:

        return jsonify({
            "success": False,
            "message": "No image uploaded"
        })


    # -----------------------------------------------------
    # Get uploaded image
    # -----------------------------------------------------

    file = request.files["image"]


    # -----------------------------------------------------
    # Check filename
    # -----------------------------------------------------

    if file.filename == "":

        return jsonify({
            "success": False,
            "message": "No image selected"
        })


    # -----------------------------------------------------
    # Generate unique filename
    # -----------------------------------------------------

    filename = (
        str(uuid.uuid4())
        + "_"
        + file.filename
    )


    # -----------------------------------------------------
    # Complete path
    # -----------------------------------------------------

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )


    # -----------------------------------------------------
    # Save uploaded image
    # -----------------------------------------------------

    file.save(filepath)


    # -----------------------------------------------------
    # Read image using OpenCV
    # -----------------------------------------------------

    image = cv2.imread(filepath)


    if image is None:

        return jsonify({
            "success": False,
            "message": "Unable to read image"
        })


    # -----------------------------------------------------
    # Run YOLO Object Detection
    # -----------------------------------------------------

    results = detection_model(image)


    # -----------------------------------------------------
    # Store detections
    # -----------------------------------------------------

    detections = []


    # -----------------------------------------------------
    # Process YOLO Results
    # -----------------------------------------------------

    for result in results:

        boxes = result.boxes


        for box in boxes:

            # Class ID
            class_id = int(
                box.cls[0]
            )


            # Class name
            class_name = detection_model.names[class_id]


            # Confidence
            confidence = float(
                box.conf[0]
            )


            # -------------------------------------------------
            # Bounding Box Coordinates
            # -------------------------------------------------

            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0]
            )


            # -------------------------------------------------
            # Store detection information
            # -------------------------------------------------

            detections.append({

                "class": class_name,

                "confidence": round(
                    confidence * 100,
                    2
                ),

                "box": {

                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2

                }

            })


            # -------------------------------------------------
            # Draw bounding box
            # -------------------------------------------------

            cv2.rectangle(

                image,

                (x1, y1),

                (x2, y2),

                (0, 255, 0),

                2

            )


            # -------------------------------------------------
            # Create object label
            # -------------------------------------------------

            label = (
                f"{class_name} "
                f"{confidence * 100:.1f}%"
            )


            # -------------------------------------------------
            # Draw label
            # -------------------------------------------------

            cv2.putText(

                image,

                label,

                (x1, y1 - 10),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.6,

                (0, 255, 0),

                2

            )


    # =====================================================
    # SAVE DETECTION DATA TO DATABASE
    # =====================================================

    conn = get_db()

    current_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for detection in detections:

        conn.execute("""
            INSERT INTO detections
            (
                image_name,
                object_name,
                confidence,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (

            file.filename,

            detection["class"],

            detection["confidence"],

            current_time

        ))


    conn.commit()
    conn.close()


    # -----------------------------------------------------
    # Create result filename
    # -----------------------------------------------------

    output_filename = (
        "result_" + filename
    )


    # -----------------------------------------------------
    # Result image path
    # -----------------------------------------------------

    output_path = os.path.join(

        app.config["UPLOAD_FOLDER"],

        output_filename

    )


    # -----------------------------------------------------
    # Save result image
    # -----------------------------------------------------

    cv2.imwrite(

        output_path,

        image

    )


    # -----------------------------------------------------
    # Send response to frontend
    # -----------------------------------------------------

    return jsonify({

        "success": True,

        "image": (
            "/uploads/"
            + output_filename
        ),

        "detections": detections,

        "total_objects": len(
            detections
        )

    })


# =========================================================
# IMAGE CLASSIFICATION API
# =========================================================

@app.route("/classify", methods=["POST"])
def classify():

    # -----------------------------------------------------
    # Check whether image was uploaded
    # -----------------------------------------------------

    if "image" not in request.files:

        return jsonify({

            "success": False,

            "message": "No image uploaded"

        })


    # -----------------------------------------------------
    # Get uploaded image
    # -----------------------------------------------------

    file = request.files["image"]


    # -----------------------------------------------------
    # Check filename
    # -----------------------------------------------------

    if file.filename == "":

        return jsonify({

            "success": False,

            "message": "No image selected"

        })


    # -----------------------------------------------------
    # Generate unique filename
    # -----------------------------------------------------

    filename = (

        str(uuid.uuid4())

        + "_"

        + file.filename

    )


    # -----------------------------------------------------
    # Complete image path
    # -----------------------------------------------------

    filepath = os.path.join(

        app.config["UPLOAD_FOLDER"],

        filename

    )


    # -----------------------------------------------------
    # Save image
    # -----------------------------------------------------

    file.save(filepath)


    # -----------------------------------------------------
    # Run Image Classification
    # -----------------------------------------------------

    results = classification_model(filepath)


    # -----------------------------------------------------
    # Get first result
    # -----------------------------------------------------

    result = results[0]


    # -----------------------------------------------------
    # Get classification probabilities
    # -----------------------------------------------------

    probabilities = result.probs


    # -----------------------------------------------------
    # Get top prediction
    # -----------------------------------------------------

    top_class_id = int(

        probabilities.top1

    )


    # -----------------------------------------------------
    # Get class name
    # -----------------------------------------------------

    top_class_name = (

        classification_model.names[

            top_class_id

        ]

    )


    # -----------------------------------------------------
    # Get confidence
    # -----------------------------------------------------

    top_confidence = float(

        probabilities.top1conf

    )


    # -----------------------------------------------------
    # Get Top 5 Predictions
    # -----------------------------------------------------

    top5_indices = probabilities.top5

    predictions = []


    for class_id in top5_indices:

        class_id = int(class_id)


        confidence = float(

            probabilities.data[class_id]

        )


        predictions.append({

            "class": (

                classification_model.names[

                    class_id

                ]

            ),

            "confidence": round(

                confidence * 100,

                2

            )

        })


    # -----------------------------------------------------
    # Send Classification Result
    # -----------------------------------------------------

    return jsonify({

        "success": True,

        "image": (

            "/uploads/"

            + filename

        ),

        "prediction": top_class_name,

        "confidence": round(

            top_confidence * 100,

            2

        ),

        "predictions": predictions

    })


# =========================================================
# START FLASK SERVER
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )