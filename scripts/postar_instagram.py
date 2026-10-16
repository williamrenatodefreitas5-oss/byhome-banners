#!/usr/bin/env python3
"""Publica 1 post de categoria no Instagram (By Home Technology).

Fluxo: le data/links.json -> escolhe a categoria do horario -> pega legenda pronta de
data/legendas.json -> cria o container de midia -> espera ficar pronto -> publica.

Somente biblioteca padrao do Python. Chaves vem de variaveis de ambiente (GitHub Secrets).

Variaveis:
  IG_USER_ID, META_ACCESS_TOKEN     obrigatorias para publicar
  IG_GRAPH_HOST                     opcional (padrao graph.instagram.com)
  DRY_RUN=1                         simula, nao publica
  CATEGORIA=<id>                    forca uma categoria (ex.: motos)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_IMAGENS = "https://raw.githubusercontent.com/williamrenatodefreitas5-oss/byhome-banners/main/"
GRAPH_VERSAO = "v21.0"
BRT = timezone(timedelta(hours=-3))  # Brasil sem horario de verao


def aviso(msg):
    print(f"::warning::{msg}", flush=True)


def http_json(url, dados=None, headers=None, timeout=60):
    corpo = None
    cab = dict(headers or {})
    if dados is not None:
        if cab.get("content-type") == "application/json":
            corpo = json.dumps(dados).encode()
        else:
            corpo = urllib.parse.urlencode(dados).encode()
    req = urllib.request.Request(url, data=corpo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"HTTP {e.code} em {url.split('?')[0]}: {detalhe}") from None


def escolher_categoria(cats):
    forcada = os.environ.get("CATEGORIA", "").strip()
    if forcada:
        for c in cats:
            if c["id"] == forcada:
                return c
        raise SystemExit(f"Categoria '{forcada}' nao existe em links.json")
    agora = datetime.now(BRT)
    slot = 0 if agora.hour < 9 else 1 if agora.hour < 14 else 2
    indice = (agora.timetuple().tm_yday * 3 + slot) % len(cats)
    return cats[indice]


def legenda_padrao(cat, cfg):
    return (
        f"{cat['nome'].upper()} EM OFERTA \U0001F525\n"
        f"{cat['sub']}.\n"
        f"Veja as ofertas: link na bio. Canal no WhatsApp tambem na bio.\n"
        f"#ofertas #shopee #{cat['id'].replace('-', '')}"
    )


def gerar_legenda(cat, cfg):
    """Escolhe uma legenda pronta de data/legendas.json (escritas com a Claude no chat)."""
    try:
        with open(os.path.join(RAIZ, "data", "legendas.json"), encoding="utf-8") as f:
            opcoes = json.load(f).get(cat["id"], [])
    except Exception as e:
        aviso(f"legendas.json ilegivel ({e}).")
        opcoes = []
    if not opcoes:
        return legenda_padrao(cat, cfg)
    dia = datetime.now(BRT).timetuple().tm_yday
    return opcoes[dia % len(opcoes)]


def publicar(imagem_url, legenda):
    host = os.environ.get("IG_GRAPH_HOST", "graph.instagram.com")
    uid = os.environ["IG_USER_ID"]
    token = os.environ["META_ACCESS_TOKEN"]
    base = f"https://{host}/{GRAPH_VERSAO}"

    c = http_json(f"{base}/{uid}/media",
                  {"image_url": imagem_url, "caption": legenda, "access_token": token})
    container = c["id"]
    for _ in range(12):  # ate ~1 minuto
        s = http_json(f"{base}/{container}?" + urllib.parse.urlencode(
            {"fields": "status_code", "access_token": token}))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError("Instagram recusou a midia (status ERROR)")
        time.sleep(5)
    p = http_json(f"{base}/{uid}/media_publish",
                  {"creation_id": container, "access_token": token})
    return p["id"]


def main():
    with open(os.path.join(RAIZ, "data", "links.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cat = escolher_categoria(cfg["categorias"])
    imagem = BASE_IMAGENS + cat["imagem"]
    legenda = gerar_legenda(cat, cfg)

    print(f"Categoria: {cat['nome']}\nImagem: {imagem}\nLink de afiliado: {cat['link']}\nLegenda:\n{legenda}\n")

    if os.environ.get("DRY_RUN"):
        print("DRY_RUN ativo: nada foi publicado.")
        return
    faltando = [v for v in ("IG_USER_ID", "META_ACCESS_TOKEN") if not os.environ.get(v)]
    if faltando:
        aviso(f"Secrets ausentes ({', '.join(faltando)}): nada foi publicado.")
        return
    post_id = publicar(imagem, legenda)
    print(f"Publicado com sucesso. ID do post: {post_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{e}")
        sys.exit(1)
