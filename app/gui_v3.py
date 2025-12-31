#!/usr/bin/env python3
import sqlite3
import tkinter as tk
import os

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ================= CONFIG =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "elections.db")

BG_COLOR = "white"
OUTLINE_COLOR = "#000000"

REGION_COLORS = {
    "C": "#6baed6",   # Continente
    "A": "#74c476",   # Açores
    "M": "#fd8d3c",   # Madeira
}

MUNICIPAL_FILL = "#c6dbef"  # azul claro
BAR_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2"
]

# ================= DB =================

def q(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

# ================= GEOMETRY =================

def parse_wkt_polygons(wkt):
    if not wkt:
        return []

    if wkt.upper().startswith("SRID="):
        wkt = wkt.split(";", 1)[1]

    def outer(s):
        d, start = 0, None
        for i, c in enumerate(s):
            if c == "(":
                d += 1
                if d == 1:
                    start = i + 1
            elif c == ")":
                d -= 1
                if d == 0:
                    return s[start:i]
        return ""

    def split_top(s):
        out, d, last = [], 0, 0
        for i, c in enumerate(s):
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
            elif c == "," and d == 0:
                out.append(s[last:i])
                last = i + 1
        out.append(s[last:])
        return out

    def ring(s):
        return [(float(x), float(y))
                for x, y in (p.strip().split()[:2] for p in s.split(","))]

    polys = []
    if wkt.upper().startswith("POLYGON"):
        c = outer(wkt[wkt.find("("):])
        polys.append([ring(outer(split_top(c)[0]))])
    elif wkt.upper().startswith("MULTIPOLYGON"):
        c = outer(wkt[wkt.find("("):])
        for p in split_top(c):
            polys.append([ring(outer(split_top(outer(p))[0]))])
    return polys

def bounds(polys):
    xs, ys = [], []
    for poly in polys:
        for x, y in poly[0]:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)

def projector(minx, miny, maxx, maxy, w, h, pad=10):
    sx = (w - 2*pad) / (maxx - minx or 1)
    sy = (h - 2*pad) / (maxy - miny or 1)
    s = min(sx, sy)
    return lambda x, y: (
        pad + (x - minx) * s,
        h - (pad + (y - miny) * s)
    )

# ================= DATA =================

def fetch_districts():
    rows = q("""
        SELECT d.CODE, d.NAME, d.REGION, s.GEOM_WKT
        FROM DISTRICTS d
        JOIN DISTRICT_SHAPE s
          ON (
                s.DISTRICT_CODE = d.CODE
             OR (d.CODE = 30 AND s.DISTRICT_CODE BETWEEN 30 AND 39)
             OR (d.CODE = 40 AND s.DISTRICT_CODE BETWEEN 40 AND 49)
          )
    """)
    out = {}
    for c, n, r, g in rows:
        out.setdefault(c, {"name": n, "region": r, "polys": []})
        out[c]["polys"] += parse_wkt_polygons(g)
    return out

def fetch_municipalities(dist):
    if dist == 30:
        where, args = "DISTRICT_CODE BETWEEN 30 AND 39", ()
    elif dist == 40:
        where, args = "DISTRICT_CODE BETWEEN 40 AND 49", ()
    else:
        where, args = "DISTRICT_CODE = ?", (dist,)

    rows = q(f"""
        SELECT m.CODE, m.NAME, s.GEOM_WKT
        FROM MUNICIPALITIES m
        JOIN MUNICIPALITY_SHAPE s ON s.MUNICIPALITY_CODE = m.CODE
        WHERE {where}
    """, args)

    return [(c, n, parse_wkt_polygons(g)) for c, n, g in rows]

def votes_by_district(dist):
    return q("""
        SELECT v.DETAILED_NAME, SUM(v.VOTES)
        FROM VOTINGS v
        JOIN MUNICIPALITIES m ON m.CODE = v.MUNICIPALITY_CODE
        WHERE m.DISTRICT_CODE = ?
        GROUP BY v.DETAILED_NAME
        HAVING SUM(v.VOTES) > 0
        ORDER BY SUM(v.VOTES) DESC
    """, (dist,))

