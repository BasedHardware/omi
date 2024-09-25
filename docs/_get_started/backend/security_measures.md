---
layout: default
title: Security Measures
parent: Backend
nav_order: 7
---

# 🔒 Current Security Measures in Omi Backend

This document outlines the security measures currently implemented in the Omi backend to protect user data and maintain system integrity.

## Table of Contents

1. [Data Encryption](#data-encryption)
2. [Authentication and Authorization](#authentication-and-authorization)
3. [Database Security](#database-security)
4. [API Security](#api-security)
5. [Secrets Management](#secrets-management)
6. [Logging and Monitoring](#logging-and-monitoring)
7. [Secure Development Practices](#secure-development-practices)

## Data Encryption

### In-Transit Encryption
- HTTPS is enforced for all API communications using FastAPI's built-in HTTPS support.
- WebSocket connections for real-time audio streaming are secured with WSS (WebSocket Secure).

### At-Rest Encryption
- Firestore data is encrypted at rest using Google Cloud's default encryption mechanisms.
- Google Cloud Storage objects (e.g., audio files) are encrypted using Google-managed encryption keys.
- Pinecone vector database is configured to use encryption at rest.

## Authentication and Authorization

### User Authentication
- Firebase Authentication is used for secure user sign-up and login.
- JWT tokens are used for API request authentication.

### Role-Based Access Control (RBAC)
- Firebase Security Rules are implemented to enforce access control in Firestore and Cloud Storage.
- Backend middleware checks user roles before processing requests.

## Database Security

### Firestore Security Rules
- Rules ensure users can only read and write their own data.
- Example rule implementation:

  ```javascript
  service cloud.firestore {
    match /databases/{database}/documents {
      match /users/{userId} {
        allow read, write: if request.auth.uid == userId;
      }
    }
  }
  ```

### Pinecone Access Control
- API key authentication is used for Pinecone vector database access.
- Namespace isolation is implemented to separate user data within the vector database.

## API Security

### Rate Limiting
- Rate limiting is implemented using the `slowapi` library to prevent abuse.

  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address
  
  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  ```

### Input Validation
- Pydantic models are used for request data validation.

  ```python
  from pydantic import BaseModel, validator

  class UserInput(BaseModel):
      username: str
      age: int

      @validator('username')
      def username_no_spaces(cls, v):
          if ' ' in v:
              raise ValueError('Username must not contain spaces')
          return v
  ```

### CORS Configuration
- CORS is configured to restrict API access to trusted domains.

  ```python
  from fastapi.middleware.cors import CORSMiddleware

  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://yourdomain.com"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

## Secrets Management

### Environment Variables
- Sensitive configuration (API keys, database credentials) is stored as environment variables.
- For production deployments, Google Cloud Secret Manager is used.

  ```python
  from google.cloud import secretmanager

  client = secretmanager.SecretManagerServiceClient()
  name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
  response = client.access_secret_version(name=name)
  secret = response.payload.data.decode('UTF-8')
  ```

## Logging and Monitoring

### Centralized Logging
- Google Cloud Logging is used for centralized log collection and analysis.

### Performance Monitoring
- Google Cloud Monitoring is used to track system performance and detect anomalies.

## Secure Development Practices

### Dependency Management
- Regular updates of dependencies to patch known vulnerabilities.
- Use of `pip` for package management with a `requirements.txt` file.

### Secure Deployment
- Deployment to Google Cloud Run using Docker containers.
- CI/CD pipeline implemented with GitHub Actions for automated, secure deployments.

---

This security measures document reflects the current implementation in the Omi backend. It's important to regularly review and update these measures as the system evolves and new security best practices emerge.
