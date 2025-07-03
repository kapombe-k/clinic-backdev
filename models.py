from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, CheckConstraint
from sqlalchemy.orm import validates
from sqlalchemy_serializer import SerializerMixin
from datetime import datetime

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)

class Patient(db.Model, SerializerMixin):
    __tablename__ = 'patients'
    serialize_rules = ('-visits.patient', '-appointments.patient')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)

    visits = db.relationship("Visit", back_populates="patient", cascade="all, delete-orphan")
    appointments = db.relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")

    @validates('phone_number')
    def validate_phone(self, key, number):
        if len(number) < 10 or not number.isdigit():
            raise ValueError("Phone number must be at least 10 digits")
        return number
    
    def get_total_balance(self):
        return sum(visit.balance for visit in self.visits if visit.balance is not None)

class Doctor(db.Model, SerializerMixin):
    __tablename__ = 'doctors'
    serialize_rules = ('-visits.doctor', '-appointments.doctor')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    visits = db.relationship("Visit", back_populates="doctor", cascade="all, delete-orphan")
    appointments = db.relationship("Appointment", back_populates="doctor", cascade="all, delete-orphan")

class Visit(db.Model, SerializerMixin):
    __tablename__ = 'visits'
    serialize_rules = (
        '-patient.visits', 
        '-doctor.visits', 
        '-prescription.visit',
        'prescription',
        'doctor.name',
        'doctor.id'
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.now())
    summary = db.Column(db.String(200), nullable=False)
    procedure_details = db.Column(db.Text, nullable=False)
    amount_paid = db.Column(db.Float, CheckConstraint('amount_paid >= 0'), nullable=False)
    balance = db.Column(db.Float, nullable=True)

    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)

    patient = db.relationship("Patient", back_populates="visits")
    doctor = db.relationship("Doctor", back_populates="visits")
    prescription = db.relationship("Prescription", back_populates="visit", uselist=False, cascade="all, delete-orphan")

class Appointment(db.Model, SerializerMixin):
    __tablename__ = 'appointments'
    serialize_rules = (
        '-patient.appointments', 
        '-doctor.appointments',
        'patient.name',
        'doctor.name'
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)

    patient = db.relationship("Patient", back_populates="appointments")
    doctor = db.relationship("Doctor", back_populates="appointments")

class Prescription(db.Model, SerializerMixin):
    __tablename__ = 'prescriptions'
    serialize_rules = ('-visit.prescription',)

    id = db.Column(db.Integer, primary_key=True)
    details = db.Column(db.Text, nullable=False)
    
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=False)
    visit = db.relationship("Visit", back_populates="prescription")
