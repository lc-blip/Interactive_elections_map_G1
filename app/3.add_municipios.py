#!/usr/bin/env python3
import sqlite3
import tkinter as tk
from collections import defaultdict
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
SQLITE_DB = os.path.join(PROJECT_ROOT, "db", "elections.db")
CANVAS_W, CANVAS_H = 900, 900
TOP_H = int(CANVAS_H * 0.6)         
BOTTOM_H = CANVAS_H - TOP_H
AZORES_W = CANVAS_W // 2
MADEIRA_W = CANVAS_W // 2
PADDING = 20

BG_COLOR = "white"
OUTLINE_COLOR = "#A6A3A3"
OUTLINE_WIDTH = 1
REGION_COLORS = {
    "C": "#377eb8",
    "A": "#4daf4a",
    "M": "#ff7f00",
}

DEFAULT_FILL = "#999999"

PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#a65628", "#f781bf", "#999999", "#66c2a5", "#fc8d62",
    "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f", "#e5c494",
]

# ---------------------- WKT parsing (SAFE, exterior rings only) ----------------------

def parse_wkt_polygons(wkt: str):
    if not wkt:
        return []

    wkt = wkt.strip()
    wkt = _strip_srid(wkt)

    if wkt.upper().startswith("POLYGON"):
        content = _outer(wkt[wkt.find("("):])
        rings = _split_top(content)
        return [[_parse_ring(_outer(rings[0]))]]

    if wkt.upper().startswith("MULTIPOLYGON"):
        content = _outer(wkt[wkt.find("("):])
        polys = []
        for poly in _split_top(content):
            rings = _split_top(_outer(poly))
            polys.append([_parse_ring(_outer(rings[0]))])
        return polys

    return []

def _strip_srid(wkt):
    if wkt.upper().startswith("SRID="):
        return wkt.split(";", 1)[1]
    return wkt

def _outer(s):
    s = s.strip()
    if not s.startswith("("):
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

def _split_top(s):
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

def _parse_ring(s):
    pts = []
    for pair in s.split(","):
        x, y = pair.strip().split()[:2]
        pts.append((float(x), float(y)))
    return pts

# ---------------------- DB helper ----------------------
def q(sql, args=()):
    conn = sqlite3.connect(SQLITE_DB)
    try:
        cur = conn.cursor()
        cur.execute(sql, args)
        return cur.fetchall()
    finally:
        conn.close()

def fetch_districts():
    rows = q("""
        SELECT
            d.CODE,
            d.NAME,
            d.REGION,
            s.GEOM_WKT
        FROM DISTRICTS d
        JOIN DISTRICT_SHAPE s
          ON (
                s.DISTRICT_CODE = d.CODE
             OR (d.CODE = 30 AND s.DISTRICT_CODE BETWEEN 30 AND 39)
             OR (d.CODE = 40 AND s.DISTRICT_CODE BETWEEN 40 AND 49)
          )
        ORDER BY d.CODE
    """)

    out = {}
    for code, name, region, geom in rows:
        polys = parse_wkt_polygons(geom)
        if code not in out:
            out[code] = {
                "name": name,
                "region": region,
                "polys": []
            }
        out[code]["polys"].extend(polys)

    return out


def fetch_municipalities(district_code):
    if district_code == 30:
        where = "m.DISTRICT_CODE BETWEEN 30 AND 39"
        args = ()
    elif district_code == 40:
        where = "m.DISTRICT_CODE BETWEEN 40 AND 49"
        args = ()
    else:
        where = "m.DISTRICT_CODE = ?"
        args = (district_code,)

    rows = q(f"""
        SELECT m.CODE, m.NAME, s.GEOM_WKT
        FROM MUNICIPALITIES m
        JOIN MUNICIPALITY_SHAPE s ON s.MUNICIPALITY_CODE = m.CODE
        WHERE {where}
        ORDER BY m.NAME
    """, args)

    out = []
    for code, name, geom in rows:
        polys = parse_wkt_polygons(geom)
        out.append((code, name, polys))

    return out

def district_name_from_code(code):
    return q("SELECT NAME FROM DISTRICTS WHERE CODE = ?", (code,))[0][0]

# ---------------------- Geometry → Canvas ----------------------
def compute_bounds(polys):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for p in polys:
        for ring in p:
            for x, y in ring:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    return minx, miny, maxx, maxy

