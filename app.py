import os
import sys
import json
import re
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
# Try to load .env.local first (for local development with SQLite)
# Fall back to .env if .env.local doesn't exist
if os.path.exists(os.path.join(os.path.dirname(__file__), '.env.local')):
    load_dotenv('.env.local')
else:
    load_dotenv()

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config

# ================================
# BASE DIR (IMPORTANT)
# ================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================================
# APP INIT
# ================================
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app)
app.config.from_object(Config)

# ================================
# DATABASE INIT
# ================================
db = SQLAlchemy(app)

# ================================
# MODELS
# ================================
from datetime import datetime as dt

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)

    # relationship
    meals = db.relationship('MealPlan', backref='user', lazy=True)


class MealPlan(db.Model):
    __tablename__ = 'meal_plans'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    meal_name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Float)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fats = db.Column(db.Float)

    date_planned = db.Column(db.DateTime, default=dt.utcnow)

# Create tables
with app.app_context():
    try:
        db.create_all()
        print("✅ Database tables created/verified")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")

# ================================
# GEMINI CONFIG
# ================================
API_KEY = os.getenv("GEMINI_API_KEY")
client = None
gemini_ready = False

if not API_KEY:
    print("⚠️ GEMINI_API_KEY not set - AI features will be limited")
else:
    try:
        from google import genai as genai_new
        client = genai_new.Client(api_key=API_KEY)
        gemini_ready = True
        print("✅ Gemini API Connected")
    except Exception as e:
        print(f"⚠️ Gemini initialization error: {e}")
        client = None
        gemini_ready = False

# ================================
# HEALTH CHECK
# ================================
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for monitoring."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db.engine.url.drivername != "sqlite" else "sqlite (dev)",
        "gemini": "connected" if API_KEY else "not configured"
    }), 200

# ================================
# ROUTES - STATIC FILES
# ================================

@app.route("/")
def home():
    """Serve login page."""
    try:
        return send_from_directory(BASE_DIR, "login.html")
    except Exception as e:
        print(f"Error serving login.html: {e}")
        return jsonify({"error": "Login page not found"}), 404

@app.route("/dashboard")
def dashboard():
    """Serve dashboard page."""
    try:
        return send_from_directory(BASE_DIR, "index.html")
    except Exception as e:
        print(f"Error serving index.html: {e}")
        return jsonify({"error": "Dashboard not found"}), 404

@app.route("/style.css")
def css():
    """Serve CSS stylesheet."""
    try:
        return send_from_directory(BASE_DIR, "style.css")
    except Exception as e:
        print(f"Error serving style.css: {e}")
        return jsonify({"error": "CSS not found"}), 404

@app.route("/script.js")
def js():
    """Serve JavaScript file."""
    try:
        return send_from_directory(BASE_DIR, "script.js")
    except Exception as e:
        print(f"Error serving script.js: {e}")
        return jsonify({"error": "JavaScript not found"}), 404

# ================================
# ERROR HANDLERS
# ================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    print(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# ================================
# AUTH APIS
# ================================

@app.route("/signup", methods=["POST"])
def signup():
    """Create a new user account."""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400

        if len(password) < 4:
            return jsonify({"success": False, "message": "Password must be at least 4 characters"}), 400

        # Check if user exists
        existing = User.query.filter_by(username=username).first()
        if existing:
            return jsonify({"success": False, "message": "Username already exists"}), 409

        # Create new user
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()

        print(f"✅ New user created: {username}")
        return jsonify({"success": True, "message": "User created successfully"}), 201

    except Exception as e:
        db.session.rollback()
        print(f"Signup error: {e}")
        return jsonify({"success": False, "message": "Signup failed"}), 500

@app.route("/login", methods=["POST"])
def login():
    """Authenticate user and return user ID."""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not username or not password:
            return jsonify({"success": False, "message": "Username and password required"}), 400

        # Find user
        user = User.query.filter_by(username=username, password=password).first()

        if user:
            print(f"✅ User logged in: {username}")
            return jsonify({"success": True, "user_id": user.id}), 200
        else:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"success": False, "message": "Login failed"}), 500

