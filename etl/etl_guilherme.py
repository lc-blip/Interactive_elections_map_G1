import pandas as pd
import sqlite3
import unicodedata
import re
from pathlib import Path

# ==============================
# CONFIGURAÇÃO
# ==============================

EXCEL_VOTOS = r"data\mapa_1_resultados_modificado.xlsx"
EXCEL_MANDATOS = r"data\mapa_2_perc_mandatos_modificado.xlsx"
SHEET_VOTOS = "mapa_I"
SHEET_MANDATOS = "mapa_II"

DB_PATH = "db/eleicoes.db"
DDL_PATH = "db/create_tables.sql"


# ==============================
# FUNÇÕES AUXILIARES
# ==============================

def normalize_text(s):
    if pd.isna(s):
        return None
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s.upper()

def to_int(x):
    try:
        return int(float(x))
    except:
        return None

def to_float(x):
    try:
        return float(x)
    except:
        return None

def normalize_columns(df):
    cols = []
    for c in df.columns:
        c = str(c).strip()
        c = unicodedata.normalize("NFKD", c)
        c = "".join(ch for ch in c if not unicodedata.combining(ch))
        cols.append(c.upper())
    df.columns = cols
    return df

# ==============================
# ETL PRINCIPAL
# ==============================

def run_etl():
    print("[ETL] A iniciar")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Criar schema
    ddl = Path(DDL_PATH).read_text(encoding="utf-8")
    conn.executescript(ddl)

    # Limpar resultados
    cur.execute("DELETE FROM result")

    # Organ CM
    cur.execute("INSERT OR IGNORE INTO organ(code,name) VALUES ('CM','Câmara Municipal')")
    cur.execute("SELECT id FROM organ WHERE code='CM'")
    organ_id = cur.fetchone()[0]

    # ======================
    # LER EXCEL VOTOS
    # ======================

    df_votos = pd.read_excel(EXCEL_VOTOS, header=[1,2], sheet_name=SHEET_VOTOS)
    df_votos.columns = [c[0] if "UNNAMED" not in str(c[0]).upper() else c[1] for c in df_votos.columns]
    df_votos = normalize_columns(df_votos)
    df_votos = df_votos[df_votos["ORG"] == "CM"]
    print(df_votos.columns)

    # ======================
    # LER EXCEL MANDATOS
    # ======================

    df_mand = pd.read_excel(EXCEL_MANDATOS, header=[3,4], sheet_name=SHEET_MANDATOS)

    df_mand.columns = [c[0] if "UNNAMED" not in str(c[0]).upper() else c[1] for c in df_mand.columns]
    df_mand = normalize_columns(df_mand)
    df_mand = df_mand[df_mand["ORG"] == "CM"]

    # Indexar mandatos por código
    mand_index = df_mand.set_index("COD").to_dict("index")

    PARTY_COLS = [
        'A','B.E.','CDS-PP','CH','E','IL','JPP','L','MAS','MPT','NC','PAN',
        'PCTP/MRPP','PDR','PPD/PSD','PPM','PS','PTP','R.I.R.','VP','PCP-PEV'
    ]

    last_district = None

    # ======================
    # PROCESSAMENTO
    # ======================

    for _, r in df_votos.iterrows():
        cod = str(r["COD"])

        # Distrito
        if pd.notna(r["DIST"]):
            last_district = normalize_text(r["DIST"])
        district_code = cod[:2]

        cur.execute("SELECT id FROM district WHERE code=?", (district_code,))
        row = cur.fetchone()
        if row:
            district_id = row[0]
        else:
            cur.execute(
                "INSERT INTO district(code,name) VALUES (?,?)",
                (district_code, last_district)
            )
            district_id = cur.lastrowid

        # Município
        cur.execute("SELECT id FROM municipality WHERE code=?", (cod,))
        row = cur.fetchone()
        if row:
            municipality_id = row[0]
        else:
            cur.execute(
                "INSERT INTO municipality(code,name,district_id) VALUES (?,?,?)",
                (cod, normalize_text(r["CONC"]), district_id)
            )
            municipality_id = cur.lastrowid

        # Resultados por partido
        for sigla in PARTY_COLS:
            votes = to_int(r.get(sigla))
            if votes is None:
                continue

            cur.execute("INSERT OR IGNORE INTO party(sigla,name) VALUES (?,?)", (sigla, sigla))
            cur.execute("SELECT id FROM party WHERE sigla=?", (sigla,))
            party_id = cur.fetchone()[0]

            mandates = None
            pct = None
            if cod in mand_index:
                mandates = to_int(mand_index[cod].get(sigla + " M"))
                pct = to_float(mand_index[cod].get(sigla + " %"))

            cur.execute("""
                INSERT INTO result(
                    organ_id, municipality_id,
                    holder_type, holder_id,
                    votes, mandates, pct_votes,
                    registered, blanks, nulls
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                organ_id, municipality_id,
                "party", party_id,
                votes, mandates, pct,
                to_int(r["INSC"]), to_int(r["BR"]), to_int(r["NUL"])
            ))

    conn.commit()
    conn.close()
    print("[ETL] Concluído com sucesso")

if __name__ == "__main__":
    run_etl()