def make_projector(minx, miny, maxx, maxy, w, h):
    dx = maxx - minx or 1
    dy = maxy - miny or 1
    scale = min((w - 2*PADDING) / dx, (h - 2*PADDING) / dy)

    def proj(x, y):
        X = PADDING + (x - minx) * scale
        Y = h - (PADDING + (y - miny) * scale)
        return X, Y
    return proj

# ---------------------- App ----------------------
class App:
    def __init__(self):
        self.district_items= [] #uso no botao back
        self.root = tk.Tk()
        self.root.title("Portugal — Distritos e Municípios")
        self.root.configure(bg=BG_COLOR)

        self.header = tk.Frame(self.root, bg=BG_COLOR)
        self.header.pack(fill="x", padx=10, pady=10)

        self.title_lbl = tk.Label(self.header, text="", font=("Arial", 14, "bold"), bg=BG_COLOR)
        self.title_lbl.pack(side="left")

        self.back_btn = tk.Button(self.header, text="Back", state="disabled", command=self.on_back)
        self.back_btn.pack(side="right")

        self.canvas = tk.Canvas(self.root, width=CANVAS_W, height=CANVAS_H,
                                bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        self.level = "districts"
        self.selected_district = None

        self.draw_districts()
        self.root.mainloop()

    def clear(self):
        self.canvas.delete("all")

    # ---------------- Drawers ----------------
    def draw_districts(self):
        self.level = "districts"
        self.back_btn.config(state="disabled")
        self.title_lbl.config(text="Distritos")
        self.clear()
        self.district_items = []
        data = fetch_districts()
        cont = [(c, d) for c, d in data.items() if d["region"] == "C"]
        azor = [(c, d) for c, d in data.items() if d["region"] == "A"]
        made = [(c, d) for c, d in data.items() if d["region"] == "M"]

        self._draw_region(cont, 0, 0, CANVAS_W, TOP_H)
        print("Açores polys:", len(azor))
        print("Madeira polys:", len(made))
        self._draw_region(azor, 0, TOP_H, AZORES_W, BOTTOM_H)
        self._draw_region(made, AZORES_W, TOP_H, MADEIRA_W, BOTTOM_H)

    def _draw_region(self, items, ox, oy, w, h):


        if not items:
            return

        all_polys = []
        for _, info in items:
            for poly in info["polys"]:
                all_polys.append(poly)

        minx, miny, maxx, maxy = compute_bounds(all_polys)
        proj = make_projector(minx, miny, maxx, maxy, w, h)

        for code, info in items:
            for poly in info["polys"]:
                pts = []
                for x, y in poly[0]:
                    X, Y = proj(x, y)
                    pts.extend([X + ox, Y + oy + 10])

                pid = self.canvas.create_polygon(
                    *pts,
                    fill=REGION_COLORS.get(info["region"], DEFAULT_FILL),
                    outline=OUTLINE_COLOR,
                    width=OUTLINE_WIDTH
                )
                self.district_items.append(pid) # assim o botao tem memoria
                self.canvas.tag_bind(pid, "<Button-1>",
                    lambda e, c=code: self.on_click_district(c))

    def draw_municipalities(self, district_code):
        self.level = "municipalities"
        self.selected_district = district_code
        self.back_btn.config(state="normal")
        for item in self.district_items:
            self.canvas.itemconfigure(item, state="hidden")
        name = district_name_from_code(district_code)
        self.title_lbl.config(text=f"Municípios — {name}")
        self.clear()
               
        data = fetch_municipalities(district_code)
        all_polys = [p for _, _, polys in data for p in polys]

        minx, miny, maxx, maxy = compute_bounds(all_polys)
        proj = make_projector(minx, miny, maxx, maxy, CANVAS_W, CANVAS_H)

        for i, (_, name, polys) in enumerate(data):
            color = PALETTE[i % len(PALETTE)]
            for poly in polys:
                pts = []
                for x, y in poly[0]:
                    X, Y = proj(x, y)
                    pts.extend([X, Y])
                self.canvas.create_polygon(
                    *pts, fill=color, outline=OUTLINE_COLOR, width=OUTLINE_WIDTH
                )

    # ---------------- Events ----------------
    def on_click_district(self, code):
        self.draw_municipalities(code)

    def on_back(self):
        if self.level == "municipalities":
            self.draw_districts()

# ---------------------- main ----------------------
if __name__ == "__main__":
    App()
