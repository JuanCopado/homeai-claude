# Validación de la detección de estilo (CLIP zero-shot)

Estilo esperado = el de la búsqueda (aproximado; revisar las fotos). `?` = caso difícil sin estilo claro (habitación vacía, poca luz).
Celda: top-1 (probabilidad) · margen sobre el 2.º.

| # | Esperado | base32 | large14 |
|---|---|---|---|
| 1 | Rústico | ❌ Industrial (0.46) · +0.08 | ✅ Rústico (0.94) · +0.92 |
| 2 | Rústico | ✅ Rústico (0.73) · +0.63 | ✅ Rústico (0.60) · +0.36 |
| 3 | Rústico | ✅ Rústico (0.38) · +0.10 | ❌ (vacía) (0.48) · +0.12 |
| 4 | Rústico | ❌ Moderno (0.45) · +0.21 | ❌ Clásico (0.79) · +0.69 |
| 5 | Industrial | ❌ Moderno (0.86) · +0.73 | ✅ Industrial (0.88) · +0.81 |
| 6 | Industrial | ✅ Industrial (0.97) · +0.94 | ✅ Industrial (0.98) · +0.96 |
| 7 | Minimalista | ❌ Moderno (0.50) · +0.15 | ✅ Minimalista (0.67) · +0.36 |
| 8 | Minimalista | ✅ Minimalista (0.48) · +0.21 | ❌ Moderno (0.45) · +0.05 |
| 9 | Moderno | ❌ Escandinavo (0.83) · +0.73 | ✅ Moderno (0.57) · +0.42 |
| 10 | Moderno | ❌ Minimalista (0.58) · +0.29 | ✅ Moderno (0.68) · +0.49 |
| 11 | (vacía) | ✅ (vacía) (0.89) · +0.81 | ✅ (vacía) (0.94) · +0.89 |
| 12 | (vacía) | ✅ (vacía) (1.00) · +0.99 | ✅ (vacía) (1.00) · +0.99 |
| 13 | ? | · Mediterráneo (0.55) · +0.34 | · Clásico (0.66) · +0.56 |
| 14 | ? | · Mediterráneo (0.72) · +0.57 | · Clásico (0.94) · +0.92 |

## Resumen

| Modelo | Aciertos (fotos con estilo esperado) | Tiempo medio/foto |
|---|---|---|
| base32 | 4/10 (vacías sin sugerencia: 2/2) | 0.19 s |
| large14 | 7/10 (vacías sin sugerencia: 2/2) | 1.28 s |

## Umbral de confianza (top-1 ≥ p y margen ≥ m)

| Modelo | p | m | Se mostraría en | Aciertos entre las mostradas |
|---|---|---|---|---|
| base32 | 0.3 | 0.1 | 9/10 | 4/9 |
| base32 | 0.3 | 0.2 | 7/10 | 3/7 |
| base32 | 0.4 | 0.1 | 8/10 | 3/8 |
| base32 | 0.4 | 0.2 | 7/10 | 3/7 |
| base32 | 0.5 | 0.1 | 5/10 | 2/5 |
| base32 | 0.5 | 0.2 | 5/10 | 2/5 |
| base32 | 0.6 | 0.1 | 4/10 | 2/4 |
| base32 | 0.6 | 0.2 | 4/10 | 2/4 |
| large14 | 0.3 | 0.1 | 8/10 | 7/8 |
| large14 | 0.3 | 0.2 | 8/10 | 7/8 |
| large14 | 0.4 | 0.1 | 8/10 | 7/8 |
| large14 | 0.4 | 0.2 | 8/10 | 7/8 |
| large14 | 0.5 | 0.1 | 8/10 | 7/8 |
| large14 | 0.5 | 0.2 | 8/10 | 7/8 |
| large14 | 0.6 | 0.1 | 7/10 | 6/7 |
| large14 | 0.6 | 0.2 | 7/10 | 6/7 |

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

## Atribución

