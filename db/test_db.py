import sqlite3
import pandas as pd
import os

# --- CONFIGURATION ---
DB_FILE = 'eleicoes_final.db'

def test_database():
    print(f"--- TESTING DATABASE: {DB_FILE} ---\n")
    
    if not os.path.exists(DB_FILE):
        print(f"❌ FATAL ERROR: Database file '{DB_FILE}' not found. Run etl_v4.py first.")
        return

    conn = sqlite3.connect(DB_FILE)

    # =========================================================
    # TEST 1: NAME RESOLUTION (Crucial for your last request)
    # =========================================================
    print(">>> TEST 1: Checking Coalition Name Resolution (DETAILED_NAME)")
    
    # We look for rows where the acronym is '[A]' but we want to see if DETAILED_NAME is resolved
    query_names = """
    SELECT MUNICIPALITY_CODE, PARTY_ACRONYM, DETAILED_NAME 
    FROM VOTINGS 
    WHERE PARTY_ACRONYM = '[A]' 
    LIMIT 5
    """
    df_names = pd.read_sql(query_names, conn)
    print(df_names.to_string(index=False))
    
    # Logic check
    sample_name = df_names.iloc[0]['DETAILED_NAME']
    if sample_name == '[A]':
        print("\n❌ FAILURE: 'DETAILED_NAME' is still '[A]'. The regex resolution did not work.")
    else:
        print(f"\n✅ PASS: 'DETAILED_NAME' was resolved to: '{sample_name}'")

    print("-" * 60)

    # =========================================================
    # TEST 2: MANDATES (Checking File 2 Merge)
    # =========================================================
    print(">>> TEST 2: Checking Mandates (File 2 Merge)")
    
    total_mandates = pd.read_sql("SELECT SUM(MANDATES) FROM VOTINGS", conn).iloc[0,0]
    print(f"   Total Mandates in DB: {total_mandates}")
    
    if total_mandates > 1900:
        print("✅ PASS: Mandates are populated.")
    else:
        print("❌ FAILURE: Mandates are 0 or too low. Merge failed.")

    print("-" * 60)

    # =========================================================
    # TEST 3: MUNICIPALITY STATS (Checking Header Fix)
    # =========================================================
    print(">>> TEST 3: Checking Municipality Stats (Blank/Null/Voters)")
    
    stats = pd.read_sql("SELECT SUM(TOTAL_VOTERS) as T, SUM(BLANK_VOTES) as B, SUM(NULL_VOTES) as N FROM MUNICIPALITIES", conn)
    print(f"   Total Voters: {stats.iloc[0]['T']:,.0f}")
    print(f"   Blank Votes:  {stats.iloc[0]['B']:,.0f}")
    
    if stats.iloc[0]['B'] > 0:
        print("✅ PASS: Stats columns are populated.")
    else:
        print("❌ FAILURE: Stats are 0. The header fix logic failed.")

    print("-" * 60)

    # =========================================================
    # TEST 4: REAL WORLD SCENARIO (Lisbon)
    # =========================================================
    print(">>> TEST 4: Visual Check - Lisbon Results")
    print("   (Should show 'Novos Tempos' coalition details and Mandates)")
    
    query_lisbon = """
    SELECT 
        p.ACRONYM as Acronym,
        v.DETAILED_NAME as 'Resolved Name',
        v.VOTES as Votes,
        v.MANDATES as Mandates
    FROM VOTINGS v
    JOIN MUNICIPALITIES m ON v.MUNICIPALITY_CODE = m.CODE
    JOIN PARTIES p ON v.PARTY_ACRONYM = p.ACRONYM
    WHERE m.NAME = 'Lisboa' AND v.VOTES > 5000
    ORDER BY v.VOTES DESC
    """
    df_lisbon = pd.read_sql(query_lisbon, conn)
    print("\n", df_lisbon.to_string(index=False))
    
    conn.close()

if __name__ == "__main__":
    test_database()