# ================================
# MEAL PLAN DATA
# ================================

INITIAL_MEAL_PLANS = [
    {
        "disease": "general",
        "food_preference": "veg",
        "allergy": "none",
        "breakfast": "Oatmeal with fruits and nuts",
        "lunch": "Vegetable curry with brown rice",
        "dinner": "Lentil soup with whole grain bread",
        "snack": "Greek yogurt with berries"
    },
    {
        "disease": "general",
        "food_preference": "non-veg",
        "allergy": "none",
        "breakfast": "Scrambled eggs with whole wheat toast",
        "lunch": "Grilled chicken with steamed vegetables",
        "dinner": "Baked fish with sweet potato",
        "snack": "Almonds and apple"
    },
    {
        "disease": "diabetes",
        "food_preference": "veg",
        "allergy": "none",
        "breakfast": "Vegetable omelet with whole wheat bread",
        "lunch": "Chickpea salad with olive oil dressing",
        "dinner": "Quinoa with roasted vegetables",
        "snack": "Handful of nuts"
    },
    {
        "disease": "diabetes",
        "food_preference": "non-veg",
        "allergy": "none",
        "breakfast": "Grilled chicken breast with vegetables",
        "lunch": "Lean beef with brown rice",
        "dinner": "Baked salmon with steamed broccoli",
        "snack": "Boiled eggs"
    },
    {
        "disease": "hypertension",
        "food_preference": "veg",
        "allergy": "none",
        "breakfast": "Low-sodium oatmeal with banana",
        "lunch": "Vegetable stir-fry with low-sodium soy sauce",
        "dinner": "Baked tofu with herbs",
        "snack": "Fresh fruit"
    },
    {
        "disease": "hypertension",
        "food_preference": "non-veg",
        "allergy": "none",
        "breakfast": "Poached eggs with herbs",
        "lunch": "Grilled chicken with herbs",
        "dinner": "Baked white fish with lemon",
        "snack": "Unsalted almonds"
    }
]

# ================================
# MEAL PLAN API
# ================================

@app.route("/initial-meal-plan", methods=["GET"])
def initial_meal_plan():
    """Get initial meal plans."""
    try:
        return jsonify(INITIAL_MEAL_PLANS), 200
    except Exception as e:
        print(f"Meal plan error: {e}")
        return jsonify({"error": "Failed to fetch meal plans"}), 500

# ================================
# UTILITY FUNCTIONS
# ================================

def safe_text(response):
    """Safely extract text from Gemini response."""
    try:
        return response.text
    except:
        return None

# ================================
# NUTRITION DATABASE
# ================================

