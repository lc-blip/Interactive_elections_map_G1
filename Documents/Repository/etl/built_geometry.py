import sqlite3
import fiona
from shapely.geometry import shape
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) #wheres the built-geometry; tells that PROJECT_ROTT its the parent
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..")) #its telling that root of built_geometry its ".." so OK
DB_FILE = os.path.join(PROJECT_ROOT, "db", "elections.db") #ABSOLUTE path to find the database!


#Have this to 2 defined so doesnt matter if the files are inside CAOP_* directories or outside
CAOP_PATH = [
    "CAOP_Continente_2024_1-gpkg",
    "CAOP_RAA_2024_1-gpkg",
    "CAOP_RAA_2024_1-gpkg",
    "CAOP_RAM_2024_1-gpkg",
]

GPKG_PATH = [
    "Continente_CAOP2024_1.gpkg",
    "ArqAcores_GCentral_GOriental_CAOP2024_1.gpkg",
    "ArqAcores_GOcidental_CAOP2024_1.gpkg",
    "ArqMadeira_CAOP2024_1.gpkg",
]

#checked in QGIS software, how the tables where defined
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

def find_gpkg_path(caop_dir, explicit_relative=None):
    base = os.path.join(PROJECT_ROOT, caop_dir)

    # 1) Try explicit path inside the CAOP directory
    if explicit_relative:
        candidate = os.path.join(base, explicit_relative)
        if os.path.exists(candidate):
            return candidate

    # 2) Try any .gpkg inside the CAOP directory
    if os.path.isdir(base):
        for name in os.listdir(base):
            if name.lower().endswith(".gpkg"):
                return os.path.join(base, name)

    # 3) Fallback: look for the same filename at the project root
    if explicit_relative:
        root_candidate = os.path.join(PROJECT_ROOT, explicit_relative)
        if os.path.exists(root_candidate):
            return root_candidate

    raise FileNotFoundError(
        f"No .gpkg found in {base} or at {os.path.join(PROJECT_ROOT, explicit_relative or '')}"
    )


def load_district_shapes(cur):
    for i in range(len(LAYER_DISTRICTS)):
        gpkg_file = find_gpkg_path(CAOP_PATH[i], GPKG_PATH[i])
        with fiona.open(gpkg_file, layer=LAYER_DISTRICTS[i]) as src:
            for feat in src:
                props = feat["properties"]
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
        gpkg_file = find_gpkg_path(CAOP_PATH[i], GPKG_PATH[i])
        with fiona.open(gpkg_file, layer=LAYER_MUNICIPS[i]) as src:
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
    cur.execute("PRAGMA foreign_keys = ON;")
    load_district_shapes(cur)
    load_municipality_shapes(cur)

    conn.commit()
    conn.close()

    print("✅ District geometry loaded ✅")
    print("✅ Municipality geometry loaded ✅")

if __name__ == "__main__":
    main()
