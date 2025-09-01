from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, CheckConstraint, func, Index, Numeric
from sqlalchemy.orm import validates, relationship
from sqlalchemy_serializer import SerializerMixin
from datetime import datetime
from flask_bcrypt import generate_password_hash, check_password_hash
import re

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(
        db.String(20), 
        nullable=False,
        default="patient"
    )
    _password_hash = db.Column("password", db.String(255), nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(
        db.DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    last_login = db.Column(db.DateTime)

    # --- Relationships ---
    doctor = relationship("Doctor", uselist=False, back_populates="user", cascade="all, delete-orphan")
    receptionist = relationship("Receptionist", uselist=False, back_populates="user", cascade="all, delete-orphan")
    technician = relationship("Technician", uselist=False, back_populates="user", cascade="all, delete-orphan")

    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="user", cascade="all, delete-orphan")
    inventory_changes = relationship("InventoryChange", back_populates="user", cascade="all, delete-orphan")
    blocked_tokens = relationship("TokenBlocklist", back_populates="user", cascade="all, delete-orphan")

    # --- Password handling ---
    @property
    def password(self):
        raise AttributeError("Password is write-only.")

    @password.setter
    def password(self, plain_password):
        self._password_hash = generate_password_hash(plain_password)

    def verify_password(self, plain_password):
        return check_password_hash(self._password_hash, plain_password)

    # --- Utility ---
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

class Patient(db.Model, SerializerMixin):
    __tablename__ = 'patients'
    serialize_rules = (
        '-visits.patient',
        '-appointments.patient',
        '-account.patient',
        '-medical_history.patient'
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(16), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(120))
    date_of_birth = db.Column(db.Date)
    insurance_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Relationships
    visits = relationship('Visit', back_populates='patient', passive_deletes=True)
    appointments = relationship('Appointment', back_populates='patient', passive_deletes=True)
    account = relationship('Account', back_populates='patient', uselist=False, passive_deletes=True)
    medical_history = relationship('MedicalHistory', back_populates='patient', uselist=False, passive_deletes=True)

    @validates('phone')
    def validate_phone(self, key, phone):
        if not re.match(r"^\+?[0-9]{10,15}$", phone):
            raise ValueError("Invalid phone number format")
        return phone

    @validates('gender')
    def validate_gender(self, key, gender):
        g = (gender or '').strip().lower()
        if g not in ['male', 'female', 'other']:
            raise ValueError("Gender must be male, female or other")
        return g

    def get_age(self):
        if not self.date_of_birth:
            return None
        today = datetime.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) <
            (self.date_of_birth.month, self.date_of_birth.day)
        )

    def get_outstanding_balance(self):
        if not self.account:
            return 0
        return float(self.account.balance or 0)


class Doctor(db.Model, SerializerMixin):
    __tablename__ = 'doctors'
    serialize_rules = (
        '-user.doctor',
        '-visits.doctor',
        '-appointments.doctor',
        '-treatments.doctor'
    )

    id = db.Column(db.Integer, primary_key=True)
    specialty = db.Column(db.String(50), nullable=False, default='Dentist')
    license_number = db.Column(db.String(50), unique=True)
    monthly_rate = db.Column(db.Numeric(12, 2), CheckConstraint('monthly_rate >= 0', name='ck_doctor_monthly_rate'), nullable=False, default=35.00)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), unique=True)
    user = relationship('User', back_populates='doctor')
    visits = relationship('Visit', back_populates='doctor', passive_deletes=True)
    appointments = relationship('Appointment', back_populates='doctor', passive_deletes=True)
    treatments = relationship('Treatment', back_populates='doctor', passive_deletes=True)

    @validates('monthly_rate')
    def validate_monthly_rate(self, key, rate):
        if rate is not None and float(rate) < 0:
            raise ValueError("Monthly rate cannot be negative")
        return rate

    def get_current_schedule(self, start_date, end_date):
        return Appointment.query.filter(
            Appointment.doctor_id == self.id,
            Appointment.date.between(start_date, end_date)
        ).all()


