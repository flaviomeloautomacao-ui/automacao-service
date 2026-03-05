# Copilot Instructions — Python Service (Automação de Laudos Técnicos)

## Project Overview

This project is a backend service written in Python responsible for **automating the generation of technical reports (laudos)** based on structured spreadsheet data and technical norms (ABNT or similar).

The service receives spreadsheets uploaded from a frontend (Next.js), validates and parses the data, enriches some sections using an LLM (via OpenRouter), and generates a final **PDF report**.

The system is designed to be **modular and reusable**, allowing the same architecture to support different types of risk analyses (e.g., dust explosion, gas hazards, etc.) by swapping prompts, templates, and norms.

Primary responsibilities of this service:

- Receive spreadsheet uploads
- Parse and validate spreadsheet data
- Normalize domain data
- Store structured data in PostgreSQL (Supabase)
- Store raw files and generated reports in object storage
- Generate recommendations and justifications using an LLM
- Render an HTML template
- Convert HTML to a final PDF document
- Expose API endpoints to trigger and retrieve reports

This service is **not responsible for UI**.

Frontend responsibilities (Next.js app):

- Upload spreadsheets
- Display validation errors
- Trigger report generation
- Download generated PDF

---

# System Architecture

The service follows a **Hexagonal Architecture (Ports & Adapters)** pattern.

The goal is to isolate the **domain logic** from infrastructure concerns.

Structure:


app/
api/
domain/
application/
adapters/
infrastructure/


Responsibilities:

### Domain

Contains **pure business logic**.

Must not depend on:
- databases
- frameworks
- HTTP
- external APIs

Includes:


domain/
entities/
schemas/
ports/
errors.py


Examples:

- MachineRiskRow
- ReportDraft
- GeneratedReport
- ValidationError

Ports define interfaces used by adapters.

---

### Application

Contains **use cases**.

Use cases orchestrate:

- parsing
- validation
- LLM generation
- template rendering
- PDF creation
- persistence

Example:


application/use_cases/process_upload.py


---

### Adapters

Adapters implement the interfaces defined in `domain/ports`.

Examples:


adapters/
spreadsheet/
storage/
db/
llm/
pdf/
norms/


Examples of adapters:

| Adapter | Responsibility |
|-------|------|
Spreadsheet Parser | Convert XLSX/CSV into domain entities |
Validator | Validate deterministic rules |
Database Repository | Store drafts and reports |
Storage | Upload files to Supabase |
LLM Client | Call OpenRouter |
PDF Renderer | Convert HTML → PDF |
Norms Provider | Provide regulatory context |

Adapters must implement **Ports defined in the domain layer**.

---

### Infrastructure

Handles configuration and wiring.

Examples:


infrastructure/
config.py
logging.py
dependencies.py
db.py


Responsibilities:

- Environment variables
- Logging
- Dependency injection
- Database connection
- Storage clients

---

# API Layer

API is built with **FastAPI**.

Routes are located in:


api/routes


Example endpoints:


POST /uploads
GET /reports/{id}
GET /health


Rules:

- Routes must remain thin
- Business logic must never live inside routes
- Routes must call **Use Cases**

Example flow:


API Route
↓
Use Case
↓
Domain + Adapters


---

# Technology Stack

### Language

Python 3.11

### Framework

FastAPI

### Database

PostgreSQL (Supabase)

### Storage

Supabase Storage

### Spreadsheet Processing

pandas  
openpyxl

### Template Rendering

Jinja2

### PDF Generation

WeasyPrint

### HTTP Client

httpx

### LLM Gateway

OpenRouter API

### Retry Logic

tenacity

### Logging

loguru

### Data Validation

pydantic

---

# Data Flow

The typical flow is:


Upload spreadsheet
↓
Store raw file
↓
Parse spreadsheet
↓
Validate deterministic rules
↓
Create normalized draft
↓
Persist draft in database
↓
Generate textual sections using LLM
↓
Render HTML template
↓
Generate PDF
↓
Upload PDF to storage
↓
Persist report metadata
↓
Return report URL


---

# Spreadsheet Processing

Supported formats:

- XLSX
- CSV

Parser must:

- normalize column names
- trim whitespace
- convert empty values to None
- map aliases for columns

Example column aliases:


Equipamento
Máquina
Machine


All must map to:


equipamento


Parser returns:


list[MachineRiskRow]


---

# Spreadsheet Validation

Validation must be **deterministic**.

LLMs must **never validate input data**.

Validation checks:

- required columns
- non-empty required values
- risk classification domain
- consistent row structure

Errors must include:


row_index
field
error_message


---

# LLM Usage

LLM is only used for **text generation**, never for:

- validation
- parsing
- structural logic

Allowed outputs:

- recommendations
- technical justifications
- executive summary

All LLM responses must be forced to **JSON format**.

Example expected output:


{
"recommendations": [],
"justifications": [],
"summary": ""
}


LLM access must use OpenRouter.

---

# Storage Strategy

Raw uploads:


uploads/{upload_id}/{filename}


Cloned file:


uploads/{upload_id}/clone_{date}_{filename}


Reports:


reports/{report_id}/report_v1.pdf


Files should store metadata:


expires_at
created_at
checksum


Expiration is handled by a cleanup job, not automatic deletion.

---

# Database Schema

Minimal tables:

uploads


id
filename
content_type
size_bytes
storage_path
created_at
expires_at


report_drafts


id
upload_id
metadata
rows_json
created_at


generated_reports


id
draft_id
pdf_storage_path
pdf_url
checksum
version
created_at


---

# Error Handling

Use domain exceptions:


ValidationError
StorageError
DBError
LLMError
TemplateError


Never expose internal stack traces in API responses.

---

# Logging

Use structured logs.

Include:

- request id
- upload id
- report id

Never log:

- API keys
- secrets
- tokens

---

# Coding Guidelines

Copilot must follow these rules:

1. Prefer **small functions**
2. Avoid giant service classes
3. Use **type hints everywhere**
4. Avoid implicit behavior
5. Write readable code over clever code
6. Do not mix infrastructure code with domain logic
7. All adapters must implement a domain port
8. Use async IO when dealing with I/O operations
9. Do not perform business logic in API routes

---

# Performance Guidelines

Important considerations:

- Spreadsheets may contain hundreds of rows
- LLM calls should be batched
- PDF generation must be deterministic
- Database queries must be async
- Avoid loading entire files into memory unnecessarily

---

# Security

The service must never:

- expose Supabase service role keys
- allow arbitrary file execution
- trust spreadsheet data blindly

All inputs must be validated.

---

# Testing Strategy

Tests must cover:

- spreadsheet parsing
- validation logic
- report generation pipeline

LLM calls must be mocked.

Storage calls must be mocked.

---

# Development Workflow

Typical development process:

1. Implement domain entity
2. Define port interface
3. Implement adapter
4. Create use case
5. Add API route
6. Write tests

---

# Expected Code Quality

Generated code must:

- include docstrings
- include type hints
- avoid dead code
- avoid unused imports
- follow consistent naming

Naming conventions:

snake_case for variables and functions  
PascalCase for classes

---

# Important Constraints

LLMs must not:

- generate final report structure
- modify spreadsheet data
- perform validation

They are used only to enrich narrative sections.

---

# Summary

This service converts structured spreadsheet data into formal technical reports.

It is designed for:

- reliability
- reproducibility
- modularity
- regulatory contexts

Maintain strict separation between:

domain logic  
infrastructure  
external services