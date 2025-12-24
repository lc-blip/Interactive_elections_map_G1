import pandas as pd
import sqlite3
import os
import re
import unicodedata

# --- CONFIGURATION ---
EXCEL_FILE_RESULTS = r"data\mapa_1_resultados_modificado.xlsx"
EXCEL_FILE_MANDATES = r"data\mapa_2_perc_mandatos_modificado.xlsx"
DB_FILE = 'eleicoes_final.db'

def get_region(dist_code):
    try:
        code = int(dist_code)
    except (ValueError, TypeError):
        return 'C' 
    if code == 40: return 'A'
    elif code == 30: return 'M'
    else: return 'C'

def read_excel_smart(filepath):
    """
    It recovers 'lost' headers (SIGLAS COLIGAÇÕES) that are placed in the row ABOVE the main header.
    """
    try:
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        return None

    # Find the row index that contains 'CÓD' or 'COD'
    header_idx = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            header_idx = idx
            break
            
    if header_idx is None:
        print(f"ERROR: Header 'CÓD' not found in {filepath}")
        return None

    print(f"   > Header detected at row {header_idx}")
    
    # Read the full file using the detected header
    df = pd.read_excel(filepath, header=[header_idx, header_idx + 1])
    # --- FLATTEN MULTI-LEVEL HEADERS ---
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            str(sub).strip()
            if not str(sub).startswith('Unnamed')
            else str(top).strip()
            for top, sub in df.columns
        ]

    
    if header_idx > 0:
        row_above = temp_df.iloc[header_idx - 1]
        
        # Create a map of {Column_Index: Correct_Name}
        col_rename_map = {}
        for col_idx, value in enumerate(row_above):
            val_str = str(value).upper()
            if 'SIGLAS' in val_str and 'COLIGA' in val_str:
                col_rename_map[col_idx] = 'SIGLAS COLIGAÇÕES'
            elif 'SIGLAS' in val_str and 'GCE' in val_str:
                col_rename_map[col_idx] = 'SIGLAS GCE'
        
        # Apply renaming
        if col_rename_map:
            print(f"   > Recovering lost columns from row above: {col_rename_map}")
            new_columns = list(df.columns)
            for idx, name in col_rename_map.items():
                if idx < len(new_columns):
                    new_columns[idx] = name
            df.columns = new_columns

    # --- FIX MISSING STAT HEADERS (INSC, BR, NUL) ---
    new_cols = list(df.columns)
    if 'INSC' not in new_cols and len(new_cols) > 8:
        # Standard layout: 0:CÓD, 1:DIST, 2:CONC, 3:ÓRG, 4:INSC, 5:VOT, 6:BR, 7:NUL
        new_cols[3] = 'ÓRG'  
        new_cols[4] = 'INSC'
        new_cols[5] = 'VOT'
        new_cols[6] = 'BR'
        new_cols[7] = 'NUL'
        df.columns = new_cols

    # Remove empty columns (Excel artifacts)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')] 
    df.columns = df.columns.str.strip()
    return df

def clean_identifiers(df):
    if 'ÓRG' in df.columns:
        df = df[df['ÓRG'] == 'CM'].copy()
    if 'DIST' in df.columns:
        df['DIST'] = df['DIST'].ffill()
        
    df['CÓD'] = df['CÓD'].astype(str).apply(lambda x: x.split('.')[0]).str.zfill(6)
    df['DIST_ID'] = df['CÓD'].str.slice(0, 2).astype(int)
    df['CONC_ID'] = df['CÓD'].str.slice(0, 4).astype(int)
    
    def standardize_district_code(code):
        if 30 <= code < 40: return 30
        if 40 <= code < 50: return 40
        return code

    df['DIST_ID'] = df['DIST_ID'].apply(standardize_district_code)
    return df

