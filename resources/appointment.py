from flask_restful import Resource, reqparse
from flask import request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Appointment, Patient, Doctor, User, AuditLog
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import bleach

class AppointmentResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('patient_id', type=int, required=True)
    parser.add_argument('doctor_id', type=int, required=True)
    parser.add_argument('date', type=str, required=True)
    parser.add_argument('reason', type=str, required=True)
    parser.add_argument('duration', type=int, default=30)
    parser.add_argument('status', type=str, default='scheduled', 
                       choices=['scheduled', 'completed', 'cancelled', 'no_show'])
    
    @jwt_required()
    def get(self, appointment_id=None):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        
        if appointment_id:
            appointment = Appointment.query.options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user)
            ).get(appointment_id)
            
            if not appointment:
                return {"message": "Appointment not found"}, 404
                
            # Authorization
            if claims['role'] not in ['receptionist', 'admin', 'patient', 'doctor']:
                return {"message": "Unauthorized"}, 403
            return self.appointment_to_dict(appointment)
        
        # List appointments with role-based filtering
        query = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
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
            query = query.filter(Appointment.date >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(Appointment.date <= datetime.fromisoformat(end_date))
            
        # Status filtering
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
            
        appointments = query.order_by(Appointment.date).limit(100).all()
        return [self.appointment_to_dict(a) for a in appointments]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin', 'patient', 'doctor']
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
            
        # Parse date
        try:
            appt_date = datetime.fromisoformat(data['date'])
        except (ValueError, TypeError):
            return {"message": "Invalid date format. Use ISO 8601"}, 400
            
        # Check for scheduling conflicts
        existing = Appointment.query.filter(
            Appointment.doctor_id == data['doctor_id'],
            Appointment.date == appt_date,
            Appointment.status != 'cancelled'
        ).first()
        if existing:
            return {"message": "Time slot already booked"}, 409
            
        # Create appointment
        appointment = Appointment(
            patient_id=data['patient_id'],
            doctor_id=data['doctor_id'],
            date=appt_date,
            reason=bleach.clean(data['reason']),
            duration=data['duration'],
            status=data['status'],
            user_id=get_jwt_identity()  # Creator
        )
        
        try:
            db.session.add(appointment)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_CREATE",
                target_id=appointment.id,
                target_type='appointment',
                details=f"Created for {patient.name} with Dr. {doctor.user.name}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.appointment_to_dict(appointment), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, appointment_id):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin', 'doctor']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        data = self.parser.parse_args()
        changes = []
        
        # Update fields
        if 'date' in data and data['date']:
            try:
                new_date = datetime.fromisoformat(data['date'])
                appointment.date = new_date
                changes.append('date')
            except (ValueError, TypeError):
                return {"message": "Invalid date format"}, 400
                
        if 'status' in data and data['status']:
            appointment.status = data['status']
            changes.append('status')
            
        if 'reason' in data and data['reason']:
            appointment.reason = bleach.clean(data['reason'])
            changes.append('reason')
            
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_UPDATE",
                target_id=appointment_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.appointment_to_dict(appointment)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment update failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def delete(self, appointment_id):
        claims = get_jwt()
        allowed_roles = ['receptionist', 'admin', 'doctor', 'patient']
        if claims['role'] not in allowed_roles:
            return {"message": "Insufficient permissions"}, 403
            
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return {"message": "Appointment not found"}, 404
            
        # Soft delete by changing status
        appointment.status = 'cancelled'
        
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="APPOINTMENT_CANCEL",
                target_id=appointment_id,
                details="Appointment cancelled"
            )
            db.session.add(audit)
            db.session.commit()
            
            return {"message": "Appointment cancelled"}
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Appointment cancellation failed: {str(e)}")
            return {"message": "Database error"}, 500

    def appointment_to_dict(self, appointment):
        return {
            "id": appointment.id,
            "patient": {
                "id": appointment.patient.id,
                "name": appointment.patient.name
            },
            "doctor": {
                "id": appointment.doctor.id,
                "name": appointment.doctor.user.name,
                "specialty": appointment.doctor.specialty
            },
            "date": appointment.date.isoformat(),
            "reason": appointment.reason,
            "duration": appointment.duration,
            "status": appointment.status,
            "created_at": appointment.created_at.isoformat()
        }


