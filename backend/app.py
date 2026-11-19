from flask import (
    Flask, 
    request,
    jsonify,
    send_from_directory)

from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import os
import uuid
import requests
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai

from database import init_db, get_db_connection

load_dotenv(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".env"
    )
)
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")

if not PLANTNET_API_KEY:
    raise ValueError("PlantNet API key is missing!")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Gemini API key is missing!")

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)

app = Flask(__name__)

def analyze_plant_health(symptoms):
    symptoms = [
        symptom.lower().strip()
        for symptom in symptoms
    ]

    if any(word in symptoms for word in [
        "yellow leaves",
        "wilting",
        "brown spots",
        "black spots",
        "white powder",
        "holes in leaves"
    ]):
        return {
            "health_status": "Needs Attention",
            "disease": "Possible plant stress or disease",
            "treatment": (
                "Inspect the leaves carefully, remove "
                "severely affected leaves, avoid overwatering "
                "and check for pests."
            ),
            "watering_advice": (
                "Check soil moisture before watering."
            )
        }

    return {
        "health_status": "Healthy",
        "disease": "No symptoms reported",
        "treatment": "Continue regular plant care.",
        "watering_advice": (
            "Water according to the plant's soil moisture needs."
        )
    }

CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://127.0.0.1:5500",
            "http://localhost:5500"
        ]
        }
})

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(error):
    return jsonify({
        "error": "Image size must be less than 5 MB"
    }), 413

#IMAGE VALIDATION
def allowed_file(filename):
    return (
        "." in filename and filename.rsplit(".", 1)
        [1].lower() in ALLOWED_EXTENSIONS
    )

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "uploads"
)

app.config["UPLOAD_FOLDER"]=UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def identify_plant(image_path):

    url = "https://my-api.plantnet.org/v2/identify/all"

    params = {
        "api-key": PLANTNET_API_KEY
    }

    try:
        with open(image_path, "rb") as image_file:

            files = {
                "images": image_file
            }

            response = requests.post(
                url,
                params=params,
                files=files,
                timeout=60
            )

        if response.status_code != 200:
            return {
                "error": "PlantNet identification failed",
                "details": response.text
            }

        return response.json()

    except requests.RequestException as error:
        return {
            "error": "Unable to connect to PlantNet",
            "details": str(error)
        }

    except OSError as error:
        return {
            "error": "Unable to read uploaded image",
            "details": str(error)
        }

@app.route("/")
def home():
    return "Welcome to PlantPulse Backend!"

@app.route("/api/test")
def test():
    return jsonify({
        "message": "PlantPulse API is working!",
        "status": "success"
    })


@app.route("/api/plant-care", methods=["POST"])
def plant_care():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Please enter a plant name"
        }), 400

    plant_name = data.get("plant_name", "").strip()

    if not plant_name:
        return jsonify({
            "error": "Plant name is required"
        }), 400

    if len(plant_name) > 100:
        return jsonify({
            "error": "Plant name is too long"
        }), 400

    prompt = f"""
    You are PlantPulse AI Plant Doctor.

    Generate a practical care guide for this plant:
    {plant_name}

    Include:
    1. Plant identification and scientific name if known.
    2. Watering requirements.
    3. Sunlight requirements.
    4. Soil type.
    5. Fertilizer recommendations.
    6. Pruning and maintenance.
    7. Common problems and prevention.
    8. Extra care tips.

    Use simple language.
    Do not invent facts.
    If the plant cannot be identified confidently,
    say so and ask for clarification.
    """

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        return jsonify({
            "status": "success",
            "plant_name": plant_name,
            "care_guide": response.text,
            "generated_by": "Gemini AI"
        })

    except Exception as error:
        print("Gemini API Error:", error)

        return jsonify({
            "error": "Unable to generate plant care tips right now."
        }), 502


@app.route("/api/doctor", methods=["POST"])
def ai_plant_doctor():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Please provide plant details"
        }), 400

    plant_name = data.get("plant_name", "").strip()
    problem = data.get("problem", "").strip()
    symptoms = data.get("symptoms", "").strip()

    if not plant_name:
        return jsonify({
            "error": "Plant name is required"
        }), 400

    if not problem:
        return jsonify({
            "error": "Please select a plant problem"
        }), 400

    if len(plant_name) > 100 or len(problem) > 100:
        return jsonify({
            "error": "Plant details are too long"
        }), 400

    if len(symptoms) > 2000:
        return jsonify({
            "error": "Symptom description is too long"
        }), 400

    prompt = f"""
    You are PlantPulse AI Plant Doctor.

    Help the user understand the possible health problems
    of their plant.

    Plant name: {plant_name}
    Observed problem: {problem}
    Additional symptoms: {symptoms or "Not provided"}

    Generate a detailed but easy-to-understand health report.

    Include:
    1. Possible causes of the problem.
    2. Explanation of the symptoms.
    3. Recommended treatment and steps to follow.
    4. Watering recommendations.
    5. Sunlight and soil recommendations.
    6. Prevention tips.
    7. When to consult a plant expert.

    Important:
    - Use simple language.
    - Do not claim a disease is confirmed from symptoms alone.
    - Mention uncertainty where appropriate.
    - Do not invent facts.
    - Give practical and safe advice.
    """

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        return jsonify({
            "status": "success",
            "plant_name": plant_name,
            "problem": problem,
            "health_report": response.text,
            "generated_by": "Gemini AI"
        })

    except Exception as error:
        print("Gemini AI Doctor Error:", error)

        return jsonify({
            "error": "Unable to generate the plant health report right now."
        }), 502


