from flask_restful import Resource, reqparse
from models import db, Visit, Patient, Doctor
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

class VisitResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True, help="Patient ID is required")
    parser.add_argument('doctor_id', type=int, required=True, help="Doctor ID is required")
    parser.add_argument('date', type=str, required=True, help="Date is required (YYYY-MM-DD)")
    parser.add_argument('summary', type=str, required=True, help="Summary is required")
    parser.add_argument('procedure_details', type=str, required=True, help="Procedure details are required")
    parser.add_argument('amount_paid', type=float, required=True, help="Amount paid is required")
    parser.add_argument('balance', type=float)

    def get(self, visit_id=None):
        if visit_id:
            visit = Visit.query.get(visit_id)
            if visit:
                return {
                    "visit": visit.to_dict(),
                    "prescription": visit.prescription.to_dict() if visit.prescription else None,
                    "doctor": visit.doctor.name,
                    "amount_paid": visit.amount_paid,
                    "balance": visit.balance,
                    "appointments": [appointment.to_dict() for appointment in visit.patient.appointments if appointment.date.date() == visit.date]
                }
            return {"message": "Visit not found"}, 404
        
        visits = Visit.query.all()
        return [v.to_dict() for v in visits]

    def post(self):
        data = VisitResource.parser.parse_args()
        data['date'] = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        # Validate patient and doctor exist
        if not Patient.query.get(data['patient_id']):
            return {"message": "Patient not found"}, 400
        if not Doctor.query.get(data['doctor_id']):
            return {"message": "Doctor not found"}, 400

        try:
            visit = Visit(**data)
            db.session.add(visit)
            db.session.commit()
            return visit.to_dict(), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def patch(self, visit_id):
        visit = Visit.query.get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
        
        data = VisitResource.parser.parse_args()
        if 'date' in data:
            data['date'] = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        for key, value in data.items():
            if value is not None:
                setattr(visit, key, value)
        
        try:
            db.session.commit()
            return visit.to_dict()
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def delete(self, visit_id):
        visit = Visit.query.get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
        
        try:
            db.session.delete(visit)
            db.session.commit()
            return {"message": "Visit deleted"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500