class AppointmentSearchResource(Resource):
    """Dedicated resource for advanced appointment search functionality"""

    @jwt_required()
    def get(self):
        claims = get_jwt()

        # Authorization - staff and doctors can search appointments
        if claims['role'] not in ['admin', 'receptionist', 'doctor']:
            return {"message": "Insufficient permissions to search appointments"}, 403

        # Parse search parameters
        search_params = self._parse_search_params()

        # Build query with role-based access
        query = self._build_search_query(claims['role'], claims.get('user_id'))

        # Apply search filters
        query = self._apply_search_filters(query, search_params)

        # Apply sorting
        query = self._apply_sorting(query, search_params)

        # Apply pagination
        page = int(search_params.get('page', 1))
        per_page = min(int(search_params.get('per_page', 20)), 100)  # Max 100 per page
        offset = (page - 1) * per_page

        # Get total count for pagination info
        total_count = query.count()

        # Apply pagination and execute
        appointments = query.offset(offset).limit(per_page).all()

        # Format results
        results = [self.appointment_to_dict(a) for a in appointments]

        return {
            "appointments": results,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_count": total_count,
                "total_pages": (total_count + per_page - 1) // per_page
            },
            "search_params": {k: v for k, v in search_params.items() if v is not None}
        }

    def _parse_search_params(self):
        """Parse and validate search parameters from request args"""
        from flask import request

        params = {}

        # Search terms
        params['q'] = request.args.get('q', '').strip()  # General search term
        params['patient_name'] = request.args.get('patient_name', '').strip()
        params['doctor_name'] = request.args.get('doctor_name', '').strip()
        params['reason'] = request.args.get('reason', '').strip()

        # Filters
        params['status'] = request.args.get('status')
        if params['status'] and params['status'] not in ['scheduled', 'completed', 'cancelled', 'no_show']:
            params['status'] = None

        # Date range
        params['start_date'] = request.args.get('start_date', '').strip()
        params['end_date'] = request.args.get('end_date', '').strip()

        # Doctor/Patient IDs
        try:
            params['doctor_id'] = int(request.args.get('doctor_id')) if request.args.get('doctor_id') else None
        except ValueError:
            params['doctor_id'] = None

        try:
            params['patient_id'] = int(request.args.get('patient_id')) if request.args.get('patient_id') else None
        except ValueError:
            params['patient_id'] = None

        # Pagination
        try:
            params['page'] = max(1, int(request.args.get('page', 1)))
        except ValueError:
            params['page'] = 1

        try:
            params['per_page'] = max(1, int(request.args.get('per_page', 20)))
        except ValueError:
            params['per_page'] = 20

        # Sorting
        params['sort_by'] = request.args.get('sort_by', 'date')
        params['sort_order'] = request.args.get('sort_order', 'desc').lower()
        if params['sort_order'] not in ['asc', 'desc']:
            params['sort_order'] = 'desc'

        return params

    def _build_search_query(self, role, user_id):
        """Build base query with role-based access control"""
        query = Appointment.query.options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        )

        # Role-based filtering
        if role == 'doctor':
            # Doctors only see their own appointments
            doctor = Doctor.query.filter_by(user_id=user_id).first()
            if doctor:
                query = query.filter_by(doctor_id=doctor.id)
        # Admin and receptionist can see all appointments

        return query

    def _apply_search_filters(self, query, search_params):
        """Apply search filters to the query"""
        from sqlalchemy import or_, and_

        # General search term (searches across multiple fields)
        if search_params.get('q'):
            search_term = f"%{search_params['q']}%"
            query = query.filter(or_(
                Appointment.reason.ilike(search_term),
                Appointment.patient.has(Patient.name.ilike(search_term)),
                Appointment.doctor.has(Doctor.user.has(User.name.ilike(search_term)))
            ))

        # Specific field searches
        if search_params.get('patient_name'):
            query = query.filter(Appointment.patient.has(Patient.name.ilike(f"%{search_params['patient_name']}%")))

        if search_params.get('doctor_name'):
            query = query.filter(Appointment.doctor.has(Doctor.user.has(User.name.ilike(f"%{search_params['doctor_name']}%"))))

        if search_params.get('reason'):
            query = query.filter(Appointment.reason.ilike(f"%{search_params['reason']}%"))

        # Exact filters
        if search_params.get('status'):
            query = query.filter(Appointment.status == search_params['status'])

        if search_params.get('doctor_id'):
            query = query.filter(Appointment.doctor_id == search_params['doctor_id'])

        if search_params.get('patient_id'):
            query = query.filter(Appointment.patient_id == search_params['patient_id'])

        # Date range filtering
        if search_params.get('start_date'):
            try:
                start_date = datetime.fromisoformat(search_params['start_date'])
                query = query.filter(Appointment.date >= start_date)
            except (ValueError, TypeError):
                pass  # Invalid date, skip filter

        if search_params.get('end_date'):
            try:
                end_date = datetime.fromisoformat(search_params['end_date'])
                query = query.filter(Appointment.date <= end_date)
            except (ValueError, TypeError):
                pass  # Invalid date, skip filter

        return query

    def _apply_sorting(self, query, search_params):
        """Apply sorting to the query"""
        sort_by = search_params.get('sort_by', 'date')
        sort_order = search_params.get('sort_order', 'desc')

        # Define sortable fields
        sort_fields = {
            'date': Appointment.date,
            'status': Appointment.status,
            'reason': Appointment.reason,
            'created_at': Appointment.created_at,
            'patient_name': Patient.name,
            'doctor_name': User.name
        }

        # Handle joined table sorting
        if sort_by in ['patient_name']:
            query = query.join(Appointment.patient)
            sort_column = Patient.name
        elif sort_by in ['doctor_name']:
            query = query.join(Appointment.doctor).join(Doctor.user)
            sort_column = User.name
        else:
            sort_column = sort_fields.get(sort_by, Appointment.date)

        if sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        return query