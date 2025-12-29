import pandas as pd
import sqlite3
import os
import re
import unicodedata

# --- CONFIGURAÇÃO ---
EXCEL_FILE_RESULTS = r"data\mapa_1_resultados_modificado.xlsx"
EXCEL_FILE_MANDATES = r"data\mapa_2_perc_mandatos_modificado.xlsx"
DB_FILE = 'eleicoes_final_v5.db'

# --- DICIONÁRIO DE NOMES COMPLETOS ---
PARTY_MAPPING = {
    'A': 'Aliança',
    'B.E.': 'Bloco de Esquerda',
    'CDS-PP': 'Centro Democrático Social – Partido Popular',
    'CH': 'CHEGA',
    'E': 'Ergue-te',
    'IL': 'Iniciativa Liberal',
    'JPP': 'Juntos Pelo Povo',
    'L': 'LIVRE',
    'MAS': 'Movimento Alternativa Socialista',
    'MPT': 'Partido da Terra',
    'NC': 'Nós, Cidadãos!',
    'PAN': 'Pessoas–Animais–Natureza',
    'PCTP/MRPP': 'Partido Comunista dos Trabalhadores Portugueses / Movimento Reorganizativo do Partido do Proletariado',
    'PDR': 'Partido Democrático Republicano',
    'PPD/PSD': 'Partido Social Democrata',
    'PPM': 'Partido Popular Monárquico',
    'PS': 'Partido Socialista',
    'PTP': 'Partido Trabalhista Português',
    'R.I.R.': 'Reagir Incluir Reciclar',
    'VP': 'Volt Portugal'
}

def get_region(dist_code):
    try:
        code = int(dist_code)
    except (ValueError, TypeError):
        return 'C' 
    if code == 40: return 'A'
    elif code == 30: return 'M'
    else: return 'C'

def read_excel_split_header(filepath):
    """
    Lê o Excel combinando a linha do CÓD (Cabeçalho 1) com a linha de baixo (Cabeçalho 2 - Partidos).
    Isto resolve o problema de 'PARTIDOS' aparecer como nome de coluna.
    """
    print(f"--- A ler (Split Header): {filepath} ---")
    try:
        # Ler linhas brutas para inspeção
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError:
        print(f"ERRO: Ficheiro não encontrado: {filepath}")
        return None

    # Encontrar a linha 'CÓD'
    idx_cod = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            idx_cod = idx
            break
            
    if idx_cod is None: return None
    print(f"   > Cabeçalho CÓD encontrado na linha {idx_cod}")

    # Ler o ficheiro assumindo a linha CÓD como header inicial
    df = pd.read_excel(filepath, header=idx_cod)
    
    # A linha imediatamente a seguir (índice 0 no dataframe lido) contém os nomes dos partidos (A, B.E., etc.)
    # Vamos combinar o cabeçalho original com esta linha.
    
    # Linha de Partidos (está na primeira linha de dados do df atual)
    row_parties = df.iloc[0]
    
    new_columns = []
    for col_idx, col_name in enumerate(df.columns):
        val_header_1 = str(col_name).strip() # Valor da linha CÓD (ex: "PARTIDOS", "CÓD")
        val_header_2 = str(row_parties[col_idx]).strip() # Valor da linha de baixo (ex: "PS", "nan")
        
        # Lógica de Combinação:
        # 1. Se a linha de baixo tem um nome válido (não é nan/empty), usamos esse (ex: "PS" substitui "PARTIDOS")
        # 2. Se a linha de baixo está vazia, mantemos a de cima (ex: "CÓD", "SIGLAS COLIGAÇÕES")
        
        if val_header_2.lower() != 'nan' and val_header_2 != '':
            new_columns.append(val_header_2)
        else:
            new_columns.append(val_header_1)
            
    # Aplicar novas colunas e remover a linha que usámos (a linha dos partidos)
    df.columns = new_columns
    df = df.iloc[1:] # Descarta a linha 0 (que era a linha dos nomes dos partidos)
    
    # Limpeza final de colunas Unnamed e normalização
    # (Mantemos colunas que tenham nomes reais, removemos apenas as que ficaram Unnamed e sem dados)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Fix para colunas de estatística se estiverem em falta
    # (Às vezes INSC/BR/NUL estão na linha CÓD e são preservadas, outras vezes não)
    cols = list(df.columns)
    if 'INSC' not in cols and len(cols) > 8:
         # Layout padrão defensivo
         cols[3] = 'ÓRG'
         cols[4] = 'INSC'
         cols[5] = 'VOT'
         cols[6] = 'BR'
         cols[7] = 'NUL'
         df.columns = cols
         
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

