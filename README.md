# Exam Seating Arrangement System

An intelligent seating assignment system that automatically detects student conflicts and allocates seats across rooms using **graph coloring**, **constraint-based room allocation**, and an **interactive dashboard**. Built using Python, Flask, and SQLite, this project streamlines large-scale university exam seating logistics.

---

## Features

- Conflict detection using graph coloring (via NetworkX)
- Dynamic room configuration (capacity, allowed years/branches)
- Auto seat allocation per layout grid (x, y positions)
- Admin dashboard with searchable seating and visualizations
- SQLite backend for storing room settings
- Exports room-wise seating in CSV format
- Sample data generation for demo/test use
- TOTP-based 2FA setup for admin/teacher login

---

## Tech Stack

- **Frontend**: HTML + CSS (Flask Templates)
- **Backend**: Python (Flask, SQLite)
- **Visualization**: Interactive HTML seat maps
- **Database**: SQLite (system config + room settings)
- **Other Libraries**: Pandas, NetworkX, PyOTP

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/ishaan2-svg/exam-seating-system.git
cd exam-seating-system
```
### 2. Create a Virtual Environment (Recommended)

```bash
python -m venv venv
venv\Scripts\activate     # On Windows
source venv/bin/activate  # On Linux/macOS
```
### 3. Install Dependencies
```bash
pip install -r requirements.txt
```
### 4. Run the Seating Pipeline
```bash
python main.py
```
## This generates:

- CSV exports in exports/
- Interactive HTML layouts in visualizations/
### 5. Launch the Web Server
```bash
python app.py
```
### Admin Security
- Shared 2FA secret (TOTP) is generated on first run.
- Add it to your Google Authenticator app.
- TOTP stored securely in data/system.db
