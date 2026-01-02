import sqlite3
import tkinter as tk
import tkinter.ttk as ttk
import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


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


def q(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows


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


class App:
    def __init__(self):
        self.level = "districts"
        self.current_fig = None
        
        self.root = tk.Tk()
        self.root.title("Portugal — Resultados Eleitorais")
        # tamanho inicial da janela
        self.root.geometry("1400x900")

        # HEADER (o que fica sempre definido)
        header = tk.Frame(self.root, bg="#f0f0f0", height=50)
        header.pack(fill="x", side="top")

        self.back_btn = tk.Button(header, text=" Back ",
                                 state="disabled", command=self.on_back,
                                 font=("Arial", 10))
        self.back_btn.pack(side="left", padx=10, pady=10)

        self.title_lbl = tk.Label(header, font=("Arial", 16, "bold"), bg="#f0f0f0")
        self.title_lbl.pack(side="left", expand=True)
        self.export_button = tk.Button(header, text = " CSV ", command=self.on_export_csv, font=("Arial", 10), state="disabled")
        self.export_button.pack(side="right", padx=10, pady=10)

        # Content Area
        self.main_container = tk.Frame(self.root)
        self.main_container.pack(fill="both", expand=True)

#divisão mapa-resultados:
        # Mapa (Esquerda)
        self.map_frame = tk.Frame(self.main_container, bg="white", borderwidth=1, relief="sunken")
        self.map_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(self.map_frame, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Resultados (Direita) - Largura fixa para não "empurrar" o mapa
        self.results_frame = tk.Frame(self.main_container, width=500)
        self.results_frame.pack(side="right", fill="both", padx=10, pady=5)
        self.results_frame.pack_propagate(False) # Mantém a largura fixa

        self.root.update()
        self.draw_districts()
        self.root.mainloop()

    def draw_districts(self):
        self.level = "districts"
        self.back_btn.config(state="disabled") #neste nivel nao se usa BACK button
        self.title_lbl.config(text="Portugal — Mapa Geral") 
        self.canvas.delete("all")
        self.clear_results()

     
        # 1ª vez Valores constantes como fallback, senão calcular melhor ajuste de valores
        curr_w = self.canvas.winfo_width()
        curr_h = self.canvas.winfo_height()
        if curr_w < 10: curr_w = CANVAS_W
        if curr_h < 10: curr_h = CANVAS_H

        # 2. Recalcular proporções baseadas no tamanho atual
        top_h = int(curr_h * 0.65)        # 65% para o Continente
        bottom_h = curr_h - top_h         # Restante para Ilhas
        half_w = curr_w // 2              # Divisão entre Açores e Madeira

        data = fetch_districts()

        # 3. Ajustar as coordenadas de origem (ox, oy) e dimensões (w, h)
        regions_config = [
            ("C", 0, 0, curr_w, top_h),       # Continente
            ("A", 0, top_h, half_w, bottom_h), # Açores ( inferior esquerdo)
            ("M", half_w, top_h, half_w, bottom_h), # Madeira ( inferior direito)
        ]

        for region, ox, oy, w, h in regions_config:
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
                        outline=OUTLINE_COLOR,
                        activefill="#5da5da" # muda cor ao passar o rato "hover"
                    )
                    #zoom by click
                    self.canvas.tag_bind(
                        pid, "<Button-1>",
                        lambda e, c=code, n=info["name"]:
                            self.show_district(c, n)
                    )

    def show_district(self, code, name):
        self.level = "municipalities"
        self.back_btn.config(state="normal")#para nao entrar antes na funcao on_back mesmo ao clical no mapa
        self.title_lbl.config(text=f"Distrito:{name}")

        self.update_results(f"{name}", votes_by_district(code))
        self.draw_municipalities(code)

    def draw_municipalities(self, dist):
        self.canvas.delete("all")
        data = fetch_municipalities(dist)
# Pega todos os polígonos do distrito selecionado para calcular o zoom ideal
        all_ps = [p for _, _, ps in data for p in ps]
        if not all_ps: return

        w = self.canvas.winfo_width() or CANVAS_W
        h = self.canvas.winfo_height() or CANVAS_H
        
        proj = projector(*bounds(all_ps), w, h)
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
                    activefill="#6699cc"
                )
                self.canvas.tag_bind(
                    pid, "<Button-1>",
                    lambda e, c=code, n=name:
                        self.update_results(f"{n}",
                                          votes_by_municipality(c))
                )


    def clear_results(self):
        # 1. Remove todos os widgets (tabela, botões... do painel lateral
        for child in self.results_frame.winfo_children():
            child.destroy()
        
        # 2. Fecha figuras do Matplotlib
        if self.current_fig:
            plt.close(self.current_fig)
            self.current_fig = None

    def update_results(self, title, rows):
        # 1. Clear previous widgets and explicitly close Matplotlib figures to save memory
        self.clear_results() 
        if self.current_fig:
            plt.close(self.current_fig) # Explicitly close the figure, cnava em si 
        self.current_rows = rows
        self.current_title = title 
        self.export_button.config(state="normal")  # Ativar botão export
        if not rows:
            tk.Label(self.results_frame, text="Sem dados para esta seleção").pack()
            return


        # 2. Create the Table (Treeview)
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
            self.tree.insert("", "end", values=r)
        self.tree.pack(fill="x", expand=True)

       # 3. Create the Chart
        labels = [r[0] for r in rows]
        votes = [r[1] for r in rows]
        chart_title = tk.Label(self.results_frame, text=f"Votos: {title}", 
                               font=("Arial", 10, "bold"), pady=5)
        chart_title.pack()

        fig, ax = plt.subplots(figsize=(5.5, 6), dpi=90)
        self.current_fig = fig 
        
        colors = BAR_COLORS[:len(labels)]
        ax.barh(labels[::-1], votes[::-1], color=colors[::-1])
        ax.tick_params(axis='both', which='major', labelsize=8) 

        canvas = FigureCanvasTkAgg(fig, master=self.results_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def on_back(self):
        if self.level == "municipalities":
            self.draw_districts()

    def on_export_csv(self):
        if not hasattr(self, 'current_rows') or not self.current_rows:
            return
        
        import pandas as pd
        
        # Detecta número de colunas dinamicamente
        num_cols = len(self.current_rows[0]) if self.current_rows else 0
        
        if num_cols == 2:
            df = pd.DataFrame(self.current_rows, columns=["Partido", "Votos"])
        elif num_cols == 3:
            df = pd.DataFrame(self.current_rows, columns=["Partido", "Votos", "Mandatos"])
        else:
            print("Formato de dados inválido")
            return
        
        if self.level == "municipalities":
            filename = f"resultados_{self.current_title}.csv"
        else:
            filename = f"resultados_portugal.csv"
        
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"Exportado: {filename}")


if __name__ == "__main__":
    App()