# Clinic Management System - Backend

## Overview

This is the backend API for the Clinic Management System, a robust RESTful web service built with Flask and SQLAlchemy. It provides comprehensive data management and business logic for clinic operations, including patient records, doctor management, appointment scheduling, treatment tracking, billing, inventory management, and analytics.

The backend serves as the central data hub, handling authentication, authorization, data persistence, and complex business operations while providing secure API endpoints for the frontend application.

## Features

### Core Functionality
- **RESTful API**: Complete REST API with JSON responses
- **JWT Authentication**: Secure token-based authentication with refresh tokens
- **Role-Based Access Control**: Granular permissions for different user roles
- **Database Management**: Robust data persistence with SQLAlchemy ORM
- **Audit Logging**: Comprehensive logging of all system activities
- **CORS Support**: Cross-origin resource sharing for frontend integration

### Business Domains
- **Patient Management**: Complete patient lifecycle with medical history
- **Doctor Management**: Doctor profiles, specialties, and schedule management
- **Appointment System**: Advanced scheduling with conflict detection
- **Visit Tracking**: Detailed visit records and treatment documentation
- **Treatment Management**: Treatment planning and execution tracking
- **Billing System**: Integrated billing with insurance claim support
- **Inventory Management**: Medical supplies tracking with low-stock alerts
- **Prescription Management**: Digital prescription creation and tracking
- **Analytics Engine**: Data aggregation for clinic performance insights

### Security Features
- **Password Hashing**: Secure password storage with bcrypt
- **Token Blacklisting**: JWT token revocation for logout
- **Input Validation**: Comprehensive data validation and sanitization
- **SQL Injection Protection**: Parameterized queries and ORM protection
- **Rate Limiting**: Configurable rate limiting (with Redis support)

## Technologies Used

### Core Framework
- **Flask 3.0.3** - Lightweight WSGI web application framework
- **Flask-RESTful** - Extension for building REST APIs
- **Flask-SQLAlchemy 3.1.1** - SQLAlchemy integration for Flask
- **SQLAlchemy 2.0.41** - Python SQL toolkit and ORM

### Authentication & Security
- **Flask-JWT-Extended 4.6.0** - JWT token management
- **Flask-Bcrypt 1.0.1** - Password hashing utilities
- **Bleach 6.1.0** - Input sanitization library

### Database & Migrations
- **Flask-Migrate 4.1.0** - Database migration framework
- **Alembic 1.14.1** - Database migration tool
- **PostgreSQL/SQLite** - Primary database support
- **psycopg2-binary 2.9.10** - PostgreSQL adapter

### Utilities
- **Flask-CORS 5.0.0** - Cross-origin resource sharing
- **python-dotenv 1.0.1** - Environment variable management

### Development Tools
- **Pipenv** - Python dependency management
- **unittest** - Built-in testing framework

## Getting Started

### Prerequisites

- **Python**: Version 3.8 or higher
- **pipenv**: For dependency management (recommended)
- **PostgreSQL** or **SQLite**: Database server
- **Git**: For version control

### Installation

1. **Navigate to the server directory:**
   ```bash
   cd server
   ```

2. **Install dependencies:**
   ```bash
   pipenv install
   ```

3. **Activate the virtual environment:**
   ```bash
   pipenv shell
   ```

4. **Configure environment variables:**
   Copy the provided `.env` file and update the values:
   ```env
   # Database Configuration
   DATABASE_URI=sqlite:///clinic.db
   SUPABASE_URI=postgresql://user:password@host:port/database

   # Security Configuration
   JWT_SECRET_KEY=your-super-secret-key-here
   JWT_ACCESS_TOKEN_EXPIRES_MINUTES=15
   JWT_REFRESH_TOKEN_EXPIRES_DAYS=30

   # CORS Configuration
   ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

   # Server Configuration
   PORT=5000
   HOST=0.0.0.0
   FLASK_ENV=development
   FLASK_DEBUG=true

   # Redis (Optional)
   REDIS_URL=redis://localhost:6379/0

   # Environment
   ENVIRONMENT=development
   ```

5. **Initialize the database:**
   ```bash
   # Create database tables
   flask db upgrade

   # Or if starting fresh
   flask db init
   flask db migrate
   flask db upgrade
   ```

6. **Create an admin user:**
   ```bash
   python create_admin.py
   ```

7. **Start the development server:**
   ```bash
   python app.py
   ```

   The API will be available at `http://localhost:5000`

### Alternative Installation (without pipenv)

If you prefer using pip directly:

```bash
pip install flask flask-sqlalchemy flask-jwt-extended flask-restful flask-cors flask-bcrypt python-dotenv bleach psycopg2-binary flask-migrate
```

## API Endpoints

### Authentication Endpoints
- `POST /auth/login` - User authentication
- `POST /auth/register` - User registration
- `POST /auth/refresh-token` - Refresh access token
- `POST /auth/logout` - User logout
- `GET /auth/me` - Get current user information