def resolve_detailed_names(df_votes, df_source):
    print("--- A Resolver Nomes Completos ---")
    
    # Identificar colunas de metadados
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
    
    for idx, row in df_source.iterrows():
        conc_id = row['CONC_ID']
        
        # Coligações
        if col_coalition and pd.notna(row[col_coalition]):
            raw_text = str(row[col_coalition]).strip()
            matches = re.findall(r'\[(.*?)\]', raw_text)
            if matches:
                letters = ['[A]', '[B]', '[C]', '[D]', '[E]', '[F]', '[G]']
                for i, real_name in enumerate(matches):
                    if i < len(letters):
                        key_acronym = letters[i]
                        real_name_map[(conc_id, key_acronym)] = real_name
            elif len(raw_text) > 1:
                real_name_map[(conc_id, '[A]')] = raw_text

        # GCE
        if col_gce and pd.notna(row[col_gce]):
            real_name = str(row[col_gce]).strip()
            real_name_map[(conc_id, 'GCE')] = real_name

    def get_full_name(row):
        acronym = row['PARTY_ACRONYM']
        mun_code = row['MUNICIPALITY_CODE']
        
        # 1. Prioridade: Nome específico do concelho (Coligação/GCE)
        if (mun_code, acronym) in real_name_map:
            return real_name_map[(mun_code, acronym)]
        
        # 2. Prioridade: Dicionário Global
        if acronym in PARTY_MAPPING:
            return PARTY_MAPPING[acronym]
            
        return acronym

    df_votes['DETAILED_NAME'] = df_votes.apply(get_full_name, axis=1)
    return df_votes

def process_mandates_file(filepath):
    """
    Processa o ficheiro de mandatos lidando com a estrutura complexa:
    Linha 1: CÓD...
    Linha 2: Nomes dos Partidos (A, B.E...)
    Linha 3: Tipos de Coluna (%, M)
    """
    print(f"--- A Processar Mandatos (Estrutura Complexa) ---")
    try:
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError: return None
    
    idx_cod = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            idx_cod = idx
            break
    if idx_cod is None: return None

    # Ler tudo a partir da linha CÓD
    df = pd.read_excel(filepath, header=idx_cod)
    
    # Linha com Nomes dos Partidos (índice 0)
    row_parties = df.iloc[0]
    # Linha com Tipos (%, M) (índice 1)
    row_types = df.iloc[1]
    
    # Construir mapa de colunas de Mandatos
    # Procuramos colunas onde row_types seja 'M'
    mandate_map = {} # {Nome_Coluna_Original : Nome_Partido}
    
    current_party = None
    
    for col_idx in range(len(df.columns)):
        col_name = df.columns[col_idx]
        val_party = str(row_parties.iloc[col_idx]).strip()
        val_type = str(row_types.iloc[col_idx]).strip()
        
        # Se encontrarmos um nome de partido, atualizamos o "current_party"
        # (Porque o nome do partido muitas vezes só aparece na primeira coluna do par %, M)
        if val_party.lower() != 'nan' and val_party != '':
            current_party = val_party
            
        # Se a coluna for do tipo 'M' (Mandatos), mapeamos para o partido atual
        if val_type == 'M' and current_party:
            mandate_map[col_name] = current_party

    # Extrair apenas colunas de IDs e Mandatos
    keep_cols = ['CONC_ID'] + list(mandate_map.keys())
    
    # Preparar DF limpo
    # Temos de limpar identificadores primeiro para ter CONC_ID
    df_clean = clean_identifiers(df)
    
    # Filtrar colunas
    df_mandates = df_clean[keep_cols].copy()
    df_mandates = df_mandates.rename(columns=mandate_map)
    
    # Melt
    df_melted = df_mandates.melt(id_vars=['CONC_ID'], var_name='PARTY_ACRONYM', value_name='MANDATES')
    df_melted['MANDATES'] = pd.to_numeric(df_melted['MANDATES'], errors='coerce').fillna(0).astype(int)
    
    return df_melted

