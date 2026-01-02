# ETL — Eleições Autárquicas 2021 ao Nível das Câmaras Municipais #

Este diretório contém o script de ETL responsável por carregar os dados oficiais das Eleições Autárquicas de 2021 para uma base de dados SQLite.

O ETL foi desenvolvido em Python e é reexecutável, garantindo que os dados são sempre carregados de forma consistente.


## Fonte de Dados ##

Os dados utilizados provêm de ficheiros Excel oficiais da Comissão Nacional de
Eleições (CNE), previamente ajustados para facilitar o processamento:

- "mapa_1_resultados_modificado.xlsx"
- "mapa_2_perc_mandatos_modificado.xlsx"


## Estrutura do ETL ##

O processo de ETL executa as seguintes etapas:

- Leitura dos ficheiros Excel com "pandas"
- Normalização de texto (remoção de acentos e espaços extra)
- Conversão de valores numéricos
- Tratamento de valores em falta
- Criação das tabelas através do ficheiro "create_tables.sql"
- Identificação de colunas de descrição nos ficheiros Excel
- Mapeamento explícito entre siglas de partidos e nomes completos
- Separação clara entre entidades geográficas e resultados eleitorais


