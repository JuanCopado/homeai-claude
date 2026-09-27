"""Descarga de una foto de Wikimedia Commons por título, con su atribución."""

import html
import io
import re

import requests
from PIL import Image

UA = {"User-Agent": "HomeAI-validation/1.0 (https://github.com/JuanCopado/homeai-claude)"}


def by_title(title: str):
    params = {"action": "query", "format": "json", "titles": title, "prop": "imageinfo",
              "iiprop": "url|extmetadata", "iiurlwidth": 1600}
    page = next(iter(requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=UA, timeout=30).json()["query"]["pages"].values()))
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    raw = requests.get(info.get("thumburl") or info["url"], headers=UA, timeout=60).content
    img = Image.open(io.BytesIO(raw))
    img.load()
    artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", "desconocido"))).strip()[:80]
    return img, {"title": title, "source": info.get("descriptionurl", ""), "artist": artist,
                 "license": meta.get("LicenseShortName", {}).get("value", "")}