def run_etl():
    print(f"--- 1. A ler Resultados (Votos) ---")
    df_res = read_excel_split_header(EXCEL_FILE_RESULTS)
    if df_res is None: return
    df_res = clean_identifiers(df_res)
    
    cols_fixed = ['CÓD', 'DIST', 'CONC', 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL', 'DIST_ID', 'CONC_ID']
    parties = []
    # Filtrar colunas que não são metadados para obter lista de partidos
    for c in df_res.columns:
        c_str = str(c).upper()
        if c not in cols_fixed and 'SIGLAS' not in c_str and 'PARTIDOS' not in c_str and 'COLIGAÇÕES' not in c_str and 'GCE' not in c_str:
            parties.append(c)

    print(f"   > Partidos Reais detetados: {len(parties)}")

    # --- GEOGRAFIA ---
    df_dist = df_res[['DIST_ID', 'DIST']].drop_duplicates().sort_values('DIST_ID')
    df_dist.columns = ['CODE', 'NAME']
    def set_clean_name(row):
        if row['CODE'] == 30: return 'Madeira'
        if row['CODE'] == 40: return 'Açores'
        return row['NAME'].title()
    df_dist['NAME'] = df_dist.apply(set_clean_name, axis=1)
    df_dist['REGION'] = df_dist['CODE'].apply(get_region)

    cols_mun = ['CONC_ID', 'CONC', 'DIST_ID']
    df_mun = df_res[cols_mun].copy()
    df_mun = df_mun.drop_duplicates(subset=['CONC_ID']).sort_values('CONC_ID')
    df_mun.columns = ['CODE', 'NAME', 'DISTRICT_CODE']
    df_mun['NAME'] = df_mun['NAME'].str.title()
    
    # --- PARTIDOS ---
    df_parties = pd.DataFrame(parties, columns=['ACRONYM'])
    df_parties['NAME'] = df_parties['ACRONYM'].apply(
        lambda x: PARTY_MAPPING.get(x, x)
    )

    # --- VOTAÇÕES ---
    df_votes = df_res.melt(id_vars=['CONC_ID'], value_vars=parties, var_name='PARTY_ACRONYM', value_name='VOTES')
    df_votes['VOTES'] = pd.to_numeric(df_votes['VOTES'], errors='coerce').fillna(0).astype(int)
    df_votes.columns = ['MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'VOTES'] 

    # --- MOVER ESTATÍSTICAS PARA VOTINGS ---
    print("--- A mover Stats para VOTINGS ---")
    for c in ['INSC', 'BR', 'NUL']:
        if c not in df_res.columns: df_res[c] = 0
    df_stats = df_res[['CONC_ID', 'INSC', 'BR', 'NUL']].drop_duplicates()
    df_votes = pd.merge(df_votes, df_stats, left_on='MUNICIPALITY_CODE', right_on='CONC_ID', how='left')
    df_votes = df_votes.drop(columns=['CONC_ID']) 
    df_votes = df_votes.rename(columns={'INSC': 'TOTAL_VOTERS', 'BR': 'BLANK_VOTES', 'NUL': 'NULL_VOTES'})
    
    # --- DETALHAR NOMES ---
    df_votes = resolve_detailed_names(df_votes, df_res)

    # --- MANDATOS ---
    df_mandates = process_mandates_file(EXCEL_FILE_MANDATES)
    if df_mandates is not None:
        print("--- A juntar Mandatos ---")
        df_mandates = df_mandates.rename(columns={'CONC_ID': 'MUNICIPALITY_CODE'})
        df_final = pd.merge(df_votes, df_mandates, on=['MUNICIPALITY_CODE', 'PARTY_ACRONYM'], how='left')
        df_final['MANDATES'] = df_final['MANDATES'].fillna(0).astype(int)
    else:
        df_final = df_votes
        df_final['MANDATES'] = 0

    # Seleção Final
    df_final = df_final[[
        'MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'DETAILED_NAME', 
        'VOTES', 'MANDATES', 'TOTAL_VOTERS', 'BLANK_VOTES', 'NULL_VOTES'
    ]]

    # --- GRAVAR DB ---
    print(f"--- A gravar: {DB_FILE} ---")
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
            TOTAL_VOTERS INTEGER,
            BLANK_VOTES INTEGER,
            NULL_VOTES INTEGER,
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
    print("--- ETL v7 Concluído! ---")

if __name__ == "__main__":
    run_etl()
