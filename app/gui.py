#!/usr/bin/env python3
import sqlite3
import tkinter as tk
import tkinter.ttk as ttk
import os

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ====================== CONFIG ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "elections.db")

CANVAS_W, CANVAS_H = 850, 850
TOP_H = int(CANVAS_H * 0.6)
BOTTOM_H = CANVAS_H - TOP_H
AZORES_W = CANVAS_W // 2
MADEIRA_W = CANVAS_W // 2
PADDING = 20

BG_COLOR = "white"
OUTLINE_COLOR = "#222222"
OUTLINE_WIDTH = 1

REGION_COLORS = {
    "C": "#377eb8",   # Continente
    "A": "#4daf4a",   # Açores
    "M": "#ff7f00",   # Madeira
}

MUNICIPALITY_FILL = "#8fbce6"   # azul claro
MUNICIPALITY_ALPHA = 0.75

BAR_COLORS = [
    "#1b9e77", "#d95f02", "#7570b3", "#e7298a",
    "#66a61e", "#e6ab02", "#a6761d", "#666666"
]

# ====================== DB ======================

def q(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

# ====================== GEOMETRY ======================

def parse_wkt_polygons(wkt):
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
        return [(float(x), float(y))
                for x, y in (p.strip().split()[:2] for p in s.split(","))]

    polys = []

    if wkt.upper().startswith("POLYGON"):
        c = outer(wkt[wkt.find("("):])
        polys.append([ring(outer(split_top(c)[0]))])

    elif wkt.upper().startswith("MULTIPOLYGON"):
        c = outer(wkt[wkt.find("("):])
        for p in split_top(c):
            rings = split_top(outer(p))
            polys.append([ring(outer(rings[0]))])

    return polys

def bounds(polys):
    xs, ys = [], []
    for poly in polys:
        for x, y in poly[0]:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)

def projector(minx, miny, maxx, maxy, w, h):
    scale = min((w - 2*PADDING)/(maxx-minx or 1),
                (h - 2*PADDING)/(maxy-miny or 1))
    return lambda x, y: (
        PADDING + (x-minx)*scale,
        h - (PADDING + (y-miny)*scale)
    )

# ====================== DATA ======================

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
        ORDER BY d.CODE
    """)
    out = {}
    for c, n, r, g in rows:
        out.setdefault(c, {"name": n, "region": r, "polys": []})
        out[c]["polys"] += parse_wkt_polygons(g)
    return out

def fetch_municipalities(dist):
    if dist == 30:
        where, args = "m.DISTRICT_CODE BETWEEN 30 AND 39", ()
    elif dist == 40:
        where, args = "m.DISTRICT_CODE BETWEEN 40 AND 49", ()
    else:
        where, args = "m.DISTRICT_CODE = ?", (dist,)

    rows = q(f"""
        SELECT m.CODE, m.NAME, s.GEOM_WKT
        FROM MUNICIPALITIES m
        JOIN MUNICIPALITY_SHAPE s ON s.MUNICIPALITY_CODE = m.CODE
        WHERE {where}
        ORDER BY m.NAME
    """, args)

    return [(c, n, parse_wkt_polygons(g)) for c, n, g in rows]

def votes_by_district(dist):
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

def votes_by_municipality(code):
    return q("""
        SELECT DETAILED_NAME, SUM(VOTES), SUM(MANDATES)
        FROM VOTINGS
        WHERE MUNICIPALITY_CODE = ?
        GROUP BY DETAILED_NAME
        HAVING SUM(VOTES) > 0
        ORDER BY SUM(VOTES) DESC
    """, (code,))

# ====================== APP ======================

class App:
    def __init__(self):
        self.level = "districts"
        self.current_fig = None
        self.current_canvas = None

        self.root = tk.Tk()
        self.root.title("Portugal — Resultados Eleitorais")

        # Header
        header = tk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=10)

        self.title_lbl = tk.Label(header, font=("Arial", 14, "bold"))
        self.title_lbl.pack(side="left")

        self.back_btn = tk.Button(header, text="Back",
                                  state="disabled", command=self.on_back)
        self.back_btn.pack(side="right")

        # Layout
        main = tk.Frame(self.root)
        main.pack(fill="both", expand=True)

        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)

        self.map_frame = tk.Frame(main)
        self.map_frame.grid(row=0, column=0, sticky="nsew")

        self.results_frame = tk.Frame(main)
        self.results_frame.grid(row=0, column=1, sticky="nsew")

        self.canvas = tk.Canvas(self.map_frame,
                                width=CANVAS_W, height=CANVAS_H,
                                bg="white")
        self.canvas.pack(fill="both", expand=True)

        self.draw_districts()
        self.root.mainloop()

    # ---------- MAP ----------

    def draw_districts(self):
        self.level = "districts"
        self.back_btn.config(state="disabled")
   #     self.title_lbl.config(text="Distritos")
        self.canvas.delete("all")
        self.clear_results()

        data = fetch_districts()

        for region, ox, oy, w, h in [
            ("C", 0, 0, CANVAS_W, TOP_H),
            ("A", 0, TOP_H, AZORES_W, BOTTOM_H),
            ("M", AZORES_W, TOP_H, MADEIRA_W, BOTTOM_H),
        ]:
            items = [(c, d) for c, d in data.items() if d["region"] == region]
            if not items:
                continue

            all_polys = [p for _, d in items for p in d["polys"]]
            proj = projector(*bounds(all_polys), w, h)

            for code, info in items:
                for poly in info["polys"]:
                    pts = []
                    for x, y in poly[0]:
                        X, Y = proj(x, y)
                        pts += [X + ox, Y + oy]

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
        self.level = "municipalities"
        self.back_btn.config(state="normal")
        self.title_lbl.config(text=f"Município:{name}")

        self.update_results(f"{name}", votes_by_district(code))
        self.draw_municipalities(code)

    def draw_municipalities(self, dist):
        self.canvas.delete("all")
        data = fetch_municipalities(dist)
        proj = projector(*bounds([p for _,_,ps in data for p in ps]),
                         CANVAS_W, CANVAS_H)

        for code, name, polys in data:
            for poly in polys:
                pts = []
                for x, y in poly[0]:
                    X, Y = proj(x, y)
                    pts += [X, Y]

                pid = self.canvas.create_polygon(
                    *pts,
                    fill=MUNICIPALITY_FILL,
                    outline=OUTLINE_COLOR,
                    width=1,
                    stipple="gray50"
                )
                self.canvas.tag_bind(
                    pid, "<Button-1>",
                    lambda e, c=code, n=name:
                        self.update_results(f"Resultados — {n}",
                                          votes_by_municipality(c))
                )

    # ---------- RESULTS ----------

    def clear_results(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        if self.current_fig:
            plt.close(self.current_fig)
            self.current_fig = None

    def update_results(self, title, rows):
        # 1. Clear previous widgets and explicitly close Matplotlib figures to save memory
        self.clear_results() 
        if self.current_fig:
            plt.close(self.current_fig) # Explicitly close the figure 

        if not rows:
            tk.Label(self.results_frame, text="Sem dados para esta seleção").pack()
            return

        # 2. Create the Table (Treeview) [cite: 41]
        # In your SQL, 'rows' should now be: (Name, Votes, Mandates)
        table_frame = tk.Frame(self.results_frame)
        table_frame.pack(fill="x", padx=10, pady=5)

        columns = ("party", "votes", "seats")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        
        self.tree.heading("party", text="Partido / Coligação")
        self.tree.heading("votes", text="Votos")
        self.tree.heading("seats", text="Mandatos")
        
        self.tree.column("party", width=200)
        self.tree.column("votes", width=80, anchor="e")
        self.tree.column("seats", width=80, anchor="center")

        for r in rows:
            # Assuming r is (Detailed_Name, Votes, Mandates)
            self.tree.insert("", "end", values=r)
        
        self.tree.pack(fill="x", expand=True)

        # 3. Create the Chart [cite: 41, 46]
        labels = [r[0] for r in rows[:10]]  # Top 10 for readability
        votes = [r[1] for r in rows[:10]]

        # Use a cleaner Object-Oriented approach for Matplotlib
        fig, ax = plt.subplots(figsize=(4.5, 4))
        self.current_fig = fig 
        
        colors = BAR_COLORS[:len(labels)]
        ax.barh(labels[::-1], votes[::-1], color=colors[::-1])
        ax.set_title(f"Distribuição de Votos: {title}", fontsize=10)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.results_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
    # ---------- NAV ----------

    def on_back(self):
        if self.level == "municipalities":
            self.draw_districts()

# ====================== RUN ======================

if __name__ == "__main__":
    App()
