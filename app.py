import sqlite3
import csv
import io
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from ultralytics import YOLO
import torch
from torchvision.models.detection import fasterrcnn_resnet50_fpn, FasterRCNN_ResNet50_FPN_Weights

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
            created_at TEXT NOT NULL,
            model_name TEXT DEFAULT 'YOLOv8'
        )
    """)

    # Ensure model_name column exists for backwards compatibility
    try:
        conn.execute("ALTER TABLE detections ADD COLUMN model_name TEXT DEFAULT 'YOLOv8'")
    except sqlite3.OperationalError:
        pass

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

# Object Detection Model - YOLOv8
detection_model = YOLO("yolov8n.pt")


# Image Classification Model
classification_model = YOLO("yolov8n-cls.pt")


# Faster R-CNN (ResNet-50 FPN) Model
faster_rcnn_weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT
faster_rcnn_classes = faster_rcnn_weights.meta["categories"]
faster_rcnn_model = None


def get_faster_rcnn_model():
    """Lazily load Faster R-CNN model on first use."""
    global faster_rcnn_model
    if faster_rcnn_model is None:
        faster_rcnn_model = fasterrcnn_resnet50_fpn(weights=faster_rcnn_weights)
        faster_rcnn_model.eval()
    return faster_rcnn_model


def run_faster_rcnn(image, conf_threshold=0.5):
    """
    Runs Faster R-CNN ResNet-50 FPN detection on an OpenCV BGR image.
    Draws bounding boxes and labels on the image in-place.
    Returns: list of detected objects with bounding boxes and confidences.
    """
    model = get_faster_rcnn_model()

    # Convert OpenCV BGR to RGB tensor normalized to [0, 1]
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb_image).permute(2, 0, 1).float() / 255.0

    with torch.no_grad():
        predictions = model([tensor])[0]

    boxes = predictions["boxes"].cpu().numpy()
    labels = predictions["labels"].cpu().numpy()
    scores = predictions["scores"].cpu().numpy()

    detections = []

    for box, label_idx, score in zip(boxes, labels, scores):
        if score < conf_threshold:
            continue

        confidence = float(score)
        class_idx = int(label_idx)
        class_name = (
            faster_rcnn_classes[class_idx]
            if class_idx < len(faster_rcnn_classes)
            else f"object_{class_idx}"
        )

        x1, y1, x2, y2 = map(int, box)

        detections.append({
            "class": class_name,
            "confidence": round(confidence * 100, 2),
            "box": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            }
        })

        # Draw bounding box (Amber / Coral: BGR 0, 140, 255)
        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 140, 255),
            2
        )

        # Draw label
        label = f"{class_name} {confidence * 100:.1f}%"
        cv2.putText(
            image,
            label,
            (x1, max(y1 - 10, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 140, 255),
            2
        )

    return detections


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

    # Total objects
    total_objects = conn.execute("""
        SELECT COUNT(*)
        FROM detections
    """).fetchone()[0]

    # Average confidence
    avg_confidence = conn.execute("""
        SELECT AVG(confidence)
        FROM detections
    """).fetchone()[0]

    # Unique images analyzed
    unique_images = conn.execute("""
        SELECT COUNT(DISTINCT image_name)
        FROM detections
    """).fetchone()[0]

    # Model usage distribution
    model_data = conn.execute("""
        SELECT COALESCE(model_name, 'YOLOv8') AS model, COUNT(*) AS count
        FROM detections
        GROUP BY model
        ORDER BY count DESC
    """).fetchall()

    # Confidence distribution brackets
    conf_ranges = [
        {"label": "90% - 100%", "count": conn.execute("SELECT COUNT(*) FROM detections WHERE confidence >= 90").fetchone()[0]},
        {"label": "75% - 89%", "count": conn.execute("SELECT COUNT(*) FROM detections WHERE confidence >= 75 AND confidence < 90").fetchone()[0]},
        {"label": "50% - 74%", "count": conn.execute("SELECT COUNT(*) FROM detections WHERE confidence >= 50 AND confidence < 75").fetchone()[0]},
        {"label": "< 50%", "count": conn.execute("SELECT COUNT(*) FROM detections WHERE confidence < 50").fetchone()[0]},
    ]

    conn.close()

    # Prepare chart arrays
    top_objects = object_data[:8]
    object_labels = [row["object_name"] for row in top_objects]
    object_counts = [row["count"] for row in top_objects]

    model_labels = [row["model"] for row in model_data]
    model_counts = [row["count"] for row in model_data]

    conf_labels = [r["label"] for r in conf_ranges]
    conf_counts = [r["count"] for r in conf_ranges]

    top_object_name = object_data[0]["object_name"] if object_data else "N/A"

    return render_template(
        "analytics.html",
        object_data=object_data,
        avg_confidence=round(avg_confidence or 0, 2),
        total_objects=total_objects,
        unique_images=unique_images,
        top_object_name=top_object_name,
        object_labels=object_labels,
        object_counts=object_counts,
        model_labels=model_labels,
        model_counts=model_counts,
        conf_labels=conf_labels,
        conf_counts=conf_counts
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
# SETTINGS
# =========================================================

@app.route("/settings")
def settings():
    conn = get_db()
    total_detections = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
    conn.close()

    db_size_kb = 0
    if os.path.exists(DATABASE):
        db_size_kb = round(os.path.getsize(DATABASE) / 1024, 2)

    uploads_count = 0
    uploads_size_kb = 0
    if os.path.exists(UPLOAD_FOLDER):
        files = [
            os.path.join(UPLOAD_FOLDER, f)
            for f in os.listdir(UPLOAD_FOLDER)
            if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))
        ]
        uploads_count = len(files)
        uploads_size_kb = round(sum(os.path.getsize(f) for f in files) / 1024, 2)

    return render_template(
        "settings.html",
        total_detections=total_detections,
        db_size_kb=db_size_kb,
        uploads_count=uploads_count,
        uploads_size_kb=uploads_size_kb
    )


# =========================================================
# CLEAR HISTORY API
# =========================================================

@app.route("/api/history/clear", methods=["POST"])
def clear_history():
    data = request.get_json(silent=True) or {}
    delete_files = data.get("delete_files", False)

    conn = get_db()
    conn.execute("DELETE FROM detections")
    conn.commit()
    conn.close()

    removed_files = 0
    if delete_files and os.path.exists(UPLOAD_FOLDER):
        for fname in os.listdir(UPLOAD_FOLDER):
            if fname.startswith("result_") or fname.endswith((".jpg", ".png", ".jpeg")):
                fpath = os.path.join(UPLOAD_FOLDER, fname)
                try:
                    os.remove(fpath)
                    removed_files += 1
                except OSError:
                    pass

    return jsonify({
        "success": True,
        "message": "Detection history cleared successfully.",
        "removed_files": removed_files
    })


# =========================================================
# EXPORT DATA APIS
# =========================================================

@app.route("/api/history/data")
def history_data():
    conn = get_db()
    records = conn.execute("""
        SELECT id, image_name, object_name, confidence, created_at, COALESCE(model_name, 'YOLOv8') as model_name
        FROM detections
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    data = [dict(r) for r in records]
    return jsonify({
        "success": True,
        "records": data,
        "total": len(data)
    })


