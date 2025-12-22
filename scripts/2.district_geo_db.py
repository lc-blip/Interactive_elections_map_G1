import sqlite3
import fiona
from shapely.geometry import shape

# caminhos (ajusta se necessário)
GPKG_PATH = [
    "../CAOP_Continente_2024_1-gpkg/Continente_CAOP2024_1.gpkg",
    "../CAOP_RAA_2024_1-gpkg/ArqAcores_GCentral_GOriental_CAOP2024_1.gpkg",
    "../CAOP_RAA_2024_1-gpkg/ArqAcores_GOcidental_CAOP2024_1.gpkg",
    "../CAOP_RAM_2024_1-gpkg/ArqMadeira_CAOP2024_1.gpkg"
    ]      
      
LAYER_NAME = [
    "cont_distritos",
    "raa_cen_ori_distritos",
    "raa_oci_distritos",
    "ram_distritos"]

REGION = [ "Continente", "Açores", "Açores", "Madeira"]

SQLITE_DB = "geom_db/geometry_real.db"

def main():
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()

    # apagar tabela se existir: recall de script
    cur.execute("DROP TABLE IF EXISTS districts")
    cur.execute("""
        CREATE TABLE districts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            name TEXT NOT NULL,
            geom TEXT NOT NULL
        )
    """)
    #e, vez de datasets, aqui iterar pelas listas..."~
    for i in range(len(LAYER_NAME)):
        with fiona.open(GPKG_PATH[i], layer=LAYER_NAME[i]) as src:
            for feat in src:
                props = feat["properties"]

                name = props["distrito"]
                if not name:#precisamos mesmo desta linha de codigo???
                    continue

                geom = shape(feat["geometry"])
                wkt = geom.wkt

                cur.execute(
                    "INSERT INTO districts (region, name, geom) VALUES (?, ?, ?)",
                    (REGION[i], name, wkt)
                )
    #algures aqui tem de associar consuante o ficheiro .gpkg qual a regiao...
    conn.commit()
    conn.close()
    print("✅ Distritos reais inseridos com sucesso")

if __name__ == "__main__":
    main()
