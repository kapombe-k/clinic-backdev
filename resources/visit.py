from flask_restful import Resource, reqparse
from flask import request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, get_jwt_claims
from models import db, Visit, Patient, Doctor, Appointment, Treatment, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach

class VisitResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True)
    parser.add_argument('doctor_id', type=int, required=True)
    parser.add_argument('appointment_id', type=int)
    parser.add_argument('visit_type', type=str, required=True)
    parser.add_argument('notes', type=str)
    parser.add_argument('duration', type=int, required=True)
    parser.add_argument('treatments', type=list, location='json')

    @jwt_required()
    def get(self, visit_id=None):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        
        if visit_id:
            visit = Visit.query.options(
                joinedload(Visit.patient),
                joinedload(Visit.doctor).joinedload(Doctor.user),
                joinedload(Visit.treatments)
            ).get(visit_id)
            
            if not visit:
                return {"message": "Visit not found"}, 404
                
            # Authorization
            if claims['role'] == 'patient' and visit.patient.user_id != current_user_id:
                return {"message": "Unauthorized"}, 403
            if claims['role'] == 'doctor' and visit.doctor.user_id != current_user_id:
                return {"message": "Unauthorized"}, 403
                
            return self.visit_to_dict(visit)
        
        # List visits with role-based filtering
        query = Visit.query.options(
            joinedload(Visit.patient),
            joinedload(Visit.doctor).joinedload(Doctor.user)
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
            query = query.filter(Visit.date >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(Visit.date <= datetime.fromisoformat(end_date))
            
        visits = query.order_by(Visit.date.desc()).limit(100).all()
        return [self.visit_to_dict(v) for v in visits]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        allowed_roles = ['doctor', 'receptionist', 'admin']
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
            
        # Validate appointment if provided
        appointment = None
        if data.get('appointment_id'):
            appointment = Appointment.query.get(data['appointment_id'])
            if not appointment:
                return {"message": "Appointment not found"}, 404
            if appointment.patient_id != data['patient_id']:
                return {"message": "Appointment patient mismatch"}, 400
            if appointment.doctor_id != data['doctor_id']:
                return {"message": "Appointment doctor mismatch"}, 400
                
        # Create visit
        visit = Visit(
            patient_id=data['patient_id'],
            doctor_id=data['doctor_id'],
            appointment_id=data.get('appointment_id'),
            visit_type=bleach.clean(data['visit_type']),
            notes=bleach.clean(data['notes']) if data.get('notes') else None,
            duration=data['duration'],
            date=datetime.now()
        )
        
        # Create treatments
        treatments = []
        for treatment_data in data.get('treatments', []):
            treatment = Treatment(
                name=bleach.clean(treatment_data['name']),
                description=bleach.clean(treatment_data.get('description', '')),
                cost=treatment_data.get('cost', 0),
                procedure_code=treatment_data.get('procedure_code'),
                visit=visit,
                doctor_id=data['doctor_id']
            )
            treatments.append(treatment)
        
        try:
            db.session.add(visit)
            for treatment in treatments:
                db.session.add(treatment)
                
            # Update appointment status if linked
            if appointment:
                appointment.status = 'completed'
                db.session.add(appointment)
                
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="VISIT_CREATE",
                target_id=visit.id,
                target_type='visit',
                details=f"Created visit with {len(treatments)} treatments"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.visit_to_dict(visit), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Visit creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, visit_id):
        claims = get_jwt()
        allowed_roles = ['doctor', 'admin']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        visit = Visit.query.options(
            joinedload(Visit.treatments)
        ).get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
            
        data = self.parser.parse_args()
        changes = []
        
        # Update fields
        if 'notes' in data and data['notes'] is not None:
            visit.notes = bleach.clean(data['notes'])
            changes.append('notes')
        if 'duration' in data and data['duration']:
            visit.duration = data['duration']
            changes.append('duration')
            
        # Add new treatments
        new_treatments = []
        for treatment_data in data.get('treatments', []):
            treatment = Treatment(
                name=bleach.clean(treatment_data['name']),
                description=bleach.clean(treatment_data.get('description', '')),
                cost=treatment_data.get('cost', 0),
                procedure_code=treatment_data.get('procedure_code'),
                visit=visit,
                doctor_id=visit.doctor_id
            )
            new_treatments.append(treatment)
            changes.append('treatment_added')
        
        if not changes and not new_treatments:
            return {"message": "No changes detected"}, 400
            
        try:
            for treatment in new_treatments:
                db.session.add(treatment)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="VISIT_UPDATE",
                target_id=visit_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.visit_to_dict(visit)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Visit update failed: {str(e)}")
            return {"message": "Database error"}, 500

    def visit_to_dict(self, visit):
        return {
            "id": visit.id,
            "date": visit.date.isoformat(),
            "patient": {
                "id": visit.patient.id,
                "name": visit.patient.name
            },
            "doctor": {
                "id": visit.doctor.id,
                "name": visit.doctor.user.name,
                "specialty": visit.doctor.specialty
            },
            "visit_type": visit.visit_type,
            "duration": visit.duration,
            "notes": visit.notes,
            "treatments": [{
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "cost": t.cost,
                "procedure_code": t.procedure_code
            } for t in visit.treatments]
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