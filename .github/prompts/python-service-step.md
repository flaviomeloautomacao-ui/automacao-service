# Python Service Development Steps
## Automated Technical Report Generation Service

This document instructs AI coding assistants (Copilot / LLM agents) how to safely develop features inside this repository without breaking the architecture.

The service follows Hexagonal Architecture (Ports and Adapters) and must be developed step-by-step.

The AI must never skip steps or implement large systems in a single response.

Each task must follow the process described below.

---

# Project Purpose

This Python service automates the generation of technical reports (laudos) based on structured spreadsheet input.

The system receives spreadsheets uploaded from a frontend (Next.js), processes the data, enriches narrative sections using LLMs, and generates a final PDF report.

Main capabilities:

- Receive spreadsheet uploads
- Parse structured spreadsheet data
- Validate deterministic rules
- Normalize domain data
- Persist drafts in PostgreSQL
- Store files in Supabase Storage
- Generate technical sections using LLMs
- Render HTML templates
- Generate PDF reports
- Expose API endpoints

---

# Architecture

The system follows Hexagonal Architecture.

Layers:

API  
↓  
Application (Use Cases)  
↓  
Domain (Entities + Ports)  
↓  
Adapters (Implementations)  
↓  
Infrastructure  

The AI must respect strict separation between layers.

---

# Folder Structure

app/
  api/
  domain/
  application/
  adapters/
  infrastructure/
tests/

---

# API Layer

The API layer is implemented with FastAPI.

Responsibilities:

- Receive HTTP requests
- Validate request payload
- Call application use cases
- Return response DTOs

Rules:

Routes must remain thin.

Routes must not contain business logic.

Routes must call use cases.

Example:

POST /uploads  
GET /reports/{id}  
GET /health  

---

# Domain Layer

The domain layer contains pure business logic.

It must never depend on:

- FastAPI
- databases
- storage services
- HTTP clients
- infrastructure code

The domain layer contains:

Entities  
Schemas  
Errors  
Ports (interfaces)

Example domain entities:

MachineRiskRow  
ReportDraft  
GeneratedReport  

Example domain errors:

ValidationError  
StorageError  
DBError  
LLMError  
TemplateError  

Ports define the contracts that adapters must implement.

Example ports:

SpreadsheetParserPort  
SpreadsheetValidatorPort  
ReportRepositoryPort  
StoragePort  
LLMPort  
PdfRendererPort  
NormsProviderPort  

---

# Application Layer

The application layer contains Use Cases.

Use cases orchestrate the workflow of the system.

They connect domain logic and adapters.

Example use cases:

ProcessSpreadsheetUpload  
GenerateReportFromDraft  
CleanupExpiredFiles  

Use cases must not contain HTTP logic.

Use cases must not contain database-specific queries.

Use cases must depend only on Ports.

---

# Adapter Layer

Adapters implement the interfaces defined in domain ports.

Adapters connect the application to external systems.

Example adapters:

Spreadsheet parser (pandas/openpyxl)  
Database repository (PostgreSQL)  
Storage adapter (Supabase Storage)  
LLM client (OpenRouter)  
PDF renderer (WeasyPrint)  
Norms provider (technical standards)

Adapters live in:

app/adapters/

Example structure:

adapters/
  spreadsheet/
  storage/
  db/
  llm/
  pdf/
  norms/

Adapters must implement ports defined in the domain layer.

---

# Infrastructure Layer

Infrastructure contains configuration and dependency wiring.

Examples:

config.py  
logging.py  
dependencies.py  
db.py  

Responsibilities:

- Load environment variables
- Configure logging
- Provide dependency injection
- Configure database connection
- Configure storage clients
- Configure LLM clients

Infrastructure must not contain business logic.

---

# Technology Stack

Language

Python 3.11

Framework

FastAPI

Database

PostgreSQL (Supabase)

Storage

Supabase Storage

Spreadsheet Processing

pandas  
openpyxl  

Template Rendering

Jinja2

PDF Generation

WeasyPrint

HTTP Client

httpx

LLM Gateway

OpenRouter API

Retry Logic

tenacity

Logging

loguru

Validation

pydantic

---

# Data Flow

Typical pipeline:

Upload spreadsheet  
↓  
Store raw file in storage  
↓  
Parse spreadsheet  
↓  
Validate deterministic rules  
↓  
Normalize rows  
↓  
Create report draft  
↓  
Persist draft in database  
↓  
Generate narrative sections using LLM  
↓  
Render HTML template  
↓  
Generate PDF from HTML  
↓  
Upload PDF to storage  
↓  
Persist generated report metadata  
↓  
Return report URL  

---

# Spreadsheet Parsing

Supported formats:

XLSX  
CSV  

The parser must:

Normalize column names  
Trim whitespace  
Convert empty values to None  
Map column aliases  

Example aliases:

Equipamento  
Máquina  
Machine  

All should map to:

equipamento  

The parser returns:

list[MachineRiskRow]

---

# Spreadsheet Validation

Validation must be deterministic.

LLMs must never validate input data.

Validation rules include:

Required columns  
Non-empty required fields  
Valid risk classification values  
Consistent row structure  

Validation errors must include:

row_index  
field  
message  

---

# LLM Usage

LLM is used only for narrative content.

Allowed sections:

Recommendations  
Technical justifications  
Executive summary  

LLM must always return JSON.

Example output:

{
 "recommendations": [],
 "justifications": [],
 "summary": ""
}

The system must validate JSON responses before using them.

LLM calls must use OpenRouter.

---

# Storage Strategy

Raw uploads:

uploads/{upload_id}/{filename}

Cloned file:

uploads/{upload_id}/clone_{date}_{filename}

Generated reports:

reports/{report_id}/report_v1.pdf

Files must store metadata:

created_at  
expires_at  
checksum  

Expiration must be handled by cleanup jobs.

---

# Database Tables

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

Do not expose internal stack traces to API clients.

---

# Logging

Logs must include:

request_id  
upload_id  
report_id  

Never log:

API keys  
tokens  
secrets  

---

# Coding Guidelines

Always:

Use type hints  
Write small functions  
Write docstrings  
Keep modules focused  

Never:

Mix infrastructure with domain logic  
Put business logic inside routes  
Write giant service classes  

Naming conventions:

snake_case for variables  
PascalCase for classes  

---

# Performance Guidelines

Spreadsheets may contain hundreds of rows.

Important considerations:

Avoid loading entire files unnecessarily  
Batch LLM calls when possible  
Use async database queries  
Avoid blocking I/O  

---

# Security Guidelines

The system must never:

Expose Supabase service role keys  
Trust spreadsheet data without validation  
Execute uploaded files  

All inputs must be validated.

---

# Testing Strategy

Tests must cover:

Spreadsheet parsing  
Validation rules  
Report generation pipeline  

External systems must be mocked.

Mock:

LLM calls  
Storage operations  

---

# Development Workflow

When implementing a feature, always follow:

1. Create or update Domain entity
2. Define or update Domain port
3. Implement Adapter
4. Implement Use Case
5. Add API route
6. Write tests

---

# Important Constraints

LLMs must never:

Parse spreadsheets  
Validate input data  
Modify structured domain data  

They may only generate narrative text sections.

---

# Final Principle

This system converts structured technical data into formal regulatory reports.

The architecture prioritizes:

Reliability  
Reproducibility  
Modularity  
Auditability