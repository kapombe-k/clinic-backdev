from flask_restful import Resource, reqparse
from flask import request  # Imported request for query parameters
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Appointment, Patient, Doctor
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import re  # For validation if needed

class AppointmentResource(Resource):
    # Reqparse configuration with all fields
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('patient_id', type=int, required=True, 
                             help="Patient ID is required")
    post_parser.add_argument('doctor_id', type=int, required=True, 
                             help="Doctor ID is required")
    post_parser.add_argument('date', type=str, required=True, 
                             help="Date and time in ISO format (YYYY-MM-DD HH:MM) is required")
    post_parser.add_argument('reason', type=str, 
                             help="Reason for appointment")
    post_parser.add_argument('duration', type=int, default=30,
                             help="Duration in minutes (default: 30)")
    
    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('patient_id', type=int, 
                             help="Updated patient ID")
    patch_parser.add_argument('doctor_id', type=int, 
                             help="Updated doctor ID")
    patch_parser.add_argument('date', type=str, 
                             help="Updated date and time in ISO format (YYYY-MM-DD HH:MM)")
    patch_parser.add_argument('reason', type=str, 
                             help="Updated reason")
    patch_parser.add_argument('status', type=str, 
                             choices=['scheduled', 'confirmed', 'cancelled', 'completed', 'no_show'],
                             help="Updated status")
    patch_parser.add_argument('duration', type=int, 
                             help="Updated duration in minutes")

    @jwt_required()
    def get(self, appointment_id=None):
        """Get appointment details with authorization checks"""
        claims = get_jwt_claims()
        current_user_id = get_jwt_identity()
        
        if appointment_id:
            # Eager load relationships for authorization
            appointment = Appointment.query.options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user)
            ).get(appointment_id)
            
            if not appointment:
                return {"message": "Appointment not found"}, 404
                
            # Authorization checks
            if claims['role'] == 'patient' and appointment.patient.user_id != current_user_id:
                return {"message": "Unauthorized to access this appointment"}, 403
                
            if claims['role'] == 'doctor' and appointment.doctor.user_id != current_user_id:
                return {"message": "Unauthorized to access this appointment"}, 403
                
            return self.appointment_to_dict(appointment)
        
        # List appointments with role-based filtering
        query = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        )
        
        # Apply role-based filters
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
            
        # Date range filtering
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Appointment.date >= start_date)
            except ValueError:
                return {"message": "Invalid start_date format. Use YYYY-MM-DD"}, 400
                
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Appointment.date < end_date)
            except ValueError:
                return {"message": "Invalid end_date format. Use YYYY-MM-DD"}, 400
                
        # Status filtering
        status = request.args.get('status')
        if status:
            query = query.filter(Appointment.status == status)
            
        appointments = query.order_by(Appointment.date).all()
        return [self.appointment_to_dict(a) for a in appointments]

    @jwt_required()
    def post(self):
        """Create new appointment (receptionists, patients, and admins)"""
        claims = get_jwt_claims()
        allowed_roles = ['receptionist', 'admin', 'patient']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions to create appointments"}, 403
            
        data = self.post_parser.parse_args()
        
        # Parse datetime
        try:
            appointment_date = datetime.strptime(data['date'], '%Y-%m-%d %H:%M')
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD HH:MM"}, 400
            
        # Validate patient
        patient = Patient.query.get(data['patient_id'])
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Patients can only create appointments for themselves
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized to create appointment for this patient"}, 403
            
        # Validate doctor
        doctor = Doctor.query.get(data['doctor_id'])
        if not doctor or not doctor.is_active:
            return {"message": "Doctor not found or inactive"}, 404
            
        # Check for overlapping appointments
        end_time = appointment_date + timedelta(minutes=data['duration'])
        overlapping = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.date < end_time,
            Appointment.date + timedelta(minutes=Appointment.duration) > appointment_date,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).first()
        
        if overlapping:
            return {
                "message": "Doctor has conflicting appointment",
                "conflicting_appointment_id": overlapping.id,
                "conflict_start": overlapping.date.isoformat(),
                "conflict_end": (overlapping.date + timedelta(minutes=overlapping.duration)).isoformat()
            }, 409

        try:
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                date=appointment_date,
                reason=data.get('reason'),
                duration=data['duration'],
                status='scheduled'
            )
            
            db.session.add(appointment)
            db.session.commit()
            
            # Reload with relationships
            db.session.refresh(appointment)
            appointment = Appointment.query.options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user)
            ).get(appointment.id)
            
            return self.appointment_to_dict(appointment), 201
            
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def patch(self, appointment_id):
        """Update appointment (receptionists, admins, and owners)"""
        claims = get_jwt_claims()
        appointment = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor)
        ).get(appointment_id)
        
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        # Authorization: Admins, receptionists, or the appointment owners
        is_admin = claims['role'] == 'admin'
        is_receptionist = claims['role'] == 'receptionist'
        is_patient_owner = claims['role'] == 'patient' and appointment.patient.user_id == get_jwt_identity()
        is_doctor_owner = claims['role'] == 'doctor' and appointment.doctor.user_id == get_jwt_identity()
        
        if not (is_admin or is_receptionist or is_patient_owner or is_doctor_owner):
            return {"message": "Unauthorized to update this appointment"}, 403
            
        data = self.patch_parser.parse_args()
        
        # Validate patient if changed
        if 'patient_id' in data and data['patient_id'] is not None:
            patient = Patient.query.get(data['patient_id'])
            if not patient:
                return {"message": "Patient not found"}, 404
                
            # Patients can only be changed by staff
            if claims['role'] == 'patient' and not is_patient_owner:
                return {"message": "Unauthorized to change patient"}, 403
                
            appointment.patient_id = data['patient_id']
            
        # Validate doctor if changed
        if 'doctor_id' in data and data['doctor_id'] is not None:
            doctor = Doctor.query.get(data['doctor_id'])
            if not doctor or not doctor.is_active:
                return {"message": "Doctor not found or inactive"}, 404
                
            # Only staff can change doctor
            if claims['role'] in ['patient', 'doctor']:
                return {"message": "Unauthorized to change doctor"}, 403
                
            appointment.doctor_id = data['doctor_id']
            
        # Parse and validate date if changed
        if 'date' in data and data['date'] is not None:
            try:
                new_date = datetime.strptime(data['date'], '%Y-%m-%d %H:%M')
            except ValueError:
                return {"message": "Invalid date format. Use YYYY-MM-DD HH:MM"}, 400
                
            appointment.date = new_date
            
        # Validate duration if changed
        if 'duration' in data and data['duration'] is not None:
            if data['duration'] <= 0:
                return {"message": "Duration must be positive"}, 400
            appointment.duration = data['duration']
            
        # Update other fields
        if 'reason' in data and data['reason'] is not None:
            appointment.reason = data['reason']
            
        if 'status' in data and data['status'] is not None:
            # Only staff can change status
            if claims['role'] in ['patient', 'doctor'] and not is_doctor_owner:
                return {"message": "Unauthorized to change status"}, 403
            appointment.status = data['status']
            
        # Check for overlapping appointments if time/doctor changed
        if 'date' in data or 'doctor_id' in data or 'duration' in data:
            end_time = appointment.date + timedelta(minutes=appointment.duration)
            overlapping = Appointment.query.filter(
                Appointment.doctor_id == appointment.doctor_id,
                Appointment.date < end_time,
                Appointment.date + timedelta(minutes=Appointment.duration) > appointment.date,
                Appointment.status.in_(['scheduled', 'confirmed']),
                Appointment.id != appointment.id
            ).first()
            
            if overlapping:
                return {
                    "message": "Doctor has conflicting appointment",
                    "conflicting_appointment_id": overlapping.id,
                    "conflict_start": overlapping.date.isoformat(),
                    "conflict_end": (overlapping.date + timedelta(minutes=overlapping.duration)).isoformat()
                }, 409

        try:
            db.session.commit()
            # Reload with relationships
            db.session.refresh(appointment)
            appointment = Appointment.query.options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user)
            ).get(appointment.id)
            
            return self.appointment_to_dict(appointment)
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def delete(self, appointment_id):
        """Cancel appointment (soft delete)"""
        claims = get_jwt_claims()
        appointment = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor)
        ).get(appointment_id)
        
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        # Authorization: Admins, receptionists, or the appointment owners
        is_admin = claims['role'] == 'admin'
        is_receptionist = claims['role'] == 'receptionist'
        is_patient_owner = claims['role'] == 'patient' and appointment.patient.user_id == get_jwt_identity()
        is_doctor_owner = claims['role'] == 'doctor' and appointment.doctor.user_id == get_jwt_identity()
        
        if not (is_admin or is_receptionist or is_patient_owner or is_doctor_owner):
            return {"message": "Unauthorized to cancel this appointment"}, 403
            
        # Soft delete by changing status
        appointment.status = 'cancelled'
        
        try:
            db.session.commit()
            return {"message": "Appointment cancelled"}
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def appointment_to_dict(self, appointment):
        """Serialize appointment with related data"""
        return {
            "id": appointment.id,
            "date": appointment.date.isoformat(),
            "duration": appointment.duration,
            "reason": appointment.reason,
            "status": appointment.status,
            "patient": {
                "id": appointment.patient.id,
                "name": appointment.patient.name,
                "phone": appointment.patient.phone
            },
            "doctor": {
                "id": appointment.doctor.id,
                "name": appointment.doctor.user.name,
                "specialty": appointment.doctor.specialty
            },
            "end_time": (appointment.date + timedelta(minutes=appointment.duration)).isoformat()
        }


