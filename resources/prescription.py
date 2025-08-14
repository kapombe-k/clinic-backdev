from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Prescription, Visit, Doctor, Patient
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

class PrescriptionResource(Resource):
    # Reqparse configuration for input validation
    post_parser = reqparse.RequestParser()
    post_parser.add_argument('visit_id', type=int, required=True, 
                             help="Visit ID is required")
    post_parser.add_argument('details', type=str, required=True, 
                             help="Prescription details are required")
    post_parser.add_argument('medications', type=list, location='json',
                             help="List of medications: [{'name': '...', 'dosage': '...'}]")
    
    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('details', type=str, 
                              help="Updated prescription details")
    patch_parser.add_argument('medications', type=list, location='json',
                              help="Updated list of medications")

    # Helper method to validate ownership
    def validate_prescription_access(self, prescription, user_id, role):
        """Check if user has permission to access this prescription"""
        # Admin has full access
        if role == 'admin':
            return True
            
        # Doctor can access their own prescriptions
        if role == 'doctor':
            # Check if doctor exists and matches visit's doctor
            return prescription.visit.doctor.user_id == user_id
            
        # Patient can access their own prescriptions
        if role == 'patient':
            # Check if patient exists and matches visit's patient
            return prescription.visit.patient.user_id == user_id
            
        # Receptionist can access all prescriptions
        return role == 'receptionist'

    @jwt_required()
    def get(self, prescription_id):
        """Get prescription details with authorization check"""
        # Eager load relationships to avoid N+1 queries
        prescription = Prescription.query.options(
            joinedload(Prescription.visit).joinedload(Visit.doctor),
            joinedload(Prescription.visit).joinedload(Visit.patient)
        ).get(prescription_id)
        
        if not prescription:
            return {"message": "Prescription not found"}, 404
            
        # Check access permissions
        current_user_id = get_jwt_identity()
        claims = get_jwt_claims()
        if not self.validate_prescription_access(prescription, current_user_id, claims['role']):
            return {"message": "Unauthorized access to prescription"}, 403
            
        return self.prescription_to_dict(prescription)

    @jwt_required()
    def post(self):
        """Create new prescription (doctors and admins only)"""
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions to create prescriptions"}, 403
            
        data = self.post_parser.parse_args()
        
        # Validate visit exists with relationships loaded
        visit = Visit.query.options(
            joinedload(Visit.doctor),
            joinedload(Visit.patient)
        ).get(data['visit_id'])
        
        if not visit:
            return {"message": "Visit not found"}, 400
            
        # Check doctor ownership if not admin
        if claims['role'] == 'doctor':
            current_user_id = get_jwt_identity()
            if visit.doctor.user_id != current_user_id:
                return {"message": "Unauthorized to create prescription for this visit"}, 403

        try:
            # Create prescription
            prescription = Prescription(
                visit_id=visit.id,
                details=data['details'],
                medications=data.get('medications', [])
            )
            
            db.session.add(prescription)
            db.session.commit()
            
            # Reload with relationships for response
            db.session.refresh(prescription)
            prescription = Prescription.query.options(
                joinedload(Prescription.visit).joinedload(Visit.doctor),
                joinedload(Prescription.visit).joinedload(Visit.patient)
            ).get(prescription.id)
            
            return self.prescription_to_dict(prescription), 201
            
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def patch(self, prescription_id):
        """Update prescription (doctors and admins only)"""
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions to update prescriptions"}, 403
            
        # Eager load relationships for access validation
        prescription = Prescription.query.options(
            joinedload(Prescription.visit).joinedload(Visit.doctor),
            joinedload(Prescription.visit).joinedload(Visit.patient)
        ).get(prescription_id)
        
        if not prescription:
            return {"message": "Prescription not found"}, 404
            
        # Check ownership if not admin
        if claims['role'] == 'doctor':
            current_user_id = get_jwt_identity()
            if prescription.visit.doctor.user_id != current_user_id:
                return {"message": "Unauthorized to update this prescription"}, 403

        data = self.patch_parser.parse_args()
        
        # Update fields
        if 'details' in data and data['details'] is not None:
            prescription.details = data['details']
            
        if 'medications' in data and data['medications'] is not None:
            prescription.medications = data['medications']

        try:
            db.session.commit()
            # Reload to get updated relationships
            db.session.refresh(prescription)
            return self.prescription_to_dict(prescription)
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    @jwt_required()
    def delete(self, prescription_id):
        """Delete prescription (admins only)"""
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can delete prescriptions"}, 403
            
        prescription = Prescription.query.get(prescription_id)
        if not prescription:
            return {"message": "Prescription not found"}, 404

        try:
            db.session.delete(prescription)
            db.session.commit()
            return {"message": "Prescription deleted"}
        except SQLAlchemyError as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    def prescription_to_dict(self, prescription):
        """Serialize prescription with related visit information"""
        return {
            "id": prescription.id,
            "details": prescription.details,
            "medications": prescription.medications,
            "visit": {
                "id": prescription.visit.id,
                "date": prescription.visit.date.isoformat(),
                "doctor": {
                    "id": prescription.visit.doctor.id,
                    "name": prescription.visit.doctor.user.name
                },
                "patient": {
                    "id": prescription.visit.patient.id,
                    "name": prescription.visit.patient.name
                }
            }
        }