"""Prueba de humo del notebook SIN GPU: el mismo measure.run y local_qwen
(carga por fases, encode, render, filtro de similitud, regeneración,
puntuador, informe) con un Qwen-Image-Edit DIMINUTO de pesos aleatorios en CPU
(las mismas piezas que usan los tests de diffusers). Comprueba que el código
del notebook funciona contra la API real de diffusers; la calidad de imagen no
significa nada aquí. CLIP y el puntuador se sustituyen por dobles para no
descargar 1,7 GB en CI.

    python validation/colab/smoke_test.py   (desde server/)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]

import torch  # noqa: E402
from PIL import Image  # noqa: E402

TINY = "hf-internal-testing/tiny-random-Qwen2VLForConditionalGeneration"


def tiny_components():
    from diffusers import AutoencoderKLQwenImage, FlowMatchEulerDiscreteScheduler, QwenImageTransformer2DModel
    from transformers import Qwen2_5_VLConfig, Qwen2_5_VLForConditionalGeneration, Qwen2Tokenizer, Qwen2VLProcessor

    torch.manual_seed(0)
    transformer = QwenImageTransformer2DModel(patch_size=2, in_channels=16, out_channels=4, num_layers=2,
                                              attention_head_dim=16, num_attention_heads=3, joint_attention_dim=16,
                                              guidance_embeds=False, axes_dims_rope=(8, 4, 4))
    vae = AutoencoderKLQwenImage(base_dim=24, z_dim=4, dim_mult=[1, 2, 4], num_res_blocks=1,
                                 temperal_downsample=[False, True], latents_mean=[0.0] * 4, latents_std=[1.0] * 4)
    config = Qwen2_5_VLConfig(
        text_config={"hidden_size": 16, "intermediate_size": 16, "num_hidden_layers": 2, "num_attention_heads": 2,
                     "num_key_value_heads": 2, "rope_theta": 1000000.0,
                     "rope_scaling": {"mrope_section": [1, 1, 2], "rope_type": "default", "type": "default"}},
        vision_config={"depth": 2, "hidden_size": 16, "intermediate_size": 16, "num_heads": 2, "out_hidden_size": 16},
        hidden_size=16, vocab_size=152064, vision_end_token_id=151653, vision_start_token_id=151652,
        vision_token_id=151654)
    return {"transformer": transformer, "vae": vae, "scheduler": FlowMatchEulerDiscreteScheduler(),
            "text_encoder": Qwen2_5_VLForConditionalGeneration(config).eval(),
            "tokenizer": Qwen2Tokenizer.from_pretrained(TINY), "processor": Qwen2VLProcessor.from_pretrained(TINY)}


def main() -> int:
    import local_qwen
    import measure
    import quality

    # Dobles de CLIP: la 1.ª variante de cada foto "casi idéntica" para
    # recorrer también la regeneración.
    calls = {"n": 0}

    def similarity(img, original, box=None):
        calls["n"] += 1
        return 0.97 if calls["n"] % 3 == 1 else 0.6

    quality.similarity = similarity
    quality.score = lambda img: {"score": 0.7, "aesthetic": 5.5, "realism": 0.8}

    comps = tiny_components()
    text_parts = {k: v for k, v in comps.items() if k not in ("transformer", "vae")}
    image_parts = {k: v for k, v in comps.items() if k != "text_encoder"}
    loaders = {
        "text": lambda: local_qwen.load(parts="text", quant="none", lightning=False, device="cpu",
                                        dtype=torch.float32, components=text_parts),
        # lightning=True: comprueba que el planificador de Lightning es válido
        # (la LoRA en sí no se puede cargar sobre un modelo diminuto).
        "image": lambda: _image_pipe(local_qwen, image_parts),
    }
    jobs = [{"n": 1, "title": "sintética 1", "style": "nórdico", "strength": 0.55},
            {"n": 2, "title": "sintética 2", "style": "industrial", "strength": 0.3}]

    def fetch(title):
        return Image.new("RGB", (320, 240), (180, 170, 160)), f"{title} (generada)"

    out = Path(tempfile.mkdtemp())
    data = measure.run(out, jobs=jobs, lightning=True, sdxl=False, steps=2, loaders=loaders, fetch=fetch)
    report = (out / "report.md").read_text(encoding="utf-8")
    print(report)
    variants = [v for j in data["jobs"] for v in j["variants"]] if data["jobs"] else []
    assert not data["errors"], data["errors"]
    assert (out / "01.jpg").exists() and (out / "02.jpg").exists()
    assert "Descartadas en la primera tanda: **2/4**" in report, "el filtro de similitud no actuó"
    assert "regeneradas 2" in report
    assert variants == [] or all(v["image"].size == (320, 240) for v in variants)
    print("\nOK: el pipeline del notebook funciona de punta a punta con la API real de diffusers.")
    return 0


def _image_pipe(local_qwen, parts):
    from diffusers import FlowMatchEulerDiscreteScheduler

    FlowMatchEulerDiscreteScheduler.from_config(local_qwen.LIGHTNING_SCHEDULER)  # config válida
    return local_qwen.load(parts="image", quant="none", lightning=False, device="cpu", dtype=torch.float32,
                           components=parts)


if __name__ == "__main__":
    sys.exit(main())