def resolve_party_names(df_votes, df_source):
    """
    Robust version to map [A] -> PPD/PSD...
    """
    print("--- Resolving Real Names for Coalitions/GCE ---")
    
    # 1. Identify columns (robust search)
    def normalize_str(s):
        return unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8').upper()

    col_coalition = None
    col_gce = None
    
    for col in df_source.columns:
        norm = normalize_str(col)
        if 'SIGLAS' in norm and 'COLIGA' in norm:
            col_coalition = col
        if 'SIGLAS' in norm and 'GCE' in norm:
            col_gce = col

    real_name_map = {}
    
    if col_coalition:
        print(f"    Coalition column found: '{col_coalition}'")
    else:
        print("    WARNING: Coalition column missing!")

    for idx, row in df_source.iterrows():
        conc_id = row['CONC_ID']
        
        # Coalitions
        if col_coalition and pd.notna(row[col_coalition]):
            raw_text = str(row[col_coalition]).strip()
            matches = re.findall(r'\[(.*?)\]', raw_text)
            
            if matches:
                letters = ['[A]', '[B]', '[C]', '[D]', '[E]', '[F]', '[G]']
                for i, real_name in enumerate(matches):
                    if i < len(letters):
                        key_acronym = letters[i]
                        real_name_map[(conc_id, key_acronym)] = real_name
            else:
                # Fallback if brackets are missing
                if len(raw_text) > 1:
                    real_name_map[(conc_id, '[A]')] = raw_text

        # GCE
        if col_gce and pd.notna(row[col_gce]):
            real_name = str(row[col_gce]).strip()
            real_name_map[(conc_id, 'GCE')] = real_name

    def get_real_name(row):
        key = (row['MUNICIPALITY_CODE'], row['PARTY_ACRONYM'])
        if key in real_name_map:
            return real_name_map[key]
        else:
            return row['PARTY_ACRONYM']

    df_votes['DETAILED_NAME'] = df_votes.apply(get_real_name, axis=1)
    return df_votes

def process_mandates_file(filepath):
    print(f"--- Processing Mandates File: {filepath} ---")
    try:
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError: return None
    
    header_idx = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            header_idx = idx
            break
    if header_idx is None: return None
    
    df = pd.read_excel(filepath, header=header_idx)
    df = clean_identifiers(df)
    
    cols_metadata = ['CÓD', 'DIST', 'CONC', 'ÓRG', 'DIST_ID', 'CONC_ID']
    cols_ignore = ['SIGLAS COLIGAÇÕES', 'SIGLAS GCE', 'INSC', 'VOT', 'BR', 'NUL'] 
    
    mandate_map = {} 
    for i in range(len(df.columns) - 1):
        col_name = df.columns[i]
        next_col_name = df.columns[i+1]
        if (col_name not in cols_metadata) and \
           (col_name not in cols_ignore) and \
           (not str(col_name).startswith('Unnamed')):
            mandate_map[next_col_name] = col_name

    keep_cols = ['CONC_ID'] + list(mandate_map.keys())
    df_mandates = df[keep_cols].copy()
    df_mandates = df_mandates.rename(columns=mandate_map)
    
    party_cols = list(mandate_map.values())
    df_melted = df_mandates.melt(id_vars=['CONC_ID'], value_vars=party_cols, var_name='PARTY_ACRONYM', value_name='MANDATES')
    df_melted['MANDATES'] = pd.to_numeric(df_melted['MANDATES'], errors='coerce').fillna(0).astype(int)
    
    return df_melted

