# Validación de la detección de estilo (CLIP zero-shot)

Estilo esperado = el de la búsqueda (aproximado; revisar las fotos). `?` = caso difícil sin estilo claro (habitación vacía, poca luz).
Celda: top-1 (probabilidad) · margen sobre el 2.º.

| # | Esperado | base32 | large14 |
|---|---|---|---|
| 1 | Rústico | ❌ Industrial (0.46) · +0.08 | ✅ Rústico (0.94) · +0.92 |
| 2 | Rústico | ✅ Rústico (0.83) · +0.75 | ✅ Rústico (0.65) · +0.39 |
| 3 | Escandinavo | ❌ Moderno (0.91) · +0.82 | ❌ Moderno (0.98) · +0.96 |
| 4 | Escandinavo | ❌ Moderno (0.99) · +0.99 | ❌ Moderno (0.83) · +0.66 |
| 5 | Industrial | ❌ Moderno (0.87) · +0.73 | ✅ Industrial (0.93) · +0.89 |
| 6 | Industrial | ✅ Industrial (0.97) · +0.95 | ✅ Industrial (0.98) · +0.96 |
| 7 | Minimalista | ❌ Moderno (0.50) · +0.15 | ✅ Minimalista (0.67) · +0.36 |
| 8 | Minimalista | ✅ Minimalista (0.52) · +0.23 | ❌ Moderno (0.49) · +0.05 |
| 9 | Bohemio | ❌ Moderno (0.36) · +0.04 | ❌ Clásico (0.50) · +0.15 |
| 10 | Bohemio | ❌ Moderno (0.97) · +0.94 | ❌ Moderno (0.98) · +0.96 |
| 11 | Moderno | ❌ Escandinavo (0.83) · +0.73 | ✅ Moderno (0.58) · +0.42 |
| 12 | Moderno | ❌ Minimalista (0.63) · +0.31 | ✅ Moderno (0.71) · +0.51 |
| 13 | ? | · Minimalista (0.74) · +0.56 | · Minimalista (0.97) · +0.95 |
| 14 | ? | · Moderno (0.52) · +0.05 | · Minimalista (0.62) · +0.24 |
| 15 | ? | · Mediterráneo (0.55) · +0.34 | · Clásico (0.66) · +0.56 |
| 16 | ? | · Mediterráneo (0.74) · +0.59 | · Clásico (0.95) · +0.92 |

## Resumen

| Modelo | Aciertos (fotos con estilo esperado) | Tiempo medio/foto |
|---|---|---|
| base32 | 3/12 | 0.16 s |
| large14 | 7/12 | 1.22 s |

## Umbral de confianza (top-1 ≥ p y margen ≥ m)

| Modelo | p | m | Se mostraría en | Aciertos entre las mostradas |
|---|---|---|---|---|
| base32 | 0.3 | 0.1 | 10/12 | 3/10 |
| base32 | 0.3 | 0.2 | 9/12 | 3/9 |
| base32 | 0.4 | 0.1 | 10/12 | 3/10 |
| base32 | 0.4 | 0.2 | 9/12 | 3/9 |
| base32 | 0.5 | 0.1 | 9/12 | 3/9 |
| base32 | 0.5 | 0.2 | 9/12 | 3/9 |
| base32 | 0.6 | 0.1 | 8/12 | 2/8 |
| base32 | 0.6 | 0.2 | 8/12 | 2/8 |
| large14 | 0.3 | 0.1 | 11/12 | 7/11 |
| large14 | 0.3 | 0.2 | 10/12 | 7/10 |
| large14 | 0.4 | 0.1 | 11/12 | 7/11 |
| large14 | 0.4 | 0.2 | 10/12 | 7/10 |
| large14 | 0.5 | 0.1 | 11/12 | 7/11 |
| large14 | 0.5 | 0.2 | 10/12 | 7/10 |
| large14 | 0.6 | 0.1 | 9/12 | 6/9 |
| large14 | 0.6 | 0.2 | 9/12 | 6/9 |

![01](01.jpg)
![02](02.jpg)
![03](03.jpg)
![04](04.jpg)
![05](05.jpg)
![06](06.jpg)
![07](07.jpg)
![08](08.jpg)
![09](09.jpg)
![10](10.jpg)
![11](11.jpg)
![12](12.jpg)
![13](13.jpg)
![14](14.jpg)
![15](15.jpg)
![16](16.jpg)

## Atribución

