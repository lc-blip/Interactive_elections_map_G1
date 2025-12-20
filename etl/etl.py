import pandas as pd
import sqlite3

# Caminho para o ficheiro Excel
EXCEL_PATH = '~/Documentos/work_dir/Interactive_elections_map_G1/dataset/mapa_1_resultados_modificado_Lucas.xlsx'
DB_PATH = 'eleicoes.db'

df = pd.read_excel(EXCEL_PATH, header=[1,2])  # header nas linhas 2 e 3 do Excel

print("Colunas originais (MultiIndex):")
print(df.columns)

# --- 2. Combina o MultiIndex em nomes únicos ---
df.columns = [
    'CÓD', 'DIST', 'CONC', 'ÓRG', 'INSC', 'VOT', 'BR', 'NUL',
    'A', 'B.E.', 'CDS-PP', 'CH', 'E', 'IL', 'JPP', 'L', 'MAS', 'MPT', 'NC', 'PAN',
    'PCTP/MRPP', 'PDR', 'PPD/PSD', 'PPM', 'PS', 'PTP', 'R.I.R.', 'VP',
    'PCP-PEV', '[A]', '[B]', '[C]', '[D]', '[E]', '[F]', '[G]',
    'SIGLAS_COLIGACOES', 'SIGLAS_GCE', 'Extra1', 'Extra2', 'Extra3'
]

print("Colunas renomeadas:")
print(list(df.columns))

# --- 3. Filtra apenas os ÓRG 'CM' (concelhos) ---
df_cm = df[df['ÓRG'] == 'CM'].copy()

# --- 4. Cria a base de dados SQLite ---
db_path = "../db/eleicoes.db"  # path final
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# --- 5. Cria tabela, substituindo se já existir ---
cur.execute('''
CREATE TABLE IF NOT EXISTS resultados_cm (
    CÓD TEXT,
    DIST TEXT,
    CONC TEXT,
    ÓRG TEXT,
    INSC INTEGER,
    VOT INTEGER,
    BR INTEGER,
    NUL INTEGER,
    A REAL,
    BE REAL,
    CDS_PP REAL,
    CH REAL,
    E REAL,
    IL REAL,
    JPP REAL,
    L REAL,
    MAS REAL,
    MPT REAL,
    NC REAL,
    PAN REAL,
    PCTP_MRPP REAL,
    PDR REAL,
    PPD_PSD REAL,
    PPM REAL,
    PS REAL,
    PTP REAL,
    RIR REAL,
    VP REAL,
    PCP_PEV REAL,
    A_COL REAL,
    B_COL REAL,
    C_COL REAL,
    D_COL REAL,
    E_COL REAL,
    F_COL REAL,
    G_COL REAL,
    SIGLAS_COLIGACOES TEXT,
    SIGLAS_GCE TEXT,
    Extra1 TEXT,
    Extra2 TEXT,
    Extra3 TEXT
)
''')

# --- 6. Insere os dados ---
df_cm.to_sql('resultados_cm', conn, if_exists='replace', index=False)

# --- 7. Fecha a conexão ---
conn.commit()
conn.close()

print("ETL concluído com sucesso!")
