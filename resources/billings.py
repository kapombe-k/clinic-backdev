from flask_restful import Resource, reqparse
from flask import current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Billing, Treatment, Account, Visit, Patient, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach

class BillingResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('treatment_id', type=int, required=True)
    parser.add_argument('payment_method', type=str, default='cash')
    parser.add_argument('insurance_claim_id', type=str)
    parser.add_argument('amount_paid', type=float, default=0.0)

    @jwt_required()
    def post(self):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        data = self.parser.parse_args()
        
        # Validate treatment
        treatment = Treatment.query.options(
            joinedload(Treatment.visit).joinedload(Visit.patient).joinedload(Patient.account)
        ).get(data['treatment_id'])
        
        if not treatment:
            return {"message": "Treatment not found"}, 404
            
        # Get or create account
        account = treatment.visit.patient.account
        if not account:
            account = Account(patient=treatment.visit.patient, balance=0.0)
            db.session.add(account)
        
        # Create billing
        billing = Billing(
            treatment=treatment,
            account=account,
            amount=treatment.cost,
            payment_method=bleach.clean(data['payment_method']),
            insurance_claim_id=bleach.clean(data['insurance_claim_id']) if data.get('insurance_claim_id') else None,
            date=datetime.now()
        )
        
        # Process payment
        amount_paid = data['amount_paid']
        if amount_paid > 0:
            billing.paid_amount = amount_paid
            billing.is_paid = (amount_paid >= treatment.cost)
            account.balance = account.balance + treatment.cost - amount_paid
            if amount_paid > 0:
                account.last_payment_date = datetime.now()
        
        try:
            db.session.add(billing)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="BILLING_CREATE",
                target_id=billing.id,
                target_type='billing',
                details=f"Billed ${treatment.cost} for treatment {treatment.id}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.billing_to_dict(billing), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Billing creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def get(self, billing_id):
        claims = get_jwt()
        billing = Billing.query.options(
            joinedload(Billing.treatment).joinedload(Treatment.visit).joinedload(Visit.patient),
            joinedload(Billing.account)
        ).get(billing_id)
        
        if not billing:
            return {"message": "Billing record not found"}, 404
            
        # Authorization
        if claims['role'] == 'patient' and billing.treatment.visit.patient.user_id != get_jwt_identity():
            return {"message": "Unauthorized"}, 403
        if claims['role'] not in ['receptionist', 'admin']:
            return {"message": "Insufficient permissions"}, 403
            
        return self.billing_to_dict(billing)

    def billing_to_dict(self, billing):
        return {
            "id": billing.id,
            "amount": billing.amount,
            "paid_amount": billing.paid_amount,
            "is_paid": billing.is_paid,
            "payment_method": billing.payment_method,
            "insurance_claim_id": billing.insurance_claim_id,
            "date": billing.date.isoformat(),
            "patient": {
                "id": billing.treatment.visit.patient.id,
                "name": billing.treatment.visit.patient.name
            },
            "treatment": {
                "id": billing.treatment.id,
                "name": billing.treatment.name,
                "cost": billing.treatment.cost
            },
            "account_balance": billing.account.balance
        }