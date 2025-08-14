from flask_restful import Resource, reqparse
from flask import request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Appointment, Patient, Doctor, User, Visit, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach

class AppointmentResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True)
    parser.add_argument('doctor_id', type=int, required=True)
    parser.add_argument('date', type=str, required=True)
    parser.add_argument('reason', type=str, required=True)
    parser.add_argument('duration', type=int, default=30)
    parser.add_argument('status', type=str, default='scheduled', 
                       choices=['scheduled', 'completed', 'cancelled', 'no_show'])
    
    @jwt_required()
    def get(self, appointment_id=None):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        
        if appointment_id:
            appointment = Appointment.query.options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user)
            ).get(appointment_id)
            
            if not appointment:
                return {"message": "Appointment not found"}, 404
                
            # Authorization
            if claims['role'] == 'patient' and appointment.patient.user_id != current_user_id:
                return {"message": "Unauthorized"}, 403
            if claims['role'] == 'doctor' and appointment.doctor.user_id != current_user_id:
                return {"message": "Unauthorized"}, 403
                
            return self.appointment_to_dict(appointment)
        
        # List appointments with role-based filtering
        query = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        )
        
        if claims['role'] == 'patient':
            patient = Patient.query.filter_by(user_id=current_user_id).first()
            if not patient:
                return {"message": "Patient profile not found"}, 404
            query = query.filter_by(patient_id=patient.id)
        elif claims['role'] == 'doctor':
            doctor = Doctor.query.filter_by(user_id=current_user_id).first()
            if not doctor:
                return {"message": "Doctor profile not found"}, 404
            query = query.filter_by(doctor_id=doctor.id)
            
        # Date filtering
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if start_date:
            query = query.filter(Appointment.date >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(Appointment.date <= datetime.fromisoformat(end_date))
            
        # Status filtering
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
            
        appointments = query.order_by(Appointment.date).limit(100).all()
        return [self.appointment_to_dict(a) for a in appointments]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin', 'patient']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.parser.parse_args()
        
        # Validate patient
        patient = Patient.query.get(data['patient_id'])
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Validate doctor
        doctor = Doctor.query.get(data['doctor_id'])
        if not doctor:
            return {"message": "Doctor not found"}, 404
            
        # Parse date
        try:
            appt_date = datetime.fromisoformat(data['date'])
        except (ValueError, TypeError):
            return {"message": "Invalid date format. Use ISO 8601"}, 400
            
        # Check for scheduling conflicts
        existing = Appointment.query.filter(
            Appointment.doctor_id == data['doctor_id'],
            Appointment.date == appt_date,
            Appointment.status != 'cancelled'
        ).first()
        if existing:
            return {"message": "Time slot already booked"}, 409
            
        # Create appointment
        appointment = Appointment(
            patient_id=data['patient_id'],
            doctor_id=data['doctor_id'],
            date=appt_date,
            reason=bleach.clean(data['reason']),
            duration=data['duration'],
            status=data['status'],
            user_id=get_jwt_identity()  # Creator
        )
        
        try:
            db.session.add(appointment)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_CREATE",
                target_id=appointment.id,
                target_type='appointment',
                details=f"Created for {patient.name} with Dr. {doctor.user.name}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.appointment_to_dict(appointment), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, appointment_id):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin', 'doctor']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        data = self.parser.parse_args()
        changes = []
        
        # Update fields
        if 'date' in data and data['date']:
            try:
                new_date = datetime.fromisoformat(data['date'])
                appointment.date = new_date
                changes.append('date')
            except (ValueError, TypeError):
                return {"message": "Invalid date format"}, 400
                
        if 'status' in data and data['status']:
            appointment.status = data['status']
            changes.append('status')
            
        if 'reason' in data and data['reason']:
            appointment.reason = bleach.clean(data['reason'])
            changes.append('reason')
            
        if 'duration' in data and data['duration']:
            appointment.duration = data['duration']
            changes.append('duration')
            
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_UPDATE",
                target_id=appointment_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.appointment_to_dict(appointment)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment update failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def delete(self, appointment_id):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        # Soft delete by changing status
        appointment.status = 'cancelled'
        
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_CANCEL",
                target_id=appointment_id,
                details="Appointment cancelled"
            )
            db.session.add(audit)
            db.session.commit()
            
            return {"message": "Appointment cancelled"}
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment cancellation failed: {str(e)}")
            return {"message": "Database error"}, 500

    def appointment_to_dict(self, appointment):
        return {
            "id": appointment.id,
            "patient": {
                "id": appointment.patient.id,
                "name": appointment.patient.name
            },
            "doctor": {
                "id": appointment.doctor.id,
                "name": appointment.doctor.user.name,
                "specialty": appointment.doctor.specialty
            },
            "date": appointment.date.isoformat(),
            "reason": appointment.reason,
            "duration": appointment.duration,
            "status": appointment.status,
            "created_at": appointment.created_at.isoformat()
        }