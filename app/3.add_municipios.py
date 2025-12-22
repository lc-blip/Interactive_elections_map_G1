#!/usr/bin/env python3
import sqlite3
import tkinter as tk

# ---------------------- Config ----------------------
SQLITE_DB   = "../scripts/geom_db/geometry_real.db"

# Tabelas e colunas
T_DISTRICTS = "districts"
D_NAME      = "name"
D_REGION    = "region" 
D_GEOM      = "geom"

T_MUNS      = "municipalities"
M_NAME      = "name"
M_DIST_ISL  = "district"
M_GEOM      = "geom"

""" Nao temos, nem vamos ter
T_PARISH    = "parishes"
P_NAME      = "name"
P_MUN_NAME  = "municipality_name"
P_DIST_ISL  = "district_island"
P_GEOM      = "geom"
"""
# Render


CANVAS_W, CANVAS_H = 900, 900
TOP_H = int(CANVAS_H * 0.75)
BOTTOM_H = CANVAS_H - TOP_H

AZORES_W = CANVAS_W // 2
MADEIRA_W = CANVAS_W // 2
PADDING = 20
BG_COLOR = "white"
OUTLINE_COLOR = "#A6A3A3"
OUTLINE_WIDTH = 1

REGION_COLORS = {
    "Continent": "#377eb8",
    "Açores":    "#4daf4a",
    "Madeira":   "#ff7f00",
}
DEFAULT_FILL = "#999999"

PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628",
    "#f781bf", "#999999", "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3", "#1b9e77", "#d95f02"
]

# ---------------------- WKT parsing ----------------------
def _strip_srid_prefix(s: str) -> str:
    s = (s or "").strip()
    if s.upper().startswith("SRID="):
        i = s.find(";")
        if i != -1:
            return s[i+1:].lstrip()
    return s

def _read_type_and_rest(s: str):
    s = s.lstrip()
    up = s.upper()
    for t in ("MULTIPOLYGON", "POLYGON", "GEOMETRYCOLLECTION"):
        if up.startswith(t):
            rest = s[len(t):].lstrip()
            rup = rest.upper()
            if rup.startswith("ZM"):
                rest = rest[2:].lstrip()
            elif rup[:1] in ("Z", "M"):
                rest = rest[1:].lstrip()
            return t, rest
    raise ValueError(f"Unsupported WKT type: {s[:40]}")

def _outer_content(s: str) -> str:
    s = s.lstrip()
    if not s or s[0] != "(":
        raise ValueError("Expected '('")
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[start:i]
    raise ValueError("Unbalanced parentheses")

def _split_top_level(s: str):
    parts, depth, last = [], 0, 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[last:i].strip())
            last = i + 1
    parts.append(s[last:].strip())
    return parts

def _parse_ring(r: str):
    pts = []
    for pair in r.strip().split(","):
        xy = pair.strip().split()
        if len(xy) < 2:
            continue
        x, y = float(xy[0]), float(xy[1])
        pts.append((x, y))
    return pts

def _parse_polygon_content(poly_content: str):
    rings = []
    for ring_block in _split_top_level(poly_content):
        ring_coords = _outer_content(ring_block)
        rings.append(_parse_ring(ring_coords))
    return rings

def parse_wkt_polygons(wkt: str):
    if not wkt or not wkt.strip():
        return []
    s = _strip_srid_prefix(wkt)
    gtype, rest = _read_type_and_rest(s)
    if rest.upper().startswith("EMPTY"):
        return []
    if gtype == "POLYGON":
        return [_parse_polygon_content(_outer_content(rest))]
    if gtype == "MULTIPOLYGON":
        content = _outer_content(rest)
        polys = []
        for poly_blk in _split_top_level(content):
            polys.append(_parse_polygon_content(_outer_content(poly_blk)))
        return polys
    if gtype == "GEOMETRYCOLLECTION":
        content = _outer_content(rest)
        polys = []
        for comp in _split_top_level(content):
            try:
                polys.extend(parse_wkt_polygons(comp))
            except Exception:
                pass
        return polys
    return []