class Visit(db.Model, SerializerMixin):
    __tablename__ = 'visits'
    serialize_rules = (
        '-patient.visits',
        '-doctor.visits',
        '-treatments.visit',
        '-appointment.visit',
        '-prescriptions.visit'
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    visit_type = db.Column(db.String(50))  # e.g., consultation, procedure
    notes = db.Column(db.Text)

    # Foreign keys
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False)
    appointment_id = db.Column(
        db.Integer,
        db.ForeignKey('appointments.id', ondelete='SET NULL'),
        unique=True,  # enforce one-to-one at DB level
        nullable=True
    )

    # Relationships
    patient = relationship('Patient', back_populates='visits')
    doctor = relationship('Doctor', back_populates='visits')
    appointment = relationship('Appointment', back_populates='visit', uselist=False)
    treatments = relationship('Treatment', back_populates='visit', cascade='all, delete-orphan', passive_deletes=True)
    prescriptions = relationship('Prescription', back_populates='visit', cascade='all, delete-orphan', passive_deletes=True)

    __table_args__ = (
        Index('ix_visits_patient_date', 'patient_id', 'date'),
        db.UniqueConstraint('appointment_id', name='uq_visits_appointment_id'),
    )


class Appointment(db.Model, SerializerMixin):
    __tablename__ = 'appointments'
    serialize_rules = (
        '-patient.appointments',
        '-doctor.appointments',
        '-visit.appointment',
        '-user.appointments'
    )

    STATUSES = ['scheduled', 'completed', 'cancelled', 'no_show']

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='scheduled', nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Foreign keys
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))  # Who created the appointment

    # Relationships
    patient = relationship('Patient', back_populates='appointments')
    doctor = relationship('Doctor', back_populates='appointments')
    visit = relationship('Visit', back_populates='appointment', uselist=False)
    user = relationship('User', back_populates='appointments')

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('scheduled','completed','cancelled','no_show')",
            name='ck_appointments_status'
        ),
        Index('ix_appointments_doctor_date', 'doctor_id', 'date'),
        Index('ix_appointments_patient_date', 'patient_id', 'date'),
    )

    @validates('status')
    def validate_status(self, key, status):
        if status not in self.STATUSES:
            raise ValueError(f"Invalid status. Must be one of {', '.join(self.STATUSES)}")
        return status


class Treatment(db.Model, SerializerMixin):
    __tablename__ = 'treatments'
    serialize_rules = (
        '-visit.treatments',
        '-doctor.treatments',
        '-inventory_usage.treatment',
        '-billing.treatment'
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    cost = db.Column(Numeric(12, 2), CheckConstraint('cost >= 0', name='ck_treatment_cost'))
    procedure_code = db.Column(db.String(20))  # e.g., ADA codes

    # Foreign keys
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=False)

    # Relationships
    visit = relationship('Visit', back_populates='treatments')
    doctor = relationship('Doctor', back_populates='treatments')
    inventory_usage = relationship('InventoryUsage', back_populates='treatment', cascade='all, delete-orphan', passive_deletes=True)
    billing = relationship('Billing', back_populates='treatment', uselist=False, passive_deletes=True)


class Billing(db.Model, SerializerMixin):
    __tablename__ = 'billings'
    serialize_rules = ('-treatment.billing', '-account.billings')

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(Numeric(12, 2), CheckConstraint('amount >= 0', name='ck_billing_amount'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), server_default=func.now())
    payment_method = db.Column(db.String(20))
    is_paid = db.Column(db.Boolean, default=False)
    insurance_claim_id = db.Column(db.String(50))

    # Foreign keys
    treatment_id = db.Column(db.Integer, db.ForeignKey('treatments.id', ondelete='CASCADE'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    treatment = relationship('Treatment', back_populates='billing')
    account = relationship('Account', back_populates='billings')


class Account(db.Model, SerializerMixin):
    __tablename__ = 'accounts'
    serialize_rules = ('-patient.account', '-billings.account')

    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(Numeric(12, 2), default=0.00)
    last_payment_date = db.Column(db.DateTime(timezone=True))

    # Foreign key
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), unique=True, nullable=False)

    # Relationships
    patient = relationship('Patient', back_populates='account')
    billings = relationship('Billing', back_populates='account', passive_deletes=True)

    def update_balance(self, amount):
        # Minimal-impact: keep existing behavior but now Numeric-safe
        self.balance = (self.balance or 0) + (amount or 0)
        if amount is not None and float(amount) < 0:  # Payment received
            self.last_payment_date = datetime.utcnow()


class MedicalHistory(db.Model, SerializerMixin):
    __tablename__ = 'medical_histories'
    serialize_rules = ('-patient.medical_history',)

    id = db.Column(db.Integer, primary_key=True)
    conditions = db.Column(db.Text)
    allergies = db.Column(db.Text)
    medications = db.Column(db.Text)
    notes = db.Column(db.Text)

    # Foreign key
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), unique=True, nullable=False)

    # Relationship
    patient = relationship('Patient', back_populates='medical_history')


