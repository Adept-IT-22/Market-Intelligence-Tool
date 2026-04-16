import sqlite3
import os

DATABASE_PATH = r"d:\Projects\ProjectsWork\MIT\Backend\DB\market-intelligence.db"

def setup_workplace_tables():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. Worker Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Worker (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        status TEXT DEFAULT 'active',
        employment_type TEXT,
        hire_date TEXT,
        department TEXT,
        location TEXT,
        manager_id TEXT,
        odoo_user_id TEXT,
        current_workload_percentage REAL DEFAULT 0.0,
        availability_status TEXT DEFAULT 'available'
    )
    """)

    # 2. Skill Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Skill (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        category TEXT,
        description TEXT
    )
    """)

    # 3. WorkerSkill Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS WorkerSkill (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id TEXT,
        skill_id INTEGER,
        proficiency_score REAL DEFAULT 0.0,
        confidence_score REAL DEFAULT 0.0,
        last_validated TEXT,
        validation_source TEXT,
        FOREIGN KEY(worker_id) REFERENCES Worker(id),
        FOREIGN KEY(skill_id) REFERENCES Skill(id)
    )
    """)

    # 4. Project Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Project (
        id TEXT PRIMARY KEY,
        client_name TEXT,
        project_name TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        priority_level TEXT,
        required_workers INTEGER,
        sla_target_seconds INTEGER,
        start_date TEXT,
        end_date TEXT,
        odoo_project_id TEXT
    )
    """)

    # 5. ProjectSkillRequirement Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ProjectSkillRequirement (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT,
        skill_id INTEGER,
        minimum_score REAL,
        importance_weight REAL,
        FOREIGN KEY(project_id) REFERENCES Project(id),
        FOREIGN KEY(skill_id) REFERENCES Skill(id)
    )
    """)

    # 6. Assignment Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Assignment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id TEXT,
        project_id TEXT,
        assigned_at TEXT,
        released_at TEXT,
        allocation_percentage REAL,
        assigned_by TEXT,
        assignment_confidence_score REAL,
        FOREIGN KEY(worker_id) REFERENCES Worker(id),
        FOREIGN KEY(project_id) REFERENCES Project(id)
    )
    """)

    # 7. PerformanceMetric Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS PerformanceMetric (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id TEXT,
        project_id TEXT,
        metric_type TEXT,
        value REAL,
        timestamp TEXT,
        FOREIGN KEY(worker_id) REFERENCES Worker(id),
        FOREIGN KEY(project_id) REFERENCES Project(id)
    )
    """)

    # 8. Availability Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Availability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id TEXT,
        date TEXT,
        available_hours REAL,
        booked_hours REAL,
        status TEXT,
        FOREIGN KEY(worker_id) REFERENCES Worker(id)
    )
    """)

    # 9. DemandEvent Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS DemandEvent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT,
        required_workers INTEGER,
        required_skills_json TEXT,
        deadline TEXT,
        priority TEXT,
        created_at TEXT,
        source TEXT,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY(project_id) REFERENCES Project(id)
    )
    """)

    conn.commit()
    conn.close()
    print("Workforce Intelligence tables initialized successfully.")

if __name__ == "__main__":
    setup_workplace_tables()
