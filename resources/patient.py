from flask_restful import Resource, reqparse
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Patient, Appointment, Visit, Account, MedicalHistory
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import re

class PatientResource(Resource):
    # Reqparse configuration with all fields
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('name', type=str, required=True, 
                             help="Name is required")
    post_parser.add_argument('gender', type=str, required=True, 
                             choices=['Male', 'Female', 'Other'],
                             help="Gender is required (Male, Female, Other)")
    post_parser.add_argument('phone', type=str, required=True, 
                             help="Phone number is required")
    post_parser.add_argument('email', type=str, 
                             help="Valid email address")
    post_parser.add_argument('date_of_birth', type=str, 
                             help="Date of birth (YYYY-MM-DD)")
    post_parser.add_argument('address', type=str, 
                             help="Full address")
    post_parser.add_argument('insurance_id', type=str, 
                             help="Insurance provider ID")
    post_parser.add_argument('emergency_contact', type=str, 
                             help="Emergency contact information")
    
    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('name', type=str, 
                              help="Updated name")
    patch_parser.add_argument('gender', type=str, 
                              choices=['Male', 'Female', 'Other'],
                              help="Updated gender")
    patch_parser.add_argument('phone', type=str, 
                              help="Updated phone number")
    patch_parser.add_argument('email', type=str, 
                              help="Updated email address")
    patch_parser.add_argument('address', type=str, 
                              help="Updated address")
    patch_parser.add_argument('insurance_id', type=str, 
                              help="Updated insurance provider ID")
    patch_parser.add_argument('emergency_contact', type=str, 
                              help="Updated emergency contact")

    @jwt_required()
    def get(self, patient_id=None):
        current_user_id = get_jwt_identity()
        claims = get_jwt_claims()
        
        if patient_id:
            patient = Patient.query.get(patient_id)
            if not patient:
                return {"message": "Patient not found"}, 404
                
            if claims['role'] == 'patient' and patient.user_id != current_user_id:
                return {"message": "Unauthorized to access this patient"}, 403
                
            return self.patient_to_dict(patient)
        
        # List patients with role-based filtering
        if claims['role'] == 'patient':
            patient = Patient.query.filter_by(user_id=current_user_id).first()
            if not patient:
                return {"message": "Patient profile not found"}, 404
            return [self.patient_to_dict(patient)]
        
        # Staff roles can see all patients
        query = Patient.query
        name_filter = request.args.get('name')
        if name_filter:
            query = query.filter(Patient.name.ilike(f"%{name_filter}%"))
            
        patients = query.order_by(Patient.name).limit(100).all()
        return [self.patient_to_dict(p) for p in patients]

    @jwt_required()
    def post(self):
        claims = get_jwt_claims()
        if claims['role'] not in ['receptionist', 'admin']:
            return {"message": "Insufficient permissions to create patients"}, 403
            
        data = self.post_parser.parse_args()
        
        # Validate phone format
        if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
            return {"message": "Invalid phone number format"}, 400
            
        # Create account and medical history records
        account = Account(balance=0.0)
        medical_history = MedicalHistory()
        
        try:
            # Parse date if provided
            dob = None
            if data.get('date_of_birth'):
                dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
                
            patient = Patient(
                name=data['name'],
                gender=data['gender'],
                phone=data['phone'],
                email=data.get('email'),
                date_of_birth=dob,
                address=data.get('address'),
                insurance_id=data.get('insurance_id'),
                emergency_contact=data.get('emergency_contact'),
                account=account,
                medical_history=medical_history
            )
            
            db.session.add(patient)
            db.session.add(account)
            db.session.add(medical_history)
            db.session.commit()
            
            return self.patient_to_dict(patient), 201
            
        except ValueError as e:
            return {"message": str(e)}, 400
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500


    @jwt_required()
    def patch(self, patient_id):
        claims = get_jwt_claims()
        allowed_roles = ['patient', 'receptionist', 'admin']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions to update patients"}, 403
            
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
            
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized to update this patient"}, 403
            
        data = self.patch_parser.parse_args()
        
        # Validate phone if provided
        if 'phone' in data and data['phone']:
            if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
                return {"message": "Invalid phone number format"}, 400
            patient.phone = data['phone']
            
        # Update fields
        update_fields = ['name', 'gender', 'email', 'address', 
                         'insurance_id', 'emergency_contact']
        for field in update_fields:
            if field in data and data[field] is not None:
                setattr(patient, field, data[field])
        
        try:
            db.session.commit()
            return self.patient_to_dict(patient)
        except ValueError as e:
            return {"message": str(e)}, 400
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def delete(self, patient_id):
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can delete patients"}, 403
            
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
        
        try:
            # Delete related records safely
            if patient.account:
                db.session.delete(patient.account)
            if patient.medical_history:
                db.session.delete(patient.medical_history)
                
            db.session.delete(patient)
            db.session.commit()
            return {"message": "Patient and related records deleted"}
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def patient_to_dict(self, patient):
        # Calculate age if DOB is available
        age = None
        if patient.date_of_birth:
            today = datetime.today()
            age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < 
                (patient.date_of_birth.month, patient.date_of_birth.day)
            )
        
        return {
            "id": patient.id,
            "name": patient.name,
            "gender": patient.gender,
            "phone": patient.phone,
            "email": patient.email,
            "age": age,
            "address": patient.address,
            "insurance_id": patient.insurance_id,
            "emergency_contact": patient.emergency_contact,
            "account": {
                "balance": patient.account.balance,
                "last_payment": patient.account.last_payment_date.isoformat() if patient.account.last_payment_date else None
            } if patient.account else None,
            "medical_history": {
                "id": patient.medical_history.id,
                "conditions": patient.medical_history.conditions,
                "allergies": patient.medical_history.allergies,
                "medications": patient.medical_history.medications,
                "notes": patient.medical_history.notes
            } if patient.medical_history else None,
            "next_appointment": self.get_next_appointment(patient),
            "last_visit": self.get_last_visit(patient)
        }
    
    def get_next_appointment(self, patient):
        next_appt = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.status == 'scheduled',
            Appointment.date >= datetime.now()
        ).order_by(Appointment.date.asc()).first()
        
        if not next_appt:
            return None
            
        return {
            "id": next_appt.id,
            "date": next_appt.date.isoformat(),
            "doctor": next_appt.doctor.user.name,
            "reason": next_appt.reason
        }
    
    def get_last_visit(self, patient):
        last_visit = Visit.query.filter_by(patient_id=patient.id)\
                       .order_by(Visit.date.desc()).first()
        
        if not last_visit:
            return None
            
        return {
            "id": last_visit.id,
            "date": last_visit.date.isoformat(),
            "doctor": last_visit.doctor.user.name,
            "summary": last_visit.notes[:100] + '...' if last_visit.notes else None
        }

class PatientMedicalHistoryResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('conditions', type=str, help="Medical conditions")
    parser.add_argument('allergies', type=str, help="Allergies information")
    parser.add_argument('medications', type=str, help="Current medications")
    parser.add_argument('notes', type=str, help="Additional medical notes")

    @jwt_required()
    def get(self, patient_id):
        """Get medical history for a patient"""
        claims = get_jwt_claims()
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Authorization: Doctors and admins can access, patients can access their own
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized to access this medical history"}, 403
        if claims['role'] not in ['doctor', 'admin', 'patient']:
            return {"message": "Insufficient permissions"}, 403
            
        if not patient.medical_history:
            return {"message": "Medical history not found for this patient"}, 404
            
        return self.medical_history_to_dict(patient.medical_history)

    @jwt_required()
    def patch(self, patient_id):
        """Update medical history (doctors only)"""
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Only doctors and admins can update medical history"}, 403
            
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
            
        if not patient.medical_history:
            # Create medical history if it doesn't exist
            patient.medical_history = MedicalHistory()
            
        data = self.parser.parse_args()
        
        # Update fields
        update_fields = ['conditions', 'allergies', 'medications', 'notes']
        for field in update_fields:
            if data.get(field) is not None:
                setattr(patient.medical_history, field, data[field])
        
        try:
            db.session.commit()
            return self.medical_history_to_dict(patient.medical_history)
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def medical_history_to_dict(self, medical_history):
        return {
            "id": medical_history.id,
            "conditions": medical_history.conditions,
            "allergies": medical_history.allergies,
            "medications": medical_history.medications,
            "notes": medical_history.notes,
            "last_updated": medical_history.last_updated.isoformat() if medical_history.last_updated else None
        }


class PatientSearchResource(Resource):
    @jwt_required()
    def get(self):
        claims = get_jwt_claims()
        if claims['role'] not in ['receptionist', 'doctor', 'admin']:
            return {"message": "Insufficient permissions to search patients"}, 403
            
        parser = reqparse.RequestParser()
        parser.add_argument('q', type=str, required=True, location='args')
        args = parser.parse_args()
        
        search_term = f"%{args['q']}%"
        patients = Patient.query.filter(
            Patient.name.ilike(search_term) |
            Patient.phone.like(search_term) |
            Patient.email.ilike(search_term) |
            Patient.insurance_id.ilike(search_term)
        ).limit(50).all()
        
        return [{
            "id": p.id,
            "name": p.name,
            "phone": p.phone,
            "next_appointment": self.get_next_appointment_date(p)
        } for p in patients]
    
    def get_next_appointment_date(self, patient):
        next_appt = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.status == 'scheduled',
            Appointment.date >= datetime.now()
        ).order_by(Appointment.date.asc()).first()
        
        return next_appt.date.isoformat() if next_appt else None