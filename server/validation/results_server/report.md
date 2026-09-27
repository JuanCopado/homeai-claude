# Comprobación del servidor con SegFormer-b4 real

| Foto | Zonas (%) | Selección | Fuga fuera de la máscara (>16 px del borde) | Ruido JPEG fuera (>12 niveles) | Dentro sustituido |
|---|---|---|---|---|---|
| 01 apartment living room | pared 27.7, suelo 15.0, techo 10.7, ventana/puerta 15.4, mobiliario 21.6, otros 9.6 | suelo | 0.000% ✅ | 0.107% | 80% |
| 01 apartment living room | pared 27.7, suelo 15.0, techo 10.7, ventana/puerta 15.4, mobiliario 21.6, otros 9.6 | pared+mobiliario | 0.000% ✅ | 0.006% | 82% |
| 02 apartment living room | pared 57.0, suelo 25.9, techo 12.0, ventana/puerta 2.4, mobiliario 2.3 | suelo | 0.000% ✅ | 0.001% | 93% |
| 02 apartment living room | pared 57.0, suelo 25.9, techo 12.0, ventana/puerta 2.4, mobiliario 2.3 | pared+mobiliario | 0.000% ✅ | 0.000% | 94% |
| 03 apartment living room | pared 33.6, suelo 30.8, techo 10.5, ventana/puerta 18.5, mobiliario 6.5 | suelo | 0.000% ✅ | 0.022% | 94% |
| 03 apartment living room | pared 33.6, suelo 30.8, techo 10.5, ventana/puerta 18.5, mobiliario 6.5 | pared+mobiliario | 0.000% ✅ | 0.036% | 78% |
| 04 apartment kitchen | pared 24.0, suelo 22.5, techo 15.4, ventana/puerta 4.0, mobiliario 31.1, otros 3.0 | suelo | 0.000% ✅ | 0.016% | 89% |
| 04 apartment kitchen | pared 24.0, suelo 22.5, techo 15.4, ventana/puerta 4.0, mobiliario 31.1, otros 3.0 | pared+mobiliario | 0.000% ✅ | 0.003% | 87% |
| 05 apartment kitchen | pared 43.8, suelo 28.6, techo 18.7, ventana/puerta 1.4, mobiliario 7.5 | suelo | 0.000% ✅ | 0.000% | 89% |
| 05 apartment kitchen | pared 43.8, suelo 28.6, techo 18.7, ventana/puerta 1.4, mobiliario 7.5 | pared+mobiliario | 0.000% ✅ | 0.000% | 87% |
| 06 apartment kitchen | pared 45.1, suelo 11.3, techo 11.6, ventana/puerta 3.8, mobiliario 28.2 | suelo | 0.000% ✅ | 0.023% | 83% |
| 06 apartment kitchen | pared 45.1, suelo 11.3, techo 11.6, ventana/puerta 3.8, mobiliario 28.2 | pared+mobiliario | 0.000% ✅ | 0.039% | 94% |

Verde = zona sustituida por el generador de prueba. Fuera de la máscara no debe haber verde.