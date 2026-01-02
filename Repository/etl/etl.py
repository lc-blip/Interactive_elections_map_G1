import pandas as pd
import sqlite3
import os
import re
import unicodedata

# --- CONFIGURAÇÃO ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

EXCEL_FILE_RESULTS = os.path.join(PROJECT_ROOT, "data", "mapa_1_resultados_modificado.xlsx")
EXCEL_FILE_MANDATES = os.path.join(PROJECT_ROOT, "data", "mapa_2_perc_mandatos_modificado.xlsx")
DB_FILE = os.path.join(PROJECT_ROOT, "db", "elections.db")
DDL_PATH = os.path.join(PROJECT_ROOT, "db", "create_tables.sql")

# Mapeamento de siglas para nomes completos
PARTY_MAPPING = {
    'PS': 'Partido Socialista',
    'PPD/PSD': 'Partido Social Democrata',
    'CH': 'Chega',
    'IL': 'Iniciativa Liberal',
    'B.E.': 'Bloco de Esquerda',
    'PCP-PEV': 'CDU - Coligação Democrática Unitária',
    'PAN': 'Pessoas-Animais-Natureza',
    'L': 'LIVRE',
    'CDS-PP': 'CDS - Partido Popular',
    'CDS-PP.PPM': 'Coligação CDS-PPM',
    'R.I.R.': 'Reagir Incluir Reciclar',
    'PCTP/MRPP': 'Partido Comunista dos Trabalhadores Portugueses',
    'MPT': 'Partido da Terra',
    'PPM': 'Partido Popular Monárquico',
    'A': 'Aliança',
    'NC': 'Nós, Cidadãos!',
    'E': 'Ergue-te',
    'JPP': 'Juntos Pelo Povo',
    'MAS': 'Movimento Alternativa Socialista',
    'PTP': 'Partido Trabalhista Português',
    'VP': 'Volt Portugal',
    'PDR': 'Partido Democrático Republicano'
}

def get_region(dist_code):
    # 30=Madeira, 40=Açores, Resto=Continente
    try:
        code = int(dist_code)
    except (ValueError, TypeError):
        return 'C' 
    if code == 40: return 'A'
    elif code == 30: return 'M'
    else: return 'C'

def read_excel_robust(filepath):
    # Lê o Excel combinando a linha do código com a linha de baixo (nomes dos partidos).
    # Também recupera as colunas 'SIGLAS' da linha imediatamente acima.
    print(f"Lendo ficheiro: {filepath}")
    try:
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError:
        print(f"Erro: Ficheiro não encontrado: {filepath}")
        return None

    # Procura a linha que contém 'CÓD'
    idx_cod = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            idx_cod = idx
            break
            
    if idx_cod is None: return None

    # Lê o ficheiro principal
    df = pd.read_excel(filepath, header=idx_cod)
    
    # 1. Recuperar cabeçalhos perdidos (linha de cima)
    if idx_cod > 0:
        row_above = temp_df.iloc[idx_cod - 1]
        col_rename_map = {}
        for col_idx, value in enumerate(row_above):
            val_str = str(value).upper()
            if 'SIGLAS' in val_str and 'COLIGA' in val_str:
                col_rename_map[col_idx] = 'SIGLAS COLIGAÇÕES'
            elif 'SIGLAS' in val_str and 'GCE' in val_str:
                col_rename_map[col_idx] = 'SIGLAS GCE'
        
        if col_rename_map:
            current_cols = list(df.columns)
            for idx, name in col_rename_map.items():
                if idx < len(current_cols):
                    current_cols[idx] = name
            df.columns = current_cols
    
    # 2. Corrigir nomes dos partidos (linha de baixo)
    row_parties = df.iloc[0]
    new_columns = []
    
    for col_idx, col_name in enumerate(df.columns):
        val_header = str(col_name).strip()
        val_row_below = str(row_parties[col_idx]).strip()
        
        # Ignora colunas de sistema, usa o valor da linha de baixo se existir
        is_special_col = ('SIGLAS' in val_header.upper()) or ('CÓD' in val_header.upper()) or ('DIST' in val_header.upper())
        
        if val_row_below.lower() != 'nan' and val_row_below != '' and not is_special_col:
            new_columns.append(val_row_below)
        else:
            new_columns.append(val_header)
            
    df.columns = new_columns
    df = df.iloc[1:] # Remove a linha que usámos para os nomes
    
    # Remove colunas vazias geradas pelo Excel
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    
    # Garante nomes padrão para colunas de estatística
    cols = list(df.columns)
    if 'INSC' not in cols and len(cols) > 8:
         cols[3], cols[4], cols[5], cols[6], cols[7] = 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL'
         df.columns = cols
         
    return df

