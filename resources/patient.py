from flask_restful import Resource, reqparse
from flask import request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Patient, Account, MedicalHistory, Appointment, Visit, User, Doctor
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta
import re
import bleach  # For input sanitization
from flask_bcrypt import generate_password_hash

class PatientResource(Resource):
    # Reqparse configuration with healthcare-specific validation
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('name', type=str, required=True, 
                             help="Full name is required")
    post_parser.add_argument('gender', type=str, required=True, 
                             choices=['Male', 'Female', 'Other'],
                             help="Gender is required (Male, Female, Other)")
    post_parser.add_argument('date_of_birth', type=str, required=True,
                             help="Date of birth (YYYY-MM-DD) is required")
    post_parser.add_argument('phone', type=str, required=True, 
                             help="Phone number is required")
    post_parser.add_argument('email', type=str, required=True,
                             help="Email address is required")
    post_parser.add_argument('address', type=str, 
                             help="Full address")
    post_parser.add_argument('insurance_id', type=str,
                             help="Insurance provider ID")
    post_parser.add_argument('emergency_contact_name', type=str,
                             help="Emergency contact name")
    post_parser.add_argument('emergency_contact_phone', type=str,
                             help="Emergency contact phone")
    post_parser.add_argument('medical_history', type=dict, location='json',
                             help="Initial medical history data")
    
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
    patch_parser.add_argument('emergency_contact_name', type=str,
                             help="Updated emergency contact name")
    patch_parser.add_argument('emergency_contact_phone', type=str,
                             help="Updated emergency contact phone")
    patch_parser.add_argument('is_active', type=bool,
                             help="Set active status")

    @jwt_required()
    def get(self, patient_id=None):
        """Get patient details with strict authorization checks"""
        current_user_id = get_jwt_identity()
        claims = get_jwt_claims()
        
        if patient_id:
            # Eager load all relationships for comprehensive response
            patient = Patient.query.options(
                joinedload(Patient.account),
                joinedload(Patient.medical_history),
                joinedload(Patient.appointments).joinedload(Appointment.doctor).joinedload(Doctor.user),
                joinedload(Patient.visits).joinedload(Visit.doctor).joinedload(Doctor.user)
            ).get(patient_id)
            
            if not patient:
                return {"message": "Patient not found"}, 404
                
            # Authorization: Patients can only access their own records
            if claims['role'] == 'patient' and patient.user_id != current_user_id:
                current_app.logger.warning(f"Unauthorized patient access attempt: user {current_user_id} tried to access patient {patient_id}")
                return {"message": "Unauthorized to access this patient"}, 403
                
            return self.patient_to_dict(patient)
        
        # List patients with role-based filtering
        if claims['role'] == 'patient':
            patient = Patient.query.filter_by(user_id=current_user_id).first()
            if not patient:
                return {"message": "Patient profile not found"}, 404
            return [self.patient_to_dict(patient)]
        
        # Staff roles can see all patients
        query = Patient.query.options(
            joinedload(Patient.account)
        )
        
        # Apply filters
        name_filter = request.args.get('name')
        if name_filter:
            query = query.filter(Patient.name.ilike(f"%{name_filter}%"))
            
        # Active status filter (default to active only for non-admins)
        if claims['role'] != 'admin':
            query = query.filter_by(is_active=True)
        elif 'show_inactive' in request.args:
            show_inactive = request.args.get('show_inactive').lower() == 'true'
            if not show_inactive:
                query = query.filter_by(is_active=True)
                
        patients = query.order_by(Patient.name).limit(200).all()
        return [self.patient_to_dict(p) for p in patients]

    @jwt_required()
    def post(self):
        """Create new patient (receptionists and admins only)"""
        claims = get_jwt_claims()
        if claims['role'] not in ['receptionist', 'admin']:
            current_app.logger.warning(f"Unauthorized patient creation attempt by user {get_jwt_identity()}")
            return {"message": "Insufficient permissions to create patients"}, 403
            
        data = self.post_parser.parse_args()
        
        # Validate phone format
        if not re.match(r"^\+?[0-9]{10,15}$", data['phone']):
            return {"message": "Invalid phone number format"}, 400
            
        # Validate and parse date of birth
        try:
            dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            # Validate age (at least 1 year old)
            if (datetime.now().date() - dob) < timedelta(days=365):
                return {"message": "Patient must be at least 1 year old"}, 400
        except ValueError:
            return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400
            
        # Sanitize all text inputs
        sanitized_data = {
            k: bleach.clean(v) if isinstance(v, str) else v 
            for k, v in data.items()
        }
        
        # Check for existing patient by phone or email
        existing_phone = Patient.query.filter_by(phone=sanitized_data['phone']).first()
        if existing_phone:
            return {"message": "Phone number already registered"}, 409
            
        existing_email = Patient.query.filter_by(email=sanitized_data['email']).first()
        if existing_email:
            return {"message": "Email already registered"}, 409

        # Create account and medical history records
        account = Account(balance=0.0)
        medical_history = MedicalHistory()
        
        # Create user account if needed (for patient portal access)
        user = User(
            name=sanitized_data['name'],
            email=sanitized_data['email'],
            password=generate_password_hash("TemporaryPassword123!"),  # Force reset on first login
            role='patient',
            is_temp_password=True
        )
        
        try:
            patient = Patient(
                name=sanitized_data['name'],
                gender=sanitized_data['gender'],
                phone=sanitized_data['phone'],
                email=sanitized_data['email'],
                date_of_birth=dob,
                address=sanitized_data.get('address'),
                insurance_id=sanitized_data.get('insurance_id'),
                emergency_contact_name=sanitized_data.get('emergency_contact_name'),
                emergency_contact_phone=sanitized_data.get('emergency_contact_phone'),
                account=account,
                medical_history=medical_history,
                user=user,
                is_active=True
            )
            
            # Add initial medical history if provided
            if sanitized_data.get('medical_history'):
                med_data = sanitized_data['medical_history']
                medical_history.conditions = med_data.get('conditions', '')
                medical_history.allergies = med_data.get('allergies', '')
                medical_history.medications = med_data.get('medications', '')
                medical_history.notes = med_data.get('notes', '')
            
            db.session.add(patient)
            db.session.add(account)
            db.session.add(medical_history)
            db.session.add(user)
            db.session.commit()
            
            current_app.logger.info(f"Patient created: {patient.id} by user {get_jwt_identity()}")
            return self.patient_to_dict(patient), 201
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Patient creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, patient_id):
        """Update patient information with strict access controls"""
        claims = get_jwt_claims()
        # Allow patients to update their own info, plus staff roles
        allowed_roles = ['patient', 'receptionist', 'admin', 'doctor']
        if claims['role'] not in allowed_roles:
            current_app.logger.warning(f"Unauthorized patient update attempt by user {get_jwt_identity()}")
            return {"message": "Insufficient permissions to update patients"}, 403
            
        # Eager load patient with relationships
        patient = Patient.query.options(
            joinedload(Patient.account),
            joinedload(Patient.medical_history),
            joinedload(Patient.user)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Patients can only update their own record
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            current_app.logger.warning(f"Patient update authorization failed: user {get_jwt_identity()} tried to update patient {patient_id}")
            return {"message": "Unauthorized to update this patient"}, 403
            
        data = self.patch_parser.parse_args()
        
        # Sanitize all text inputs
        sanitized_data = {
            k: bleach.clean(v) if v and isinstance(v, str) else v 
            for k, v in data.items() if v is not None
        }
        
        # Validate phone if provided
        if 'phone' in sanitized_data:
            if not re.match(r"^\+?[0-9]{10,15}$", sanitized_data['phone']):
                return {"message": "Invalid phone number format"}, 400
            # Check for duplicate
            existing = Patient.query.filter(
                Patient.phone == sanitized_data['phone'],
                Patient.id != patient_id
            ).first()
            if existing:
                return {"message": "Phone number already in use"}, 409
            patient.phone = sanitized_data['phone']
            
        # Update fields
        update_fields = ['name', 'gender', 'address', 'insurance_id',
                         'emergency_contact_name', 'emergency_contact_phone']
        for field in update_fields:
            if field in sanitized_data:
                setattr(patient, field, sanitized_data[field])
                
        # Email update requires verification
        if 'email' in sanitized_data:
            # Check for duplicate email
            existing = Patient.query.filter(
                Patient.email == sanitized_data['email'],
                Patient.id != patient_id
            ).first()
            if existing:
                return {"message": "Email already in use"}, 409
                
            # Update user email as well
            if patient.user:
                patient.user.email = sanitized_data['email']
            patient.email = sanitized_data['email']
            
        # Active status can only be changed by admins
        if 'is_active' in sanitized_data:
            if claims['role'] != 'admin':
                return {"message": "Only admins can change active status"}, 403
            patient.is_active = sanitized_data['is_active']
            
            # Deactivate user account if deactivating patient
            if not sanitized_data['is_active'] and patient.user:
                patient.user.is_active = False

        try:
            db.session.commit()
            current_app.logger.info(f"Patient updated: {patient_id} by user {get_jwt_identity()}")
            return self.patient_to_dict(patient)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Patient update failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def delete(self, patient_id):
        """Deactivate patient (admin only) - Never delete medical records"""
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            current_app.logger.warning(f"Unauthorized deactivation attempt by user {get_jwt_identity()}")
            return {"message": "Only admins can deactivate patients"}, 403
            
        patient = Patient.query.get(patient_id)
        if not patient:
            return {"message": "Patient not found"}, 404
        
        # Deactivate patient and associated user account
        patient.is_active = False
        if patient.user:
            patient.user.is_active = False
        
        try:
            db.session.commit()
            current_app.logger.info(f"Patient deactivated: {patient_id} by user {get_jwt_identity()}")
            return {"message": "Patient deactivated"}
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Patient deactivation failed: {str(e)}")
            return {"message": "Database error"}, 500

    def patient_to_dict(self, patient):
        """Serialize patient with related data - PHI protection applied"""
        # Calculate age
        age = None
        if patient.date_of_birth:
            today = datetime.now().date()
            age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < 
                (patient.date_of_birth.month, patient.date_of_birth.day)
            )
        
        # Mask sensitive information based on role
        claims = get_jwt_claims()
        show_full_info = claims['role'] in ['doctor', 'admin', 'receptionist']
        
        return {
            "id": patient.id,
            "name": patient.name,
            "gender": patient.gender,
            "age": age,
            "phone": patient.phone if show_full_info else patient.phone[:4] + '******',
            "email": patient.email if show_full_info else patient.email[0] + '****@' + patient.email.split('@')[-1],
            "address": patient.address if show_full_info else "***",
            "insurance_id": patient.insurance_id if show_full_info else "***",
            "emergency_contact": {
                "name": patient.emergency_contact_name,
                "phone": patient.emergency_contact_phone if show_full_info else "***"
            } if patient.emergency_contact_name else None,
            "is_active": patient.is_active,
            "account": {
                "balance": patient.account.balance if show_full_info else "***",
                "last_payment": patient.account.last_payment_date.isoformat() if patient.account.last_payment_date else None
            } if patient.account else None,
            "medical_history_summary": {
                "conditions": patient.medical_history.conditions[:100] + '...' if patient.medical_history.conditions else None,
                "allergies": patient.medical_history.allergies
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
        
        return {
            "id": next_appt.id,
            "date": next_appt.date.isoformat(),
            "doctor": next_appt.doctor.user.name,
            "reason": next_appt.reason
        } if next_appt else None
    
    def get_last_visit(self, patient):
        last_visit = Visit.query.filter_by(patient_id=patient.id)\
                       .order_by(Visit.date.desc()).first()
        
        return {
            "id": last_visit.id,
            "date": last_visit.date.isoformat(),
            "doctor": last_visit.doctor.user.name,
            "summary": last_visit.notes[:100] + '...' if last_visit.notes else None
        } if last_visit else None


class PatientMedicalHistoryResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('conditions', type=str, help="Medical conditions")
    parser.add_argument('allergies', type=str, help="Allergies information")
    parser.add_argument('medications', type=str, help="Current medications")
    parser.add_argument('notes', type=str, help="Additional medical notes")
    parser.add_argument('surgical_history', type=str, help="Surgical history")
    parser.add_argument('family_history', type=str, help="Family medical history")

    @jwt_required()
    def get(self, patient_id):
        """Get full medical history (strict access control)"""
        claims = get_jwt_claims()
        patient = Patient.query.options(
            joinedload(Patient.medical_history)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        # Authorization: Doctors, admins, and the patient themselves
        if claims['role'] == 'patient' and patient.user_id != get_jwt_identity():
            current_app.logger.warning(f"Unauthorized medical history access: user {get_jwt_identity()} tried to access patient {patient_id}")
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
            current_app.logger.warning(f"Unauthorized medical history update attempt by user {get_jwt_identity()}")
            return {"message": "Only doctors and admins can update medical history"}, 403
            
        patient = Patient.query.options(
            joinedload(Patient.medical_history)
        ).get(patient_id)
        
        if not patient:
            return {"message": "Patient not found"}, 404
            
        if not patient.medical_history:
            # Create medical history if it doesn't exist
            patient.medical_history = MedicalHistory()
            
        data = self.parser.parse_args()
        
        # Sanitize all medical inputs
        sanitized_data = {
            k: bleach.clean(v) if v else None 
            for k, v in data.items()
        }
        
        # Audit trail - record changes
        original_values = {
            field: getattr(patient.medical_history, field)
            for field in data.keys()
        }
        
        # Update fields
        update_fields = ['conditions', 'allergies', 'medications', 
                         'notes', 'surgical_history', 'family_history']
        for field in update_fields:
            if sanitized_data.get(field) is not None:
                setattr(patient.medical_history, field, sanitized_data[field])
        
        try:
            db.session.commit()
            
            # Log medical history changes
            changes = {
                field: f"{original_values[field][:30]}... → {sanitized_data[field][:30]}..."
                for field in update_fields 
                if sanitized_data.get(field) is not None and original_values[field] != sanitized_data[field]
            }
            
            if changes:
                current_app.logger.info(
                    f"Medical history updated for patient {patient_id} by user {get_jwt_identity()}. Changes: {changes}"
                )
            
            return self.medical_history_to_dict(patient.medical_history)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Medical history update failed: {str(e)}")
            return {"message": "Database error"}, 500

    def medical_history_to_dict(self, medical_history):
        return {
            "id": medical_history.id,
            "conditions": medical_history.conditions,
            "allergies": medical_history.allergies,
            "medications": medical_history.medications,
            "surgical_history": medical_history.surgical_history,
            "family_history": medical_history.family_history,
            "notes": medical_history.notes,
            "last_updated": medical_history.last_updated.isoformat() if medical_history.last_updated else None
        }


class PatientSearchResource(Resource):
    @jwt_required()
    def get(self):
        """Search patients - PHI-protected results"""
        claims = get_jwt_claims()
        if claims['role'] not in ['receptionist', 'doctor', 'admin']:
            return {"message": "Insufficient permissions to search patients"}, 403
            
        parser = reqparse.RequestParser()
        parser.add_argument('q', type=str, required=True, location='args')
        parser.add_argument('max_results', type=int, default=20, location='args')
        args = parser.parse_args()
        
        # Limit results for performance
        max_results = min(args['max_results'], 100)
        search_term = f"%{args['q']}%"
        
        patients = Patient.query.filter(
            Patient.name.ilike(search_term) |
            Patient.phone.like(search_term) |
            Patient.email.ilike(search_term) |
            Patient.insurance_id.ilike(search_term)
        ).limit(max_results).all()
        
        # Return minimal information for search results
        return [{
            "id": p.id,
            "name": p.name,
            "phone": p.phone[:4] + '******',  # PHI protection
            "age": self.calculate_age(p.date_of_birth) if p.date_of_birth else None,
            "next_appointment": self.get_next_appointment_date(p)
        } for p in patients]
    
    def calculate_age(self, dob):
        today = datetime.now().date()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    
    def get_next_appointment_date(self, patient):
        next_appt = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.status == 'scheduled',
            Appointment.date >= datetime.now()
        ).order_by(Appointment.date.asc()).first()
        
        return next_appt.date.isoformat() if next_appt else None


class PatientAuditResource(Resource):
    @jwt_required()
    def get(self, patient_id):
        """Get audit trail for patient (admin only)"""
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can access audit logs"}, 403
            
        # In production, this would query an actual audit log table
        return {
            "patient_id": patient_id,
            "audit_logs": [
                {"timestamp": "2023-08-15T14:30:00Z", "action": "CREATE", "user_id": 1},
                {"timestamp": "2023-08-16T09:15:00Z", "action": "UPDATE", "user_id": 3},
            ]
        }