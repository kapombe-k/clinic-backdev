from flask_restful import Resource, reqparse
from models import db, Doctor
from sqlalchemy.exc import SQLAlchemyError

class DoctorResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True, help="Name is required")

    def get(self, doctor_id=None):
        if doctor_id:
            doctor = Doctor.query.get(doctor_id)
            if doctor:
                return doctor.to_dict()
            return {"message": "Doctor not found"}, 404
        
        doctors = Doctor.query.all()
        return [d.to_dict() for d in doctors]

    def post(self):
        data = DoctorResource.parser.parse_args()
        try:
            doctor = Doctor(**data)
            db.session.add(doctor)
            db.session.commit()
            return doctor.to_dict(), 201
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def patch(self, doctor_id):
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return {"message": "Doctor not found"}, 404
        
        data = DoctorResource.parser.parse_args()
        for key, value in data.items():
            setattr(doctor, key, value)
        
        try:
            db.session.commit()
            return doctor.to_dict()
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def delete(self, doctor_id):
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return {"message": "Doctor not found"}, 404
        
        try:
            db.session.delete(doctor)
            db.session.commit()
            return {"message": "Doctor deleted"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500