### User Management
- `GET /users` - List all users
- `POST /users` - Create new user
- `GET /users/<user_id>` - Get user details
- `PATCH /users/<user_id>` - Update user
- `DELETE /users/<user_id>` - Deactivate user

### Patient Management
- `GET /patients` - List patients with pagination
- `POST /patients` - Create new patient
- `GET /patients/<patient_id>` - Get patient details
- `PATCH /patients/<patient_id>` - Update patient
- `GET /patients/<patient_id>/medical-history` - Get patient medical history
- `PATCH /patients/<patient_id>/medical-history` - Update medical history
- `GET /patients/search` - Search patients with filters

### Doctor Management
- `GET /doctors` - List doctors
- `POST /doctors` - Create new doctor
- `GET /doctors/<doctor_id>` - Get doctor details
- `PATCH /doctors/<doctor_id>` - Update doctor
- `DELETE /doctors/<doctor_id>` - Deactivate doctor
- `GET /doctors/<doctor_id>/schedule` - Get doctor schedule
- `GET /doctors/<doctor_id>/availability` - Check doctor availability
- `GET /doctors/search` - Search doctors

### Appointment Management
- `GET /appointments` - List appointments
- `POST /appointments` - Create appointment
- `GET /appointments/<appointment_id>` - Get appointment details
- `PATCH /appointments/<appointment_id>` - Update appointment
- `DELETE /appointments/<appointment_id>` - Cancel appointment
- `GET /appointments/search` - Search appointments

### Visit Management
- `GET /visits` - List visits
- `POST /visits` - Create visit record
- `GET /visits/<visit_id>` - Get visit details
- `PATCH /visits/<visit_id>` - Update visit

### Treatment Management
- `GET /treatments` - List treatments
- `POST /treatments` - Create treatment
- `GET /treatments/<treatment_id>` - Get treatment details
- `PATCH /treatments/<treatment_id>` - Update treatment

### Billing Management
- `GET /billings` - List billing records
- `POST /billings` - Create billing record
- `GET /billings/<billing_id>` - Get billing details
- `PATCH /billings/<billing_id>` - Update billing

### Inventory Management
- `GET /inventory` - List inventory items
- `POST /inventory` - Add inventory item
- `GET /inventory/<item_id>` - Get inventory item details
- `PATCH /inventory/<item_id>` - Update inventory item
- `DELETE /inventory/<item_id>` - Remove inventory item

### Analytics
- `GET /analytics/revenue` - Revenue analytics
- `GET /analytics/doctor-performance` - Doctor performance metrics
- `GET /analytics/patient-stats` - Patient statistics

### Prescription Management
- `GET /prescriptions` - List prescriptions
- `POST /prescriptions` - Create prescription
- `GET /prescriptions/<prescription_id>` - Get prescription details
- `PATCH /prescriptions/<prescription_id>` - Update prescription
- `DELETE /prescriptions/<prescription_id>` - Delete prescription

## Database Models

### Core Models

#### User
- Authentication and authorization
- Role-based access (admin, doctor, receptionist, technician)
- Profile information and activity tracking

#### Patient
- Personal and contact information
- Medical history and allergies
- Account balance and payment tracking
- Visit and appointment relationships

#### Doctor
- Professional information and specialties
- License and certification details
- Schedule and availability management
- Treatment and appointment associations

#### Appointment
- Scheduling and status management
- Patient-doctor relationships
- Visit linkage and notes
- Status tracking (scheduled, completed, cancelled, no_show)

#### Visit
- Clinical encounter documentation
- Treatment and prescription linkage
- Notes and follow-up tracking
- Appointment association

#### Treatment
- Procedure and service tracking
- Cost and billing integration
- Inventory usage linkage
- Doctor and visit associations

#### Billing
- Payment processing and tracking
- Insurance claim management
- Treatment cost calculation
- Account balance updates

#### InventoryItem
- Medical supplies and equipment tracking
- Quantity and cost management
- Low-stock alerts and reordering
- Usage tracking across treatments

#### Prescription
- Medication management
- Visit association
- Digital prescription creation

#### AuditLog
- System activity tracking
- User action logging
- Security and compliance monitoring

### Relationships
- **One-to-Many**: User → Appointments, Doctor → Visits/Treatments
- **Many-to-Many**: Patients ↔ Doctors (through Appointments/Visits)
- **Hierarchical**: Visit → Treatments → Billing → Account
- **Associative**: Treatment → InventoryUsage → InventoryItem

## Project Structure

