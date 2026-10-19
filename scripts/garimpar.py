#!/usr/bin/env python3
"""Garimpeiro de ofertas de MARCA (Shopee + Mercado Livre) - By Home Technology.

Para cada marca de data/marcas.json busca produtos nos marketplaces, filtra, calcula
desconto REAL (contra o historico de precos que o proprio script guarda) e grava:
  data/candidatos.json   lista ranqueada para aprovar
  docs/candidatos.md     tabela legivel
  data/historico.json    precos observados por dia
Modo teste grava tambem data/amostra_*.json (resposta crua) e data/teste_apis.json.

Somente biblioteca padrao. Chaves por variaveis de ambiente (GitHub Secrets):
  SHOPEE_APP_ID, SHOPEE_SECRET        API de afiliados da Shopee
  ML_CLIENT_ID, ML_CLIENT_SECRET      opcional: token do Mercado Livre (se a busca exigir)

Uso: garimpar.py [--modo teste|completo] [--categoria ID] [--marketplaces shopee,ml]
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRT = timezone(timedelta(hours=-3))
SHOPEE_URL = "https://open-api.affiliate.shopee.com.br/graphql"
ML_BUSCA = "https://api.mercadolibre.com/sites/MLB/search"
ML_TOKEN = "https://api.mercadolibre.com/oauth/token"


def caminho(*p):
    return os.path.join(RAIZ, *p)


def ler(arq, padrao):
    try:
        with open(caminho(arq), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def gravar(arq, dados):
    os.makedirs(os.path.dirname(caminho(arq)), exist_ok=True)
    with open(caminho(arq), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum() or c == " ")


def num(v, padrao=0.0):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return padrao


def http(url, dados=None, headers=None, timeout=40):
    corpo = dados.encode() if isinstance(dados, str) else dados
    req = urllib.request.Request(url, data=corpo, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:800]
    except Exception as e:  # rede
        return 0, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- Shopee
CAMPOS_SHOPEE = ["itemId", "productName", "commissionRate", "price", "priceMin", "priceMax",
                 "sales", "ratingStar", "priceDiscountRate", "imageUrl", "shopName", "shopType",
                 "offerLink", "productLink"]


def shopee_consulta(keyword, campos, limite=20, ordem=2, pagina=1):
    q = ("{ productOfferV2(keyword: %s, sortType: %d, page: %d, limit: %d) "
         "{ nodes { %s } pageInfo { hasNextPage } } }") % (
        json.dumps(keyword, ensure_ascii=False), ordem, pagina, limite, " ".join(campos))
    corpo = json.dumps({"query": q}, ensure_ascii=False, separators=(",", ":"))
    app, seg = os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"]
    ts = str(int(time.time()))
    assinatura = hashlib.sha256((app + ts + corpo + seg).encode()).hexdigest()
    cab = {"Content-Type": "application/json",
           "Authorization": f"SHA256 Credential={app}, Timestamp={ts}, Signature={assinatura}"}
    return http(SHOPEE_URL, corpo, cab)


def shopee_buscar(keyword, limite=20, bruto=None):
    """Retorna (lista_de_nos, info). Remove sozinho campos que a API nao conhecer."""
    campos = list(CAMPOS_SHOPEE)
    removidos = []
    for _ in range(8):
        status, texto = shopee_consulta(keyword, campos, limite)
        try:
            j = json.loads(texto)
        except Exception:
            return [], {"status": status, "erro": texto[:300], "removidos": removidos}
        if bruto is not None and not bruto:
            bruto.append(j)
        erros = j.get("errors") or []
        if erros:
            msg = erros[0].get("message", "")
            alvo = next((c for c in campos if f'"{c}"' in msg or f" {c} " in msg + " "), None)
            if "Cannot query field" in msg and alvo:
                campos.remove(alvo)
                removidos.append(alvo)
                continue
            return [], {"status": status, "erro": msg[:300], "removidos": removidos}
        nos = (((j.get("data") or {}).get("productOfferV2")) or {}).get("nodes") or []
        return nos, {"status": status, "campos": campos, "removidos": removidos}
    return [], {"erro": "muitas tentativas de remover campos", "removidos": removidos}


def shopee_normalizar(n, marca, cat):
    preco = num(n.get("price")) or num(n.get("priceMin"))
    desc_plat = num(n.get("priceDiscountRate"))
    comissao = num(n.get("commissionRate"))
    if comissao > 1:
        comissao /= 100
    tipos = n.get("shopType") or []
    if not isinstance(tipos, list):
        tipos = [tipos]
    return {
        "marketplace": "shopee", "marca": marca, "categoria": cat,
        "id": str(n.get("itemId")), "nome": n.get("productName", ""),
        "preco": preco, "preco_max": num(n.get("priceMax")) or preco,
        "preco_de": round(preco / (1 - desc_plat / 100), 2) if 0 < desc_plat < 95 and preco else None,
        "desconto_plataforma_pct": desc_plat,
        "vendas": int(num(n.get("sales"))), "nota": num(n.get("ratingStar")),
        "oficial": 1 in tipos, "loja": n.get("shopName", ""),
        "comissao_pct": round(comissao * 100, 2),
        "imagem": n.get("imageUrl", ""), "link": n.get("offerLink") or n.get("productLink", ""),
        "link_afiliado": bool(n.get("offerLink")),
    }


# ---------------------------------------------------------------- Mercado Livre
def ml_token():
    cid, seg = os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")
    if not (cid and seg):
        return None
    dados = urllib.parse.urlencode({"grant_type": "client_credentials",
                                    "client_id": cid, "client_secret": seg})
    st, tx = http(ML_TOKEN, dados, {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        return json.loads(tx).get("access_token") if st == 200 else None
    except Exception:
        return None


def ml_buscar(keyword, token=None, limite=20):
    url = ML_BUSCA + "?" + urllib.parse.urlencode(
        {"q": keyword, "limit": limite, "sort": "relevance"})
    cab = {"Accept": "application/json", "User-Agent": "byhome-garimpeiro/1.0"}
    if token:
        cab["Authorization"] = "Bearer " + token
    st, tx = http(url, None, cab)
    try:
        j = json.loads(tx)
    except Exception:
        return [], {"status": st, "erro": tx[:300]}
    if st != 200:
        return [], {"status": st, "erro": (j.get("message") or tx)[:300]}
    return j.get("results", []), {"status": st}


def ml_normalizar(r, marca, cat):
    preco = num(r.get("price"))
    de = num(r.get("original_price")) or None
    return {
        "marketplace": "mercadolivre", "marca": marca, "categoria": cat,
        "id": str(r.get("id")), "nome": r.get("title", ""),
        "preco": preco, "preco_max": preco, "preco_de": de,
        "desconto_plataforma_pct": round((de - preco) / de * 100, 1) if de and de > preco else 0,
        "vendas": int(num(r.get("sold_quantity"))), "nota": 0.0,
        "oficial": bool(r.get("official_store_id")), "loja": (r.get("seller") or {}).get("nickname", ""),
        "comissao_pct": 0.0, "imagem": (r.get("thumbnail") or "").replace("http://", "https://"),
        "link": r.get("permalink", ""), "link_afiliado": False,
        "frete_gratis": bool((r.get("shipping") or {}).get("free_shipping")),
    }


# ---------------------------------------------------------------- historico e score
def desconto_real(item, hist, hoje, minimo):
    chave = f"{item['marketplace']}:{item['id']}"
    pontos = [p for d, p in hist.get(chave, []) if d != hoje]
    if len(pontos) >= minimo:
        ref = statistics.median(pontos)
        if ref > 0 and item["preco"] < ref:
            return round((ref - item["preco"]) / ref * 100, 1), True
        return 0.0, True
    return item["desconto_plataforma_pct"], False


def registrar(item, hist, hoje):
    chave = f"{item['marketplace']}:{item['id']}"
    lista = [p for p in hist.get(chave, []) if p[0] != hoje]
    lista.append([hoje, item["preco"]])
    hist[chave] = lista[-30:]


def pontuar(item, pesos):
    desc = min(item["desconto_real_pct"], 50) / 50
    if not item["desconto_verificado"]:
        desc *= 0.6  # desconto so da plataforma vale menos ate termos historico
    vendas = min(item["vendas"], 5000) / 5000
    nota = max(0.0, (item["nota"] - 4.0)) / 1.0 if item["nota"] else 0.5
    com = min(item["comissao_pct"], 10) / 10
    return round(100 * (pesos["desconto"] * desc + pesos["vendas"] * vendas ** 0.5
                        + pesos["nota"] * min(nota, 1) + pesos["oficial"] * (1 if item["oficial"] else 0)
                        + pesos["comissao"] * com), 1)


def casa_marca(nome, marca):
    palavras = [p for p in norm(marca).split() if p not in ("amazon", "iphone")] or norm(marca).split()
    return all(p in norm(nome) for p in palavras[:2])


# ---------------------------------------------------------------- execucao
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="completo", choices=["teste", "completo"])
    ap.add_argument("--categoria", default="")
    ap.add_argument("--marketplaces", default="shopee,ml")
    a = ap.parse_args()

    cfg = ler("data/marcas.json", {})
    filtros, pesos = cfg["filtros"], cfg["pesos"]
    mkts = [m.strip() for m in a.marketplaces.split(",")]
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    hist = ler("data/historico.json", {})
    token_ml = ml_token() if "ml" in mkts else None
    tem_shopee = bool(os.environ.get("SHOPEE_APP_ID") and os.environ.get("SHOPEE_SECRET"))
    relatorio = {"data": hoje, "shopee_configurada": tem_shopee, "ml_token": bool(token_ml),
                 "amostras": [], "erros": []}

    if "shopee" in mkts and not tem_shopee:
        relatorio["erros"].append("SHOPEE_APP_ID/SHOPEE_SECRET nao configurados: Shopee ignorada")

    cats = cfg["categorias"]
    if a.categoria:
        cats = {a.categoria: cats[a.categoria]}
    itens = []
    for cat, dados in cats.items():
        marcas = dados["marcas"][:3] if a.modo == "teste" else dados["marcas"]
        for marca in marcas:
            q = f"{marca} {dados['termo']}"
            if "shopee" in mkts and tem_shopee:
                bruto = []
                nos, info = shopee_buscar(q, 20, bruto if a.modo == "teste" else None)
                if info.get("erro"):
                    relatorio["erros"].append(f"shopee '{q}': {info['erro']}")
                if a.modo == "teste" and len(relatorio["amostras"]) < 6:
                    relatorio["amostras"].append({"mkt": "shopee", "q": q, "info": info, "n": len(nos)})
                    if bruto:
                        gravar(f"data/amostra_shopee_{len(relatorio['amostras'])}.json", bruto[0])
                itens += [shopee_normalizar(n, marca, cat) for n in nos]
                time.sleep(0.4)
            if "ml" in mkts:
                res, info = ml_buscar(q, token_ml, 20)
                if info.get("erro"):
                    relatorio["erros"].append(f"ml '{q}': {info['erro']}")
                if a.modo == "teste" and len(relatorio["amostras"]) < 12:
                    relatorio["amostras"].append({"mkt": "ml", "q": q, "info": info, "n": len(res)})
                    if res:
                        gravar("data/amostra_ml.json", res[:2])
                itens += [ml_normalizar(r, marca, cat) for r in res]
                time.sleep(0.4)

    brutos = len(itens)
    aprovados, vistos = [], set()
    for it in itens:
        chave = (it["marketplace"], it["id"])
        if chave in vistos or not it["preco"]:
            continue
        vistos.add(chave)
        if not casa_marca(it["nome"], it["marca"]):
            continue
        it["desconto_real_pct"], it["desconto_verificado"] = desconto_real(
            it, hist, hoje, filtros["historico_min_pontos"])
        registrar(it, hist, hoje)
        if it["preco"] < filtros["preco_min"] or it["vendas"] < filtros["vendas_min"]:
            continue
        if it["nota"] and it["nota"] < filtros["nota_min"]:
            continue
        if filtros["so_loja_oficial"] and not it["oficial"]:
            continue
        it["score"] = pontuar(it, pesos)
        aprovados.append(it)

    # limita por marca/marketplace e ordena
    aprovados.sort(key=lambda x: -x["score"])
    contagem, final = {}, []
    for it in aprovados:
        k = (it["marketplace"], it["marca"])
        if contagem.get(k, 0) >= filtros["max_por_marca"]:
            continue
        contagem[k] = contagem.get(k, 0) + 1
        final.append(it)

    relatorio.update({"itens_brutos": brutos, "aprovados": len(final)})
    gravar("data/historico.json", hist)
    gravar("data/candidatos.json", {"gerado_em": datetime.now(BRT).isoformat(timespec="minutes"),
                                    "itens": final})
    gravar("data/teste_apis.json" if a.modo == "teste" else "data/ultimo_relatorio.json", relatorio)

    linhas = ["# Candidatos do dia", f"_Gerado {hoje}. Desconto 'real' so com historico (nao verificado = so da plataforma)._", "",
              "| # | Mkt | Marca | Produto | Preco | De | Desc. | Verif. | Vendas | Nota | Oficial | Com. | Score |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, it in enumerate(final[:80], 1):
        linhas.append("| %d | %s | %s | [%s](%s) | R$ %.2f | %s | %s%% | %s | %d | %s | %s | %s%% | %s |" % (
            i, it["marketplace"][:4], it["marca"], it["nome"][:60].replace("|", "/"), it["link"], it["preco"],
            ("R$ %.2f" % it["preco_de"]) if it["preco_de"] else "-", it["desconto_real_pct"],
            "sim" if it["desconto_verificado"] else "nao", it["vendas"], it["nota"] or "-",
            "sim" if it["oficial"] else "-", it["comissao_pct"], it["score"]))
    os.makedirs(caminho("docs"), exist_ok=True)
    with open(caminho("docs", "candidatos.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    print(json.dumps(relatorio, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::{type(e).__name__}: {e}")
        sys.exit(1)
