from flask_restful import Resource, request
from flask_jwt_extended import jwt_required, get_jwt
from models import db, Billing, Treatment, Patient, Visit, Doctor, User, Appointment, InventoryItem
from sqlalchemy import func, and_, case, desc
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
        elif report_type == 'dashboard-stats':
            return self.dashboard_stats()
        elif report_type == 'appointments':
            return self.appointment_stats()
        elif report_type == 'recent-activity':
            return self.recent_activity()
        else:
            return {"message": "Invalid report type"}, 400

    def dashboard_stats(self):
        today = datetime.now()
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = start_of_month - timedelta(days=1)
        start_of_last_month = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Patients
        total_patients = Patient.query.count()
        new_patients_this_month = Patient.query.filter(Patient.created_at >= start_of_month).count()
        new_patients_last_month = Patient.query.filter(
            and_(Patient.created_at >= start_of_last_month, Patient.created_at <= last_month_end)
        ).count()

        # 2. Appointments
        total_appointments = Appointment.query.count()
        appointments_this_month = Appointment.query.filter(Appointment.date >= start_of_month).count()
        appointments_last_month = Appointment.query.filter(
            and_(Appointment.date >= start_of_last_month, Appointment.date <= last_month_end)
        ).count()

        # 3. Revenue
        total_revenue = db.session.query(func.sum(Billing.amount)).scalar() or 0
        revenue_this_month = db.session.query(func.sum(Billing.amount)).filter(Billing.date >= start_of_month).scalar() or 0
        revenue_last_month = db.session.query(func.sum(Billing.amount)).filter(
            and_(Billing.date >= start_of_last_month, Billing.date <= last_month_end)
        ).scalar() or 0

        # 4. Other Stats
        # Active treatments: Approximation using scheduled appointments today
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        active_treatments = Appointment.query.filter(
            and_(Appointment.date >= start_of_day, Appointment.status == 'scheduled')
        ).count()
        
        pending_payments = db.session.query(func.sum(Billing.amount)).filter(Billing.is_paid == False).scalar() or 0

        return {
            "totalPatients": total_patients,
            "newPatientsThisMonth": new_patients_this_month,
            "patientsLastMonth": new_patients_last_month,
            "totalAppointments": total_appointments,
            "appointmentsThisMonth": appointments_this_month,
            "appointmentsLastMonth": appointments_last_month,
            "totalRevenue": float(total_revenue),
            "revenueThisMonth": float(revenue_this_month),
            "revenueLastMonth": float(revenue_last_month),
            "activeTreatments": active_treatments,
            "pendingPayments": float(pending_payments)
        }

    def revenue_report(self):
        # Get parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        group_by = request.args.get('group_by', 'daily') # 'daily', 'monthly', 'yearly'
        
        # Defaults
        if not start_date_str:
             # Default to current year if monthly, else current month
            if group_by == 'monthly':
                start_date = datetime.now().replace(month=1, day=1)
            else:
                start_date = datetime.now().replace(day=1)
        else:
            start_date = datetime.fromisoformat(start_date_str)
            
        if not end_date_str:
            end_date = datetime.now()
        else:
            end_date = datetime.fromisoformat(end_date_str)

        # Date truncation based on grouping
        if group_by == 'monthly':
            date_trunc = func.date_trunc('month', Billing.date) # Postgres specific, might need sqlite adjustment
            # For SQLite, we might need strftime
            if 'sqlite' in str(db.engine.url):
                date_trunc = func.strftime('%Y-%m', Billing.date)
            else:
                date_trunc = func.to_char(Billing.date, 'YYYY-MM') # Standard SQL often uses something else, sticking to common
        elif group_by == 'yearly':
            if 'sqlite' in str(db.engine.url):
                date_trunc = func.strftime('%Y', Billing.date)
            else:
                date_trunc = func.to_char(Billing.date, 'YYYY')
        else: # daily
             if 'sqlite' in str(db.engine.url):
                date_trunc = func.date(Billing.date)
             else:
                date_trunc = func.date(Billing.date)

        # Query revenue data grouped
        revenue_data = db.session.query(
            date_trunc.label('period'),
            func.sum(Billing.amount).label('total_billed'),
            func.sum(Billing.paid_amount if hasattr(Billing, 'paid_amount') else Billing.amount).label('total_collected') # Fallback if paid_amount missing
        ).filter(
            and_(
                Billing.date >= start_date,
                Billing.date <= end_date
            )
        ).group_by('period').order_by('period').all()
        
        # Build target map (simplified targets)
        targets = {}
        # Example logic: target is 1000 * days in period
        
        # Format response
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "group_by": group_by,
            "data": [{
                "period": row.period,
                "revenue": float(row.total_billed) if row.total_billed else 0,
                # Simple target generation for demo
                "target": float(row.total_billed) * 0.9 if row.total_billed else 0
            } for row in revenue_data]
        }

    def appointment_stats(self):
        # Default to last 7 days for daily view
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        if 'start_date' in request.args:
            start_date = datetime.fromisoformat(request.args.get('start_date'))
        if 'end_date' in request.args:
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        # Group by date and status
        if 'sqlite' in str(db.engine.url):
            date_grp = func.date(Appointment.date)
        else:
            date_grp = func.date(Appointment.date)

        stats = db.session.query(
            date_grp.label('date'),
            Appointment.status,
            func.count(Appointment.id).label('count')
        ).filter(
            Appointment.date.between(start_date, end_date)
        ).group_by('date', Appointment.status).all()

        # Transform data for frontend chart
        # We need: [{day: 'Mon', total: 10, scheduled: 5, ...}, ...]
        
        # Initialize map
        date_map = {}
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            day_name = current.strftime('%a')
            date_map[date_str] = {
                'day': day_name,
                'date': date_str,
                'total': 0,
                'scheduled': 0,
                'completed': 0,
                'cancelled': 0,
                'noShow': 0 # Frontend expects 'noShow'
            }
            current += timedelta(days=1)
            
        for row in stats:
            d_str = row.date
            if d_str in date_map:
                count = row.count
                status = row.status
                date_map[d_str]['total'] += count
                # Backend status: 'scheduled', 'completed', 'cancelled', 'no_show'
                # Frontend keys: 'scheduled', 'completed', 'cancelled', 'noShow'
                if status == 'no_show':
                    date_map[d_str]['noShow'] += count
                else:
                    date_map[d_str][status] += count

        return list(date_map.values())

    def recent_activity(self):
        activities = []
        
        # 1. Recent Appointments
        recent_appts = db.session.query(Appointment, Patient.name.label('patient_name'), Doctor.id.label('doc_id'), User.name.label('doc_name'))\
            .join(Patient, Appointment.patient_id == Patient.id)\
            .join(Doctor, Appointment.doctor_id == Doctor.id)\
            .join(User, Doctor.user_id == User.id)\
            .order_by(desc(Appointment.created_at))\
            .limit(5).all()
            
        for appt, p_name, d_id, d_name in recent_appts:
            activities.append({
                "id": f"appt_{appt.id}",
                "type": "appointment",
                "action": appt.status if appt.status != 'scheduled' else 'scheduled',
                "description": f"Appointment {appt.status} for {p_name}",
                "timestamp": appt.created_at.isoformat(),
                "user": d_name, # Approximation
                "details": {
                    "patientName": p_name,
                    "date": appt.date.strftime('%Y-%m-%d'),
                    "time": appt.date.strftime('%H:%M')
                }
            })
            
        # 2. Recent Patients
        recent_patients = Patient.query.order_by(desc(Patient.created_at)).limit(5).all()
        for patient in recent_patients:
            activities.append({
                "id": f"pat_{patient.id}",
                "type": "patient",
                "action": "registered",
                "description": f"New patient registered: {patient.name}",
                "timestamp": patient.created_at.isoformat(),
                "user": "Reception", # Placeholder
                "details": {
                    "patientName": patient.name,
                    "phone": patient.phone
                }
            })
            
        # 3. Recent Billings (Payments)
        # Assuming Billing has created_at
        if hasattr(Billing, 'created_at'):
            recent_bills = db.session.query(Billing, Patient.name.label('patient_name'))\
                .join(Account, Billing.account_id == Account.id)\
                .join(Patient, Account.patient_id == Patient.id)\
                .order_by(desc(Billing.date))\
                .limit(5).all() # Using date as proxy for created_at if needed
                
            for bill, p_name in recent_bills:
                if bill.is_paid:
                    activities.append({
                        "id": f"bill_{bill.id}",
                        "type": "payment",
                        "action": "received",
                        "description": f"Payment received from {p_name}",
                        "timestamp": bill.date.isoformat(),
                        "user": "Billing",
                        "details": {
                            "patientName": p_name,
                            "amount": float(bill.amount),
                            "method": bill.payment_method
                        }
                    })

        # Sort combined list by timestamp desc
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return activities[:10] # Return top 10

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

        # Growth history (last 12 months)
        # Using simplified approach: counting per month
        growth_history = []
        today = datetime.now()
        for i in range(11, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=i*30)).replace(day=1) # Approx
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            
            count = Patient.query.filter(
                and_(Patient.created_at >= month_start, Patient.created_at < next_month)
            ).count()
            
            total_until = Patient.query.filter(Patient.created_at < next_month).count()
            
            growth_history.append({
                "month": month_start.strftime("%b"),
                "newPatients": count,
                "totalPatients": total_until
            })
        
        return {
            "gender_distribution": {row[0]: row[1] for row in gender_stats},
            "age_distribution": {row[0]: row[1] for row in age_groups},
            "total_patients": Patient.query.count(),
            "new_patients_last_30": new_patients,
            "growth_history": growth_history,
             # Return as list for frontend
            "demographics": [{ "category": row[0], "count": row[1], "percentage": 0 } for row in age_groups] # Calc percent in frontend
        }
    
    