import sqlite3
import fiona
from shapely.geometry import shape
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_FILE = os.path.join(PROJECT_ROOT, "db", "elections.db")

GPKG_PATH = [
    "CAOP_Continente_2024_1-gpkg/Continente_CAOP2024_1.gpkg",
    "CAOP_RAA_2024_1-gpkg/ArqAcores_GCentral_GOriental_CAOP2024_1.gpkg",
    "CAOP_RAA_2024_1-gpkg/ArqAcores_GOcidental_CAOP2024_1.gpkg",
    "CAOP_RAM_2024_1-gpkg/ArqMadeira_CAOP2024_1.gpkg",
]

LAYER_DISTRICTS = [
    "cont_distritos",
    "raa_cen_ori_distritos",
    "raa_oci_distritos",
    "ram_distritos",
]

LAYER_MUNICIPS = [
    "cont_municipios",
    "raa_cen_ori_municipios",
    "raa_oci_municipios",
    "ram_municipios",
]

def load_district_shapes(cur):
    for i in range(len(LAYER_DISTRICTS)):
        with fiona.open(GPKG_PATH[i], layer=LAYER_DISTRICTS[i]) as src:
            for feat in src:
                props = feat["properties"]

                # CAOP district numeric code
                dist_code = props.get("dt")
                if not dist_code:
                    continue

                dist_code = int(dist_code)
                geom = shape(feat["geometry"]).wkt

                cur.execute(
                    """
                    INSERT OR REPLACE INTO DISTRICT_SHAPE
                    (DISTRICT_CODE, GEOM_WKT)
                    VALUES (?, ?)
                    """,
                    (dist_code, geom),
                )

def load_municipality_shapes(cur):
    for i in range(len(LAYER_MUNICIPS)):
        with fiona.open(GPKG_PATH[i], layer=LAYER_MUNICIPS[i]) as src:
            for feat in src:
                props = feat["properties"]

                mun_code = props.get("dtmn")
                if not mun_code:
                    continue

                mun_code = int(mun_code)
                geom = shape(feat["geometry"]).wkt

                cur.execute(
                    """
                    INSERT OR REPLACE INTO MUNICIPALITY_SHAPE
                    (MUNICIPALITY_CODE, GEOM_WKT)
                    VALUES (?, ?)
                    """,
                    (mun_code, geom),
                )

def main():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError("elections.db not found. Run etl.py first.")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    load_district_shapes(cur)
    load_municipality_shapes(cur)

    conn.commit()
    conn.close()

    print("✅ District geometry loaded")
    print("✅ Municipality geometry loaded")

if __name__ == "__main__":
    main()