def clean_identifiers(df):
    # Filtra apenas Câmaras Municipais e normaliza códigos (6 dígitos)
    if 'ÓRG' in df.columns:
        df = df[df['ÓRG'] == 'CM'].copy()
    if 'DIST' in df.columns:
        df['DIST'] = df['DIST'].ffill()
        
    df['CÓD'] = df['CÓD'].astype(str).apply(lambda x: x.split('.')[0]).str.zfill(6)
    df['DIST_ID'] = df['CÓD'].str.slice(0, 2).astype(int)
    df['CONC_ID'] = df['CÓD'].str.slice(0, 4).astype(int)
    
    # Normaliza distritos das ilhas
    df['DIST_ID'] = df['DIST_ID'].apply(lambda x: 30 if 30 <= x < 40 else (40 if 40 <= x < 50 else x))
    return df

def resolve_detailed_names(df_votes, df_source):
    # Preenche o nome detalhado usando regex para coligações/GCE e o dicionário global para partidos
    print("Resolvendo nomes detalhados...")
    
    def normalize_str(s):
        return unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8').upper()

    col_coalition = None
    col_gce = None
    
    # Identifica colunas de descrição
    for col in df_source.columns:
        norm = normalize_str(col)
        if 'SIGLAS' in norm and 'COLIGA' in norm: col_coalition = col
        if 'SIGLAS' in norm and 'GCE' in norm: col_gce = col

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
                        real_name_map[(conc_id, letters[i])] = real_name
            elif len(raw_text) > 1:
                real_name_map[(conc_id, '[A]')] = raw_text

        # GCE
        if col_gce and pd.notna(row[col_gce]):
            raw_text = str(row[col_gce]).strip()
            matches = re.findall(r'\[(.*?)\]', raw_text)
            letters = ['[D]', '[E]', '[F]', '[G]']  
            if matches:
                for i, real_name in enumerate(matches):
                    if i < len(letters):
                        real_name_map[(conc_id, letters[i])] = real_name
            elif len(raw_text) > 1:
                real_name_map[(conc_id, '[D]')] = raw_text 


    def get_full_name(row):
        acronym = row['PARTY_ACRONYM']
        mun_code = row['MUNICIPALITY_CODE']
        
        # 1. Tenta nome específico local
        if (mun_code, acronym) in real_name_map:
            return real_name_map[(mun_code, acronym)]
        # 2. Tenta dicionário global
        if acronym in PARTY_MAPPING:
            return PARTY_MAPPING[acronym]
            
        return acronym

    df_votes['DETAILED_NAME'] = df_votes.apply(get_full_name, axis=1)
    return df_votes

def process_mandates_file(filepath):
    # Processa ficheiro de mandatos (nomes na linha X, tipos na linha X+1)
    print("Processando mandatos...")
    try:
        temp_df = pd.read_excel(filepath, header=None, nrows=15)
    except FileNotFoundError: return None
    
    idx_cod = None
    for idx, row in temp_df.iterrows():
        if row.astype(str).str.contains('CÓD|COD', case=False).any():
            idx_cod = idx
            break
    if idx_cod is None: return None

    df = pd.read_excel(filepath, header=idx_cod)
    
    row_parties = df.iloc[0]
    row_types = df.iloc[1]
    
    mandate_map = {} 
    current_party = None
    
    for col_idx in range(len(df.columns)):
        col_name = df.columns[col_idx]
        val_party = str(row_parties.iloc[col_idx]).strip()
        val_type = str(row_types.iloc[col_idx]).strip()
        
        if val_party.lower() != 'nan' and val_party != '':
            current_party = val_party
            
        if val_type == 'M' and current_party:
            mandate_map[col_name] = current_party

    keep_cols = ['CONC_ID'] + list(mandate_map.keys())
    
    df_clean = clean_identifiers(df)
    df_mandates = df_clean[keep_cols].copy()
    df_mandates = df_mandates.rename(columns=mandate_map)
    
    df_melted = df_mandates.melt(id_vars=['CONC_ID'], var_name='PARTY_ACRONYM', value_name='MANDATES')
    df_melted['MANDATES'] = pd.to_numeric(df_melted['MANDATES'], errors='coerce').fillna(0).astype(int)
    
    return df_melted

