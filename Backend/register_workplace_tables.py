import sqlite3

DATABASE_PATH = r"d:\Projects\ProjectsWork\MIT\Backend\DB\market-intelligence.db"

def register_tables():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    tables_to_register = [
        ("Worker", "Adept Team Members", "Internal", "List of all employees and contractors including Frank Mwangi, Kelvin Maina, Hedronilla Juma, John Doe. Tracks workload and status.", "Structured", "Workforce"),
        ("Skill", "Skill Directory", "Internal", "Catalog of technical and soft skills like Solar Sales, Data Cleaning, Lead Mining, VICIdial.", "Structured", "Workforce"),
        ("Project", "Active Project List", "Internal", "Tracks projects including Plexus Energy (Solar Outreach), Vendii Inventory (Merchant Onboarding), and others.", "Structured", "Operations"),
        ("Assignment", "Worker Assignments", "Internal", "Maps workers to projects like Plexus or Vendii with allocation percentages.", "Structured", "Operations"),
        ("PerformanceMetric", "SLA & Performance Data", "Internal", "Tracks metrics (SLA, accuracy, conversion) for projects like Plexus Energy.", "Structured", "Operations"),
        ("DemandEvent", "Recruitment & Project Demand", "Internal", "Upcoming project requirements and skill needs.", "Structured", "Strategy")
    ]

    for table_name, title, source, summary, datatype, sectors in tables_to_register:
        # We use the actual table name (no 'route_' prefix needed in the table_name column)
        # But for routing compatibility, if the agent looks for it, we should ensure it matches
        # Actually our AgentManager looks for table_name in Master.
        
        cursor.execute("""
            INSERT OR REPLACE INTO Master (table_name, Title, Source, Summary, Datatype, Sectors)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (table_name, title, source, summary, datatype, sectors))

    conn.commit()
    conn.close()
    print("Workforce tables registered in Master successfully.")

if __name__ == "__main__":
    register_tables()
