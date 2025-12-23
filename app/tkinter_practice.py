
"""
Loop: event-driven
root.mainloop()
event-> callback: functions
connect by: widget.bung("<Button-1>", my_handler) ex.

<Button-1> left button click: consuante coordenadas abrir aquele distrito

<Enter>: Mouse entered widget area
pode aparrecer nome do distrito/municipio numa caixa de texto
Ou/e numero de votos 

<Button-2> right mouse click: pode aparecer mensagem tipo "Click on left side"

"""
"""
Key concepts: ver melhor GUI logic nisto
"""

import tkinter as tk
def on_click(color):
    print(color)

def main():
    root = tk.Tk()
    root.title("Click a color (press End to quit)")
    #é aqui que entra o WKT text? sim ou create_polygon()
    canvas = tk.Canvas(root, width=400, height=400, highlightthickness=0)
    canvas.pack(padx=10, pady=10)
    #sub-areas: districts; sub-sub-area: municípios
    #seria giro associar cor de districtos consuante
    quads= {
        "red": canvas.create_rectangle(0, 0, 200, 200, fill="red", outline="white"),
        "green": canvas.create_rectangle(200, 0, 400, 200, fill="green", outline="white"),
        "blue": canvas.create_rectangle(0, 200, 200, 400, fill="blue", outline="white"),
        "yellow": canvas.create_rectangle(200, 200, 400, 400, fill="yellow", outline="white"),
    }

    for color, rect_id in quads.items():
        canvas.tag_bind(rect_id, "<Button-1>", lambda e, c=color: on_click(c))
    
    tk.Button(root, text="End", command=root.destroy).pack(pady=(0,10))

    root.mainloop() #tem mesmo de estar no fim da pagina
if __name__ == "__main__":
    main()
#no fundo estrutura de TO-DOs:
    # O que precisamos que aconteça? ação-evento: funçoes
    #quais os eventos? binding
    #canva: como ja escrevi: sub, sub-sub area