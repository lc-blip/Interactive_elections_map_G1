import sqlite3
import fiona
from shapely.geometry import shape

GPKG_PATH = [
    "../CAOP_Continente_2024_1-gpkg/Continente_CAOP2024_1.gpkg",
    "../CAOP_RAA_2024_1-gpkg/ArqAcores_GCentral_GOriental_CAOP2024_1.gpkg",
    "../CAOP_RAA_2024_1-gpkg/ArqAcores_GOcidental_CAOP2024_1.gpkg",
    "../CAOP_RAM_2024_1-gpkg/ArqMadeira_CAOP2024_1.gpkg"
]

LAYER_MUNICIPS_NAME = [
    "cont_municipios",
    "raa_cen_ori_municipios",
    "raa_oci_municipios",
    "ram_municipios"
]

SQLITE_DB = "geom_db/geometry_real.db"


def main():
    conn = sqlite3.connect(SQLITE_DB)
    cur = conn.cursor()

    # apagar tabela se existir
    cur.execute("DROP TABLE IF EXISTS municipalities")
    cur.execute("""
        CREATE TABLE municipalities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            district TEXT NOT NULL,
            name TEXT NOT NULL,
            geom TEXT NOT NULL
        )
    """)

    for i in range(len(LAYER_MUNICIPS_NAME)):
        with fiona.open(GPKG_PATH[i], layer=LAYER_MUNICIPS_NAME[i]) as src:
            for feat in src:
                props = feat["properties"]

                name = props.get("municipio")
                district = props.get("distrito_ilha")

                if not name or not district:
                    continue

                geom = shape(feat["geometry"])
                wkt = geom.wkt

                cur.execute(
                    "INSERT INTO municipalities (district, name, geom) VALUES (?, ?, ?)",
                    (district, name, wkt)
                )

    conn.commit()
    conn.close()
    print("✅ Municípios reais inseridos com sucesso")


if __name__ == "__main__":
    main()
