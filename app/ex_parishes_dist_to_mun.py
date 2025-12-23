#!/usr/bin/env python3
import sqlite3
import tkinter as tk

# ---------------------- Config ----------------------
SQLITE_DB   = "portugal_geoms.db"

# Tabelas e colunas
T_DISTRICTS = "districts"
D_NAME      = "name"
D_REGION    = "region"
D_GEOM      = "geom"

T_MUNS      = "municipalities"
M_NAME      = "name"
M_DIST_ISL  = "district_island"
M_GEOM      = "geom"

T_PARISH    = "parishes"
P_NAME      = "name"
P_MUN_NAME  = "municipality_name"
P_DIST_ISL  = "district_island"
P_GEOM      = "geom"

# Render
CANVAS_W, CANVAS_H = 900, 900
PADDING = 20
BG_COLOR = "white"
OUTLINE_COLOR = "#222222"
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
        ORDER BY {D_REGION}, {D_NAME}
    """)
    out = []
    for name, region, wkt in rows:
        polys = parse_wkt_polygons(wkt or "")
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

def fetch_parishes(district_name, municipality_name):
    rows = q(f"""
        SELECT {P_NAME}, {P_GEOM}
        FROM {T_PARISH}
        WHERE {P_DIST_ISL} = ? AND {P_MUN_NAME} = ?
        ORDER BY {P_NAME}
    """, (district_name, municipality_name))
    out = []
    for name, wkt in rows:
        polys = parse_wkt_polygons(wkt or "")
        out.append((str(name), polys))
    return out

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

        data = fetch_districts()  # [(name, region, polys)]
        if not data:
            self.canvas.create_text(CANVAS_W/2, CANVAS_H/2, text="Sem distritos.", fill="red")
            return

        # Bounds
        list_polys = [polys for _, _, polys in data if polys]
        minx, miny, maxx, maxy = compute_bounds(list_polys)
        project = make_transform(minx, miny, maxx, maxy, CANVAS_W, CANVAS_H, PADDING)

        # Legenda por região
        legend_y = 10
        tk.Label(self.canvas, text="Distritos — EPSG:3857", bg=BG_COLOR,
                 font=("Arial", 12, "bold")).place(x=10, y=legend_y)
        legend_y += 22
        for label in ("Continent", "Açores", "Madeira"):
            color = REGION_COLORS.get(label, DEFAULT_FILL)
            self.canvas.create_rectangle(10, legend_y+2, 26, legend_y+18, fill=color, outline="#444")
            self.canvas.create_text(36, legend_y+10, text=label, anchor="w", fill="#333", font=("Arial", 10))
            legend_y += 18

        # Desenho
        for name, region, polys in data:
            fill = REGION_COLORS.get(region, DEFAULT_FILL)
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
                    # Binding: click distrito -> municípios
                    self.canvas.tag_bind(pid, "<Button-1>",
                                         lambda e, n=name: self.on_click_district(n))
                # Buracos (pinta com BG)
                for hole in rings[1:]:
                    pts_h = []
                    for x, y in hole:
                        X, Y = project(x, y)
                        pts_h.extend([X, Y])
                    draw_polygon(self.canvas, pts_h, fill=BG_COLOR)

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
                                         lambda e, n=name: self.on_click_municipality(n))
                for hole in rings[1:]:
                    pts_h = []
                    for x, y in hole:
                        X, Y = project(x, y)
                        pts_h.extend([X, Y])
                    draw_polygon(self.canvas, pts_h, fill=BG_COLOR)

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

    # ---------- events ----------
    def on_click_district(self, district_name):
        self.draw_municipalities(district_name)

    def on_click_municipality(self, municipality_name):
        if not self.selected_district:
            return
        self.draw_parishes(self.selected_district, municipality_name)

    def on_back(self):
        if self.level == "parishes":
            # volta a municípios do distrito selecionado
            self.draw_municipalities(self.selected_district)
        elif self.level == "municipalities":
            # volta a distritos
            self.clear_canvas()
            self.draw_districts()
        else:
            # já está no topo
            pass

# ---------------------- main ----------------------
if __name__ == "__main__":
    App()