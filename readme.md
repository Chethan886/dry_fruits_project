# Dry Fruits Business Management System

This is a Django-based application to manage a dry fruits business, including customer management, product and price lists, billing, payments, and reporting.

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python** (3.10 or higher)
- **pip** (Python package installer)
- **MySQL Server**

---

## Local Setup and Installation

Follow these steps to get your development environment set up.

### 1. Clone the Repository

git clone <your-repository-url>
cd dry_fruits_project


### 2. Create and Activate a Virtual Environment

It's highly recommended to use a virtual environment to manage project dependencies.

**On Windows:**
python -m venv env
.\env\Scripts\activate


### 3. Install Dependencies

Install all the required packages from the requirements.txt file.
pip install -r requirements.txt


### 4. Set Up the MySQL Database

- Make sure your MySQL server is running.
- Open a MySQL client (like MySQL Workbench, DBeaver, or the command-line client).
- Create a new database for the project.

CREATE DATABASE dry_fruits_db;


> The project is configured to connect with the user **root** and password **dead1234pool** to this database on `localhost:3306`.  
> If your credentials are different, update them in `dry_fruits_project/settings.py`.

### 5. Run Database Migrations

Apply the database schema to your newly created database.

python manage.py migrate


### 6. Create a Superuser

Create an admin account to access the Django admin panel and the application's admin-level features.

python manage.py createsuperuser


Follow the prompts to create your superuser account.

### 7. Run the Development Server

You are now ready to run the project!

python manage.py runserver


The application will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## Accessing the Application

- **Main Application:** Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and log in with your superuser credentials.
- **Django Admin Panel:** Navigate to [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) to manage the backend models directly.
