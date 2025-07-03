from flask_restful import Resource, reqparse
from models import db, Prescription, Visit
from sqlalchemy.exc import SQLAlchemyError

class PrescriptionResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('visit_id', type=int, required=True, help="Visit ID is required")
    parser.add_argument('details', type=str, required=True, help="Prescription details are required")

    def get(self, prescription_id):
        prescription = Prescription.query.get(prescription_id)
        if prescription:
            return prescription.to_dict()
        return {"message": "Prescription not found"}, 404

    def post(self):
        data = PrescriptionResource.parser.parse_args()
        
        # Validate visit exists
        if not Visit.query.get(data['visit_id']):
            return {"message": "Visit not found"}, 400

        try:
            prescription = Prescription(**data)
            db.session.add(prescription)
            db.session.commit()
            return prescription.to_dict(), 201
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def patch(self, prescription_id):
        prescription = Prescription.query.get(prescription_id)
        if not prescription:
            return {"message": "Prescription not found"}, 404
        
        data = PrescriptionResource.parser.parse_args()
        for key, value in data.items():
            if value is not None:
                setattr(prescription, key, value)
        
        try:
            db.session.commit()
            return prescription.to_dict()
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def delete(self, prescription_id):
        prescription = Prescription.query.get(prescription_id)
        if not prescription:
            return {"message": "Prescription not found"}, 404
        
        try:
            db.session.delete(prescription)
            db.session.commit()
            return {"message": "Prescription deleted"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500