@app.route("/api/scan", methods=["POST"])
def scan_plant():

    if "image" not in request.files:
        return jsonify({
            "error":"No image uploaded"
        }), 400

    image = request.files["image"]

    if image.filename == "":
        return jsonify({
            "error": "No file selected"
        }), 400

    original_filename = secure_filename(image.filename)

    if not allowed_file(original_filename):
        return jsonify ({
            "error": "Only JPG, JPEG and PNG images are allowed"
        }), 400

    if not original_filename:
        return jsonify({
            "error": "Invalid filename"
        }), 400

    extension = original_filename.rsplit(".", 1)[1].lower()
    
    filename = f"{uuid.uuid4().hex}.{extension}"

    image_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    image.save(image_path)

    # Identify plant using PlantNet
    ai_result = identify_plant(image_path)

    print("PLANTNET RESPONSE:", ai_result)

    # Check whether PlantNet returned an error
    if "error" in ai_result:
        return jsonify({
        "status": "error",
        "error": ai_result.get("error"),
        "message": "Plant identification failed",
        "details": ai_result.get("details")
    }), 502

    plant_name = "Unknown plant"
    scientific_name = "Not identified"
    confidence = None

    results = ai_result.get("results", [])

    if results:
        results.sort(
            key=lambda item:
            item.get("score", 0),
            reverse=True
        )
        best_match = results[0]
        species = best_match.get("species", {})

        scientific_name = species.get(
            "scientificNameWithoutAuthor",
            "Unknown species"
        )

        common_names = species.get("commonNames", [])

        plant_name = (
            common_names[0]
            if common_names
            else scientific_name
        )

        confidence = round(
            best_match.get("score", 0) * 100, 2
        )

    # Save scan information in database
    conn = get_db_connection()

    conn.execute(
        """
        INSERT INTO plants (plant_name, image_filename)
        VALUES (?, ?)
        """,
        (plant_name, filename)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "message": "Plant scan completed!",
        "filename": filename,
        "plant_name": plant_name,
        "scientific_name": scientific_name,
        "confidence": confidence,
        "identification_status": (
            "identified" if results else "not identified"
        ),
        "ai_error": ai_result.get("error")
    })

@app.route("/api/health-analysis", methods=["POST"])
def health_analysis():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Please provide plant symptoms"
        }), 400

    plant_id = data.get("plant_id")
    symptoms = data.get("symptoms", [])

    if not plant_id:
        return jsonify({
            "error": "Plant ID is required"
        }), 400

    if not isinstance(symptoms, list):
        return jsonify({
            "error": "Symptoms must be a list"
        }), 400

    if not all(isinstance(item, str) for item in symptoms):
        return jsonify({
            "error": "Each symptom must be text"
        }), 400

    if len(symptoms) > 20:
        return jsonify({
            "error": "Maximum 20 symptoms allowed"
        }), 400

    result = analyze_plant_health(symptoms)

    conn = get_db_connection()

    plant = conn.execute(
        "SELECT id FROM plants WHERE id = ?",
        (plant_id,)
    ).fetchone()

    if plant is None:
        conn.close()
        return jsonify({
            "error": "Plant scan not found"
        }), 404

    conn.execute(
        """
        UPDATE plants
        SET health_status = ?,
            disease = ?,
            symptoms = ?,
            treatment = ?,
            watering_advice = ?
        WHERE id = ?
        """,
        (
            result["health_status"],
            result["disease"],
            ", ".join(symptoms),
            result["treatment"],
            result["watering_advice"],
            plant_id
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "plant_id": plant_id,
        "health_status": result["health_status"],
        "disease": result["disease"],
        "symptoms": symptoms,
        "treatment": result["treatment"],
        "watering_advice": result["watering_advice"],
        "assessment_type": "symptom_based"
    })

@app.route("/api/history", methods=["GET"])
def get_scan_history():
    conn = get_db_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM plants
        ORDER BY scan_date DESC
        """
    ).fetchall()

    conn.close()

    history = [dict(row) for row in rows]

    return jsonify({
        "status": "success",
        "total_scans": len(history),
        "history": history
    })

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"], filename
    )

init_db()

if __name__ == "__main__":
    app.run(
        debug=True, 
        port=5001,
        use_reloader=False
    )