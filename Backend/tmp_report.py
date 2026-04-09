import sqlite3
import os
import re

db_path = 'd:/Projects/ProjectsWork\MIT/Backend/DB/market-intelligence.db'

def map_to_department(sectors, source, title):
    sectors = (sectors or "").lower()
    source = (source or "").lower()
    title = (title or "").lower()

    # 1. Check for explicit folder codes in Source path
    if "03." in source or "marketing" in source:
        return "Marketing & Comms"
    if "12." in source or "software development" in source:
        return "Software Development"
    if "36." in source or "bd collateral" in source or "business development" in source:
        return "Business Development"
    if "30." in source or "cloud" in source or "automation" in source:
        return "Cloud & Business Automation"
    if "innovations" in source:
        return "Innovations"
    if "finance" in source or "internal operations" in source:
        return "Finance & Operations"

    # 2. Heuristics based on Sectors
    if any(kw in sectors for kw in ["marketing", "brand", "communication", "pr"]):
        return "Marketing & Comms"
    if any(kw in sectors for kw in ["software development", "ict", "application"]):
        return "Software Development"
    if any(kw in sectors for kw in ["business development", "sales", "strategy"]):
        return "Business Development"
    if any(kw in sectors for kw in ["finance", "operation", "admin"]):
        return "Finance & Operations"
    if any(kw in sectors for kw in ["cloud", "automation"]):
        return "Cloud & Business Automation"
    if "innovation" in sectors:
        return "Innovations"

    # 3. Market Research / External
    external_sectors = ["agriculture", "tourism", "transportation", "construction", "energy", "healthcare", "education"]
    if any(sec in sectors for sec in external_sectors) or source.startswith("http"):
        return "Market Research / External"

    return "Other / General"

def run_report():
    if not os.path.exists(db_path):
        print(f"Error: DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- DOCUMENT DISTRIBUTION BY TYPE ---")
    cursor.execute('SELECT Datatype, COUNT(*) FROM Master GROUP BY Datatype ORDER BY COUNT(*) DESC')
    for row in cursor.fetchall():
        print(f'{row[0] or "Unknown"}: {row[1]}')

    print("\n--- ADEPT DEPARTMENTAL BREAKDOWN ---")
    cursor.execute('SELECT Sectors, Source, Title FROM Master')
    rows = cursor.fetchall()
    
    dept_counts = {}
    for sectors, source, title in rows:
        dept = map_to_department(sectors, source, title)
        dept_counts[dept] = dept_counts.get(dept, 0) + 1
    
    # Sort by count
    sorted_depts = sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)
    for dept, count in sorted_depts:
        print(f'{dept}: {count}')

    print("\n--- SECTORS (Detailed) ---")
    cursor.execute('SELECT Sectors, COUNT(*) FROM Master GROUP BY Sectors ORDER BY COUNT(*) DESC LIMIT 10')
    for row in cursor.fetchall():
        print(f'{row[0] or "Unknown"}: {row[1]}')

    print("\n--- OWNERSHIP ---")
    cursor.execute("SELECT COUNT(*) FROM Master WHERE Title LIKE '%Adept%' OR Summary LIKE '%Adept%' OR Source LIKE '%Adept%'")
    adept_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM Master")
    total_count = cursor.fetchone()[0]
    print(f'Adept Related: {adept_count} ({(adept_count/total_count)*100:.1f}%)')
    print(f'Market Data / Other: {total_count - adept_count} ({(1 - adept_count/total_count)*100:.1f}%)')
    
    # Domains (heuristic based on Source)
    print("\n--- SOURCE DOMAINS (Heuristic) ---")
    cursor.execute("SELECT Source FROM Master")
    sources = cursor.fetchall()
    domains = {}
    for (src,) in sources:
        if not src: continue
        if src.startswith('http'):
            from urllib.parse import urlparse
            domain = urlparse(src).netloc
            domains[domain] = domains.get(domain, 0) + 1
        elif re.match(r'[A-Za-z]:[\\/]', src) or '/' in src or '\\' in src:
            domains['Local Filesystem'] = domains.get('Local Filesystem', 0) + 1
        else:
            domains['Unknown/Other'] = domains.get('Unknown/Other', 0) + 1
    
    sorted_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)
    for dom, count in sorted_domains[:10]:
        print(f'{dom}: {count}')

    conn.close()

if __name__ == "__main__":
    run_report()
