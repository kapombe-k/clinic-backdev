import os
from flask import Flask, jsonify, request
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
from resources.auth import LoginResource, RegisterResource, RefreshTokenResource, LogoutResource, MeResource
from resources.users import UserResource
from resources.patient import PatientResource, PatientMedicalHistoryResource, PatientSearchResource
from resources.visit import VisitResource
from resources.appointment import AppointmentResource, AppointmentSearchResource
from resources.treatments import TreatmentResource
from resources.billings import BillingResource
from resources.inventory import InventoryResource
from resources.analytics import AnalyticsResource
from resources.doctor import DoctorResource, DoctorScheduleResource, DoctorAvailabilityResource, DoctorSearchResource
from resources.prescription import PrescriptionResource

# Load environment variables
load_dotenv()

app = Flask(__name__)

# ===========================================
# Application Configuration
# ===========================================

# Database configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT")
if ENVIRONMENT == "production":
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SUPABASE_URL")
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True

# JWT Configuration
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 15)))
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 30)))
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = os.environ.get("FLASK_ENV")
# Temporarily disable CSRF for debugging
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
app.config["JWT_CSRF_CHECK_FORM"] = False
app.config["JWT_COOKIE_SAMESITE"] = "Lax"  # Strict in production if possible

# Get BASE_URL for CORS configuration
BASE_URL = os.environ.get('ALLOWED_ORIGIN')

# CORS Configuration
app.config["CORS_SUPPORTS_CREDENTIALS"] = True
app.config["CORS_ORIGINS"] = os.environ.get('ALLOWED_ORIGIN')
app.config["CORS_ALLOW_HEADERS"] = ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"]
app.config["CORS_METHODS"] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
app.config["CORS_EXPOSE_HEADERS"] = ["Set-Cookie"]

# # Rate limiting configuration (using Redis if available)
# redis_url = os.environ.get("REDIS_URL")
# if redis_url:
#     app.config["RATELIMIT_STORAGE_URL"] = redis_url
#     app.config["RATELIMIT_STRATEGY"] = "fixed-window"
#     app.config["RATELIMIT_DEFAULT"] = "100 per minute"

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

# CORS setup with proper credentials support
CORS(
    app,
    origins=BASE_URL,  
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    expose_headers=["Set-Cookie"]
)

# Initialize API with CORS support
api = Api(app, catch_all_404s=True)

print(f"🔧 CORS configured for origins: {app.config['CORS_ORIGINS']}")

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
    # Handle both user objects and string IDs
    if hasattr(user, 'id'):
        return user.id
    return user

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
# After Request Handler
# ===========================================

@app.after_request
def after_request(response):
    # Debug logging for CORS issues
    origin = request.headers.get('Origin')
    if request.method == 'OPTIONS':
        print(f"🔄 OPTIONS request to: {request.path} from origin: {origin}")
    elif 'auth' in request.path:
        print(f"🔐 Auth request: {request.method} {request.path} from origin: {origin}")
    
    # Log CORS headers for debugging
    if origin:
        print(f"🔧 Request from origin: {origin}")
        print(f"🔧 Response CORS header: {response.headers.get('Access-Control-Allow-Origin', 'NOT SET')}")

    return response

# ===========================================
# API Endpoint Registration
# ===========================================

# Authentication endpoints
api.add_resource(LoginResource, '/auth/login')
api.add_resource(RegisterResource, '/auth/register')
api.add_resource(RefreshTokenResource, '/auth/refresh-token')
api.add_resource(LogoutResource, '/auth/logout')
api.add_resource(MeResource, '/auth/me')

# User management
api.add_resource(UserResource, '/users', '/users/<int:user_id>')

# Patient management
api.add_resource(PatientResource, '/patients', '/patients/<int:patient_id>')
api.add_resource(PatientMedicalHistoryResource, '/patients/<int:patient_id>/medical-history')
api.add_resource(PatientSearchResource, '/patients/search')