class DoctorScheduleResource(Resource):
    @jwt_required()
    def get(self, doctor_id):
        """Get doctor's schedule for a given date range"""
        claims = get_jwt_claims()
        doctor = Doctor.query.get(doctor_id)
        if not doctor or not doctor.is_active:
            return {"message": "Doctor not found"}, 404
            
        # Authorization: Doctor themselves or staff
        is_doctor = claims['role'] == 'doctor' and doctor.user_id == get_jwt_identity()
        is_staff = claims['role'] in ['receptionist', 'admin']
        
        if not (is_doctor or is_staff):
            return {"message": "Unauthorized to view this schedule"}, 403
            
        # Parse date range
        start_date = request.args.get('start_date', default=datetime.now().date().isoformat())
        end_date = request.args.get('end_date', default=(datetime.now() + timedelta(days=7)).date().isoformat())
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
            
        # Get appointments in date range
        appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.date >= start_date,
            Appointment.date <= end_date
        ).options(
            joinedload(Appointment.patient)
        ).order_by(Appointment.date).all()
        
        return [{
            "id": a.id,
            "date": a.date.isoformat(),
            "duration": a.duration,
            "reason": a.reason,
            "status": a.status,
            "patient": {
                "id": a.patient.id,
                "name": a.patient.name,
                "phone": a.patient.phone
            }
        } for a in appointments]


