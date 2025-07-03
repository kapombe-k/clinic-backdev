from flask_restful import Resource, reqparse
from models import db, Patient
from sqlalchemy.exc import SQLAlchemyError

class PatientResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True, help="Name is required")
    parser.add_argument('age', type=int, required=True, help="Age is required")
    parser.add_argument('phone_number', type=str, required=True, help="Phone number is required")
    parser.add_argument('address', type=str, required=True, help="Address is required")
    parser.add_argument('account_type', type=str, required=True, help="Account type is required")

    def get(self, patient_id=None):
        if patient_id:
            patient = Patient.query.get(patient_id)
            if patient:
                return {
                    "patient": patient.to_dict(),
                    "visits": [visit.to_dict() for visit in patient.visits],
                    "prescriptions": [visit.prescription.to_dict() for visit in patient.visits if visit.prescription],
                    "total_balance": patient.get_total_balance()
                }
            return {"message": "Patient not found"}, 404
        
        patients = Patient.query.all()
        return [p.to_dict() for p in patients]

    def post(self):
        data = PatientResource.parser.parse_args()
        try:
            patient = Patient(**data)
            db.session.add(patient)
            db.session.commit()
            return patient.to_dict(), 201
        except ValueError as e:
            return {"message": str(e)}, 400
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def patch(self, patient_id):
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
        
        data = PatientResource.parser.parse_args()
        for key, value in data.items():
            setattr(patient, key, value)
        
        try:
            db.session.commit()
            return patient.to_dict()
        except ValueError as e:
            return {"message": str(e)}, 400
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def delete(self, patient_id):
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
        
        try:
            db.session.delete(patient)
            db.session.commit()
            return {"message": "Patient deleted"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

class PatientSearchResource(Resource):
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument('q', type=str, required=True, location='args')
        args = parser.parse_args()
        
        patients = Patient.query.filter(
            Patient.name.ilike(f"%{args['q']}%") |
            Patient.phone_number.like(f"%{args['q']}%")
        ).all()
        
        return [p.to_dict() for p in patients]
