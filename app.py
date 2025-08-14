import os
from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_cors import CORS
from flask_restful import Api
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from datetime import timedelta
from dotenv import load_dotenv
from models import db
import logging
from logging.handlers import RotatingFileHandler

# Import all resources
from resources.auth import AuthResource
from resources.users import UserResource
from resources.patients import PatientResource, PatientMedicalHistoryResource, PatientSearchResource
from resources.visits import VisitResource, VisitMediaResource
from resources.appointments import AppointmentResource
from resources.treatments import TreatmentResource
from resources.billings import BillingResource
from resources.inventory import InventoryResource
from resources.analytics import AnalyticsResource

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ===========================================
# Application Configuration
# ===========================================

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///clinic.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"

# JWT Configuration
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "super-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
    minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 15)))
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(
    days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 30)))
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["JWT_COOKIE_CSRF_PROTECT"] = True
app.config["JWT_CSRF_CHECK_FORM"] = True
app.config["JWT_COOKIE_SAMESITE"] = "Lax"  # Strict in production if possible

# CORS Configuration
app.config["CORS_SUPPORTS_CREDENTIALS"] = True
app.config["CORS_ORIGINS"] = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.config["CORS_ALLOW_HEADERS"] = ["Content-Type", "Authorization"]
app.config["CORS_METHODS"] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# Rate limiting configuration (using Redis if available)
redis_url = os.environ.get("REDIS_URL")
if redis_url:
    app.config["RATELIMIT_STORAGE_URL"] = redis_url
    app.config["RATELIMIT_STRATEGY"] = "fixed-window"
    app.config["RATELIMIT_DEFAULT"] = "100 per minute"

# Server configuration
app.config["HOST"] = os.environ.get("HOST", "0.0.0.0")
app.config["PORT"] = int(os.environ.get("PORT", 5000))

# ===========================================
# Extension Initialization
# ===========================================

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# Initialize JWT
jwt = JWTManager(app)

# Initialize bcrypt
bcrypt = Bcrypt(app)

# Initialize API
api = Api(app)

# Initialize CORS
CORS(app, 
     resources={r"/*": {"origins": app.config["CORS_ORIGINS"]}},
     supports_credentials=app.config["CORS_SUPPORTS_CREDENTIALS"],
     allow_headers=app.config["CORS_ALLOW_HEADERS"],
     methods=app.config["CORS_METHODS"])

# ===========================================
# JWT Callbacks
# ===========================================

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    from models import TokenBlocklist
    jti = jwt_payload["jti"]
    token = TokenBlocklist.query.filter_by(jti=jti).first()
    return token is not None

@jwt.user_identity_loader
def user_identity_lookup(user):
    return user.id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    from models import User
    identity = jwt_data["sub"]
    return User.query.get(identity)

# ===========================================
# Error Handlers
# ===========================================

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request", "message": str(error)}), 400

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({"error": "Unauthorized", "message": "Authentication required"}), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({"error": "Forbidden", "message": "Insufficient permissions"}), 403

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found", "message": str(error)}), 404

@app.errorhandler(409)
def conflict(error):
    return jsonify({"error": "Conflict", "message": "Resource already exists"}), 409

@app.errorhandler(422)
def unprocessable(error):
    return jsonify({"error": "Unprocessable entity", "message": str(error)}), 422

@app.errorhandler(500)
def server_error(error):
    app.logger.error(f"Server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

# ===========================================
# Logging Configuration
# ===========================================

if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Application startup')

# ===========================================
# After Request Handler (CORS)
# ===========================================

@app.after_request
def after_request(response):
    # Add CORS headers to every response
    response.headers.add('Access-Control-Allow-Origin', ', '.join(app.config["CORS_ORIGINS"]))
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers', ', '.join(app.config["CORS_ALLOW_HEADERS"]))
    response.headers.add('Access-Control-Allow-Methods', ', '.join(app.config["CORS_METHODS"]))
    return response

# ===========================================
# API Endpoint Registration
# ===========================================

# Authentication endpoints
api.add_resource(AuthResource, '/auth/login', '/auth/register', 
                 '/auth/refresh-token', '/auth/logout', endpoint='auth')

# User management
api.add_resource(UserResource, '/users', '/users/<int:user_id>')

# Patient management
api.add_resource(PatientResource, '/patients', '/patients/<int:patient_id>')
api.add_resource(PatientMedicalHistoryResource, '/patients/<int:patient_id>/medical-history')
api.add_resource(PatientSearchResource, '/patients/search')

# Visit management
api.add_resource(VisitResource, '/visits', '/visits/<int:visit_id>')
api.add_resource(VisitMediaResource, '/visits/<int:visit_id>/media')

# Appointment management
api.add_resource(AppointmentResource, '/appointments', '/appointments/<int:appointment_id>')

# Treatment management
api.add_resource(TreatmentResource, '/treatments', '/treatments/<int:treatment_id>')

# Billing management
api.add_resource(BillingResource, '/billings', '/billings/<int:billing_id>')

# Inventory management
api.add_resource(InventoryResource, '/inventory', '/inventory/<int:item_id>')

# Analytics
api.add_resource(AnalyticsResource, '/analytics/<string:report_type>')

# ===========================================
# Root Endpoint
# ===========================================

@app.route('/')
def index():
    return jsonify({
        "message": "Clinic Management API",
        "version": "1.0.0",
        "endpoints": {
            "authentication": {
                "login": "POST /auth/login",
                "register": "POST /auth/register",
                "refresh": "POST /auth/refresh-token",
                "logout": "POST /auth/logout"
            },
            "users": {
                "list": "GET /users",
                "create": "POST /users",
                "detail": "GET /users/<id>",
                "update": "PATCH /users/<id>",
                "deactivate": "DELETE /users/<id>"
            },
            "patients": {
                "list": "GET /patients",
                "create": "POST /patients",
                "detail": "GET /patients/<id>",
                "update": "PATCH /patients/<id>",
                "medical_history": "GET/PATCH /patients/<id>/medical-history",
                "search": "GET /patients/search?q=<term>"
            },
            "visits": {
                "create": "POST /visits",
                "detail": "GET /visits/<id>",
                "update": "PATCH /visits/<id>",
                "add_media": "POST /visits/<id>/media"
            },
            "appointments": {
                "list": "GET /appointments",
                "create": "POST /appointments",
                "detail": "GET /appointments/<id>",
                "update": "PATCH /appointments/<id>",
                "cancel": "DELETE /appointments/<id>"
            },
            "treatments": {
                "create": "POST /treatments",
                "detail": "GET /treatments/<id>"
            },
            "billings": {
                "create": "POST /billings",
                "detail": "GET /billings/<id>",
                "update": "PATCH /billings/<id>"
            },
            "inventory": {
                "list": "GET /inventory",
                "create": "POST /inventory",
                "update": "PATCH /inventory/<id>",
                "delete": "DELETE /inventory/<id>"
            },
            "analytics": {
                "revenue": "GET /analytics/revenue",
                "doctor_performance": "GET /analytics/doctor-performance",
                "patient_stats": "GET /analytics/patient-stats"
            }
        }
    })

# ===========================================
# Application Entry Point
# ===========================================

if __name__ == '__main__':
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )