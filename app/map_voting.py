import sqlite3
import matplotlib.pyplot as plt
import os

# ---------------- Config ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "elections.db")

# 👉 Município para testar (ex: 0101 = Águeda)
MUNICIPALITY_CODE = 101  

# ---------------- DB helpers ----------------
def q(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------------- Nome do município ----------------
mun_name = q(
    "SELECT NAME FROM MUNICIPALITIES WHERE CODE = ?",
    (MUNICIPALITY_CODE,)
)[0][0]

# ---------------- Query de votos ----------------
SQL = """
    SELECT
        DETAILED_NAME,
        SUM(VOTES) AS TOTAL_VOTES
    FROM VOTINGS
    WHERE MUNICIPALITY_CODE = ?
    GROUP BY DETAILED_NAME
    HAVING SUM(VOTES) > 0
    ORDER BY TOTAL_VOTES DESC;
"""

rows = q(SQL, (MUNICIPALITY_CODE,))

labels = [r[0] for r in rows[:10]]
votes = [r[1] for r in rows[:10]]

# ---------------- Gráfico ----------------
fig, ax = plt.subplots(figsize=(8, 5))

colors = plt.cm.tab10.colors
bar_colors = [colors[i % len(colors)] for i in range(len(labels))]

bars = ax.barh(labels[::-1], votes[::-1], color=bar_colors[::-1])

ax.set_xlabel("Votos")
ax.set_title(f"Resultados eleitorais — {mun_name}")

# ---------------- Hover ----------------
annot = ax.annotate(
    "",
    xy=(0, 0),
    xytext=(10, 10),
    textcoords="offset points",
    bbox=dict(boxstyle="round", fc="w"),
)
annot.set_visible(False)

def update_annot(bar, value):
    x = bar.get_width()
    y = bar.get_y() + bar.get_height() / 2
    annot.xy = (x, y)
    annot.set_text(f"{value:,} votos")
    annot.set_position((-60, 0))
    annot.get_bbox_patch().set_alpha(0.9)

def hover(event):
    vis = annot.get_visible()
    if event.inaxes == ax:
        for bar, value in zip(bars, votes[::-1]):
            contains, _ = bar.contains(event)
            if contains:
                update_annot(bar, value)
                annot.set_visible(True)
                fig.canvas.draw_idle()
                return
    if vis:
        annot.set_visible(False)
        fig.canvas.draw_idle()

fig.canvas.mpl_connect("motion_notify_event", hover)

plt.tight_layout()
plt.show()
