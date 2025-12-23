import pandas as pd
import sqlite3
import os

# --- CONFIG ---
EXCEL_FILE = '~/Documentos/work_dir/Interactive_elections_map_G1/dataset/mapa_1_resultados_modificado.xlsx' 
DB_FILE = 'eleicoes_v2.db'

def get_region(dist_code):
    """
    Determines the region based on the standardized district code:
    40 -> Azores (A)
    30 -> Madeira (M)
    Others -> Continent (C)
    """
    try:
        code = int(dist_code)
    except (ValueError, TypeError):
        return 'C' 

    if code == 40:
        return 'A'
    elif code == 30:
        return 'M'
    else:
        return 'C'

def run_etl():
    print(f"--- Reading: {EXCEL_FILE} ---")

    # 1. Finds the correct header line
    try:
        temp_df = pd.read_excel(EXCEL_FILE, header=None, nrows=10)
    except FileNotFoundError:
        print(f"EXCEL_FILE not found")
        return

    # Looking for the line (index) where "CÓD" appears
    header_row_idx = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            header_row_idx = idx
            break
    
    if header_row_idx is None:
        print("ERROR: Could not find the word 'CÓD' in the first 10 lines.")
        return

    print(f"Header located on line: {header_row_idx}")

    # 2. Read the correct excel file with the correct header found previously
    df = pd.read_excel(EXCEL_FILE, header=header_row_idx)

    # ... Removes unwanted columns such as empty columns returned as Unnamed ...
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip() # Removes extra spaces
    
    print("Successfully read columns:", df.columns.tolist()[:5], "...")
    
    # 2. Initial cleaning

    # Filters for "Câmara Municipal" in case other "órgãos" are present.
    if 'ÓRG' in df.columns:
        df = df[df['ÓRG'] == 'CM'].copy()

    # Fill districts that might be empty (merge cells problem)
    if 'DIST' in df.columns:
        df['DIST'] = df['DIST'].ffill()
    
    # 3. CODE treatment (IDs)
    # Convert "CÓD" to string and guarantee 6 digits (ex: '101' -> '010100')
    df['CÓD'] = df['CÓD'].astype(str).apply(lambda x: x.split('.')[0]).str.zfill(6)
    
    # Create separate IDs  
    df['DIST_ID'] = df['CÓD'].str.slice(0, 2).astype(int)
    df['CONC_ID'] = df['CÓD'].str.slice(0, 4).astype(int)

    # --- NEW: STANDARDIZE REGIONS (FLATTEN ISLANDS) ---
    # Forces all Azores codes (40-49) to 40 and Madeira (30-39) to 30
    def standardize_district_code(code):
        if 30 <= code < 40: return 30
        if 40 <= code < 50: return 40
        return code

    # Apply this BEFORE creating tables so duplicates are removed later
    df['DIST_ID'] = df['DIST_ID'].apply(standardize_district_code)

    # 4. Identify Data Columns
    cols_fixas = ['CÓD', 'DIST', 'CONC', 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL']
    cols_lixo = ['SIGLAS COLIGAÇÕES', 'SIGLAS GCE'] 
    
    partidos = [c for c in df.columns if c not in cols_fixas and c not in cols_lixo]
    print(f"Partidos detetados ({len(partidos)}): {partidos[:5]} ...")

    # 5. Preparing tables (Relational Model)

    # --- TABLE: DISTRICTS ---
    # Now drop_duplicates will collapse 9 Azores rows into 1 because they all have ID 40
    df_dist = df[['DIST_ID', 'DIST']].drop_duplicates().sort_values('DIST_ID')
    df_dist.columns = ['CODE', 'NAME']
    
    # Force the Names "Madeira" and "Açores" based on the standardized code
    def set_clean_name(row):
        if row['CODE'] == 30: return 'Madeira'
        if row['CODE'] == 40: return 'Açores'
        return row['NAME'].title() # Makes "AVEIRO" -> "Aveiro"

    df_dist['NAME'] = df_dist.apply(set_clean_name, axis=1)
    df_dist['REGION'] = df_dist['CODE'].apply(get_region)
    
    # --- Table MUNICIPALITIES ---
    df_mun = df[['CONC_ID', 'CONC', 'DIST_ID']].drop_duplicates().sort_values('CONC_ID')
    df_mun.columns = ['CODE', 'NAME', 'DISTRICT_CODE']
    df_mun['NAME'] = df_mun['NAME'].str.title()

    # --- Table PARTIES ---
    df_parties = pd.DataFrame(partidos, columns=['ACRONYM'])
    df_parties['NAME'] = df_parties['ACRONYM'] 

    # --- Table VOTINGS  (MELT transformation) ---
    df_votes = df.melt(
        id_vars=['CONC_ID'],       # Keep municipality ID 
        value_vars=partidos,       # "Melt" parties columns
        var_name='PARTY_ACRONYM',  # New acronym column
        value_name='VOTES'         # New vote column
    ) 
    
    # Clean votes: convert to numeric, zeros where erros appear
    df_votes['VOTES'] = pd.to_numeric(df_votes['VOTES'], errors='coerce').fillna(0).astype(int)
    
    df_votes.columns = ['MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'VOTES']

    # 6. Save in the database
    print(f"--- Saving in the database: {DB_FILE} ---")
    
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Schema SQL 
    cursor.executescript("""
        CREATE TABLE DISTRICTS (
            CODE INTEGER PRIMARY KEY,
            NAME TEXT,
            REGION TEXT
        );

        CREATE TABLE MUNICIPALITIES (
            CODE INTEGER PRIMARY KEY,
            NAME TEXT,
            DISTRICT_CODE INTEGER,
            FOREIGN KEY(DISTRICT_CODE) REFERENCES DISTRICTS(CODE)
        );

        CREATE TABLE PARTIES (
            ACRONYM TEXT PRIMARY KEY,
            NAME TEXT
        );

        CREATE TABLE VOTINGS (
            MUNICIPALITY_CODE INTEGER,
            PARTY_ACRONYM TEXT,
            VOTES INTEGER,
            PRIMARY KEY (MUNICIPALITY_CODE, PARTY_ACRONYM),
            FOREIGN KEY(MUNICIPALITY_CODE) REFERENCES MUNICIPALITIES(CODE),
            FOREIGN KEY(PARTY_ACRONYM) REFERENCES PARTIES(ACRONYM)
        );
    """)

    # Insert DataFrames
    df_dist.to_sql('DISTRICTS', conn, if_exists='append', index=False)
    df_mun.to_sql('MUNICIPALITIES', conn, if_exists='append', index=False)
    df_parties.to_sql('PARTIES', conn, if_exists='append', index=False)
    df_votes.to_sql('VOTINGS', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()
    
    print("--- Database successfully created and populated. ---")

if __name__ == "__main__":
    run_etl()