- 01: [File:Modern rustic interior of a spacious bar featuring wooden accents and stylish seating in a lively social setting.jpg](https://commons.wikimedia.org/wiki/File:Modern_rustic_interior_of_a_spacious_bar_featuring_wooden_accents_and_stylish_seating_in_a_lively_social_setting.jpg) — Shixart1985, CC BY 2.0
- 02: [File:Old Serbian traditional shirt hanging on a wooden post in a rustic interior space with woven textiles in Bistrica Serbia.jpg](https://commons.wikimedia.org/wiki/File:Old_Serbian_traditional_shirt_hanging_on_a_wooden_post_in_a_rustic_interior_space_with_woven_textiles_in_Bistrica_Serbia.jpg) — Shixart1985, CC BY 2.0
- 03: [File:Futuro-talo Sisustus 2.JPG](https://commons.wikimedia.org/wiki/File:Futuro-talo_Sisustus_2.JPG) — Grigur, CC BY-SA 4.0
- 04: [File:Futuro-talo Sisustus 1.JPG](https://commons.wikimedia.org/wiki/File:Futuro-talo_Sisustus_1.JPG) — Grigur, CC BY-SA 4.0
- 05: [File:Milwaukee August 2024 057 (Square D Company-Industrial Controller Division--Junior House Lofts).jpg](https://commons.wikimedia.org/wiki/File:Milwaukee_August_2024_057_(Square_D_Company-Industrial_Controller_Division--Junior_House_Lofts).jpg) — Michael Barera, CC BY-SA 4.0
- 06: [File:Kerker Lofts.JPG](https://commons.wikimedia.org/wiki/File:Kerker_Lofts.JPG) — Farragutful, CC BY-SA 3.0
- 07: [File:Modern pendant lights illuminate minimalist interior design in stylish dining area during evening hours.jpg](https://commons.wikimedia.org/wiki/File:Modern_pendant_lights_illuminate_minimalist_interior_design_in_stylish_dining_area_during_evening_hours.jpg) — Shixart1985, CC BY 2.0
- 08: [File:Minimalist chandelier in the Mița the Cyclist House, Bucharest.jpg](https://commons.wikimedia.org/wiki/File:Minimalist_chandelier_in_the_Mi%C8%9Ba_the_Cyclist_House,_Bucharest.jpg) — Neoclassicism Enthusiast, CC0
- 09: [File:Interior-Auditorium chair, Meadowlands Lodge 361-Western Bohemian Fraternal Union Hall-03.jpg](https://commons.wikimedia.org/wiki/File:Interior-Auditorium_chair,_Meadowlands_Lodge_361-Western_Bohemian_Fraternal_Union_Hall-03.jpg) — Myotus, CC BY-SA 4.0
- 10: [File:Bohemian Hall Staircase by Kreiss.jpg](https://commons.wikimedia.org/wiki/File:Bohemian_Hall_Staircase_by_Kreiss.jpg) — Kreisscm, CC BY-SA 4.0
- 11: [File:Elegant dining area in a modern apartment with wooden accents and stylish decor.jpg](https://commons.wikimedia.org/wiki/File:Elegant_dining_area_in_a_modern_apartment_with_wooden_accents_and_stylish_decor.jpg) — Shixart1985, CC BY 2.0
- 12: [File:Modern living room with stylish furniture and a view of the outdoors in a cozy apartment setting.jpg](https://commons.wikimedia.org/wiki/File:Modern_living_room_with_stylish_furniture_and_a_view_of_the_outdoors_in_a_cozy_apartment_setting.jpg) — Shixart1985, CC BY 2.0
- 13: [File:Empty apartment room with extension cord.jpg](https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_extension_cord.jpg) — aismallard, CC BY-SA 3.0
- 14: [File:Empty room in apartment.jpg](https://commons.wikimedia.org/wiki/File:Empty_room_in_apartment.jpg) — aismallard, CC BY-SA 3.0
- 15: [File:Restaurant room of Amantaka luxury Resort & Hotel in Luang Prabang Laos.jpg](https://commons.wikimedia.org/wiki/File:Restaurant_room_of_Amantaka_luxury_Resort_%26_Hotel_in_Luang_Prabang_Laos.jpg) — Basile Morin, CC BY-SA 4.0
- 16: [File:Lobby lounge of Amantaka Suite Amantaka luxury Resort & Hotel Luang Prabang Laos.jpg](https://commons.wikimedia.org/wiki/File:Lobby_lounge_of_Amantaka_Suite_Amantaka_luxury_Resort_%26_Hotel_Luang_Prabang_Laos.jpg) — Basile Morin, CC BY-SA 4.0