# ---------------------- DB helpers ----------------------
def q(sql, args=()):
    conn = sqlite3.connect(SQLITE_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        rows = cur.fetchall()
    finally:
        conn.close()
    return rows

def fetch_districts():
    rows = q(f"""
        SELECT {D_NAME}, {D_REGION}, {D_GEOM}
        FROM {T_DISTRICTS}
        ORDER BY {D_NAME}
    """)
    out = []
    for name, region, geom in rows:
        polys = parse_wkt_polygons(geom)
        out.append((str(name), str(region), polys))
    return out

def fetch_municipalities(district_name):
    rows = q(f"""
        SELECT {M_NAME}, {M_GEOM}
        FROM {T_MUNS}
        WHERE {M_DIST_ISL} = ?
        ORDER BY {M_NAME}
    """, (district_name,))
    out = []
    for name, wkt in rows:
        polys = parse_wkt_polygons(wkt or "")
        out.append((str(name), polys))
    return out


"""
def fetch_parishes(district_name, municipality_name):
    rows = q(f""""""
        SELECT {P_NAME}, {P_GEOM}
        FROM {T_PARISH}
        WHERE {P_DIST_ISL} = ? AND {P_MUN_NAME} = ?
        ORDER BY {P_NAME}
    """""", (district_name, municipality_name))
    out = []
    for name, wkt in rows:
        polys = parse_wkt_polygons(wkt or "")
        out.append((str(name), polys))
    return out"""

# ---------------------- Geometry -> Canvas ----------------------
def compute_bounds(list_of_polys):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for polys in list_of_polys:
        for rings in polys:
            if not rings:
                continue
            for x, y in rings[0]:
                if x < minx: minx = x
                if y < miny: miny = y
                if x > maxx: maxx = x
                if y > maxy: maxy = y
    if minx == float("inf"):
        raise RuntimeError("No coordinates to compute bounds.")
    return (minx, miny, maxx, maxy)

def make_transform(minx, miny, maxx, maxy, w, h, pad):
    dx = maxx - minx or 1.0
    dy = maxy - miny or 1.0
    scale = min((w - 2*pad) / dx, (h - 2*pad) / dy)
    def project(x, y):
        X = pad + (x - minx) * scale
        Y = h - pad - (y - miny) * scale  # inverter Y (origem no topo)
        return (X, Y)
    return project

def draw_polygon(canvas, pts, fill, outline=OUTLINE_COLOR, width=OUTLINE_WIDTH):
    if len(pts) >= 6:
        return canvas.create_polygon(*pts, fill=fill, outline=outline, width=width)

# ---------------------- App ----------------------
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Portugal — Drill-down (EPSG:3857) — SQLite")
        self.root.configure(bg=BG_COLOR)

        self.header = tk.Frame(self.root, bg=BG_COLOR)
        self.header.pack(fill="x", padx=10, pady=(10, 0))

        self.title_lbl = tk.Label(self.header, text="", bg=BG_COLOR, font=("Arial", 14, "bold"))
        self.title_lbl.pack(side="left")

        self.back_btn = tk.Button(self.header, text="Back", command=self.on_back, state="disabled")
        self.back_btn.pack(side="right")

        self.canvas = tk.Canvas(self.root, width=CANVAS_W, height=CANVAS_H,
                                background=BG_COLOR, highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # Navegação
        self.level = "districts"  # "districts" -> "municipalities" -> "parishes"
        self.selected_district = None
        self.selected_municipality = None

        self.draw_districts()

        self.root.mainloop()

    def clear_canvas(self):
        self.canvas.delete("all")
    # ---------- drawers ----------
    def draw_districts(self):
        self.level = "districts"
        self.selected_district = None
        self.selected_municipality = None
        self.back_btn.config(state="disabled")
        self.title_lbl.config(text="Distritos")

        self.canvas.delete("all")

        data = fetch_districts()  # [(name, region, polys)]
    # separar por região
        cont = [(n, p) for n, r, p in data if r == "Continente"]
        azor = [(n, p) for n, r, p in data if "Açores" in r]
        made = [(n, p) for n, r, p in data if r == "Madeira"]

        # -------- CONTINENTE (topo) --------
        if cont:
            list_polys = [p for _, p in cont if p]
            minx, miny, maxx, maxy = compute_bounds(list_polys)
            project = make_transform(
                minx, miny, maxx, maxy,
                CANVAS_W, TOP_H, PADDING
            )

            for name, polys in cont:
                for rings in polys:
                    if not rings:
                        continue
                    pts = []
                    for x, y in rings[0]:
                        X, Y = project(x, y)
                        pts.extend([X, Y])
                    pid = draw_polygon(
                        self.canvas, pts,
                        fill=REGION_COLORS.get("Continent", DEFAULT_FILL)
                    )
                    if pid:
                        self.canvas.tag_bind(
                            pid, "<Button-1>",
                            lambda e, n=name: self.on_click_district(n)
                        )

        # -------- AÇORES (baixo esquerda) --------
        if azor:
            list_polys = [p for _, p in azor if p]
            minx, miny, maxx, maxy = compute_bounds(list_polys)
            project = make_transform(
                minx, miny, maxx, maxy,
                AZORES_W, BOTTOM_H, PADDING
            )

            for name, polys in azor:
                for rings in polys:
                    if not rings:
                        continue
                    pts = []
                    for x, y in rings[0]:
                        X, Y = project(x, y)
                        pts.extend([X, Y + TOP_H])
                    draw_polygon(
                        self.canvas, pts,
                        fill=REGION_COLORS.get("Açores", DEFAULT_FILL)
                    )

        # -------- MADEIRA (baixo direita) --------
        if made:
            list_polys = [p for _, p in made if p]
            minx, miny, maxx, maxy = compute_bounds(list_polys)
            project = make_transform(
                minx, miny, maxx, maxy,
                MADEIRA_W, BOTTOM_H, PADDING
            )

            for name, polys in made:
                for rings in polys:
                    if not rings:
                        continue
                    pts = []
                    for x, y in rings[0]:
                        X, Y = project(x, y)
                        pts.extend([X + AZORES_W, Y + TOP_H])
                    draw_polygon(
                        self.canvas, pts,
                        fill=REGION_COLORS.get("Madeira", DEFAULT_FILL)
                    )


    def draw_municipalities(self, district_name):
            self.level = "municipalities"
            self.selected_district = district_name
            self.selected_municipality = None
            self.back_btn.config(state="normal")
            self.title_lbl.config(text=f"Municípios — {district_name}")

            self.clear_canvas()
            data = fetch_municipalities(district_name)  # [(name, polys)]
            if not data:
                self.canvas.create_text(CANVAS_W/2, CANVAS_H/2,
                                        text=f"Sem municípios para '{district_name}'.",
                                        fill="red")
                return

            list_polys = [polys for _, polys in data if polys]
            minx, miny, maxx, maxy = compute_bounds(list_polys)
            project = make_transform(minx, miny, maxx, maxy, CANVAS_W, CANVAS_H, PADDING)

            for i, (name, polys) in enumerate(data):
                fill = PALETTE[i % len(PALETTE)]
                for rings in polys:
                    if not rings:
                        continue
                    ext = rings[0]
                    pts_ext = []
                    for x, y in ext:
                        X, Y = project(x, y)
                        pts_ext.extend([X, Y])
                    pid = draw_polygon(self.canvas, pts_ext, fill=fill)
                    if pid:
                        # Click município -> freguesias
                        self.canvas.tag_bind(pid, "<Button-1>",
                                            lambda e, n=name: self.show_votes(n))
                    for hole in rings[1:]:
                        pts_h = []
                        for x, y in hole:
                            X, Y = project(x, y)
                            pts_h.extend([X, Y])
                        draw_polygon(self.canvas, pts_h, fill=BG_COLOR)
    # ---------- events ----------
    def on_click_district(self, district_name):
        self.draw_municipalities(district_name)
    def on_back(self):
           # if self.level == "parishes":
           #     # volta a municípios do distrito selecionado
            #    self.draw_municipalities(self.selected_district)
            if self.level == "municipalities":
                # volta a distritos
                self.clear_canvas()
                self.draw_districts()
            else:
                pass
    def show_votes(municipy_name):
        pass
    
"""
    def draw_parishes(self, district_name, municipality_name):
            self.level = "parishes"
            self.selected_district = district_name
            self.selected_municipality = municipality_name
            self.back_btn.config(state="normal")
            self.title_lbl.config(text=f"Freguesias — {municipality_name} ({district_name})")

            self.clear_canvas()
            data = fetch_parishes(district_name, municipality_name)  # [(name, polys)]
            if not data:
                self.canvas.create_text(CANVAS_W/2, CANVAS_H/2,
                                        text=f"Sem freguesias para '{municipality_name}'.",
                                        fill="red")
                return

            list_polys = [polys for _, polys in data if polys]
            minx, miny, maxx, maxy = compute_bounds(list_polys)
            project = make_transform(minx, miny, maxx, maxy, CANVAS_W, CANVAS_H, PADDING)

            for i, (name, polys) in enumerate(data):
                fill = PALETTE[i % len(PALETTE)]
                for rings in polys:
                    if not rings:
                        continue
                    ext = rings[0]
                    pts_ext = []
                    for x, y in ext:
                        X, Y = project(x, y)
                        pts_ext.extend([X, Y])
                    draw_polygon(self.canvas, pts_ext, fill=fill)
                    for hole in rings[1:]:
                        pts_h = []
                        for x, y in hole:
                            X, Y = project(x, y)
                            pts_h.extend([X, Y])
                        draw_polygon(self.canvas, pts_h, fill=BG_COLOR)
"""


"""
    def on_click_municipality(self, municipality_name):
            if not self.selected_district:
                return
            self.draw_parishes(self.selected_district, municipality_name)
"""

# ---------------------- main ----------------------
if __name__ == "__main__":
    App()