class AppointmentConflictsResource(Resource):
    @jwt_required()
    def get(self):
        """Check for appointment conflicts (for staff use)"""
        claims = get_jwt_claims()
        if claims['role'] not in ['receptionist', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        parser = reqparse.RequestParser()
        parser.add_argument('doctor_id', type=int, required=True)
        parser.add_argument('start_time', type=str, required=True)
        parser.add_argument('end_time', type=str, required=True)
        args = parser.parse_args()
        
        try:
            start_time = datetime.strptime(args['start_time'], '%Y-%m-%d %H:%M')
            end_time = datetime.strptime(args['end_time'], '%Y-%m-%d %H:%M')
        except ValueError:
            return {"message": "Invalid datetime format. Use YYYY-MM-DD HH:MM"}, 400
            
        conflicts = Appointment.query.filter(
            Appointment.doctor_id == args['doctor_id'],
            Appointment.date < end_time,
            Appointment.date + timedelta(minutes=Appointment.duration) > start_time,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor)
        ).all()
        
        return [{
            "id": c.id,
            "start": c.date.isoformat(),
            "end": (c.date + timedelta(minutes=c.duration)).isoformat(),
            "patient": {
                "id": c.patient.id,
                "name": c.patient.name
            },
            "status": c.status
        } for c in conflicts]