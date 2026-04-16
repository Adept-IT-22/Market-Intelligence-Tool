import sqlite3
import datetime

DATABASE_PATH = r"d:\Projects\ProjectsWork\MIT\Backend\DB\market-intelligence.db"

def seed_data():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. Seed Workers
    workers = [
        ("W001", "Frank Mwangi", "frank@adept.com", "0711122233", "active", "full_time", "2023-01-15", "BPO", "Nairobi", "M001", "U101", 85.0, "busy"),
        ("W002", "Kelvin Maina", "kelvin@adept.com", "0722233344", "active", "full_time", "2023-03-10", "Digital Media", "Nairobi", "M001", "U102", 40.0, "available"),
        ("W003", "Hedronilla Juma", "hedronilla@adept.com", "0733344455", "active", "contractor", "2024-02-01", "Call Center", "Mombasa", "M002", "U103", 95.0, "busy"),
        ("W004", "John Doe", "john@adept.com", "0744455566", "active", "contractor", "2024-03-20", "Call Center", "Nairobi", "M002", "U104", 0.0, "available")
    ]
    cursor.executemany("INSERT OR REPLACE INTO Worker VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", workers)

    # 2. Seed Skills
    skills = [
        (1, "Data Cleaning", "technical", "Cleaning and normalizing raw BPO datasets."),
        (2, "Lead Mining", "domain", "Extracting prospects from LinkedIn and Google Maps."),
        (3, "Solar Sales", "domain", "Deep knowledge of solar ROI for Kenyan SMEs."),
        (4, "VICIdial Handling", "technical", "Expertise in managing VICIdial agent screens and dispositions."),
        (5, "English Fluency", "language", "Certified C1/C2 English proficiency."),
        (6, "Customer Support", "soft_skill", "Handling difficult calls and objection management.")
    ]
    cursor.executemany("INSERT OR REPLACE INTO Skill VALUES (?,?,?,?)", skills)

    # 3. Seed WorkerSkills
    worker_skills = [
        (1, "W001", 1, 0.95, 0.90, "2024-03-01", "supervisor"),
        (2, "W001", 2, 0.85, 0.80, "2024-03-01", "performance"),
        (3, "W002", 1, 0.70, 0.75, "2024-03-05", "test"),
        (4, "W003", 4, 0.90, 0.95, "2024-03-10", "supervisor"),
        (5, "W003", 6, 0.88, 0.85, "2024-03-10", "performance"),
        (6, "W004", 5, 0.85, 0.90, "2024-03-25", "onboarding")
    ]
    cursor.executemany("INSERT OR REPLACE INTO WorkerSkill VALUES (?,?,?,?,?,?,?)", worker_skills)

    # 4. Seed Projects
    projects = [
        ("P001", "Plexus Energy", "Solar SME Outreach", "active", "high", 5, 300, "2026-03-01", "2026-04-30", "O-991"),
        ("P002", "Vendii Inventory", "Merchant Onboarding", "active", "medium", 2, 600, "2026-03-15", "2026-05-15", "O-992")
    ]
    cursor.executemany("INSERT OR REPLACE INTO Project VALUES (?,?,?,?,?,?,?,?,?,?)", projects)

    # 5. Seed ProjectSkillRequirements
    requirements = [
        (1, "P001", 3, 0.80, 0.5), # Solar Sales
        (2, "P001", 4, 0.70, 0.3), # VICIdial
        (3, "P001", 6, 0.85, 0.2), # Customer Support
        (4, "P002", 1, 0.60, 0.4), # Data Cleaning
        (5, "P002", 5, 0.80, 0.6)  # English
    ]
    cursor.executemany("INSERT OR REPLACE INTO ProjectSkillRequirement VALUES (?,?,?,?,?)", requirements)

    # 6. Seed Assignments
    assignments = [
        (1, "W003", "P001", "2026-03-01", None, 100.0, "system", 0.92),
        (2, "W001", "P001", "2026-03-05", None, 50.0, "manager", 0.88)
    ]
    cursor.executemany("INSERT OR REPLACE INTO Assignment VALUES (?,?,?,?,?,?,?,?)", assignments)

    # 7. Seed Metrics
    metrics = [
        (1, "W003", "P001", "conversion_rate", 0.12, "2026-03-25"),
        (2, "W003", "P001", "avg_handle_time", 245.0, "2026-03-25"),
        (3, "W001", "P001", "accuracy_score", 0.98, "2026-03-24")
    ]
    cursor.executemany("INSERT OR REPLACE INTO PerformanceMetric VALUES (?,?,?,?,?,?)", metrics)

    conn.commit()
    conn.close()
    print("Workplace mock data seeded successfully.")

if __name__ == "__main__":
    seed_data()
