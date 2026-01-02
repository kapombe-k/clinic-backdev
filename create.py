#!/usr/bin/env python3

from app import app, db
from models import User
from flask_bcrypt import generate_password_hash

def create_users():
    roles = ['admin', 'doctor', 'receptionist', 'technician']

    with app.app_context():
        for role in roles:
            # Check if user already exists
            existing_user = User.query.filter_by(email=f'{role}@clinic.com').first()
            if existing_user:
                print(f"User for role '{role}' already exists.")
                continue

            # Create new user
            user = User(
                name=f'{role.capitalize()} User',
                email=f'{role}@clinic.com',
                phone='0712345678',
                role=role
            )
            # Explicitly hash the password to ensure it's properly stored
            # Ensure to change the password once you log in
            user._password_hash = generate_password_hash('password123').decode('utf-8')

            db.session.add(user)
            print(f"Created user for role '{role}' with hashed password")

        db.session.commit()
        print("All users created successfully.")

if __name__ == '__main__':
    create_users()