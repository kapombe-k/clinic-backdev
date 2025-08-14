from flask_restful import Resource, request
from flask_jwt_extended import jwt_required, get_jwt
from models import db, Billing, Treatment, Patient, Visit, Doctor, User
from sqlalchemy import func, and_, case
from datetime import datetime, timedelta

class AnalyticsResource(Resource):
    @jwt_required()
    def get(self, report_type):
        claims = get_jwt()
        if claims['role'] != 'admin':
            return {"message": "Admin access required"}, 403
            
        if report_type == 'revenue':
            return self.revenue_report()
        elif report_type == 'doctor-performance':
            return self.doctor_performance()
        elif report_type == 'patient-stats':
            return self.patient_stats()
        else:
            return {"message": "Invalid report type"}, 400

    def revenue_report(self):
        # Get date range (default: current month)
        start_date = request.args.get('start_date', datetime.now().replace(day=1).date().isoformat())
        end_date = request.args.get('end_date', datetime.now().date().isoformat())
        
        # Query revenue data grouped by day
        revenue_data = db.session.query(
            func.date(Billing.date).label('date'),
            func.sum(Billing.amount).label('total_billed'),
            func.sum(Billing.paid_amount).label('total_collected')
        ).filter(
            and_(
                Billing.date >= start_date,
                Billing.date <= end_date
            )
        ).group_by('date').order_by('date').all()
        
        # Format response
        return {
            "start_date": start_date,
            "end_date": end_date,
            "data": [{
                "date": row.date.isoformat(),
                "billed": float(row.total_billed) if row.total_billed else 0,
                "collected": float(row.total_collected) if row.total_collected else 0
            } for row in revenue_data]
        }

    def doctor_performance(self):
        # Date range (default: last 30 days)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        # Get performance metrics
        performance = db.session.query(
            Doctor.id,
            User.name.label('doctor_name'),
            func.count(Visit.id).label('visit_count'),
            func.avg(Visit.duration).label('avg_duration'),
            func.sum(Treatment.cost).label('total_revenue')
        ).join(Visit, Visit.doctor_id == Doctor.id)\
         .join(User, Doctor.user_id == User.id)\
         .join(Treatment, Treatment.visit_id == Visit.id)\
         .filter(Visit.date.between(start_date, end_date))\
         .group_by(Doctor.id, User.name)\
         .order_by(func.sum(Treatment.cost).desc())\
         .all()
        
        return [{
            "doctor_id": row.id,
            "doctor_name": row.doctor_name,
            "visit_count": row.visit_count,
            "avg_duration": float(row.avg_duration) if row.avg_duration else 0,
            "total_revenue": float(row.total_revenue) if row.total_revenue else 0
        } for row in performance]

    def patient_stats(self):
        # Gender distribution
        gender_stats = db.session.query(
            Patient.gender,
            func.count(Patient.id)
        ).group_by(Patient.gender).all()
        
        # Age groups
        age_query = db.session.query(
            (func.extract('year', func.current_date()) - func.extract('year', Patient.date_of_birth)).label('age'),
            func.count(Patient.id)
        ).group_by('age').subquery()
        
        age_groups = db.session.query(
            case(
                [(age_query.c.age < 18, '0-17')],
                [(and_(age_query.c.age >= 18, age_query.c.age < 30), '18-29')],
                [(and_(age_query.c.age >= 30, age_query.c.age < 50), '30-49')],
                [(and_(age_query.c.age >= 50, age_query.c.age < 70), '50-69')],
                else_='70+'
            ).label('age_group'),
            func.sum(age_query.c.count)
        ).group_by('age_group').all()
        
        # New patients (last 30 days)
        new_patients = Patient.query.filter(
            Patient.created_at >= datetime.now() - timedelta(days=30)
        ).count()
        
        return {
            "gender_distribution": {row[0]: row[1] for row in gender_stats},
            "age_distribution": {row[0]: row[1] for row in age_groups},
            "total_patients": Patient.query.count(),
            "new_patients_last_30": new_patients
        }
    
    