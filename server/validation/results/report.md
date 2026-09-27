# Validación de la segmentación por zonas

Modelo: `nvidia/segformer-b0-finetuned-ade-512-512` (ADE20K, CPU). Cada imagen: original a la izquierda, zonas a la derecha.
Formato de celda: % de la foto (confianza media del modelo en esa zona, 0–1).

| # | Tipo | pared | suelo | techo | ventana/puerta | mobiliario | otros | Avisos |
|---|---|---|---|---|---|---|---|---|
| 1 | living room interior | 36.7% (0.79) | 30.8% (0.91) | 0.0% (-) | 0.4% (0.52) | 32.1% (0.55) | 0.0% (-) | confianza baja en mobiliario |
| 2 | living room interior | 71.1% (0.78) | 0.0% (0.41) | 0.0% (-) | 0.0% (-) | 23.1% (0.85) | 5.8% (0.55) | apenas detecta suelo |
| 3 | kitchen interior | 52.6% (0.74) | 3.3% (0.57) | 0.0% (0.5) | 0.0% (-) | 43.8% (0.67) | 0.2% (0.58) | confianza baja en suelo |
| 4 | kitchen interior | 34.7% (0.81) | 0.0% (-) | 2.1% (0.44) | 0.0% (-) | 63.1% (0.78) | 0.0% (-) | apenas detecta suelo |
| 5 | bedroom interior | 46.9% (0.89) | 30.6% (0.88) | 0.0% (-) | 0.0% (-) | 2.9% (0.61) | 19.6% (0.72) | ok |
| 6 | bedroom interior | 40.7% (0.93) | 13.7% (0.94) | 8.1% (0.95) | 9.9% (0.96) | 27.6% (0.85) | 0.1% (0.14) | ok |
| 7 | bathroom interior | 30.2% (0.72) | 15.2% (0.95) | 35.3% (0.78) | 0.0% (0.49) | 1.0% (0.57) | 18.3% (0.88) | ok |
| 8 | bathroom interior | 11.9% (0.8) | 4.2% (0.71) | 18.7% (0.95) | 28.4% (0.83) | 35.9% (0.78) | 1.0% (0.43) | ok |
| 9 | attic room interior sloped ceiling | 0.0% (-) | 0.0% (0.29) | 0.0% (-) | 0.0% (-) | 0.0% (-) | 100.0% (0.79) | apenas detecta pared; apenas detecta suelo; 100.0% en clases fuera de las zonas |
| 10 | attic room interior sloped ceiling | 0.0% (-) | 0.0% (-) | 0.0% (-) | 0.0% (-) | 0.0% (0.3) | 100.0% (0.94) | apenas detecta pared; apenas detecta suelo; 100.0% en clases fuera de las zonas |

## 01 — living room interior

![01](01.jpg)

Clases principales: wall 37%, floor 31%, chair 11%, armchair 8%, table 6%, curtain 3%

## 02 — living room interior

![02](02.jpg)

Clases principales: wall 71%, painting 23%, building 6%, floor 0%

## 03 — kitchen interior

![03](03.jpg)

Clases principales: wall 53%, painting 44%, floor 3%, person 0%, ceiling 0%

## 04 — kitchen interior

![04](04.jpg)

Clases principales: painting 63%, wall 35%, ceiling 2%

## 05 — bedroom interior

![05](05.jpg)

Clases principales: wall 47%, floor 31%, person 19%, table 2%, barrel 1%, painting 0%

## 06 — bedroom interior

![06](06.jpg)

Clases principales: wall 41%, bed 21%, floor 14%, windowpane 10%, ceiling 8%, table 4%

## 07 — bathroom interior

![07](07.jpg)

Clases principales: ceiling 35%, wall 30%, column 18%, floor 15%, flag 1%, lamp 1%

## 08 — bathroom interior

![08](08.jpg)

Clases principales: screen door 28%, ceiling 19%, mirror 14%, wall 12%, cabinet 7%, rug 7%

## 09 — attic room interior sloped ceiling

![09](09.jpg)

Clases principales: building 66%, column 28%, sidewalk 6%, floor 0%

## 10 — attic room interior sloped ceiling

![10](10.jpg)

Clases principales: building 50%, sky 30%, road 11%, ashcan 3%, sidewalk 3%, tree 3%

## Atribución de las fotos

- 01: [File:(Barcelona) Dining Room by Pere Torné Esquius - Museu Nacional d'Art de Catalunya.jpg](https://commons.wikimedia.org/wiki/File:(Barcelona)_Dining_Room_by_Pere_Torn%C3%A9_Esquius_-_Museu_Nacional_d%27Art_de_Catalunya.jpg) — Didier Descouens, Public domain
- 02: [File:Living room of a typical rural house in northeast Brazil.jpg](https://commons.wikimedia.org/wiki/File:Living_room_of_a_typical_rural_house_in_northeast_Brazil.jpg) — Wilfredor, CC0
- 03: [File:Dirck de Vries - Kitchen Interior - Walters 372651.jpg](https://commons.wikimedia.org/wiki/File:Dirck_de_Vries_-_Kitchen_Interior_-_Walters_372651.jpg) — Dirck de Vries, Public domain
- 04: [File:Kitchen Interior by Johannes Anthonie Balthasar Stroebel Rijksdienst voor het Cultureel Erfgoed NK1331.jpg](https://commons.wikimedia.org/wiki/File:Kitchen_Interior_by_Johannes_Anthonie_Balthasar_Stroebel_Rijksdienst_voor_het_Cultureel_Erfgoed_NK1331.jpg) — Johannes Anthonie Balthasar Stroebel, Public domain
- 05: [File:Morning, Interior - Luce.jpeg](https://commons.wikimedia.org/wiki/File:Morning,_Interior_-_Luce.jpeg) — Maximilien Luce, Public domain
- 06: [File:Bedroom, Interior of apartment in Brisbane, 2025, 02.jpg](https://commons.wikimedia.org/wiki/File:Bedroom,_Interior_of_apartment_in_Brisbane,_2025,_02.jpg) — Chris Olszewski, CC BY-SA 4.0
- 07: [File:Fin bathroom in Fin garden, Kashan, Iran.jpg](https://commons.wikimedia.org/wiki/File:Fin_bathroom_in_Fin_garden,_Kashan,_Iran.jpg) — Amir Pashaei, CC BY-SA 4.0
- 08: [File:Bathroom, Interior of apartment in Brisbane, 2025, 07.jpg](https://commons.wikimedia.org/wiki/File:Bathroom,_Interior_of_apartment_in_Brisbane,_2025,_07.jpg) — Chris Olszewski, CC BY-SA 4.0
- 09: [File:Grand Hotel from Colmore Row - Porch (5137140037).jpg](https://commons.wikimedia.org/wiki/File:Grand_Hotel_from_Colmore_Row_-_Porch_(5137140037).jpg) — Elliott Brown from Birmingham, United Kingdom, CC BY 2.0
- 10: [File:Town Hall, Market Place, Wells (3662857247).jpg](https://commons.wikimedia.org/wiki/File:Town_Hall,_Market_Place,_Wells_(3662857247).jpg) — Elliott Brown from Birmingham, United Kingdom, CC BY 2.0