- 01: [File:Modern rustic interior of a spacious bar featuring wooden accents and stylish seating in a lively social setting.jpg](https://commons.wikimedia.org/wiki/File:Modern_rustic_interior_of_a_spacious_bar_featuring_wooden_accents_and_stylish_seating_in_a_lively_social_setting.jpg) — Shixart1985, CC BY 2.0
- 02: [File:Old Serbian traditional shirt hanging on a wooden post in a rustic interior space with woven textiles in Bistrica Serbia.jpg](https://commons.wikimedia.org/wiki/File:Old_Serbian_traditional_shirt_hanging_on_a_wooden_post_in_a_rustic_interior_space_with_woven_textiles_in_Bistrica_Serbia.jpg) — Shixart1985, CC BY 2.0
- 03: [File:Summer Kitchen, White Hall, Richmond, KY.jpg](https://commons.wikimedia.org/wiki/File:Summer_Kitchen,_White_Hall,_Richmond,_KY.jpg) — w_lemay, CC BY-SA 2.0
- 04: [File:Kitchen Wing, White Hall, Richmond, KY.jpg](https://commons.wikimedia.org/wiki/File:Kitchen_Wing,_White_Hall,_Richmond,_KY.jpg) — w_lemay, CC BY-SA 2.0
- 05: [File:Milwaukee August 2024 057 (Square D Company-Industrial Controller Division--Junior House Lofts).jpg](https://commons.wikimedia.org/wiki/File:Milwaukee_August_2024_057_(Square_D_Company-Industrial_Controller_Division--Junior_House_Lofts).jpg) — Michael Barera, CC BY-SA 4.0
- 06: [File:Kerker Lofts.JPG](https://commons.wikimedia.org/wiki/File:Kerker_Lofts.JPG) — Farragutful, CC BY-SA 3.0
- 07: [File:Modern pendant lights illuminate minimalist interior design in stylish dining area during evening hours.jpg](https://commons.wikimedia.org/wiki/File:Modern_pendant_lights_illuminate_minimalist_interior_design_in_stylish_dining_area_during_evening_hours.jpg) — Shixart1985, CC BY 2.0
- 08: [File:Minimalist chandelier in the Mița the Cyclist House, Bucharest.jpg](https://commons.wikimedia.org/wiki/File:Minimalist_chandelier_in_the_Mi%C8%9Ba_the_Cyclist_House,_Bucharest.jpg) — Neoclassicism Enthusiast, CC0
- 09: [File:Elegant dining area in a modern apartment with wooden accents and stylish decor.jpg](https://commons.wikimedia.org/wiki/File:Elegant_dining_area_in_a_modern_apartment_with_wooden_accents_and_stylish_decor.jpg) — Shixart1985, CC BY 2.0
- 10: [File:Modern living room with stylish furniture and a view of the outdoors in a cozy apartment setting.jpg](https://commons.wikimedia.org/wiki/File:Modern_living_room_with_stylish_furniture_and_a_view_of_the_outdoors_in_a_cozy_apartment_setting.jpg) — Shixart1985, CC BY 2.0
- 11: [File:Empty apartment room with extension cord.jpg](https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_extension_cord.jpg) — aismallard, CC BY-SA 3.0
- 12: [File:Empty room in apartment.jpg](https://commons.wikimedia.org/wiki/File:Empty_room_in_apartment.jpg) — aismallard, CC BY-SA 3.0
- 13: [File:Restaurant room of Amantaka luxury Resort & Hotel in Luang Prabang Laos.jpg](https://commons.wikimedia.org/wiki/File:Restaurant_room_of_Amantaka_luxury_Resort_%26_Hotel_in_Luang_Prabang_Laos.jpg) — Basile Morin, CC BY-SA 4.0
- 14: [File:Lobby lounge of Amantaka Suite Amantaka luxury Resort & Hotel Luang Prabang Laos.jpg](https://commons.wikimedia.org/wiki/File:Lobby_lounge_of_Amantaka_Suite_Amantaka_luxury_Resort_%26_Hotel_Luang_Prabang_Laos.jpg) — Basile Morin, CC BY-SA 4.0