# Visit management
api.add_resource(VisitResource, '/visits', '/visits/<int:visit_id>')
#api.add_resource(VisitMediaResource, '/visits/<int:visit_id>/media')

# Appointment management
api.add_resource(AppointmentResource, '/appointments', '/appointments/<int:appointment_id>')
api.add_resource(AppointmentSearchResource, '/appointments/search')

# Treatment management
api.add_resource(TreatmentResource, '/treatments', '/treatments/<int:treatment_id>')

# Billing management
api.add_resource(BillingResource, '/billings', '/billings/<int:billing_id>')

# Inventory management
api.add_resource(InventoryResource, '/inventory', '/inventory/<int:item_id>')

# Analytics
api.add_resource(AnalyticsResource, '/analytics/<string:report_type>')

# Doctor management
api.add_resource(DoctorResource, '/doctors', '/doctors/<int:doctor_id>')
api.add_resource(DoctorScheduleResource, '/doctors/<int:doctor_id>/schedule')
api.add_resource(DoctorAvailabilityResource, '/doctors/<int:doctor_id>/availability')
api.add_resource(DoctorSearchResource, '/doctors/search')

# Prescription management
api.add_resource(PrescriptionResource, '/prescriptions', '/prescriptions/<int:prescription_id>')

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
                "logout": "POST /auth/logout",
                "me": "GET /auth/me"
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
                "search": "GET /patients/search",
                "search_params": {
                    "q": "General search term",
                    "name": "Search by name",
                    "phone": "Search by phone",
                    "email": "Search by email",
                    "insurance_id": "Search by insurance ID",
                    "gender": "Filter by gender (male/female/other)",
                    "is_active": "Filter by active status",
                    "min_age": "Minimum age filter",
                    "max_age": "Maximum age filter",
                    "page": "Page number (default: 1)",
                    "per_page": "Results per page (default: 20, max: 100)",
                    "sort_by": "Sort field (name, phone, email, gender, date_of_birth, created_at)",
                    "sort_order": "Sort order (asc/desc)"
                }
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
                "cancel": "DELETE /appointments/<id>",
                "search": "GET /appointments/search",
                "search_params": {
                    "q": "General search term",
                    "patient_name": "Search by patient name",
                    "doctor_name": "Search by doctor name",
                    "reason": "Search by appointment reason",
                    "status": "Filter by status (scheduled/completed/cancelled/no_show)",
                    "start_date": "Start date filter (ISO format)",
                    "end_date": "End date filter (ISO format)",
                    "doctor_id": "Filter by doctor ID",
                    "patient_id": "Filter by patient ID",
                    "page": "Page number (default: 1)",
                    "per_page": "Results per page (default: 20, max: 100)",
                    "sort_by": "Sort field (date, status, reason, patient_name, doctor_name, created_at)",
                    "sort_order": "Sort order (asc/desc)"
                }
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
            },
            "doctors": {
                "list": "GET /doctors",
                "create": "POST /doctors",
                "detail": "GET /doctors/<id>",
                "update": "PATCH /doctors/<id>",
                "deactivate": "DELETE /doctors/<id>",
                "schedule": "GET /doctors/<id>/schedule",
                "availability": "GET /doctors/<id>/availability",
                "search": "GET /doctors/search",
                "search_params": {
                    "q": "General search term",
                    "name": "Search by doctor name",
                    "specialty": "Search by specialty",
                    "license_number": "Search by license number",
                    "is_active": "Filter by active status",
                    "min_rate": "Minimum monthly rate filter",
                    "max_rate": "Maximum monthly rate filter",
                    "page": "Page number (default: 1)",
                    "per_page": "Results per page (default: 20, max: 100)",
                    "sort_by": "Sort field (name, specialty, license_number, monthly_rate, is_active)",
                    "sort_order": "Sort order (asc/desc)"
                }
            },
            "prescriptions": {
                "create": "POST /prescriptions",
                "detail": "GET /prescriptions/<id>",
                "update": "PATCH /prescriptions/<id>",
                "delete": "DELETE /prescriptions/<id>"
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