```
server/
├── app.py                      # Main Flask application
├── models.py                   # Database models and relationships
├── resources/                  # API resource classes
│   ├── auth.py                 # Authentication endpoints
│   ├── users.py                # User management
│   ├── patient.py              # Patient management
│   ├── doctor.py               # Doctor management
│   ├── appointment.py          # Appointment scheduling
│   ├── visit.py                # Visit tracking
│   ├── treatments.py           # Treatment management
│   ├── billings.py             # Billing system
│   ├── inventory.py            # Inventory management
│   ├── analytics.py            # Analytics engine
│   ├── prescription.py         # Prescription management
│   └── treatments.py           # Treatment resources
├── migrations/                 # Database migrations
│   └── versions/               # Migration files
├── create.py                   # User creation script
├── Pipfile                     # Python dependencies
├── Pipfile.lock                # Locked dependencies
├── .env                        # Environment variables
├── .gitignore                  # Git ignore rules
└── README.md                   # This documentation
```

## Configuration

### Environment Variables

#### Database Configuration
- `DATABASE_URI`: Primary database connection string
- `SUPABASE_URI`: Supabase database URL (for production)

#### Security Configuration
- `JWT_SECRET_KEY`: Secret key for JWT token signing
- `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`: Access token lifetime
- `JWT_REFRESH_TOKEN_EXPIRES_DAYS`: Refresh token lifetime

#### Server Configuration
- `PORT`: Server port (default: 5000)
- `HOST`: Server host (default: 0.0.0.0)
- `FLASK_ENV`: Environment (development/production)
- `FLASK_DEBUG`: Debug mode (true/false)

#### CORS Configuration
- `ALLOWED_ORIGINS`: Comma-separated list of allowed origins

### Database Setup

The application supports multiple database configurations:

1. **SQLite** (Development):
   ```env
   DATABASE_URI=sqlite:///clinic.db
   ```

2. **PostgreSQL** (Production):
   ```env
   DATABASE_URI=postgresql://user:password@host:port/database
   ```

3. **Supabase** (Cloud):
   ```env
   SUPABASE_URI=postgresql://user:password@host:port/database
   ```

## API Usage Examples

### Authentication
```bash
# Login
curl -X POST http://localhost:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@clinic.com", "password": "password"}'

# Get current user
curl -X GET http://localhost:5000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

### Patient Management
```bash
# List patients
curl -X GET http://localhost:5000/patients \
  -H "Authorization: Bearer <access_token>"

# Create patient
curl -X POST http://localhost:5000/patients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "name": "John Doe",
    "phone": "+1234567890",
    "email": "john@example.com",
    "gender": "male",
    "date_of_birth": "1990-01-01"
  }'
```

### Search Functionality
```bash
# Search patients
curl -X GET "http://localhost:5000/patients/search?q=john&gender=male" \
  -H "Authorization: Bearer <access_token>"
```

## Testing

### Running Tests
```bash
python tests.py
```

### Test Coverage
The test suite includes:
- API endpoint testing
- Authentication flow testing
- Database model validation
- Error handling verification
- CORS configuration testing

## Deployment

### Development Deployment
```bash
# Using pipenv
pipenv install
pipenv run python app.py

# Using pip
pip install -r requirements.txt
python app.py
```

### Production Deployment
1. Set `FLASK_ENV=production`
2. Configure production database
3. Set secure `JWT_SECRET_KEY`
4. Enable HTTPS
5. Configure reverse proxy (nginx/apache)
6. Set up monitoring and logging

### Docker Deployment (Optional)
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "app.py"]
```

## Security Considerations

### Authentication
- JWT tokens with expiration
- Password hashing with bcrypt
- Token blacklisting for logout
- Role-based access control

### Data Protection
- Input sanitization with bleach
- SQL injection prevention
- XSS protection
- CORS configuration

### Best Practices
- Environment variable usage
- Secure secret management
- Regular dependency updates
- Audit logging implementation

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   - Verify database credentials
   - Check database server status
   - Ensure correct database URI format

2. **JWT Token Issues**
   - Verify `JWT_SECRET_KEY` is set
   - Check token expiration settings
   - Ensure proper token format

3. **CORS Errors**
   - Verify `ALLOWED_ORIGINS` includes frontend URL
   - Check CORS headers in requests

4. **Import Errors**
   - Ensure all dependencies are installed
   - Check Python path
   - Verify virtual environment activation

### Debug Mode
- Set `FLASK_DEBUG=true` for detailed error messages
- Check application logs
- Use Flask's built-in debugger
- Monitor database queries with `SQLALCHEMY_ECHO=true`

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Make changes with proper documentation
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add docstrings to functions and classes
- Write comprehensive unit tests
- Update documentation for API changes
- Use meaningful commit messages

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Review the API documentation in the root endpoint (`GET /`)
- Check the models.py file for database schema details
- Create an issue in the repository for bugs or feature requests
- Review the test files for usage examples

## API Documentation

Complete API documentation is available at the root endpoint:
```
GET http://localhost:5000/
```

This returns a comprehensive JSON response with all available endpoints, their parameters, and usage examples.