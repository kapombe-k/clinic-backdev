from flask_restful import Resource, reqparse
from flask import current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Patient, User, Account, MedicalHistory, Appointment, Visit, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach
import re

class PatientResource(Resource):
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('name', type=str, required=True)
    post_parser.add_argument('gender', type=str, required=True, choices=['Male', 'Female', 'Other'])
    post_parser.add_argument('date_of_birth', type=str, required=True)
    post_parser.add_argument('phone', type=str, required=True)
    post_parser.add_argument('email', type=str)
    post_parser.add_argument('insurance_id', type=str)
    post_parser.add_argument('emergency_contact_name', type=str)
    post_parser.add_argument('emergency_contact_phone', type=str)
    post_parser.add_argument('create_user_account', type=bool, default=False)
    post_parser.add_argument('user_password', type=str)

    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('name', type=str)
    patch_parser.add_argument('gender', type=str, choices=['Male', 'Female', 'Other'])
    patch_parser.add_argument('phone', type=str)
    patch_parser.add_argument('email', type=str)
    patch_parser.add_argument('insurance_id', type=str)
    patch_parser.add_argument('emergency_contact_name', type=str)
    patch_parser.add_argument('emergency_contact_phone', type=str)
    patch_parser.add_argument('is_active', type=bool)

    @jwt_required()
    def get(self, patient_id=None):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        
        if patient_id:
            patient = Patient.query.options(
                joinedload(Patient.account),
                joinedload(Patient.medical_history),
                joinedload(Patient.appointments),
                joinedload(Patient.visits)
            ).get(patient_id)
            
            if not patient:
                return {"message": "Patient not found"}, 404
                
            # Authorization
            if claims['role'] == 'patient' and patient.user_id != current_user_id:
                return {"message": "Unauthorized"}, 403
                
            return self.patient_to_dict(patient, claims['role'])
        
        # List patients with role-based access
        query = Patient.query.options(joinedload(Patient.account))
        
        if claims['role'] == 'patient':
            patient = Patient.query.filter_by(user_id=current_user_id).first()
            if not patient:
                return {"message": "Patient profile not found"}, 404
            return [self.patient_to_dict(patient, claims['role'])]
        
        # Staff roles can see all patients
        if claims['role'] != 'admin':
            query = query.filter_by(is_active=True)
            
        patients = query.order_by(Patient.name).limit(200).all()
        return [self.patient_to_dict(p, claims['role']) for p in patients]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        if claims['role'] not in ['receptionist', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.post_parser.parse_args()
        
        # Validate phone
        if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
            return {"message": "Invalid phone format"}, 400
            
        # Parse date of birth
        try:
            dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            if (datetime.now().date() - dob).days < 365:
                return {"message": "Patient must be at least 1 year old"}, 400
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
            
        # Sanitize inputs v is the variable
        sanitized = {k: bleach.clean(v) if isinstance(v, str) else v for k, v in data.items()}
        
        # Check for duplicates
        if Patient.query.filter_by(name=sanitized['name']).first():
            return {"message": "Patient with this name already exists"}, 409

        # Create patient
        patient = Patient(
            name=sanitized['name'],
            gender=sanitized['gender'],
            date_of_birth=dob,
            phone=sanitized['phone'],
            email=sanitized.get('email'),
            insurance_id=sanitized.get('insurance_id'),
            emergency_contact_name=sanitized.get('emergency_contact_name'),
            emergency_contact_phone=sanitized.get('emergency_contact_phone'),
            is_active=True
        )
        
        # Create account
        account = Account(patient=patient, balance=0.0)
        
        # Create medical history
        medical_history = MedicalHistory(patient=patient)
        
        # Create user account if requested
        user = None
        if data.get('create_user_account'):
            if not data.get('user_password'):
                return {"message": "Password required for user account"}, 400
                
            user = User(
                name=sanitized['name'],
                email=sanitized.get('email') or f"patient-{sanitized['phone']}@clinic.com",
                role='patient',
                is_active=True
            )
            user.password = data['user_password']
            patient.user = user
        
        try:
            db.session.add(patient)
            db.session.add(account)
            db.session.add(medical_history)
            if user: 
                db.session.add(user)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="PATIENT_CREATE",
                target_id=patient.id,
                target_type='patient',
                details=f"Created patient: {patient.name}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.patient_to_dict(patient, claims['role']), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Patient creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, patient_id):
        claims = get_jwt()
        patient = Patient.query.options(
            joinedload(Patient.user),
            joinedload(Patient.account)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Authorization
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized"}, 403
        if claims['role'] not in ['admin', 'receptionist', 'patient']:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.patch_parser.parse_args()
        changes = []
        
        # Update fields
        fields = ['name', 'gender', 'phone', 'email', 'insurance_id', 
                 'emergency_contact_name', 'emergency_contact_phone']
        for field in fields:
            if field in data and data[field] is not None:
                sanitized = bleach.clean(data[field]) if isinstance(data[field], str) else data[field]
                setattr(patient, field, sanitized)
                changes.append(field)
                
        # Phone validation
        if 'phone' in changes:
            if not re.match(r"^\+?[0-9]{10,15}$", patient.phone):
                return {"message": "Invalid phone format"}, 400
                
        # Active status (admin only)
        if 'is_active' in data and data['is_active'] is not None:
            if claims['role'] != 'admin':
                return {"message": "Admin access required"}, 403
            patient.is_active = data['is_active']
            changes.append('is_active')
            
            # Deactivate user account
            if patient.user:
                patient.user.is_active = data['is_active']
                
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="PATIENT_UPDATE",
                target_id=patient_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.patient_to_dict(patient, claims['role'])
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Patient update failed: {str(e)}")
            return {"message": "Database error"}, 500

    def patient_to_dict(self, patient, role):
        # Calculate age
        age = None
        if patient.date_of_birth:
            today = datetime.now().date()
            age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < 
                (patient.date_of_birth.month, patient.date_of_birth.day)
            )
        
        # PHI protection based on role
        show_full_info = role in ['admin', 'doctor', 'receptionist', 'patient']

        return {
            "id": patient.id,
            "name": patient.name,
            "gender": patient.gender,
            "age": age,
            "phone": patient.phone if show_full_info else patient.phone[:4] + '******',
            "email": patient.email if show_full_info else patient.email[0] + '****@' + patient.email.split('@')[-1] if patient.email else None,
            "insurance_id": patient.insurance_id if show_full_info else "***",
            "emergency_contact": {
                "name": patient.emergency_contact_name,
                "phone": patient.emergency_contact_phone if show_full_info else "***"
            } if patient.emergency_contact_name else None,
            "is_active": patient.is_active,
            "account_balance": patient.account.balance if show_full_info and patient.account else None,
            "last_visit": self.get_last_visit(patient),
            "next_appointment": self.get_next_appointment(patient)
        }
    
    def get_last_visit(self, patient):
        visit = Visit.query.filter_by(patient_id=patient.id)\
                   .order_by(Visit.date.desc()).first()
        return visit.date.isoformat() if visit else None
    
    def get_next_appointment(self, patient):
        appointment = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.status == 'scheduled',
            Appointment.date >= datetime.now()
        ).order_by(Appointment.date.asc()).first()
        return appointment.date.isoformat() if appointment else None


class PatientMedicalHistoryResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('conditions', type=str)
    parser.add_argument('allergies', type=str)
    parser.add_argument('medications', type=str)
    parser.add_argument('notes', type=str)
    parser.add_argument('surgical_history', type=str)
    parser.add_argument('family_history', type=str)

    @jwt_required()
    def get(self, patient_id):
        claims = get_jwt()
        patient = Patient.query.options(
            joinedload(Patient.medical_history)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Authorization
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized"}, 403
        if claims['role'] not in ['doctor', 'admin', 'patient']:
            return {"message": "Insufficient permissions"}, 403
            
        if not patient.medical_history:
            return {"message": "Medical history not found"}, 404
            
        return self.history_to_dict(patient.medical_history)

    @jwt_required()
    def patch(self, patient_id):
        claims = get_jwt()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        patient = Patient.query.options(
            joinedload(Patient.medical_history)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        if not patient.medical_history:
            patient.medical_history = MedicalHistory()
            
        data = self.parser.parse_args()
        changes = []
        
        # Update medical history
        fields = ['conditions', 'allergies', 'medications', 
                 'notes', 'surgical_history', 'family_history']
        for field in fields:
            if field in data and data[field] is not None:
                sanitized = bleach.clean(data[field]) if data[field] else None
                setattr(patient.medical_history, field, sanitized)
                changes.append(field)
                
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="MEDICAL_HISTORY_UPDATE",
                target_id=patient_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.history_to_dict(patient.medical_history)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Medical history update failed: {str(e)}")
            return {"message": "Database error"}, 500

    def history_to_dict(self, history):
        return {
            "id": history.id,
            "conditions": history.conditions,
            "allergies": history.allergies,
            "medications": history.medications,
            "surgical_history": history.surgical_history,
            "family_history": history.family_history,
            "notes": history.notes,
            "last_updated": history.last_updated.isoformat() if history.last_updated else None
        }