@app.route("/export/csv")
def export_csv():
    conn = get_db()
    records = conn.execute("""
        SELECT id, image_name, object_name, confidence, created_at, COALESCE(model_name, 'YOLOv8') as model_name
        FROM detections
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Image Name", "Detected Object", "Confidence (%)", "Timestamp", "Model"])

    for r in records:
        writer.writerow([
            r["id"],
            r["image_name"],
            r["object_name"],
            r["confidence"],
            r["created_at"],
            r["model_name"]
        ])

    output.seek(0)
    filename = f"detection_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )


@app.route("/export/json")
def export_json():
    conn = get_db()
    records = conn.execute("""
        SELECT id, image_name, object_name, confidence, created_at, COALESCE(model_name, 'YOLOv8') as model_name
        FROM detections
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    data = [dict(r) for r in records]
    response = jsonify(data)
    filename = f"detection_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    response.headers["Content-Disposition"] = f"attachment;filename={filename}"
    return response


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
    # Selected Model & Confidence Threshold
    # -----------------------------------------------------
    selected_model = request.form.get("model", "yolo").strip().lower()
    is_rcnn = ("rcnn" in selected_model) or ("faster" in selected_model)
    model_display_name = "Faster R-CNN" if is_rcnn else "YOLOv8"

    try:
        conf_param = request.form.get("confidence")
        conf_threshold = float(conf_param) / 100.0 if conf_param else 0.5
        conf_threshold = max(0.1, min(0.95, conf_threshold))
    except (ValueError, TypeError):
        conf_threshold = 0.5

    detections = []

    if is_rcnn:
        # -------------------------------------------------
        # Run Faster R-CNN Object Detection
        # -------------------------------------------------
        detections = run_faster_rcnn(image, conf_threshold=conf_threshold)

    else:
        # -------------------------------------------------
        # Run YOLO Object Detection
        # -------------------------------------------------
        results = detection_model(image, conf=conf_threshold)

        for result in results:
            boxes = result.boxes

            for box in boxes:
                class_id = int(box.cls[0])
                class_name = detection_model.names[class_id]
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                detections.append({
                    "class": class_name,
                    "confidence": round(confidence * 100, 2),
                    "box": {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2
                    }
                })

                # Draw bounding box
                cv2.rectangle(
                    image,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                # Create object label
                label = f"{class_name} {confidence * 100:.1f}%"

                # Draw label
                cv2.putText(
                    image,
                    label,
                    (x1, max(y1 - 10, 15)),
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
                created_at,
                model_name
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            file.filename,
            detection["class"],
            detection["confidence"],
            current_time,
            model_display_name
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
        "model": model_display_name,
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