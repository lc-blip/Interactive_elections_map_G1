Eleições Autárquicas 2021 - Mapa Interativo
Este projeto é uma ferramenta de visualização de dados das Eleições Autárquicas de 2021 em Portugal. Permite a exploração dos resultados através de um mapa interativo com funcionalidade de drill-down (Distrito -> Município), acompanhado por gráficos e tabelas detalhadas.

# 0. Pré-requisitos
Certifique-se de que tem o Python 3.x instalado.
As dependências necessárias:

    >>  pip install pandas openpyxl matplotlib fiona shapely

!Todos os comandos devem ser executados a partir da raiz do repositório, ou adaptados cosuante a profundidade nos directórios!

1. Criar a Base de Dados 

Este passo lê os ficheiros Excel oficiais na pasta /data, cria a estrutura de tabelas via SQL e popula a base de dados SQLite.
    >>  python etl/etl.py
Resultado: Criação do ficheiro /db/elections.db.

2. Integrar Geometria WKT

Download dos ficheiros da CAOP:
    https://www.dgterritorio.gov.pt/cartografia/cartografia-tematica/caop
(Nota: pode estar em qualquer local do repositorio, mas aconselhamos cada pasta(Continetal/Madeira/Açores) na root)~

Este passo processa os ficheiros da CAOP para extrair os polígonos dos distritos e municípios em formato WKT e guarda-os na base de dados para serem usados pelo mapa.
    >> python etl/built_geometry.py

3. Iniciar a Aplicação Gráfica
Após a base de dados estar completa com dados e geometria, pode iniciar a interface:

    >>  python app/gui.py

Funcionalidades da GUI
Mapa Interativo:
    Clique num distrito para fazer zoom e ver os municípios desse distrito. Clique no botão "Back" para retornar à vista nacional.
    Num distrito, clique sobre um municipio para ver os resultados dinâmicos correspondentes

Resultados Dinâmicos: Ao selecionar um distrito, a tabela mostra os votos e mandatos, enquanto o gráfico de barras destaca a distribuição de votos.

Interatividade: Passe o rato sobre as barras do gráfico para ver os valores exatos através de tooltips.