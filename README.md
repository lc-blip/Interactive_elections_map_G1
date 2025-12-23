## TASK_B
#### 1º

NOTA: bd e ficheiros CAOP são muito grandes não me deixou fazer push

script

&nbsp;	1.simpler_geo_db.py: criar sqlite simples; districts(if, name, geom=WKT\_fake

(foto slqlite3 terminal)



ex_district_parsing.py:

aqui é comentar e simplificar grande parte do que a professora deu (foto 2 quadrados cinzentos, botão "Back" esta lá mas não funciona) 



#### 2º 

WKT\_fake-> WKT\_real:



|||NOTA: bd de ficheiros CAOP: nuts1: é a região, em vez de definirmos com código manual podemos vir daqui; *nas camadas municípios também temos* nuts2: também ficava fofo para fazer um gradiente de cores. sub-regiões||||

(foto tabela de atributos através de software QGIS: confirma 18 distritos no continente coluna "distrito" a utilizar)

script 

&nbsp;	2.district_geo_db.py: 

&nbsp;	CAOP dá-nos ficheiros do tipo .gpkg	

&nbsp;	extrair distritos: Madeira e Açores também: *escolhas de layout, UX por rever açores ilhas nao estão bem ordenadas, espaço entre açores e madeira; tamanho das ilhas…)*

&nbsp;	converter em WKT

&nbsp;	inserir num sqlite geometry\_real.db

&nbsp;	LIBRARYs:

&nbsp;		Fiona: ler ficheiros GIS ("wrapper do GDAL")

&nbsp;		Shapely:utilizado pata converter o objeto geométrico em WKT(texto)		



ex\_discrit\_parsing\_real: descometei e acrescentei onde  necessário REGION; mudei a estrutura de draw\_districts() funciona OK, mas secalhar mudar a implementação dividida de Continente, madeira, Açores para algo mais eficiente no rendering (ou seja diminuir o tempo que a janela demora a abrir)



#### 3º: Municipios YUPIIII



script:	mun\_geo\_db.py: à anterior db já criada, acrescenta a tabela municipalities sem mexer na tabela districts que a script anterior faz

&nbsp;	(4/5 fotos de sqlite3 terminal)

&nbsp;	add\_municipios: descomentei tudo- nao temos, nem vamos freguesias (tabela/funçoes c/"parish" i think…) tirar/voltar a comentar da stora

#### 4º
-Madeira e Açores: nao aparece nada ao clicar nos distritos
-show votes(): TODO implementar com CNE abrir as tabelas, agora esta so pass
-back(): esta a funcionar esta so muitoooo lento 





