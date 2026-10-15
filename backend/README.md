# OCRLab Backend

## Requirements

- Python 3.11
- pip
- Git

## Local setup

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
$env:PYTHONPATH = "backend"
uvicorn app.main:app --app-dir backend --reload
```

Open the API documentation at `http://127.0.0.1:8000/docs` and check `http://127.0.0.1:8000/api/v1/health`.

## Tests and syntax checks

From the repository root with the virtual environment activated:

```powershell
$env:PYTHONPATH = "backend"
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests -q
```

The initial phase contains only the API foundation and health endpoint. Database access, authentication, PDF ingestion, and OCR workers will be added in later phases.
