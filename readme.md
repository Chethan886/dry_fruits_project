# Dry Fruits Business Management System

This document outlines the setup and installation instructions for the Dry Fruits Business Management System, a Django-based application.

## Prerequisites

* Python (3.10 or higher)
* pip (Python package installer)
* MySQL Server

## Local Setup and Installation

1. **Clone the Repository:**

   ```bash
   git clone <your-repository-url>
   cd dry_fruits_project
   ```

2. **Create and Activate a Virtual Environment:**

   **Windows:**

   ```bash
   python -m venv env
   .\env\Scripts\activate
   ```

   **macOS/Linux:**

   ```bash
   python3 -m venv env
   source env/bin/activate
   ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set Up the MySQL Database:**

   Ensure your MySQL server is running. Create a database:

   ```sql
   CREATE DATABASE dry_fruits_db;
   ```

   Update `dry_fruits_project/settings.py` if your MySQL credentials (root/dead1234pool) differ.  Default connection is localhost:3306.

5. **Run Database Migrations:**

   ```bash
   python manage.py migrate
   ```

6. **Create a Superuser:**

   ```bash
   python manage.py createsuperuser
   ```

   Follow the prompts to create your superuser account.

7. **Run the Development Server:**

   ```bash
   python manage.py runserver
   ```

   Access the application at http://127.0.0.1:8000/

8. **Accessing the Application:**

   * **Main Application:** http://127.0.0.1:8000/ (login with superuser credentials)
   * **Django Admin Panel:** http://127.0.0.1:8000/admin/