def votes_by_municipality(code):
    return q("""
        SELECT DETAILED_NAME, SUM(VOTES)
        FROM VOTINGS
        WHERE MUNICIPALITY_CODE = ?
        GROUP BY DETAILED_NAME
        HAVING SUM(VOTES) > 0
        ORDER BY SUM(VOTES) DESC
    """, (code,))

# ================= APP =================

class App:
    def __init__(self):
        self.level = "national"
        self.cur_fig = None

        self.root = tk.Tk()
        self.root.title("Resultados Eleitorais")
        self.root.geometry("1100x800")

        self.map_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.map_frame.pack(fill="both", expand=True)

        self.results_frame = tk.Frame(self.root, bg=BG_COLOR)

        self.canvas = tk.Canvas(self.map_frame, bg=BG_COLOR)
        self.canvas.pack(fill="both", expand=True)

        self.draw_national()
        self.root.mainloop()

    # ---------- MAP STATES ----------

    def draw_national(self):
        self.level = "national"
        self.results_frame.pack_forget()
        self.map_frame.pack(fill="both", expand=True)
        self.canvas.delete("all")

        data = fetch_districts()
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()

        layouts = {
            "C": (0, 0, w, int(h*0.7)),
            "A": (0, int(h*0.7), w//2, int(h*0.3)),
            "M": (w//2, int(h*0.7), w//2, int(h*0.3)),
        }

        for region, (ox, oy, rw, rh) in layouts.items():
            items = [d for d in data.values() if d["region"] == region]
            polys = [p for d in items for p in d["polys"]]
            if not polys:
                continue

            proj = projector(*bounds(polys), rw, rh)
            for d in items:
                for poly in d["polys"]:
                    pts = []
                    for x, y in poly[0]:
                        X, Y = proj(x, y)
                        pts += [X+ox, Y+oy]
                    pid = self.canvas.create_polygon(
                        *pts,
                        fill=REGION_COLORS[region],
                        outline=OUTLINE_COLOR
                    )
                    self.canvas.tag_bind(
                        pid, "<Button-1>",
                        lambda e, c=d, code=list(data.keys())[list(data.values()).index(d)]:
                            self.show_district(code)
                    )

    def show_district(self, dist):
        self.level = "district"
        self.map_frame.pack(fill="x")
        self.results_frame.pack(fill="both", expand=True)

        self.canvas.delete("all")
        data = fetch_municipalities(dist)

        polys = [p for _, _, ps in data for p in ps]
        proj = projector(*bounds(polys), self.canvas.winfo_width(), 200)

        for code, name, ps in data:
            for poly in ps:
                pts=[]
                for x,y in poly[0]:
                    X,Y = proj(x,y)
                    pts += [X,Y]
                pid = self.canvas.create_polygon(
                    *pts, fill=MUNICIPAL_FILL, outline="black"
                )
                self.canvas.tag_bind(
                    pid, "<Button-1>",
                    lambda e,c=code,n=name:
                        self.update_chart(f"{n}", votes_by_municipality(c))
                )

        self.update_chart("Resultados do Distrito", votes_by_district(dist))

    # ---------- CHART ----------

    def update_chart(self, title, rows):
        for w in self.results_frame.winfo_children():
            w.destroy()

        if self.cur_fig:
            plt.close(self.cur_fig)

        labels = [r[0] for r in rows[:10]]
        values = [r[1] for r in rows[:10]]

        fig, ax = plt.subplots(figsize=(6,4))
        bars = ax.barh(labels[::-1], values[::-1],
                        color=BAR_COLORS[:len(labels)][::-1])
        ax.set_title(title)
        ax.set_xlabel("Votos")

        self.cur_fig = fig
        canvas = FigureCanvasTkAgg(fig, master=self.results_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

# ================= RUN =================

if __name__ == "__main__":
    App()
