from flask_restful import Resource, reqparse
from flask import current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, User, Doctor, Receptionist, Technician, AuditLog
from sqlalchemy.exc import SQLAlchemyError
import bleach
from datetime import datetime

class UserResource(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, required=True)
    parser.add_argument('email', type=str, required=True)
    parser.add_argument('role', type=str, required=True, 
                        choices=['admin', 'doctor', 'receptionist', 'technician', 'patient'])
    parser.add_argument('password', type=str, required=True)
    parser.add_argument('phone', type=str)
    parser.add_argument('is_active', type=bool, default=True)
    
    update_parser = reqparse.RequestParser()
    update_parser.add_argument('name', type=str)
    update_parser.add_argument('email', type=str)
    update_parser.add_argument('phone', type=str)
    update_parser.add_argument('is_active', type=bool)
    update_parser.add_argument('password', type=str)

    @jwt_required()
    def get(self, user_id=None):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        
        if user_id:
            user = User.query.get(user_id)
            if not user:
                return {"message": "User not found"}, 404
                
            # Authorization
            if claims['role'] != 'admin' and user.id != current_user_id:
                return {"message": "Unauthorized"}, 403
                
            return self.user_to_dict(user)
        
        # List users (admin only)
        if claims['role'] != 'admin':
            return {"message": "Admin access required"}, 403
            
        users = User.query.all()
        return [self.user_to_dict(u) for u in users]

    @jwt_required()
    def post(self):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        if claims['role'] != 'admin':
            return {"message": "Admin access required"}, 403
            
        data = self.parser.parse_args()
        
        # Validate email uniqueness
        if User.query.filter_by(email=data['email']).first():
            return {"message": "Email already exists"}, 409
            
        # Create user
        new_user = User(
            name=bleach.clean(data['name']),
            email=bleach.clean(data['email']),
            role=data['role'],
            is_active=data['is_active']
        )
        new_user.password = data['password']  # Uses setter for hashing
        
        # Optional phone
        if data.get('phone'):
            new_user.phone = bleach.clean(data['phone'])
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            # Create role-specific profile if needed
            if data['role'] == 'doctor':
                doctor = Doctor(user=new_user, specialty='General', hourly_rate=100.0)
                db.session.add(doctor)
            elif data['role'] == 'receptionist':
                receptionist = Receptionist(user=new_user)
                db.session.add(receptionist)
            elif data['role'] == 'technician':
                technician = Technician(user=new_user)
                db.session.add(technician)
                
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=get_jwt_identity(),
                action="USER_CREATE",
                target_id=new_user.id,
                target_type='user',
                details=f"Created {data['role']} user"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.user_to_dict(new_user), 201
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"User creation failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def patch(self, user_id):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return {"message": "User not found"}, 404
            
        # Authorization
        if claims['role'] != 'admin' and user.id != current_user_id:
            return {"message": "Unauthorized"}, 403
            
        data = self.update_parser.parse_args()
        changes = []
        
        # Update fields
        if 'name' in data and data['name']:
            user.name = bleach.clean(data['name'])
            changes.append('name')
        if 'phone' in data:
            user.phone = bleach.clean(data['phone']) if data['phone'] else None
            changes.append('phone')
        if 'email' in data and data['email']:
            # Validate new email
            if User.query.filter(User.email == data['email'], User.id != user.id).first():
                return {"message": "Email already in use"}, 409
            user.email = bleach.clean(data['email'])
            changes.append('email')
        if 'password' in data and data['password']:
            user.password = data['password']
            changes.append('password')
        if 'is_active' in data and claims['role'] == 'admin':
            user.is_active = data['is_active']
            changes.append('is_active')
            
        if not changes:
            return {"message": "No changes detected"}, 400
            
        try:
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                user_id=current_user_id,
                action="USER_UPDATE",
                target_id=user_id,
                details=f"Updated: {', '.join(changes)}"
            )
            db.session.add(audit)
            db.session.commit()
            
            return self.user_to_dict(user)
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"User update failed: {str(e)}")
            return {"message": "Database error"}, 500

    @jwt_required()
    def delete(self, user_id):
        claims = get_jwt()
        current_user_id = get_jwt_identity()
        if claims['role'] != 'admin':
            return {"message": "Admin access required"}, 403
            
        user = User.query.get(user_id)
        if not user:
            return {"message": "User not found"}, 404
            
        # Soft delete
        user.is_active = False
        
        try:
            db.session.commit()
            
            audit = AuditLog(
                user_id=current_user_id,
                action="USER_DEACTIVATE",
                target_id=user_id,
                details="User deactivated"
            )
            db.session.add(audit)
            db.session.commit()
            
            return {"message": "User deactivated"}
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"User deactivation failed: {str(e)}")
            return {"message": "Database error"}, 500

    def user_to_dict(self, user):
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None
        }