# Comprehensive food nutrition database (per 100g or per serving as noted)
FOOD_NUTRITION_DB = {
    # Breakfast items
    "oatmeal": {"calories": 389, "protein": 17, "carbohydrates": 66, "fat": 7, "fiber": 10, "sodium": 1},
    "eggs": {"calories": 155, "protein": 13, "carbohydrates": 1.1, "fat": 11, "fiber": 0, "sodium": 124},
    "scrambled eggs": {"calories": 155, "protein": 13, "carbohydrates": 1.1, "fat": 11, "fiber": 0, "sodium": 124},
    "toast": {"calories": 265, "protein": 9, "carbohydrates": 49, "fat": 3.3, "fiber": 2.7, "sodium": 510},
    "whole wheat bread": {"calories": 247, "protein": 10, "carbohydrates": 41, "fat": 3.2, "fiber": 6.8, "sodium": 486},
    "banana": {"calories": 89, "protein": 1.1, "carbohydrates": 23, "fat": 0.3, "fiber": 2.6, "sodium": 1},
    "apple": {"calories": 52, "protein": 0.3, "carbohydrates": 14, "fat": 0.2, "fiber": 2.4, "sodium": 1},
    "berries": {"calories": 57, "protein": 1.1, "carbohydrates": 14, "fat": 0.3, "fiber": 2.4, "sodium": 6},
    "yogurt": {"calories": 59, "protein": 10, "carbohydrates": 3.6, "fat": 0.4, "fiber": 0, "sodium": 75},
    "greek yogurt": {"calories": 59, "protein": 10, "carbohydrates": 3.6, "fat": 0.4, "fiber": 0, "sodium": 75},
    
    # Lunch items
    "chicken": {"calories": 165, "protein": 31, "carbohydrates": 0, "fat": 3.6, "fiber": 0, "sodium": 74},
    "grilled chicken": {"calories": 165, "protein": 31, "carbohydrates": 0, "fat": 3.6, "fiber": 0, "sodium": 74},
    "fish": {"calories": 100, "protein": 20, "carbohydrates": 0, "fat": 1.3, "fiber": 0, "sodium": 75},
    "salmon": {"calories": 208, "protein": 20, "carbohydrates": 0, "fat": 13, "fiber": 0, "sodium": 59},
    "baked fish": {"calories": 100, "protein": 20, "carbohydrates": 0, "fat": 1.3, "fiber": 0, "sodium": 75},
    "rice": {"calories": 130, "protein": 2.7, "carbohydrates": 28, "fat": 0.3, "fiber": 0.4, "sodium": 1},
    "brown rice": {"calories": 111, "protein": 2.6, "carbohydrates": 23, "fat": 0.9, "fiber": 1.8, "sodium": 7},
    "broccoli": {"calories": 34, "protein": 2.8, "carbohydrates": 7, "fat": 0.4, "fiber": 2.4, "sodium": 64},
    "vegetables": {"calories": 40, "protein": 2, "carbohydrates": 7, "fat": 0.5, "fiber": 1.5, "sodium": 50},
    "curry": {"calories": 120, "protein": 8, "carbohydrates": 12, "fat": 4, "fiber": 1, "sodium": 500},
    "vegetable curry": {"calories": 120, "protein": 8, "carbohydrates": 12, "fat": 4, "fiber": 1, "sodium": 500},
    "lentils": {"calories": 116, "protein": 9, "carbohydrates": 20, "fat": 0.4, "fiber": 3.8, "sodium": 2},
    "chickpeas": {"calories": 164, "protein": 8.9, "carbohydrates": 27, "fat": 2.6, "fiber": 6.5, "sodium": 7},
    "salad": {"calories": 30, "protein": 1.5, "carbohydrates": 5, "fat": 0.5, "fiber": 1, "sodium": 50},
    "soup": {"calories": 50, "protein": 3, "carbohydrates": 8, "fat": 1, "fiber": 1, "sodium": 400},
    "lentil soup": {"calories": 50, "protein": 3, "carbohydrates": 8, "fat": 1, "fiber": 1, "sodium": 400},
    
    # Dinner items
    "beef": {"calories": 250, "protein": 26, "carbohydrates": 0, "fat": 15, "fiber": 0, "sodium": 75},
    "sweet potato": {"calories": 86, "protein": 1.6, "carbohydrates": 20, "fat": 0.1, "fiber": 3, "sodium": 55},
    "tofu": {"calories": 76, "protein": 8.1, "carbohydrates": 1.9, "fat": 4.8, "fiber": 1.2, "sodium": 7},
    "baked tofu": {"calories": 76, "protein": 8.1, "carbohydrates": 1.9, "fat": 4.8, "fiber": 1.2, "sodium": 7},
    "white fish": {"calories": 82, "protein": 18, "carbohydrates": 0, "fat": 0.7, "fiber": 0, "sodium": 74},
    "herbal": {"calories": 0, "protein": 0, "carbohydrates": 0, "fat": 0, "fiber": 0, "sodium": 5},
    "herbs": {"calories": 0, "protein": 0, "carbohydrates": 0, "fat": 0, "fiber": 0, "sodium": 5},
    
    # Snacks
    "almonds": {"calories": 579, "protein": 21, "carbohydrates": 22, "fat": 50, "fiber": 12.5, "sodium": 0},
    "nuts": {"calories": 579, "protein": 21, "carbohydrates": 22, "fat": 50, "fiber": 12.5, "sodium": 0},
    "apple": {"calories": 52, "protein": 0.3, "carbohydrates": 14, "fat": 0.2, "fiber": 2.4, "sodium": 1},
    "fruit": {"calories": 70, "protein": 0.5, "carbohydrates": 18, "fat": 0.3, "fiber": 2, "sodium": 2},
    "popcorn": {"calories": 387, "protein": 12, "carbohydrates": 77, "fat": 4.3, "fiber": 14.5, "sodium": 98},
    
    # Additional items
    "quinoa": {"calories": 120, "protein": 4.4, "carbohydrates": 21, "fat": 1.9, "fiber": 2.8, "sodium": 7},
    "beans": {"calories": 127, "protein": 8.7, "carbohydrates": 23, "fat": 0.5, "fiber": 6.4, "sodium": 2},
    "potato": {"calories": 77, "protein": 2, "carbohydrates": 17, "fat": 0.1, "fiber": 2.1, "sodium": 6},
    "pasta": {"calories": 371, "protein": 13, "carbohydrates": 75, "fat": 1.1, "fiber": 3.5, "sodium": 189},
    "cereal": {"calories": 380, "protein": 9, "carbohydrates": 75, "fat": 2, "fiber": 7, "sodium": 500},
    "milk": {"calories": 42, "protein": 3.4, "carbohydrates": 5, "fat": 1, "fiber": 0, "sodium": 44},
    "cheese": {"calories": 402, "protein": 25, "carbohydrates": 1.3, "fat": 33, "fiber": 0, "sodium": 621},
    "butter": {"calories": 717, "protein": 0.9, "carbohydrates": 0.1, "fat": 81, "fiber": 0, "sodium": 714},
    "oil": {"calories": 884, "protein": 0, "carbohydrates": 0, "fat": 100, "fiber": 0, "sodium": 0},
    "olive oil": {"calories": 884, "protein": 0, "carbohydrates": 0, "fat": 100, "fiber": 0, "sodium": 0},
}

