#!/usr/bin/env python3
"""Post de produto: card com imagem, preco e parcela -> Instagram.

Uso:
  python scripts/postar_produto.py preparar   # escolhe produto, gera card + legenda
  python scripts/postar_produto.py publicar   # publica o card (ja enviado ao GitHub)
Variaveis: IG_USER_ID, META_ACCESS_TOKEN, IG_GRAPH_HOST, DRY_RUN=1, PRODUTO=<id>
"""
import json, os, re, sys, time, io, urllib.request, urllib.parse, urllib.error
from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "https://raw.githubusercontent.com/williamrenatodefreitas5-oss/byhome-banners/main/"
PAGINA = "https://williamrenatodefreitas5-oss.github.io/byhome-banners/"
BG, CIANO, LARANJA, TEXTO, CINZA = "#0E171D", "#4CC3E0", "#FF8A3D", "#F2F7F9", "#9AABB7"
HOOKS = {"tecnologia": "ACHADO TECH", "automotivo": "PRA QUEM CUIDA DO CARRO", "ferramentas": "FERRAMENTA EM OFERTA",
         "fitness": "SEU TREINO AGRADECE", "moda": "ACHADO DE MODA", "beleza": "PERFUMARIA EM OFERTA"}
TAGS = {"tecnologia": "#tecnologia #gadgets", "automotivo": "#carros #automotivo", "ferramentas": "#ferramentas #bricolagem",
        "fitness": "#fitness #suplementos", "moda": "#moda #estilo", "beleza": "#perfume #beleza"}


