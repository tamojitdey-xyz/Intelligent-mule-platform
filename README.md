# Intelligent Mule — Account Detection and Financial Fraud Investigation Platform

Competition-oriented educational prototype built with Flask, SQLite, and vanilla JavaScript. It includes a dashboard, explainable rule-based transaction scores, account profiles, transaction network visualization, investigation case management, CSV import/export, and an audit log.

## Run on Ubuntu
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000` on that PC. The app intentionally binds to localhost.

## CSV format
Required headers: `txn_ref,timestamp,sender,receiver,amount,channel`; optional `narration`. Use ISO timestamps such as `2026-10-26 14:30:00`. Duplicate transaction references are ignored. `sample_transactions.csv` is a template.

## 8–10 minute demo plan
1. Explain the mule-account investigation problem (1 min).
2. Dashboard and risk indicators (1 min).
3. Filter transactions and explain the score reasons (2 min).
4. Open an account profile and network graph (2 min).
5. Create a case, change its status, and show the audit trail (2 min).
6. Import/export CSV and discuss safeguards/limitations (1 min).

## Important limitations and safeguards
All seeded records are synthetic. Risk scores are illustrative heuristics, not a validated ML model, not proof of wrongdoing, and not a basis for automatic adverse decisions. Use only synthetic or properly authorized anonymized data. Do not upload customer data, credentials, or the local SQLite database to GitHub. This prototype is not production-ready: add authentication, role-based access, CSRF protection, secure deployment, privacy/retention controls, tamper-evident audit logging, and validation on authorized labelled data before any real-world use. GitHub stores source code; it does not run this app by itself.
