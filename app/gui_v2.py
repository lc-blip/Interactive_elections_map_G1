#!/usr/bin/env python3
import os
import sqlite3
import tkinter as tk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ================= CONFIG =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "elections.db")

MAP_W, MAP_H = 900, 250          # mapa pequeno (1/6)
GRAPH_W, GRAPH_H = 900, 650      # gráfico grande (5/6)
PADDING = 20

BG_COLOR = "white"
OUTLINE_COLOR = "#222222"

REGION_COLORS = {
    "C": "#4c72b0",   # Continente
    "A": "#55a868",   # Açores
    "M": "#dd8452",   # Madeira
}

MUNICIPAL_FILL = "#4c72b0"
MUNICIPAL_ALPHA = 0.35

PARTY_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

# ================= DB =================

def q(sql, args=()):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, args)
        return cur.fetchall()

# ================= GEOMETRY =================

def parse_wkt(wkt):
    if not wkt:
        return []

    if wkt.upper().startswith("SRID="):
        wkt = wkt.split(";", 1)[1]

    def outer(s):
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
        return ""

    def split_top(s):
        out, depth, last = [], 0, 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(s[last:i].strip())
                last = i + 1
        out.append(s[last:].strip())
        return out

    def ring(s):
        return [(float(x), float(y)) for x, y in
                (p.strip().split()[:2] for p in s.split(","))]

    polys = []

    if wkt.upper().startswith("POLYGON"):
        c = outer(wkt[wkt.find("("):])
        polys.append(ring(outer(split_top(c)[0])))

    elif wkt.upper().startswith("MULTIPOLYGON"):
        c = outer(wkt[wkt.find("("):])
        for p in split_top(c):
            polys.append(ring(outer(split_top(outer(p))[0])))

    return polys

def bounds(polys):
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    return min(xs), min(ys), max(xs), max(ys)

def projector(minx, miny, maxx, maxy, w, h):
    scale = min((w - 2*PADDING)/(maxx-minx or 1),
                (h - 2*PADDING)/(maxy-miny or 1))
    return lambda x, y: (
        PADDING + (x - minx) * scale,
        h - (PADDING + (y - miny) * scale)
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
        out[c]["polys"] += parse_wkt(g)
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

    return [(c, n, parse_wkt(g)) for c, n, g in rows]

def votes_district(dist):
    if dist == 30:
        where, args = "m.DISTRICT_CODE BETWEEN 30 AND 39", ()
    elif dist == 40:
        where, args = "m.DISTRICT_CODE BETWEEN 40 AND 49", ()
    else:
        where, args = "m.DISTRICT_CODE = ?", (dist,)

    return q(f"""
        SELECT v.DETAILED_NAME, SUM(v.VOTES)
        FROM VOTINGS v
        JOIN MUNICIPALITIES m ON m.CODE = v.MUNICIPALITY_CODE
        WHERE {where}
        GROUP BY v.DETAILED_NAME
        HAVING SUM(v.VOTES) > 0
        ORDER BY SUM(v.VOTES) DESC
    """, args)

def votes_municipality(code):
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
        self.root = tk.Tk()
        self.root.title("Portugal — Resultados Eleitorais")
        self.root.configure(bg=BG_COLOR)

        self.canvas = tk.Canvas(self.root, width=MAP_W, height=MAP_H,
                                bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack()

        self.graph_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.graph_frame.pack(fill="both", expand=True)

        self.fig = None
        self.fig_canvas = None
        self.tooltip = None

        self.level = "districts"
        self.draw_districts()
        self.root.mainloop()

    # ---------- MAP ----------

    def draw_districts(self):
        self.level = "districts"
        self.canvas.delete("all")
        data = fetch_districts()

        for region in ("C", "A", "M"):
            items = [(c, d) for c, d in data.items() if d["region"] == region]
            if not items:
                continue

            all_polys = [p for _, d in items for p in d["polys"]]
            proj = projector(*bounds(all_polys), MAP_W, MAP_H)

            for code, info in items:
                for poly in info["polys"]:
                    pts = []
                    for x, y in poly:
                        X, Y = proj(x, y)
                        pts += [X, Y]

                    pid = self.canvas.create_polygon(
                        *pts,
                        fill=REGION_COLORS[region],
                        outline=OUTLINE_COLOR
                    )
                    self.canvas.tag_bind(
                        pid, "<Button-1>",
                        lambda e, c=code, n=info["name"]:
                            self.show_district(c, n)
                    )

    def show_district(self, code, name):
        self.draw_municipalities(code)
        self.update_chart(f"Resultados — {name}", votes_district(code))

    def draw_municipalities(self, dist):
        self.canvas.delete("all")
        data = fetch_municipalities(dist)
        all_polys = [p for _, _, ps in data for p in ps]
        proj = projector(*bounds(all_polys), MAP_W, MAP_H)

        for code, name, polys in data:
            for poly in polys:
                pts = []
                for x, y in poly:
                    X, Y = proj(x, y)
                    pts += [X, Y]

                pid = self.canvas.create_polygon(
                    *pts,
                    fill=MUNICIPAL_FILL,
                    outline="black",
                    stipple="gray50"
                )
                self.canvas.tag_bind(
                    pid, "<Button-1>",
                    lambda e, c=code, n=name:
                        self.update_chart(f"Resultados — {n}",
                                          votes_municipality(c))
                )

    # ---------- GRAPH ----------

    def update_chart(self, title, rows):
        if self.fig:
            plt.close(self.fig)
            self.fig_canvas.get_tk_widget().destroy()

        labels = [r[0] for r in rows]
        values = [r[1] for r in rows]

        self.fig, ax = plt.subplots(figsize=(9, 6))
        bars = ax.barh(
            labels[::-1],
            values[::-1],
            color=PARTY_COLORS[:len(labels)][::-1]
        )

        ax.set_title(title)
        ax.set_xlabel("Votos")
        ax.set_ylabel("")
        self.fig.tight_layout()

        self.fig_canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.fig_canvas.draw()
        self.fig_canvas.get_tk_widget().pack(fill="both", expand=True)

        self._bind_tooltips(ax, bars, labels[::-1], values[::-1])

    def _bind_tooltips(self, ax, bars, labels, values):
        tooltip = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 0),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="white"),
            arrowprops=None,
            visible=False
        )

        def on_move(event):
            if event.inaxes != ax:
                tooltip.set_visible(False)
                self.fig_canvas.draw_idle()
                return

            for bar, label, value in zip(bars, labels, values):
                if bar.contains(event)[0]:
                    tooltip.xy = (value, bar.get_y() + bar.get_height()/2)
                    tooltip.set_text(f"{label}\n{value} votos")
                    tooltip.set_visible(True)
                    self.fig_canvas.draw_idle()
                    return

            tooltip.set_visible(False)
            self.fig_canvas.draw_idle()

        self.fig.canvas.mpl_connect("motion_notify_event", on_move)

# ================= RUN =================

if __name__ == "__main__":
    App()
