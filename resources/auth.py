# resources/auth.py
from flask import jsonify, current_app
from flask_restful import Resource, reqparse
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies
)
from flask_bcrypt import check_password_hash
from models import db, User, Doctor, Receptionist, Technician, TokenBlocklist
from datetime import datetime, timezone
import bleach
import re  # Added for email validation

class LoginResource(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('email', type=str, required=True,
                                help="Email is required", location='json')
        self.parser.add_argument('password', type=str, required=True,
                                help="Password is required", location='json')

    def options(self):
        """Handle OPTIONS request for CORS preflight"""
        return {}, 200

    def post(self):
        return self.login()

    def login(self):
        try:
            data = self.parser.parse_args()
            print(f"🔍 Login attempt for email: {data.get('email', 'None')}")

            if not data.get('email') or not data.get('password'):
                return {"error": "Email and password are required"}, 400

            sanitized_email = bleach.clean(data['email'].lower())
        except Exception as e:
            print(f"❌ Error parsing login data: {e}")
            return {"error": "Invalid request data"}, 400

        # Rate limiting check (prevent brute force)
        if self._is_rate_limited(sanitized_email):
            current_app.logger.warning(f"Rate limited login attempt for: {sanitized_email}")
            return {"error": "Too many login attempts. Please try again later."}, 429

        user = User.query.filter_by(email=sanitized_email).first()

        if not user:
            current_app.logger.info(f"Login attempt for unknown email: {sanitized_email}")
            return {"error": "Invalid credentials"}, 401

        if not user.is_active:
            current_app.logger.warning(f"Login attempt for deactivated account: {sanitized_email}")
            return {"error": "Account deactivated"}, 403

        if not check_password_hash(user._password_hash, data['password']):
            current_app.logger.info(f"Failed login for: {sanitized_email}")
            self._record_failed_attempt(sanitized_email)
            return {"error": "Invalid credentials"}, 401

        # Successful login
        current_app.logger.info(f"Successful login for: {user.email} (ID: {user.id})")
        self._reset_failed_attempts(sanitized_email)

        # Create tokens
        access_token = create_access_token(identity=str(user.id),
                                          additional_claims={"role": user.role})
        refresh_token = create_refresh_token(identity=str(user.id))

        # Prepare response
        response = jsonify({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role
            }
        })

        # Set cookies (HTTP-only, secure in production)
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        return response

    # Security helper methods
    def _is_rate_limited(self, email):
        """Check if login attempts exceed rate limit"""
        # Implement Redis-based rate limiting in production
        # For now, simple in-memory cache (replace with Redis in production)
        cache_key = f"login_attempts:{email}"
        attempts = getattr(current_app, 'cache', {}).get(cache_key) or 0
        return attempts >= 5

    def _record_failed_attempt(self, email):
        """Record failed login attempt"""
        cache_key = f"login_attempts:{email}"
        attempts = getattr(current_app, 'cache', {}).get(cache_key) or 0
        if hasattr(current_app, 'cache'):
            current_app.cache[cache_key] = attempts + 1

    def _reset_failed_attempts(self, email):
        """Reset failed attempts counter on successful login"""
        cache_key = f"login_attempts:{email}"
        if hasattr(current_app, 'cache'):
            current_app.cache.pop(cache_key, None)


class RegisterResource(Resource):
    def __init__(self):
        self.parser = reqparse.RequestParser()
        self.parser.add_argument('name', type=str, required=True, location='json')
        self.parser.add_argument('email', type=str, required=True, location='json')
        self.parser.add_argument('password', type=str, required=True, location='json')
        self.parser.add_argument('role', type=str, required=True,
                                choices=['patient', 'doctor', 'receptionist', 'technician'], location='json')
        self.parser.add_argument('phone', type=str, location='json')

    def options(self):
        """Handle OPTIONS request for CORS preflight"""
        return {}, 200

    def post(self):
        return self.register()

    def register(self):
        data = self.parser.parse_args()
        sanitized_email = bleach.clean(data['email'].lower())

        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", sanitized_email):
            return {"error": "Invalid email format"}, 400

        # Check if email exists
        if User.query.filter_by(email=sanitized_email).first():
            return {"error": "Email already registered"}, 409

        # Create user
        user = User(
            name=bleach.clean(data['name']),
            email=sanitized_email,
            role=data['role'],
            is_active=True
        )
        user.password = data['password']  # Uses setter to hash password

        # Optional phone
        if data.get('phone'):
            user.phone = bleach.clean(data['phone'])

        try:
            db.session.add(user)
            db.session.commit()

            # Create role-specific profile if needed
            if data['role'] == 'doctor':
                doctor = Doctor(user=user, specialty='Dentist', monthly_rate=35.0)
                db.session.add(doctor)
            elif data['role'] == 'receptionist':
                receptionist = Receptionist(user=user)
                db.session.add(receptionist)
            elif data['role'] == 'technician':
                technician = Technician(user=user)
                db.session.add(technician)

            db.session.commit()

            current_app.logger.info(f"New user registered: {user.email} (ID: {user.id})")

            # Create tokens
            access_token = create_access_token(identity=str(user.id),
                                              additional_claims={"role": user.role})
            refresh_token = create_refresh_token(identity=str(user.id))

            response = jsonify({
                "message": "Registration successful",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role
                }
            })

            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)

            return response, 201

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration failed: {str(e)}")
            return {"error": "Registration failed"}, 500


class RefreshTokenResource(Resource):
    def options(self):
        """Handle OPTIONS request for CORS preflight"""
        return {}, 200

    @jwt_required(refresh=True)
    def post(self):
        current_user_id = get_jwt_identity()
        claims = get_jwt()

        user = User.query.get(current_user_id)
        if not user or not user.is_active:
            return {"error": "Invalid user"}, 401

        # Create new access token
        access_token = create_access_token(identity=current_user_id,
                                          additional_claims={"role": claims['role']})

        response = jsonify({"message": "Token refreshed"})
        set_access_cookies(response, access_token)
        return response


class LogoutResource(Resource):
    def options(self):
        """Handle OPTIONS request for CORS preflight"""
        return {}, 200

    @jwt_required(verify_type=False)
    def post(self):
        token = get_jwt()
        jti = token['jti']
        token_type = token['type']
        expires = datetime.fromtimestamp(token['exp'], timezone.utc)

        # Add token to blocklist
        db.session.add(TokenBlocklist(jti=jti, type=token_type, expires=expires))
        db.session.commit()

        response = jsonify({"message": "Logout successful"})
        unset_jwt_cookies(response)
        return response


class MeResource(Resource):
    def options(self):
        """Handle OPTIONS request for CORS preflight"""
        return {}, 200

    @jwt_required()
    def get(self):
        """Get current authenticated user information"""
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return {"error": "User not found"}, 404

        if not user.is_active:
            return {"error": "User account is deactivated"}, 403

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }