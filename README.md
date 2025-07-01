# intelehealth-ai-middleware

 # Medical Diagnosis and Treatment API

A Flask-based REST API for medical diagnosis assistance, treatment recommendations, and SNOMED CT terminology management. This application integrates with AI models for differential diagnosis and treatment planning, and maintains a database of medical concepts and their mappings.

## 🚀 Features

- **Differential Diagnosis Generation**: AI-powered diagnosis suggestions based on patient case history
- **Treatment Recommendations**: Comprehensive treatment plans including medications and dosages
- **SNOMED CT Integration**: Search and manage medical terminology from SNOMED CT
- **Concept Management**: Create and map medical concepts in OpenMRS database
- **Request Tracking**: Elasticsearch logging for all API requests
- **Environment Configuration**: Flexible configuration via environment variables

## 📋 Prerequisites

- Python 3.7+
- MySQL/MariaDB database (OpenMRS compatible)
- Elasticsearch 7.x+
- Access to AI model services (Gemini models)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd intelehealth-ai-middleware
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create environment file**
   ```bash
   cp ai.env.example ai.env
   ```

4. **Configure environment variables**
   Edit `ai.env` with your specific configuration (see Configuration section below)

## ⚙️ Configuration

Create a `ai.env` file in the project root with the following variables:

### Flask Application
```env
FLASK_DEBUG=False
FLASK_HOST=0.0.0.0
```

### Base URLs
```env
BASE_URL=XXXX
SNOMED_BASE_URL=XXXX
```

### Database Configuration
```env
DB_HOST=XXXX
DB_NAME=XXXX
DB_USER=XXXX
DB_PASSWORD=XXXX
```

### Elasticsearch Configuration
```env
ELASTICSEARCH_URL=XXXX
DDX_INDEX_NAME=XXXX
TTX_INDEX_NAME=XXXX
```

### AI Model Services
```env
DDX_MODEL_URL=XXXX
TTX_MODEL_URL=XXXX
DDX_MODEL_NAME=XXXX
TTX_MODEL_NAME=XXXX
```

### Timezone
```env
TIMEZONE=Asia/Calcutta
```

### Database Constants
```env
CONCEPT_SET_ID=XXXX
CONCEPT_SOURCE_ID=XXXX
CONCEPT_MAP_TYPE_ID=XXXX
CONCEPT_CLASS_ID=XXXX
CONCEPT_DATATYPE_ID=XXXX
CONCEPT_CREATOR_ID=XXXX
CONCEPT_RETIRED=XXXX
CONCEPT_IS_SET=XXXX
CONCEPT_NAME_TYPE=XXXX
CONCEPT_LOCALE=XXXX
```

### Retry Configuration
```env
RETRY_TOTAL=XXX
RETRY_BACKOFF_FACTOR=XX
RETRY_STATUS_FORCELIST=XX,XX,XX
```

## 🚀 Running the Application

### Development Mode
```bash
python index.py
```

### Production Mode
```bash
# Using Gunicorn (recommended for production)
gunicorn -w 4 -b 0.0.0.0:5000 index:app

# Using uWSGI
uwsgi --http 0.0.0.0:5000 --module index:app --processes 4
```

The application will be available at `http://localhost:5000`

## 📚 API Documentation

### 1. Differential Diagnosis (`POST /ddx`)

Generate differential diagnosis using AI model.

**Request Body:**
```json
{
  "visitUuid": "unique-visit-id",
  "casehistory": "Patient presents with fever, cough, and fatigue for 3 days..."
}
```

**Response:**
```json
{
  "result": {
    "data": {
      "conclusion": "Summary conclusion",
      "output": {
        "diagnosis": "1. COVID-19 (Likelihood: High)\n2. Influenza (Likelihood: Medium)",
        "rationale": "Clinical reasoning..."
      }
    }
  },
  "conclusion": "Summary conclusion"
}
```

### 2. SNOMED CT Search (`GET /getdiags/<term>`)

Search SNOMED CT terminology for medical concepts.

**Example:**
```
GET /getdiags/diabetes
```

**Response:**
```json
{
  "result": [
    {
      "conceptId": "73211009",
      "term": "Diabetes mellitus",
      "active": true
    }
  ]
}
```

### 3. SNOMED CT Management (`POST /snomed`)

Create or update SNOMED CT concept mappings.

**Request Body:**
```json
{
  "conceptName": "Hypertension",
  "snomedCode": "38341003"
}
```

**Response:**
```json
{
  "result": "Diagnosis Hypertension is created with Concept ID 12345"
}
```

### 4. Treatment Recommendations (`POST /ttxv1`)

Generate treatment recommendations based on case history and diagnosis.

**Request Body:**
```json
{
  "visitUuid": "unique-visit-id",
  "case": "Patient case history...",
  "diagnosis": "Hypertension"
}
```

**Response:**
```json
{
  "result": {
    "data": {
      "medications": [
        {
          "name": "Amlodipine",
          "dosage": "5mg daily",
          "duration": "Lifetime"
        }
      ],
      "recommendations": "Lifestyle modifications..."
    }
  }
}
```

## 🗄️ Database Schema

The application integrates with OpenMRS database and uses the following tables:

- `concept`: Main concept table
- `concept_name`: Concept names and synonyms
- `concept_reference_term`: External terminology references
- `concept_reference_map`: Mapping between concepts and reference terms
- `concept_set`: Grouping of related concepts

## 📊 Logging

The application uses structured logging with the following components:

- **DDX Logger**: Logs differential diagnosis requests and responses
- **TTX Logger**: Logs treatment recommendation requests and responses
- **Elasticsearch**: Stores request metadata for tracking and analytics

## 🔧 Development

### Project Structure
```
/
├── index.py              # Main Flask application
├── ai.env                # Environment configuration
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── loggerddx.py         # DDX logging configuration
├── loggerttx.py         # TTX logging configuration
```

### Adding New Endpoints

1. Create the route function with proper documentation
2. Add error handling and logging
3. Update this README with API documentation
4. Add any new environment variables to `ai.env`

### Testing

```bash
# Run basic health check
curl http://localhost:5000/health

# Test differential diagnosis
curl -X POST http://localhost:5000/ddx \
  -H "Content-Type: application/json" \
  -d '{"visitUuid":"test","casehistory":"Patient with fever"}'
```

## 🚨 Error Handling

The application includes comprehensive error handling:

- **400 Bad Request**: Invalid input data
- **500 Internal Server Error**: Database or external service errors
- **Retry Logic**: Automatic retries for external API calls
- **Logging**: All errors are logged for debugging

## 🔒 Security Considerations

- Use HTTPS in production
- Secure database credentials
- Implement rate limiting
- Add authentication/authorization as needed
- Validate all input data

## 📝 License

[Add your license information here]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Update documentation
6. Submit a pull request

## 📞 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the logs for debugging information

## 🔄 Version History

- **v1.0**: Initial release with basic diagnosis and treatment endpoints
- **v1.1**: Added SNOMED CT integration and concept management
- **v1.2**: Improved error handling and logging
- **v1.3**: Environment variable configuration and documentation

---

**Note**: This application is designed for medical use and should be deployed in compliance with relevant healthcare regulations and security standards.