def p(*a): return os.path.join(RAIZ, *a)
def load(path, default=None):
    try:
        with open(p(path), encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default
def aviso(m): print(f"::warning::{m}", flush=True)


def escolher():
    dados = load("data/produtos.json")["produtos"]
    feitos = set(load("data/postados.json", []))
    alvo = os.environ.get("PRODUTO", "").strip()
    for x in dados:
        if (alvo and x["id"] == alvo) or (not alvo and x.get("ativo", True) and x["id"] not in feitos):
            return x
    return None


def fonte(peso, tam): return ImageFont.truetype(p("fonts", f"inter-latin-{peso}-normal.woff"), tam)


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://shopee.com.br/"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception as e:
        if os.environ.get("DRY_RUN"):
            aviso(f"Imagem nao baixada ({e}); usando placeholder no teste.")
            return Image.new("RGB", (800, 800), "#d9dee2")
        raise RuntimeError(f"Falha ao baixar imagem do produto: {e}")


def quebrar(draw, txt, f, larg, maxl=2):
    linhas, atual = [], ""
    for w in txt.split():
        t = (atual + " " + w).strip()
        if draw.textlength(t, font=f) <= larg: atual = t
        else: linhas.append(atual); atual = w
    linhas.append(atual)
    if len(linhas) > maxl:
        linhas = linhas[:maxl]; linhas[-1] = linhas[-1].rstrip(" .,") + "…"
    return linhas


def card(x, W=1080, H=1350, saida=None, rodape="Link na bio · @byhome.technology"):
    quad = H <= W  # versao quadrada (WhatsApp)
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rounded_rectangle((40, 40, W - 40, H - 40), 28, outline="#3A5666", width=2)
    topo = 84 if quad else 100
    d.text((W // 2, topo), "BY HOME", font=fonte(800, 26 if quad else 28), fill=TEXTO, anchor="rs")
    d.text((W // 2 + 12, topo), "TECHNOLOGY", font=fonte(800, 26 if quad else 28), fill=CIANO, anchor="ls")
    # foto do produto em painel branco
    foto = baixar(x["imagem"]); S = 560 if quad else 660
    foto.thumbnail((S, S))
    pan = Image.new("RGB", (S, S), "white"); pan.paste(foto, ((S - foto.width) // 2, (S - foto.height) // 2))
    mask = Image.new("L", (S, S), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, S, S), 32, fill=255)
    y0 = 112 if quad else 150
    im.paste(pan, ((W - S) // 2, y0), mask)
    y = y0 + S + (22 if quad else 30)
    f = fonte(800, 36 if quad else 44)
    for l in quebrar(d, x["nome"], f, 900):
        d.text((W // 2, y), l, font=f, fill=TEXTO, anchor="ma"); y += 44 if quad else 54
    y += 8 if quad else 14
    preco = "R$ " + x["preco"]
    if x.get("preco_de"):
        de = "R$ " + x["preco_de"]; fd = fonte(500, 26 if quad else 30)
        d.text((W // 2, y), de, font=fd, fill=CINZA, anchor="ma")
        w = d.textlength(de, font=fd); d.line((W // 2 - w / 2, y + 15, W // 2 + w / 2, y + 15), fill=CINZA, width=3)
        y += 36 if quad else 42
    d.text((W // 2, y), preco, font=fonte(800, 68 if quad else 80), fill=LARANJA, anchor="ma"); y += 82 if quad else 96
    if x.get("parcela"):
        n, v = x["parcela"].split(" ", 1)
        d.text((W // 2, y), f"ou {n} de {v}", font=fonte(500, 28 if quad else 32), fill=CIANO, anchor="ma")
    d.text((W // 2, H - (66 if quad else 100)), rodape, font=fonte(500, 24 if quad else 26), fill=CINZA, anchor="ms")
    destino = saida or p("cards", f"{x['id']}.png")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    im.save(destino, optimize=True)


def story(x, saida=None):
    """Story 1080x1920. Zonas seguras: 250px no topo e 340px na base. Balao do link fica em branco (sticker)."""
    W, H = 1080, 1920
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.ellipse((W // 2 - 500, 330, W // 2 + 500, 1230), fill="#12303a")  # brilho suave atras da foto
    d.text((W // 2, 300), "BY HOME", font=fonte(800, 30), fill=TEXTO, anchor="rs")
    d.text((W // 2 + 12, 300), "TECHNOLOGY", font=fonte(800, 30), fill=CIANO, anchor="ls")
    foto = baixar(x["imagem"]); S = 660
    foto.thumbnail((S, S))
    pan = Image.new("RGB", (S, S), "white"); pan.paste(foto, ((S - foto.width) // 2, (S - foto.height) // 2))
    mask = Image.new("L", (S, S), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, S, S), 36, fill=255)
    im.paste(pan, ((W - S) // 2, 340), mask)
    y = 340 + S + 34
    f = fonte(800, 46)
    for l in quebrar(d, x["nome"], f, 920):
        d.text((W // 2, y), l, font=f, fill=TEXTO, anchor="ma"); y += 56
    y += 10
    if x.get("preco_de"):
        de = "R$ " + x["preco_de"]; fd = fonte(500, 34)
        d.text((W // 2, y), de, font=fd, fill=CINZA, anchor="ma")
        w = d.textlength(de, font=fd); d.line((W // 2 - w / 2, y + 19, W // 2 + w / 2, y + 19), fill=CINZA, width=3)
        y += 46
    # balao do preco promocional
    texto = "R$ " + x["preco"]; fp = fonte(800, 92)
    tw = d.textlength(texto, font=fp); bw = tw + 90
    d.rounded_rectangle((W // 2 - bw / 2, y, W // 2 + bw / 2, y + 128), 64, fill=LARANJA)
    d.text((W // 2, y + 64), texto, font=fp, fill="#1A0E04", anchor="mm"); y += 148
    if x.get("parcela"):
        n, v = x["parcela"].split(" ", 1)
        d.text((W // 2, y), f"ou {n} de {v}", font=fonte(500, 34), fill=CIANO, anchor="ma")
    # balao do link em branco (o link entra pelo sticker do Instagram na hora de postar)
    d.rounded_rectangle((W // 2 - 260, 1410, W // 2 + 260, 1510), 50, outline=CIANO, width=3)
    d.text((W // 2, 1545), "essa promoção pode acabar a qualquer momento", font=fonte(500, 28), fill=CINZA, anchor="ma")
    destino = saida or p("cards", f"{x['id']}-story.png")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    im.save(destino, optimize=True)


def legenda(x):
    l = [f"{HOOKS.get(x['categoria'], 'ACHADO DO DIA')} 🔥", f"✅ {x['nome']}", f"🔥 POR R$ {x['preco']}"]
    if x.get("preco_de"): l[2] = f"🔥 DE R$ {x['preco_de']} POR R$ {x['preco']}"
    if x.get("parcela"):
        n, v = x["parcela"].split(" ", 1); l.append(f"💳 ou {n} de {v}")
    l += ["🔗 Link na bio (página de ofertas)", "⚠️ Preço e estoque podem mudar. Confira o valor final na loja.",
          "Links de afiliado: podemos receber comissão sem custo extra para você.",
          f"{TAGS.get(x['categoria'], '')} #ofertas #shopee"]
    return "\n".join(l)


def http_json(url, dados=None):
    corpo = urllib.parse.urlencode(dados).encode() if dados is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=corpo), timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}") from None


def publicar(x):
    uid, tok = os.environ["IG_USER_ID"], os.environ["META_ACCESS_TOKEN"]
    base = f"https://{os.environ.get('IG_GRAPH_HOST', 'graph.instagram.com')}/v21.0"
    img = RAW + f"cards/{x['id']}.png"
    for _ in range(10):  # espera o arquivo ficar disponivel no GitHub
        try: urllib.request.urlopen(img, timeout=20); break
        except Exception: time.sleep(6)
    c = http_json(f"{base}/{uid}/media", {"image_url": img, "caption": legenda(x), "access_token": tok})["id"]
    for _ in range(12):
        s = http_json(f"{base}/{c}?" + urllib.parse.urlencode({"fields": "status_code", "access_token": tok}))
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") == "ERROR": raise RuntimeError("Instagram recusou a midia")
        time.sleep(5)
    return http_json(f"{base}/{uid}/media_publish", {"creation_id": c, "access_token": tok})["id"]


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "preparar"
    x = escolher()
    if not x:
        aviso("Nenhum produto pendente em data/produtos.json. Adicione novos produtos."); return
    if modo == "preparar":
        card(x)
        print(f"Produto: {x['nome']}\nLink: {x['link']}\n\n{legenda(x)}")
        os.makedirs(p("out"), exist_ok=True)
        open(p("out", "produto_id.txt"), "w").write(x["id"])
        return
    if os.environ.get("DRY_RUN"): print("DRY_RUN: nao publicou."); return
    if not (os.environ.get("IG_USER_ID") and os.environ.get("META_ACCESS_TOKEN")):
        aviso("Secrets ausentes: nada publicado."); return
    pid = publicar(x)
    feitos = load("data/postados.json", [])
    if x["id"] not in feitos: feitos.append(x["id"])
    json.dump(feitos, open(p("data", "postados.json"), "w"), indent=1)
    print(f"Publicado: {pid}")


if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"::error::{e}"); sys.exit(1)
