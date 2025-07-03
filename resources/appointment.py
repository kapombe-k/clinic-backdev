from flask_restful import Resource, reqparse
from models import db, Appointment, Patient, Doctor
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

class AppointmentResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True, help="Patient ID is required")
    parser.add_argument('doctor_id', type=int, required=True, help="Doctor ID is required")
    parser.add_argument('date', type=str, required=True, help="Date is required (YYYY-MM-DD HH:MM)")

    def get(self, appointment_id=None):
        if appointment_id:
            appointment = Appointment.query.get(appointment_id)
            if appointment:
                return appointment.to_dict()
            return {"message": "Appointment not found"}, 404
        
        appointments = Appointment.query.all()
        return [a.to_dict() for a in appointments]

    def post(self):
        data = AppointmentResource.parser.parse_args()
        data['date'] = datetime.strptime(data['date'], '%Y-%m-%d %H:%M')
        
        # Validate patient and doctor exist
        if not Patient.query.get(data['patient_id']):
            return {"message": "Patient not found"}, 400
        if not Doctor.query.get(data['doctor_id']):
            return {"message": "Doctor not found"}, 400

        try:
            appointment = Appointment(**data)
            db.session.add(appointment)
            db.session.commit()
            return appointment.to_dict(), 201
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def patch(self, appointment_id):
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
        
        data = AppointmentResource.parser.parse_args()
        if 'date' in data:
            data['date'] = datetime.strptime(data['date'], '%Y-%m-%d %H:%M')
        
        for key, value in data.items():
            if value is not None:
                setattr(appointment, key, value)
        
        try:
            db.session.commit()
            return appointment.to_dict()
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

    def delete(self, appointment_id):
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
        
        try:
            db.session.delete(appointment)
            db.session.commit()
            return {"message": "Appointment deleted"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Database error"}, 500

class DailyAppointmentsResource(Resource):
    def get(self, date):
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            appointments = Appointment.query.filter(Appointment.date.has(date=date_obj)).all()
            return [a.to_dict() for a in appointments]
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD."}, 400