# ================================
# DDS CALCULATION API
# ================================

def estimate_food_nutrition(foods):
    """
    Estimate nutrition values based on food list.
    Tries Gemini API first, falls back to database lookup.
    """
    actual = None
    
    # Try Gemini API first
    if gemini_ready and client:
        try:
            prompt = f"""
            Estimate nutrition for these foods: {foods}

            Return ONLY valid JSON (no markdown, no extra text):
            {{
              "calories": number,
              "protein": number,
              "carbohydrates": number,
              "fat": number,
              "fiber": number,
              "sodium": number
            }}
            """

            response = client.models.generate_content(
               model="gemini-2.0-flash",
               contents=prompt
            )
            text = response.text
            if text:
                actual = json.loads(re.sub(r"^```json|```$", "", text.strip()))
                print(f"✅ Using Gemini API results")
                return actual
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")
            actual = None
    
    # Fallback: Calculate from local database
    print(f"📊 Using local food database for: {foods}")
    total_nutrition = {
        "calories": 0,
        "protein": 0,
        "carbohydrates": 0,
        "fat": 0,
        "fiber": 0,
        "sodium": 0
    }
    
    matched_foods = []
    for food_text in foods:
        food_lower = food_text.lower().strip()
        
        # Try exact match first
        if food_lower in FOOD_NUTRITION_DB:
            nutrition = FOOD_NUTRITION_DB[food_lower]
            matched_foods.append(food_lower)
        else:
            # Try partial match (check if food is mentioned in keys)
            found = False
            for db_food, nutrition in FOOD_NUTRITION_DB.items():
                if db_food in food_lower or food_lower in db_food:
                    matched_foods.append(db_food)
                    found = True
                    break
            
            if not found:
                # Default portion assumption if not found
                print(f"  ⚠️ Food '{food_text}' not in database, using generic estimate")
                nutrition = {"calories": 150, "protein": 5, "carbohydrates": 20, "fat": 5, "fiber": 2, "sodium": 100}
        
        # Add to totals
        for key in total_nutrition:
            total_nutrition[key] += nutrition[key]
    
    print(f"  ✅ Matched foods: {matched_foods}")
    return total_nutrition