def run_etl():
    # 1. Leitura e Limpeza
    df_res = read_excel_robust(EXCEL_FILE_RESULTS)
    if df_res is None: return
    df_res = clean_identifiers(df_res)
    
    # Identificar partidos reais (excluir metadados)
    cols_fixed = ['CÓD', 'DIST', 'CONC', 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL', 'DIST_ID', 'CONC_ID']
    parties = []
    
    for c in df_res.columns:
        c_str = str(c).upper()
        if c not in cols_fixed and 'SIGLAS' not in c_str and 'PARTIDOS' not in c_str and 'COLIGAÇÕES' not in c_str and 'GCE' not in c_str:
            parties.append(c)

    print(f"Partidos detetados: {len(parties)}")

    # 2. Tabelas Auxiliares
    df_dist = df_res[['DIST_ID', 'DIST']].drop_duplicates().sort_values('DIST_ID')
    df_dist.columns = ['CODE', 'NAME']
    df_dist['NAME'] = df_dist.apply(lambda r: 'Madeira' if r['CODE']==30 else ('Açores' if r['CODE']==40 else r['NAME'].title()), axis=1)
    df_dist['REGION'] = df_dist['CODE'].apply(get_region)

    df_mun = df_res[['CONC_ID', 'CONC', 'DIST_ID']].copy()
    df_mun = df_mun.drop_duplicates(subset=['CONC_ID']).sort_values('CONC_ID')
    df_mun.columns = ['CODE', 'NAME', 'DISTRICT_CODE']
    df_mun['NAME'] = df_mun['NAME'].str.title()
    
    df_parties = pd.DataFrame(parties, columns=['ACRONYM'])
    df_parties['NAME'] = df_parties['ACRONYM']

    # 3. Processar Votos
    df_votes = df_res.melt(id_vars=['CONC_ID'], value_vars=parties, var_name='PARTY_ACRONYM', value_name='VOTES')
    df_votes['VOTES'] = pd.to_numeric(df_votes['VOTES'], errors='coerce').fillna(0).astype(int)
    df_votes.columns = ['MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'VOTES'] 

    # Adicionar estatísticas à tabela de votos
    for c in ['INSC', 'BR', 'NUL']:
        if c not in df_res.columns: df_res[c] = 0
    df_stats = df_res[['CONC_ID', 'INSC', 'BR', 'NUL']].drop_duplicates()
    df_votes = pd.merge(df_votes, df_stats, left_on='MUNICIPALITY_CODE', right_on='CONC_ID', how='left')
    df_votes = df_votes.drop(columns=['CONC_ID']) 
    df_votes = df_votes.rename(columns={'INSC': 'TOTAL_VOTERS', 'BR': 'BLANK_VOTES', 'NUL': 'NULL_VOTES'})
    
    # Resolver nomes detalhados
    df_votes = resolve_detailed_names(df_votes, df_res)

    # 4. Juntar Mandatos
    df_mandates = process_mandates_file(EXCEL_FILE_MANDATES)
    if df_mandates is not None:
        print("Juntando dados dos mandatos...")
        df_mandates = df_mandates.rename(columns={'CONC_ID': 'MUNICIPALITY_CODE'})
        df_final = pd.merge(df_votes, df_mandates, on=['MUNICIPALITY_CODE', 'PARTY_ACRONYM'], how='left')
        df_final['MANDATES'] = df_final['MANDATES'].fillna(0).astype(int)
    else:
        df_final = df_votes
        df_final['MANDATES'] = 0

    df_final = df_final[[
        'MUNICIPALITY_CODE', 'PARTY_ACRONYM', 'DETAILED_NAME', 
        'VOTES', 'MANDATES', 'TOTAL_VOTERS', 'BLANK_VOTES', 'NULL_VOTES'
    ]]

    # 5. Gravar na BD
    print(f"--- A gravar: {DB_FILE} ---")

# Recriar base de dados
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    if not os.path.exists(DDL_PATH):
        raise FileNotFoundError(f"DDL não encontrado: {DDL_PATH}")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

# Ativar FK
    cursor.execute("PRAGMA foreign_keys = ON;")

# Executar DDL externo
    print(f"--- A executar DDL: {DDL_PATH} ---")
    with open(DDL_PATH, "r", encoding="utf-8") as ddl_file:
        ddl_sql = ddl_file.read()
    cursor.executescript(ddl_sql)

# Inserções
    df_dist.to_sql('DISTRICTS', conn, if_exists='append', index=False)
    df_mun.to_sql('MUNICIPALITIES', conn, if_exists='append', index=False)
    df_parties.to_sql('PARTIES', conn, if_exists='append', index=False)
    df_final.to_sql('VOTINGS', conn, if_exists='append', index=False)

    conn.commit()
    conn.close()

    print("--- ETL Concluído! ---")

if __name__ == "__main__":
    run_etl()