def run_etl():
    print(f"--- 1. Reading Results File: {EXCEL_FILE_RESULTS} ---")
    df_res = read_excel_smart(EXCEL_FILE_RESULTS)
    if df_res is None: return
    df_res = clean_identifiers(df_res)
    
    cols_fixed = ['CÓD', 'DIST', 'CONC', 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL', 'DIST_ID', 'CONC_ID']
    parties = []
    for c in df_res.columns:
        if c not in cols_fixed and 'SIGLAS' not in str(c).upper():
            parties.append(c)

    print(f"   > Parties detected: {len(parties)}")

    # --- TABLES ---
    # 1. DISTRICTS
    df_dist = df_res[['DIST_ID', 'DIST']].drop_duplicates().sort_values('DIST_ID')
    df_dist.columns = ['CODE', 'NAME']
    def set_clean_name(row):
        if row['CODE'] == 30: return 'Madeira'
        if row['CODE'] == 40: return 'Açores'
        return row['NAME'].title()
    df_dist['NAME'] = df_dist.apply(set_clean_name, axis=1)
    df_dist['REGION'] = df_dist['CODE'].apply(get_region)

    # 2. MUNICIPALITIES
    cols_mun_stats = ['INSC', 'BR', 'NUL']
    for c in cols_mun_stats:
        if c not in df_res.columns: df_res[c] = 0
            
    cols_mun = ['CONC_ID', 'CONC', 'DIST_ID'] + cols_mun_stats
    df_mun = df_res[cols_mun].copy()
    df_mun = df_mun.drop_duplicates(subset=['CONC_ID']).sort_values('CONC_ID')
    df_mun.columns = ['CODE', 'NAME', 'DISTRICT_CODE', 'TOTAL_VOTERS', 'BLANK_VOTES', 'NULL_VOTES']
    df_mun['NAME'] = df_mun['NAME'].str.title()
    
    # 3. PARTIES
    df_parties = pd.DataFrame(parties, columns=['ACRONYM'])
    df_parties['NAME'] = df_parties['ACRONYM']

    # 4. VOTINGS
    df_votes = df_res.melt(id_vars=['CONC_ID'], value_vars=parties, var_name='PARTY_ACRONYM', value_name='VOTES')
    df_votes['VOTES'] = pd.to_numeric(df_votes['VOTES'], errors='coerce').fillna(0).astype(int)
    df_votes.columns = ['MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'VOTES'] 

    # --- RESOLVE NAMES ---
    df_votes = resolve_party_names(df_votes, df_res)

    # --- MANDATES ---
    df_mandates = process_mandates_file(EXCEL_FILE_MANDATES)
    
    if df_mandates is not None:
        print("--- Merging Votes and Mandates ---")
        df_mandates = df_mandates.rename(columns={'CONC_ID': 'MUNICIPALITY_CODE'})
        df_final = pd.merge(df_votes, df_mandates, on=['MUNICIPALITY_CODE', 'PARTY_ACRONYM'], how='left')
        df_final['MANDATES'] = df_final['MANDATES'].fillna(0).astype(int)
    else:
        df_final = df_votes
        df_final['MANDATES'] = 0

    df_final = df_final[['MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'DETAILED_NAME', 'VOTES', 'MANDATES']]

    # --- SAVE ---
    print(f"--- Saving to Database: {DB_FILE} ---")
    if os.path.exists(DB_FILE): os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

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
            TOTAL_VOTERS INTEGER,
            BLANK_VOTES INTEGER,
            NULL_VOTES INTEGER,
            FOREIGN KEY(DISTRICT_CODE) REFERENCES DISTRICTS(CODE)
        );
        CREATE TABLE PARTIES (
            ACRONYM TEXT PRIMARY KEY,
            NAME TEXT
        );
        CREATE TABLE VOTINGS (
            MUNICIPALITY_CODE INTEGER,
            PARTY_ACRONYM TEXT,
            DETAILED_NAME TEXT,
            VOTES INTEGER,
            MANDATES INTEGER DEFAULT 0,
            PRIMARY KEY (MUNICIPALITY_CODE, PARTY_ACRONYM),
            FOREIGN KEY(MUNICIPALITY_CODE) REFERENCES MUNICIPALITIES(CODE),
            FOREIGN KEY(PARTY_ACRONYM) REFERENCES PARTIES(ACRONYM)
        );
    """)

    df_dist.to_sql('DISTRICTS', conn, if_exists='append', index=False)
    df_mun.to_sql('MUNICIPALITIES', conn, if_exists='append', index=False)
    df_parties.to_sql('PARTIES', conn, if_exists='append', index=False)
    df_final.to_sql('VOTINGS', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()
    print("--- ETL Final Completed Successfully! ---")

if __name__ == "__main__":
    run_etl()
