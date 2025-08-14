from flask_restful import Resource, reqparse, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt_claims
from models import db, Visit, Patient, Doctor, Treatment, Billing, Appointment, InventoryUsage, InventoryItem
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime


class VisitResource(Resource):
    # Parser for POST/PATCH requests
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True, help="Patient ID is required")
    parser.add_argument('doctor_id', type=int, required=True, help="Doctor ID is required")
    parser.add_argument('appointment_id', type=int, help="Appointment ID if exists")
    parser.add_argument('date', type=str, help="Visit date (YYYY-MM-DD HH:MM)")
    parser.add_argument('visit_type', type=str, choices=['consultation', 'review', 'procedure', 'emergency'], 
                        help="Visit type: consultation, review, procedure, emergency")
    parser.add_argument('notes', type=str, help="Clinical notes")
    parser.add_argument('duration', type=int, help="Duration in minutes")
    parser.add_argument('treatments', type=list, location='json', 
                        help="List of treatments with names and costs")
    
    # Helper method to validate and parse datetime
    def parse_datetime(self, date_str):
        if not date_str:
            return datetime.now()
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M')
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except:
                raise ValueError("Invalid date format. Use YYYY-MM-DD or YYYY-MM-DD HH:MM")

    # GET single visit with detailed information
    @jwt_required()
    def get(self, visit_id=None):
        current_user_id = get_jwt_identity()
        claims = get_jwt_claims()
        
        if visit_id:
            visit = Visit.query.get(visit_id)
            if not visit:
                return {"message": "Visit not found"}, 404
            
            # Authorization check
            if claims['role'] == 'patient' and visit.patient.user_id != current_user_id:
                return {"message": "Unauthorized access to visit"}, 403
                
            if claims['role'] == 'doctor' and visit.doctor.user_id != current_user_id:
                return {"message": "Unauthorized access to visit"}, 403
                
            return self.visit_to_dict(visit)
        
        # List visits with filters based on role
        query = Visit.query
        
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
            
        # Date range filter
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Visit.date >= start_date)
            except ValueError:
                pass
                
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                query = query.filter(Visit.date <= end_date)
            except ValueError:
                pass
        
        visits = query.order_by(Visit.date.desc()).limit(50).all()
        return [self.visit_to_dict(v) for v in visits]

    # Create new visit
    @jwt_required()
    def post(self):
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'receptionist', 'admin']:
            return {"message": "Insufficient permissions to create visits"}, 403
            
        data = VisitResource.parser.parse_args()
        
        # Parse and validate date
        try:
            data['date'] = self.parse_datetime(data.get('date'))
        except ValueError as e:
            return {"message": str(e)}, 400
            
        # Validate patient and doctor exist
        patient = Patient.query.get(data['patient_id'])
        if not patient:
            return {"message": "Patient not found"}, 400
            
        doctor = Doctor.query.get(data['doctor_id'])
        if not doctor or not doctor.is_active:
            return {"message": "Doctor not found or inactive"}, 400
            
        # Check appointment if provided
        appointment = None
        if data.get('appointment_id'):
            appointment = Appointment.query.get(data['appointment_id'])
            if not appointment or appointment.patient_id != patient.id or appointment.doctor_id != doctor.id:
                return {"message": "Invalid appointment"}, 400
            if appointment.status != 'scheduled':
                return {"message": "Appointment is not in scheduled status"}, 400
        
        # Create visit
        visit = Visit(
            date=data['date'],
            visit_type=data.get('visit_type', 'consultation'),
            notes=data.get('notes'),
            duration=data.get('duration', 30),
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_id=appointment.id if appointment else None
        )
        
        # Handle treatments
        treatments = []
        for t in data.get('treatments', []):
            treatment = Treatment(
                name=t.get('name'),
                description=t.get('description'),
                cost=t.get('cost', 0),
                procedure_code=t.get('procedure_code'),
                doctor_id=doctor.id,
                visit=visit
            )
            treatments.append(treatment)
        
        try:
            db.session.add(visit)
            if appointment:
                appointment.status = 'completed'
                db.session.add(appointment)
            
            for treatment in treatments:
                db.session.add(treatment)
                
            db.session.commit()
            
            # Create billing records
            for treatment in treatments:
                billing = Billing(
                    amount=treatment.cost,
                    treatment=treatment,
                    account=patient.account
                )
                db.session.add(billing)
                patient.account.balance += treatment.cost
                
            db.session.commit()
            
            return self.visit_to_dict(visit), 201
            
        except (SQLAlchemyError, IntegrityError) as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    # Update visit
    @jwt_required()
    def patch(self, visit_id):
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions to update visits"}, 403
            
        visit = Visit.query.get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
            
        # Only the doctor who conducted the visit or admin can update
        if claims['role'] == 'doctor':
            doctor = Doctor.query.filter_by(user_id=get_jwt_identity()).first()
            if not doctor or doctor.id != visit.doctor_id:
                return {"message": "Unauthorized to update this visit"}, 403
            
        data = VisitResource.parser.parse_args()
        
        # Update fields
        if 'date' in data and data['date']:
            try:
                visit.date = self.parse_datetime(data['date'])
            except ValueError as e:
                return {"message": str(e)}, 400
                
        if 'visit_type' in data:
            visit.visit_type = data['visit_type']
            
        if 'notes' in data:
            visit.notes = data['notes']
            
        if 'duration' in data:
            visit.duration = data['duration']
            
        # Update appointment if changed
        if 'appointment_id' in data:
            # Implementation similar to POST
            pass
            
        try:
            db.session.commit()
            return self.visit_to_dict(visit)
        except (SQLAlchemyError, IntegrityError) as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    # Delete visit
    @jwt_required()
    def delete(self, visit_id):
        claims = get_jwt_claims()
        if claims['role'] != 'admin':
            return {"message": "Only admins can delete visits"}, 403
            
        visit = Visit.query.get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
            
        try:
            # First delete dependent objects
            for treatment in visit.treatments:
                # Delete billing and inventory usage
                if treatment.billing:
                    treatment.billing.account.balance -= treatment.billing.amount
                    db.session.delete(treatment.billing)
                
                for usage in treatment.inventory_usage:
                    # Return inventory items to stock
                    usage.item.quantity += usage.quantity_used
                    db.session.delete(usage)
                
                db.session.delete(treatment)
            
            # Reset appointment status if exists
            if visit.appointment:
                visit.appointment.status = 'scheduled'
                db.session.add(visit.appointment)
            
            db.session.delete(visit)
            db.session.commit()
            return {"message": "Visit and associated records deleted"}
        except (SQLAlchemyError, IntegrityError) as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500

    # Convert visit to dictionary with all related data
    def visit_to_dict(self, visit):
        return {
            "id": visit.id,
            "date": visit.date.isoformat(),
            "visit_type": visit.visit_type,
            "duration": visit.duration,
            "notes": visit.notes,
            "patient": {
                "id": visit.patient.id,
                "name": visit.patient.name,
                "phone": visit.patient.phone
            },
            "doctor": {
                "id": visit.doctor.id,
                "name": visit.doctor.user.name,
                "specialty": visit.doctor.specialty
            },
            "appointment": {
                "id": visit.appointment.id,
                "reason": visit.appointment.reason
            } if visit.appointment else None,
            "treatments": [{
                "id": t.id,
                "name": t.name,
                "cost": t.cost,
                "procedure_code": t.procedure_code,
                "billing": {
                    "id": t.billing.id,
                    "amount": t.billing.amount,
                    "is_paid": t.billing.is_paid
                } if t.billing else None,
                "inventory_used": [{
                    "item_id": u.item_id,
                    "item_name": u.item.name,
                    "quantity_used": u.quantity_used
                } for u in t.inventory_usage]
            } for t in visit.treatments]
        }


class VisitTreatmentResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True)
    parser.add_argument('cost', type=float, required=True)
    parser.add_argument('procedure_code', type=str)
    parser.add_argument('description', type=str)
    parser.add_argument('inventory_items', type=list, location='json',
                        help="List of inventory items used: [{'item_id': 1, 'quantity': 2}]")

    @jwt_required()
    def post(self, visit_id):
        claims = get_jwt_claims()
        if claims['role'] not in ['doctor', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        visit = Visit.query.get(visit_id)
        if not visit:
            return {"message": "Visit not found"}, 404
            
        # Only the visit doctor or admin can add treatments
        if claims['role'] == 'doctor':
            doctor = Doctor.query.filter_by(user_id=get_jwt_identity()).first()
            if not doctor or doctor.id != visit.doctor_id:
                return {"message": "Unauthorized to add treatments to this visit"}, 403
        
        data = VisitTreatmentResource.parser.parse_args()
        
        # Create treatment
        treatment = Treatment(
            name=data['name'],
            cost=data['cost'],
            procedure_code=data.get('procedure_code'),
            description=data.get('description'),
            visit=visit,
            doctor=visit.doctor
        )
        
        inventory_usages = []
        for item_data in data.get('inventory_items', []):
            item = InventoryItem.query.get(item_data.get('item_id'))
            if not item:
                return {"message": f"Inventory item {item_data.get('item_id')} not found"}, 400
                
            if item.quantity < item_data.get('quantity', 0):
                return {"message": f"Insufficient stock for {item.name}"}, 400
                
            item.quantity -= item_data.get('quantity')
            inventory_usage = InventoryUsage(
                quantity_used=item_data.get('quantity'),
                item=item,
                treatment=treatment
            )
            inventory_usages.append(inventory_usage)
        
        try:
            db.session.add(treatment)
            for usage in inventory_usages:
                db.session.add(usage)
                
            # Create billing record
            billing = Billing(
                amount=data['cost'],
                treatment=treatment,
                account=visit.patient.account
            )
            db.session.add(billing)
            
            # Update patient balance
            visit.patient.account.balance += data['cost']
            
            db.session.commit()
            return {
                "message": "Treatment added",
                "treatment": {
                    "id": treatment.id,
                    "name": treatment.name,
                    "cost": treatment.cost,
                    "billing_id": billing.id
                }
            }, 201
            
        except (SQLAlchemyError, IntegrityError) as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500


class VisitInventoryResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('item_id', type=int, required=True)
    parser.add_argument('quantity', type=int, required=True)

    @jwt_required()
    def post(self, visit_id, treatment_id):
        claims = get_jwt_claims()
        if claims['role'] not in ['technician', 'doctor', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        treatment = Treatment.query.get(treatment_id)
        if not treatment or treatment.visit_id != visit_id:
            return {"message": "Treatment not found"}, 404
            
        data = VisitInventoryResource.parser.parse_args()
        item = InventoryItem.query.get(data['item_id'])
        if not item:
            return {"message": "Inventory item not found"}, 404
            
        if item.quantity < data['quantity']:
            return {"message": f"Insufficient stock for {item.name}"}, 400
            
        # Create inventory usage record
        inventory_usage = InventoryUsage(
            quantity_used=data['quantity'],
            item=item,
            treatment=treatment
        )
        
        # Update stock
        item.quantity -= data['quantity']
        
        try:
            db.session.add(inventory_usage)
            db.session.commit()
            return {
                "message": "Inventory usage recorded",
                "inventory_usage": {
                    "id": inventory_usage.id,
                    "item_name": item.name,
                    "quantity_used": data['quantity'],
                    "remaining_stock": item.quantity
                }
            }, 201
            
        except (SQLAlchemyError, IntegrityError) as e:
            db.session.rollback()
            return {"message": f"Database error: {str(e)}"}, 500