class InventoryItem(db.Model, SerializerMixin):
    __tablename__ = 'inventory_items'
    serialize_rules = ('-usages.item', '-changes.item')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # e.g., dental, medical, office
    quantity = db.Column(db.Integer, CheckConstraint('quantity >= 0', name='ck_inventory_qty_nonneg'), default=0)
    min_quantity = db.Column(db.Integer, CheckConstraint('min_quantity >= 0', name='ck_inventory_min_nonneg'), default=5)
    unit_cost = db.Column(Numeric(12, 2), CheckConstraint('unit_cost >= 0', name='ck_inventory_unit_cost'))
    last_restocked = db.Column(db.DateTime(timezone=True))

    # Relationships
    usages = relationship('InventoryUsage', back_populates='item', passive_deletes=True)
    changes = relationship('InventoryChange', back_populates='item', passive_deletes=True)

    def check_low_stock(self):
        return (self.quantity or 0) <= (self.min_quantity or 0)


class InventoryUsage(db.Model, SerializerMixin):
    __tablename__ = 'inventory_usages'
    serialize_rules = ('-item.usages', '-treatment.inventory_usage')

    id = db.Column(db.Integer, primary_key=True)
    quantity_used = db.Column(db.Integer, CheckConstraint('quantity_used > 0', name='ck_usage_qty_pos'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Foreign keys
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False)
    treatment_id = db.Column(db.Integer, db.ForeignKey('treatments.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    item = relationship('InventoryItem', back_populates='usages')
    treatment = relationship('Treatment', back_populates='inventory_usage')


class InventoryChange(db.Model, SerializerMixin):
    __tablename__ = 'inventory_changes'
    serialize_rules = ('-item.changes', '-user.inventory_changes')

    TYPES = ['restock', 'adjustment', 'waste', 'usage']

    id = db.Column(db.Integer, primary_key=True)
    change_type = db.Column(db.String(20), nullable=False)
    quantity_change = db.Column(db.Integer, CheckConstraint('quantity_change <> 0', name='ck_inventory_changes_nonzero'), nullable=False)
    notes = db.Column(db.Text)
    date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Foreign keys
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=False)

    # Relationships
    item = relationship('InventoryItem', back_populates='changes')
    user = relationship('User', back_populates='inventory_changes')

    __table_args__ = (
        db.CheckConstraint(
            "change_type IN ('restock','adjustment','waste','usage')",
            name='ck_inventory_changes_type'
        ),
        Index('ix_inventory_changes_item_date', 'item_id', 'date'),
    )

    @validates('change_type')
    def validate_change_type(self, key, change_type):
        if change_type not in self.TYPES:
            raise ValueError(f"Invalid change type. Must be one of {', '.join(self.TYPES)}")
        return change_type


# Role-specific profile tables
class Receptionist(db.Model, SerializerMixin):
    __tablename__ = 'receptionists'
    serialize_rules = ('-user.receptionist',)

    id = db.Column(db.Integer, primary_key=True)
    shift = db.Column(db.String(50))  # e.g., "Morning", "Evening"

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    user = relationship('User', back_populates='receptionist')


class Technician(db.Model, SerializerMixin):
    __tablename__ = 'technicians'
    serialize_rules = ('-user.technician',)

    id = db.Column(db.Integer, primary_key=True)
    specialization = db.Column(db.String(50))  # e.g., "X-Ray", "Sterilization"

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    user = relationship('User', back_populates='technician')


class AuditLog(db.Model, SerializerMixin):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer)  # ID of the affected entity
    target_type = db.Column(db.String(50))  # e.g., 'patient', 'appointment'
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship('User', back_populates='audit_logs')

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user_id}>'


class Prescription(db.Model, SerializerMixin):
    __tablename__ = 'prescriptions'
    serialize_rules = ('-visit.prescriptions',)

    id = db.Column(db.Integer, primary_key=True)
    details = db.Column(db.Text, nullable=False)
    medications = db.Column(db.JSON, default=list)  # List of medication objects
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Foreign keys
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id', ondelete='CASCADE'), nullable=False)

    # Relationships
    visit = relationship('Visit', back_populates='prescriptions')


class TokenBlocklist(db.Model):
    __tablename__ = 'token_blocklist'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    type = db.Column(db.String(16), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    expires = db.Column(db.DateTime(timezone=True), nullable=False)

    user = relationship('User', back_populates='blocked_tokens')

    def __repr__(self):
        return f'<BlockedToken {self.jti}>'
