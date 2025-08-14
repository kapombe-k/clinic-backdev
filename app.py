from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_restful import Api
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from models import db
import os
import logging
from logging.handlers import RotatingFileHandler

# Import all resources
from resources.auth import AuthResource
from resources.users import UserResource
from resources.patient import PatientResource, PatientMedicalHistoryResource, PatientSearchResource
from resources.visit import VisitResource, VisitMediaResource
from resources.appointment import AppointmentResource
from resources.treatments import TreatmentResource
from resources.billings import BillingResource
from resources.inventory import InventoryResource
from resources.analytics import AnalyticsResource

app = Flask(__name__)

# Configuration
app.config.from_object('config.Config')

# Database initialization
db.init_app(app)
migrate = Migrate(app, db)

# CORS setup
CORS(app, resources={r"/*": {"origins": app.config['ALLOWED_ORIGINS']}})

# API initialization
api = Api(app)

# JWT initialization
jwt = JWTManager(app)

# Configure logging
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

# Error handlers
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

# Register resources
api.add_resource(AuthResource, '/auth/login', '/auth/register', 
                 '/auth/refresh-token', '/auth/logout')
api.add_resource(UserResource, '/users', '/users/<int:user_id>')
api.add_resource(PatientResource, '/patients', '/patients/<int:patient_id>')
api.add_resource(PatientMedicalHistoryResource, '/patients/<int:patient_id>/medical-history')
api.add_resource(PatientSearchResource, '/patients/search')
api.add_resource(VisitResource, '/visits', '/visits/<int:visit_id>')
api.add_resource(VisitMediaResource, '/visits/<int:visit_id>/media')
api.add_resource(AppointmentResource, '/appointments', '/appointments/<int:appointment_id>')
api.add_resource(TreatmentResource, '/treatments', '/treatments/<int:treatment_id>')
api.add_resource(BillingResource, '/billings', '/billings/<int:billing_id>')
api.add_resource(InventoryResource, '/inventory', '/inventory/<int:item_id>')
api.add_resource(AnalyticsResource, '/analytics/<string:report_type>')

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

if __name__ == '__main__':
    app.run(host=app.config['HOST'], port=app.config['PORT'])