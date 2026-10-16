#!/usr/bin/env python3
"""Gera docs/index.html (pagina 'link na bio') e docs/whatsapp.txt a partir de data/produtos.json."""
import html, json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(R, "data", "produtos.json"), encoding="utf-8"))
links = json.load(open(os.path.join(R, "data", "links.json"), encoding="utf-8"))
prods = [x for x in d["produtos"] if x.get("ativo", True)]
e = html.escape
cards = ""
for x in prods:
    de = f'<s>R$ {e(x["preco_de"])}</s> ' if x.get("preco_de") else ""
    par = f'<small>ou {e(x["parcela"].split(" ",1)[0])} de {e(x["parcela"].split(" ",1)[1])}</small>' if x.get("parcela") else ""
    cards += (f'<a class="p" href="{e(x["link"])}" target="_blank" rel="sponsored noopener"><img loading="lazy" referrerpolicy="no-referrer" src="{e(x["imagem"])}" alt="">'
              f'<div><h3>{e(x["nome"])}</h3><p>{de}<b>R$ {e(x["preco"])}</b></p>{par}<span>Ver na Shopee →</span></div></a>\n')
cats = "".join(f'<a href="{e(c["link"])}" target="_blank" rel="sponsored noopener">{e(c["nome"])}</a>' for c in links["categorias"])
page = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>By Home Technology — Ofertas</title><style>
:root{{--bg:#0E171D;--pn:#16252E;--ln:#3A5666;--tx:#F2F7F9;--mu:#9AABB7;--ci:#4CC3E0;--la:#FF8A3D}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:640px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0}}h1 b{{color:var(--ci)}}.sub{{color:var(--mu);margin:4px 0 20px}}
.wa{{display:block;background:var(--la);color:#1A0E04;font-weight:800;text-align:center;padding:14px;border-radius:12px;text-decoration:none;margin-bottom:24px}}
.p{{display:flex;gap:14px;background:var(--pn);border:1px solid var(--ln);border-radius:14px;padding:12px;margin-bottom:12px;text-decoration:none;color:inherit}}
.p img{{width:96px;height:96px;object-fit:cover;border-radius:10px;background:#fff;flex:none}}.p h3{{font-size:15px;margin:0 0 4px}}.p p{{margin:0;color:var(--la);font-size:20px}}.p s{{color:var(--mu);font-size:14px}}
.p small{{color:var(--ci);display:block}}.p span{{color:var(--ci);font-size:14px;font-weight:700}}h2{{font-size:16px;color:var(--mu);margin:28px 0 10px}}
.c a{{display:inline-block;border:1px solid var(--ln);border-radius:999px;padding:6px 12px;margin:0 6px 8px 0;color:var(--tx);text-decoration:none;font-size:14px}}
footer{{color:var(--mu);font-size:12px;margin-top:28px}}</style></head><body><main>
<h1>BY HOME <b>TECHNOLOGY</b></h1><p class="sub">Ofertas selecionadas na Shopee, todo dia.</p>
<a class="wa" href="{e(links["canal_whatsapp"])}" target="_blank" rel="noopener">Entrar no canal grátis do WhatsApp</a>
{cards}<h2>Ofertas por categoria</h2><div class="c">{cats}</div>
<footer>{e(links["aviso_afiliado"])} Preços e parcelas conforme a Shopee em {e(d["coletado_em"])}; podem mudar. Confira o valor final na loja.</footer></main></body></html>'''
os.makedirs(os.path.join(R, "docs"), exist_ok=True)
open(os.path.join(R, "docs", "index.html"), "w", encoding="utf-8").write(page)
wa = ""
for x in prods:
    wa += f"🔥 *{x['nome']}*\n✅ POR *R$ {x['preco']}*" + (f" (DE ~R$ {x['preco_de']}~)" if x.get("preco_de") else "")
    wa += (f"\n💳 ou {x['parcela'].split(' ',1)[0]} de {x['parcela'].split(' ',1)[1]}" if x.get("parcela") else "")
    wa += f"\n🔗 {x['link']}\n\n"
open(os.path.join(R, "docs", "whatsapp.txt"), "w", encoding="utf-8").write(wa.strip() + "\n")
print(f"{len(prods)} produtos na pagina")