@app.route("/calculate-dds", methods=["POST"])
def calculate_dds():
    """Calculate Dietary Deviation Score and provide recommendations."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        foods = data.get("foods", [])
        disease = data.get("disease", "general")

        if not foods:
            return jsonify({"error": "No foods provided"}), 400

        # Get nutrition data from Gemini or database
        actual = estimate_food_nutrition(foods)

        # Recommended daily values
        recommended = {
            "calories": 2000,
            "protein": 75,
            "carbohydrates": 250,
            "fat": 60,
            "fiber": 30,
            "sodium": 2300
        }

        # Calculate NDV (Nutrient Deviation Value)
        ndv = {
            k: round((actual[k] - recommended[k]) / recommended[k] * 100, 2)
            for k in recommended
        }

        # Calculate DDS (Dietary Deviation Score)
        dds = round(sum(abs(v) for v in ndv.values()) / len(ndv), 2)

        # Calculate DW-DDS (Disease-Weighted DDS)
        dw_dds = dds
        if disease == "diabetes":
            dw_dds = round(dds * 1.2, 2)
        elif disease == "hypertension":
            dw_dds = round(dds * 1.15, 2)

        # Risk level
        risk = "Low" if dds < 20 else "Medium" if dds < 40 else "High"

        # DCM (Dietary Compliance Momentum)
        dcm_value = round(100 - dds, 2)
        dcm_status = "Positive Momentum" if dcm_value > 60 else "Neutral" if dcm_value > 40 else "Negative Momentum"

        # Adaptive meal plan based on disease
        if disease == "diabetes":
            adaptive_plan = {
                "breakfast": "Low-glycemic oatmeal with nuts",
                "lunch": "Grilled chicken with brown rice",
                "dinner": "Baked fish with vegetables",
                "snack": "Almonds and berries"
            }
        elif disease == "hypertension":
            adaptive_plan = {
                "breakfast": "Low-sodium oatmeal with fruits",
                "lunch": "Lean meat with low-sodium vegetables",
                "dinner": "Baked white fish with herbs",
                "snack": "Unsalted nuts"
            }
        else:
            adaptive_plan = {
                "breakfast": "Balanced breakfast with protein and carbs",
                "lunch": "Balanced lunch with all nutrients",
                "dinner": "Light dinner with vegetables",
                "snack": "Healthy snack option"
            }

        return jsonify({
            "DDS": dds,
            "DW_DDS": dw_dds,
            "risk_level": risk,
            "actual": actual,
            "recommended": recommended,
            "NDV": ndv,
            "DCM_value": dcm_value,
            "DCM_status": dcm_status,
            "adaptive_meal_plan": adaptive_plan
        }), 200

    except Exception as e:
        print(f"DDS calculation error: {e}")
        return jsonify({"error": "Failed to calculate DDS"}), 500

# ================================
# MEAL STORAGE APIS
# ================================

@app.route("/api/save-meal", methods=["POST"])
def save_meal():
    """Save a meal plan for the user."""
    try:
        data = request.json
        # In a real app, we'd get user_id from session
        # For now, we'll use a default or the one from localStorage if passed
        user_id = data.get("user_id", 1) 
        
        meal = MealPlan(
            user_id=user_id,
            meal_name=data.get("meal_name", "Unnamed Meal"),
            calories=data.get("calories"),
            protein=data.get("protein"),
            carbs=data.get("carbs"),
            fats=data.get("fats")
        )
        db.session.add(meal)
        db.session.commit()
        return jsonify({"success": True, "message": "Meal saved successfully"}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Save meal error: {e}")
        return jsonify({"success": False, "message": "Failed to save meal"}), 500

@app.route("/api/get-meals", methods=["GET"])
def get_meals():
    """Get all saved meals for a user."""
    try:
        # In a real app, we'd get user_id from session
        user_id = request.args.get("user_id", 1)
        meals = MealPlan.query.filter_by(user_id=user_id).all()
        return jsonify([{
            "id": m.id,
            "meal_name": m.meal_name,
            "calories": m.calories,
            "protein": m.protein,
            "carbs": m.carbs,
            "fats": m.fats,
            "date": m.date_planned.isoformat()
        } for m in meals]), 200
    except Exception as e:
        print(f"Get meals error: {e}")
        return jsonify({"error": "Failed to fetch meals"}), 500

# ================================
# RUN
# ================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)