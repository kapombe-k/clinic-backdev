from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_restful import Api
from flask_cors import CORS
from models import db

# Import resources
from resources.patient import PatientResource, PatientSearchResource
from resources.visit import VisitResource, VisitPrescriptionResource
from resources.appointment import AppointmentResource
from resources.doctor import DoctorResource
from resources.prescription import PrescriptionResource

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clinic.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

migrate = Migrate(app=app, db=db)
db.init_app(app=app)
CORS(app)
api = Api(app=app)

# Error handlers
@app.errorhandler(404)
def not_found():
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(400)
def bad_request():
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(500)
def server_error():
    return jsonify({"error": "Internal server error"}), 500

# Register resources
api.add_resource(PatientResource, '/patients', '/patients/<int:patient_id>')
api.add_resource(PatientSearchResource, '/patients/search')
api.add_resource(VisitResource, '/visits', '/visits/<int:visit_id>')
api.add_resource(VisitPrescriptionResource, '/visits/<int:visit_id>/prescription')
api.add_resource(AppointmentResource, '/appointments', '/appointments/<int:appointment_id>')
api.add_resource(DoctorResource, '/doctors', '/doctors/<int:doctor_id>')
api.add_resource(PrescriptionResource, '/prescriptions/<int:prescription_id>')

@app.route('/')
def index():
    return jsonify({
        "message": "Clinic Management API",
        "endpoints": {
            "patients": "/patients",
            "patient_search": "/patients/search?q=<term>",
            "visits": "/visits",
            "appointments": "/appointments",
            "doctors": "/doctors"
        }
    })

if __name__ == '__main__':
    app.run(port=5555, debug=True)
