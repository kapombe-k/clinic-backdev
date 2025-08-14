from flask_restful import Resource, reqparse
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Doctor, User, Appointment
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import re

class DoctorResource(Resource):
    # Reqparse configuration with all doctor fields
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('name', type=str, required=True, 
                             help="Doctor's full name is required")
    post_parser.add_argument('specialty', type=str, required=True, 
                             help="Medical specialty is required")
    post_parser.add_argument('license_number', type=str, required=True, 
                             help="Medical license number is required")
    post_parser.add_argument('hourly_rate', type=float, required=True, 
                             help="Hourly rate is required")
    post_parser.add_argument('email', type=str, required=True, 
                             help="Email address is required")
    post_parser.add_argument('phone', type=str, required=True, 
                             help="Phone number is required")
    
    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('name', type=str, 
                             help="Updated name")
    patch_parser.add_argument('specialty', type=str, 
                             help="Updated specialty")
    patch_parser.add_argument('license_number', type=str, 
                             help="Updated license number")
    patch_parser.add_argument('hourly_rate', type=float, 
                             help="Updated hourly rate")
    patch_parser.add_argument('email', type=str, 
                             help="Updated email address")
    patch_parser.add_argument('phone', type=str, 
                             help="Updated phone number")
    patch_parser.add_argument('is_active', type=bool, 
                             help="Set active status")

    @jwt_required()
    def get(self, doctor_id=None):
        """Get doctor details with authorization checks"""
        claims = get_jwt_claims()
        
        if doctor_id:
            doctor = Doctor.query.get(doctor_id)
            if not doctor:
                return {"message": "Doctor not found"}, 404
                
            # Only active doctors are visible to non-admins
            if not doctor.is_active and claims['role'] != 'admin':
                return {"message": "Doctor not found"}, 404
                
            return self.doctor_to_dict(doctor)
        
        # List doctors - different rules per role
        query = Doctor.query
        
        # Patients and receptionists only see active doctors
        if claims['role'] in ['patient', 'receptionist']:
            query = query.filter_by(is_active=True)
        
        # Filter by specialty if requested
        specialty = request.args.get('specialty')
        if specialty:
            query = query.filter(Doctor.specialty.ilike(f"%{specialty}%"))
            
        # Filter by name if requested
        name_filter = request.args.get('name')
        if name_filter:
            query = query.filter(Doctor.user.has(name=name_filter))
            
        doctors = query.order_by(Doctor.specialty, Doctor.user_id).all()
        return [self.doctor_to_dict(d) for d in doctors]

    @jwt_required()
    def post(self):
        """Create new doctor (admin only)"""
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can create doctors"}, 403
            
        data = self.post_parser.parse_args()
        
        # Validate inputs
        if data['hourly_rate'] <= 0:
            return {"message": "Hourly rate must be positive"}, 400
            
        if not re.match(r"^[\w\s-]+$", data['specialty']):
            return {"message": "Invalid specialty format"}, 400
            
        if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
            return {"message": "Invalid phone number format"}, 400
            
        # Check if license number is unique
        if Doctor.query.filter_by(license_number=data['license_number']).first():
            return {"message": "License number already exists"}, 409
            
        try:
            # Create user account for the doctor
            user = User(
                name=data['name'],
                email=data['email'],
                password="temp_password",  # Should be reset upon first login
                role='doctor'
            )
            
            # Create doctor profile
            doctor = Doctor(
                specialty=data['specialty'],
                license_number=data['license_number'],
                hourly_rate=data['hourly_rate'],
                phone=data['phone'],
                is_active=True,
                user=user
            )
            
            db.session.add(user)
            db.session.add(doctor)
            db.session.commit()
            
            return self.doctor_to_dict(doctor), 201
            
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def patch(self, doctor_id):
        """Update doctor information (admin and the doctor themselves)"""
        claims = get_jwt_claims()
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return {"message": "Doctor not found"}, 404
            
        # Authorization: Admins or the doctor themselves
        is_admin = claims['role'] == 'admin'
        is_self = claims['role'] == 'doctor' and doctor.user_id == get_jwt_identity()
        
        if not (is_admin or is_self):
            return {"message": "Unauthorized to update this doctor"}, 403
            
        data = self.patch_parser.parse_args()
        
        # Validate inputs
        if 'hourly_rate' in data and data['hourly_rate'] is not None:
            if data['hourly_rate'] <= 0:
                return {"message": "Hourly rate must be positive"}, 400
            doctor.hourly_rate = data['hourly_rate']
            
        if 'license_number' in data and data['license_number'] is not None:
            # Check for duplicate license number
            existing = Doctor.query.filter(
                Doctor.license_number == data['license_number'],
                Doctor.id != doctor_id
            ).first()
            if existing:
                return {"message": "License number already in use"}, 409
            doctor.license_number = data['license_number']
            
        if 'phone' in data and data['phone'] is not None:
            if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
                return {"message": "Invalid phone number format"}, 400
            doctor.phone = data['phone']
            
        if 'is_active' in data and data['is_active'] is not None:
            # Only admins can change active status
            if not is_admin:
                return {"message": "Only admins can change active status"}, 403
            doctor.is_active = data['is_active']
            
        # Update user info if changed
        if 'name' in data and data['name'] is not None:
            doctor.user.name = data['name']
            
        if 'email' in data and data['email'] is not None:
            doctor.user.email = data['email']
            
        try:
            db.session.commit()
            return self.doctor_to_dict(doctor)
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def delete(self, doctor_id):
        """Deactivate doctor (admin only) - Soft delete"""
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can deactivate doctors"}, 403
            
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return {"message": "Doctor not found"}, 404
            
        # Don't actually delete - set to inactive
        doctor.is_active = False
        
        try:
            db.session.commit()
            return {"message": "Doctor deactivated"}
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def doctor_to_dict(self, doctor):
        """Serialize doctor with relevant information"""
        return {
            "id": doctor.id,
            "name": doctor.user.name,
            "email": doctor.user.email,
            "specialty": doctor.specialty,
            "license_number": doctor.license_number,
            "hourly_rate": doctor.hourly_rate,
            "phone": doctor.phone,
            "is_active": doctor.is_active,
            "next_available": self.get_next_available(doctor),
            "patient_count": self.get_patient_count(doctor)
        }
    
    def get_next_available(self, doctor):
        """Get next available appointment slot"""
        # This would typically come from a scheduling system
        # For demo, return tomorrow at 9am
        tomorrow = datetime.now() + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0).isoformat()
    
    def get_patient_count(self, doctor):
        """Get count of active patients"""
        return Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status == 'scheduled'
        ).distinct(Appointment.patient_id).count()


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
        ).order_by(Appointment.date).all()
        
        return [{
            "id": a.id,
            "date": a.date.isoformat(),
            "patient": {
                "id": a.patient.id,
                "name": a.patient.name
            },
            "status": a.status,
            "reason": a.reason
        } for a in appointments]


class DoctorAvailabilityResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('date', type=str, required=True, 
                        help="Date (YYYY-MM-DD) is required")
    parser.add_argument('duration', type=int, required=True, 
                        help="Duration in minutes is required")

    @jwt_required()
    def get(self, doctor_id):
        """Check doctor availability for a time slot"""
        doctor = Doctor.query.get(doctor_id)
        if not doctor or not doctor.is_active:
            return {"message": "Doctor not found"}, 404
            
        # Parse arguments
        args = self.parser.parse_args()
        
        try:
            date = datetime.strptime(args['date'], '%Y-%m-%d')
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
            
        duration = args['duration']
        
        # Check if doctor has availability (simplified)
        # In production, this would check against actual schedule
        has_availability = True
        
        return {
            "available": has_availability,
            "next_available": self.get_next_available(doctor, date, duration)
        }
    
    def get_next_available(self, doctor, requested_date, duration):
        """Find next available slot after requested date"""
        # Simplified implementation
        # Production would integrate with scheduling system
        return (requested_date + timedelta(days=1)).replace(hour=9, minute=0).isoformat()