"""User action (click / dropdown)
        ↓
Read current filters (district, organ)
        ↓
Query SQLite
        ↓
Update table
        ↓
Update chart

we need to have codes from the disctricts?
or just define as class with list of CMs?

Do mapa usado como exemplo:
-quando se passa sobre mapa diz o nome do distrito/municipio
- local para voltar a parte anterior do mapa
- Titulo: mapa vs localidades: inicalmente por so "Mapa eleições"

"""
#no fundo estrutura de TO-DOs:
# O que precisamos que aconteça? ação-evento: funçoes
'''
                Lista funções(sem BD associada):
                passar cursor sobre distrito/dar nome deste
                clicar municipio: mapa passar a ser so ele, dividido em municipios
                passar cursor sobre municipio/dar nome deste
                ter linha-botao para voltar atrás ao mapa completo de portugal (dentro de municipio)

                (com BD)
                definir core de distrito municipio consusnte partido vencedor
                aparecer tabelas de votos: ordenado descresecentemente 
        '''
#quais os eventos? binding

#canva: como ja escrevi: sub, sub-sub area

import tkinter

#dados geograficos de portigal
#https://dados.gov.pt/en/datasets/distritos-de-portugal/?utm_source=chatgpt.com