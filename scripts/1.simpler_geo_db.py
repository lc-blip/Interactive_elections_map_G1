import sqlite3
import os

DB_PATH = "geom_db/geometry.db"

def main():
    # garantir que a pasta existe
    os.makedirs("geom_db", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # apagar tabela se existir (para testes repetidos)
    cur.execute("DROP TABLE IF EXISTS districts")

    # criar tabela mínima
    cur.execute("""
        CREATE TABLE districts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            geom TEXT NOT NULL
        )
    """)

    # WKT de exemplo (polígonos simples)
    # NÃO são distritos reais — são só para testar o mapa
    districts = [
        (
            "Distrito A",
            "POLYGON((0 0, 10 0, 10 8, 0 8, 0 0))"
        ),
        (
            "Distrito B",
            "POLYGON((12 2, 20 2, 18 10, 12 10, 12 2))"
        )
    ]

    cur.executemany(
        "INSERT INTO districts (name, geom) VALUES (?, ?)",
        districts
    )

    conn.commit()
    conn.close()

    print("✅ Base de dados criada com sucesso em:", DB_PATH)
    print("   Distritos inseridos:", len(districts))


if __name__ == "__main__":
    main()
