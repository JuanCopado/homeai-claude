# Comprobación en el Hub para el notebook de Colab

## `Qwen/Qwen-Image-Edit` (licencia: apache-2.0)

| Parte | Tamaño total | Archivo más grande |
|---|---|---|
| (raíz) | 0.0 GB | 0.00 GB |
| processor | 0.0 GB | 0.01 GB |
| scheduler | 0.0 GB | 0.00 GB |
| text_encoder | 15.4 GB | 4.65 GB |
| tokenizer | 0.0 GB | 0.00 GB |
| transformer | 38.1 GB | 4.65 GB |
| vae | 0.2 GB | 0.24 GB |

Total: 53.8 GB.

## LoRA Lightning (`lightx2v/Qwen-Image-Lightning`)

- Archivo usado: `Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors` → **existe**.
- Variantes para Edit disponibles:
  - `Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors`
  - `Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-fp32.safetensors`
  - `Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.safetensors`
  - `Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-8steps-V1.0-fp32.safetensors`
  - `Qwen-Image-Edit-2509/qwen_image_edit_2509_fp8_e4m3fn_scaled.safetensors`
  - `Qwen-Image-Edit-Lightning-4steps-V1.0-bf16.safetensors`
  - `Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors`
  - `Qwen-Image-Edit-Lightning-8steps-V1.0-bf16.safetensors`
  - `Qwen-Image-Edit-Lightning-8steps-V1.0.safetensors`

- Licencia: apache-2.0

## Proveedores (Inference Providers)

- fal-ai (live, image-to-image)
- wavespeed (live, image-to-image)
- replicate (error, image-to-image)
