from flask_restful import Resource, reqparse
from flask import current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Treatment, Visit, Doctor, InventoryUsage, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
import bleach

class TreatmentResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('visit_id', type=int, required=True)
    parser.add_argument('name', type=str, required=True)
    parser.add_argument('description', type=str)
    parser.add_argument('cost', type=float, required=True)
    parser.add_argument('procedure_code', type=str)
    parser.add_argument('inventory_items', type=list, location='json')

    @jwt_required()
    def post(self):
        claims = get_jwt()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.parser.parse_args()
        
        # Validate visit
        visit = Visit.query.get(data['visit_id'])
        if not visit:
            return {"message": "Visit not found"}, 404
            
        # Create treatment
        treatment = Treatment(
            visit_id=data['visit_id'],
            doctor_id=visit.doctor_id,
            name=bleach.clean(data['name']),
            description=bleach.clean(data['description']) if data.get('description') else None,
            cost=data['cost'],
            procedure_code=data.get('procedure_code')
        )
        
        # Create inventory usages
        inventory_usages = []
        for item_data in data.get('inventory_items', []):
            usage = InventoryUsage(
                treatment=treatment,
                item_id=item_data['item_id'],
                quantity_used=item_data['quantity']
            )
            inventory_usages.append(usage)
        
        try:
            db.session.add(treatment)
            for usage in inventory_usages:
                db.session.add(usage)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="TREATMENT_CREATE",
                target_id=treatment.id,
                target_type='treatment',
                details=f"Created treatment: {treatment.name}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.treatment_to_dict(treatment), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Treatment creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def get(self, treatment_id):
        claims = get_jwt()
        treatment = Treatment.query.options(
            joinedload(Treatment.visit).joinedload(Visit.patient),
            joinedload(Treatment.doctor).joinedload(Doctor.user),
            joinedload(Treatment.inventory_usage).joinedload(InventoryUsage.item)
        ).get(treatment_id)
        
        if not treatment:
            return {"message": "Treatment not found"}, 404
            
        # Authorization
        if claims['role'] == 'patient' and treatment.visit.patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized"}, 403
        if claims['role'] == 'doctor' and treatment.doctor.user_id != get_jwt_identity():
            return {"message": "Unauthorized"}, 403
            
        return self.treatment_to_dict(treatment)

    def treatment_to_dict(self, treatment):
        return {
            "id": treatment.id,
            "name": treatment.name,
            "description": treatment.description,
            "cost": treatment.cost,
            "procedure_code": treatment.procedure_code,
            "visit_id": treatment.visit_id,
            "doctor": {
                "id": treatment.doctor.id,
                "name": treatment.doctor.user.name
            },
            "inventory_used": [{
                "item_id": u.item_id,
                "item_name": u.item.name,
                "quantity": u.quantity_used
            } for u in treatment.inventory_usage]
        }