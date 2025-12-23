import sqlite3
import pandas as pd

# O nome da tua base de dados gerada
DB_FILE = 'eleicoes_v2.db'

print(f"--- A verificar: {DB_FILE} ---")
conn = sqlite3.connect(DB_FILE)

# 1. Ver se as tabelas existem
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("\nTabelas encontradas:", [t[0] for t in tables])

# 2. Ver uma amostra dos votos (para confirmar o 'melt')
print("\n--- Amostra de Votos (VOTINGS) ---")
df_votes = pd.read_sql("SELECT * FROM VOTINGS LIMIT 5", conn)
print(df_votes)

# 3. Ver uma amostra de um concelho específico (ex: Águeda - 010100 -> 101)
# Nota: O código 010100 transformado em inteiro fica 10100 ou 101 dependendo do teu script anterior
# Vamos listar um exemplo real
print("\n--- Exemplo de votos num Município ---")
query = """
    SELECT m.NAME as Municipio, v.PARTY_ACRONYM, v.VOTES 
    FROM VOTINGS v
    JOIN MUNICIPALITIES m ON v.MUNICIPALITY_CODE = m.CODE
    WHERE v.VOTES > 0
    LIMIT 5
"""
df_exemplo = pd.read_sql(query, conn)
print(df_exemplo)

conn.close()
