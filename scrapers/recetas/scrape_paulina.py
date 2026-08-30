#!/usr/bin/env python3
"""Carga inicial (una sola corrida, no cron) del catálogo de "pre-recetas"
de lista-super a partir de paulinacocina.net.

Solo guarda nombre + ingredientes categorizados + link a la receta
original. Deliberadamente NO guarda pasos de preparación: son el texto
creativo de otra creadora y este repo es público en GitHub Pages, así que
copiarlos en bloque para ~2000 recetas es una exposición de copyright real,
no solo teórica. Ver el plan de la feature "Pre-recetas" para el contexto
completo de esta decisión.

Uso: python3 scrape_paulina.py
Escribe assets/pre-recetas.json (relativo a la raíz del repo).
"""

import concurrent.futures
import json
import re
import time
import unicodedata
import uuid
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.paulinacocina.net"
SITEMAPS = [f"{BASE}/post-sitemap{i}.xml" for i in range(1, 12)]
OUT_PATH = Path(__file__).resolve().parents[2] / "assets" / "pre-recetas.json"
ERR_PATH = Path(__file__).resolve().parents[2] / "assets" / "pre-recetas-errores.log"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
WORKERS = 6
REQUEST_DELAY = 0.15  # segundos por request en cada worker, cortesía con el sitio
STEP_MARKERS = (
    "preparaci", "paso a paso", "instruccion", "procedimiento",
    "como hacer", "modo de preparacion", "elaboracion",
)

# ---------------------------------------------------------------------------
# Port de CATEGORIES / PRODUCT_MAP / normalize / detectCategory desde
# index.html (líneas ~1799-1962 al momento de escribir esto). Mismo
# diccionario y misma lógica de matching por substring que usa la app al
# categorizar un ingrediente tipeado a mano, para que una pre-receta
# agregada se categorice exactamente igual que si el usuario la hubiera
# tipeado ella misma.
# ---------------------------------------------------------------------------
PRODUCT_MAP = {
    # Frutas y verduras
    'manzana': 'frutas_verduras', 'banana': 'frutas_verduras', 'platano': 'frutas_verduras', 'naranja': 'frutas_verduras',
    'mandarina': 'frutas_verduras', 'limon': 'frutas_verduras', 'pomelo': 'frutas_verduras', 'pera': 'frutas_verduras',
    'uva': 'frutas_verduras', 'frutilla': 'frutas_verduras', 'durazno': 'frutas_verduras', 'ciruela': 'frutas_verduras',
    'kiwi': 'frutas_verduras', 'ananá': 'frutas_verduras', 'ananas': 'frutas_verduras', 'melon': 'frutas_verduras',
    'sandia': 'frutas_verduras', 'palta': 'frutas_verduras', 'mango': 'frutas_verduras', 'cereza': 'frutas_verduras',
    'papa': 'frutas_verduras', 'batata': 'frutas_verduras', 'cebolla': 'frutas_verduras',
    'tomate': 'frutas_verduras', 'lechuga': 'frutas_verduras', 'zanahoria': 'frutas_verduras', 'zapallo': 'frutas_verduras',
    'zapallito': 'frutas_verduras', 'calabaza': 'frutas_verduras', 'morron': 'frutas_verduras', 'pimiento': 'frutas_verduras',
    'ajo': 'frutas_verduras', 'apio': 'frutas_verduras', 'brocoli': 'frutas_verduras', 'coliflor': 'frutas_verduras',
    'espinaca': 'frutas_verduras', 'acelga': 'frutas_verduras', 'repollo': 'frutas_verduras', 'pepino': 'frutas_verduras',
    'berenjena': 'frutas_verduras', 'choclo': 'frutas_verduras', 'remolacha': 'frutas_verduras', 'rabanito': 'frutas_verduras',
    'perejil': 'frutas_verduras', 'cilantro': 'frutas_verduras', 'albahaca': 'frutas_verduras', 'jengibre': 'frutas_verduras',
    'hongos': 'frutas_verduras', 'champiñones': 'frutas_verduras', 'champignones': 'frutas_verduras', 'puerro': 'frutas_verduras',
    'chaucha': 'frutas_verduras', 'arveja': 'frutas_verduras', 'arvejas frescas': 'frutas_verduras',

    # Carnes y fiambres
    'carne': 'carnes', 'carne picada': 'carnes', 'asado': 'carnes', 'vacio': 'carnes', 'matambre': 'carnes',
    'bife': 'carnes', 'bife de chorizo': 'carnes', 'lomo': 'carnes', 'pollo': 'carnes', 'pechuga': 'carnes',
    'pata muslo': 'carnes', 'milanesa': 'carnes', 'cerdo': 'carnes', 'chorizo': 'carnes',
    'salchicha': 'carnes', 'morcilla': 'carnes', 'panceta': 'carnes', 'costilla': 'carnes',
    'costeleta': 'carnes', 'jamon': 'carnes', 'jamon cocido': 'carnes', 'jamon crudo': 'carnes', 'salame': 'carnes',
    'salamin': 'carnes', 'mortadela': 'carnes', 'paleta': 'carnes', 'bondiola': 'carnes', 'higado': 'carnes',
    'nalga': 'carnes', 'peceto': 'carnes', 'cuadril': 'carnes', 'entraña': 'carnes', 'tapa de asado': 'carnes',
    'hamburguesa': 'carnes', 'pate': 'carnes', 'fiambre': 'carnes', 'queso de cerdo': 'carnes',

    # Pescados
    'pescado': 'pescados', 'merluza': 'pescados', 'salmon': 'pescados', 'atun': 'pescados', 'atun lata': 'pescados',
    'camaron': 'pescados', 'langostino': 'pescados',
    'mejillon': 'pescados', 'calamar': 'pescados', 'pulpo': 'pescados', 'trucha': 'pescados',
    'anchoa': 'pescados', 'caballa': 'pescados', 'sardina': 'pescados',

    # Lácteos y huevos
    'leche': 'lacteos', 'yogur': 'lacteos', 'yogurt': 'lacteos', 'queso': 'lacteos', 'queso rallado': 'lacteos',
    'queso cremoso': 'lacteos', 'queso untable': 'lacteos', 'muzzarella': 'lacteos', 'mozzarella': 'lacteos',
    'manteca': 'lacteos', 'crema': 'lacteos', 'crema de leche': 'lacteos', 'huevo': 'lacteos',
    'dulce de leche': 'lacteos', 'ricota': 'lacteos', 'flan': 'lacteos', 'postre': 'lacteos', 'danonino': 'lacteos',
    'yogur bebible': 'lacteos', 'leche chocolatada': 'lacteos', 'crema chantilly': 'lacteos', 'margarina': 'lacteos',

    # Panadería
    'pan': 'panaderia', 'pan lactal': 'panaderia', 'pan de molde': 'panaderia', 'pan frances': 'panaderia',
    'factura': 'panaderia', 'medialuna': 'panaderia',
    'tostadas': 'panaderia', 'tostado': 'panaderia', 'bizcocho': 'panaderia',
    'grisines': 'panaderia', 'pan rallado': 'panaderia', 'pan dulce': 'panaderia', 'torta': 'panaderia',
    'masitas': 'panaderia', 'magdalenas': 'panaderia', 'budin': 'panaderia', 'pan arabe': 'panaderia',
    'tapas de empanada': 'panaderia', 'tapas de tarta': 'panaderia', 'prepizza': 'panaderia',

    # Almacén (secos, enlatados, básicos)
    'arroz': 'almacen', 'fideos': 'almacen', 'pasta': 'almacen', 'polenta': 'almacen', 'harina': 'almacen',
    'harina 0000': 'almacen', 'harina leudante': 'almacen', 'azucar': 'almacen', 'sal': 'almacen', 'yerba': 'almacen',
    'yerba mate': 'almacen', 'cafe': 'almacen', 'te': 'almacen', 'mate cocido': 'almacen', 'aceite': 'almacen',
    'vinagre': 'almacen', 'lenteja': 'almacen', 'garbanzo': 'almacen',
    'poroto': 'almacen', 'tomate lata': 'almacen', 'pure de tomate': 'almacen',
    'salsa de tomate': 'almacen', 'caldo': 'almacen', 'caldo en cubos': 'almacen', 'gelatina': 'almacen',
    'avena': 'almacen', 'cereal': 'almacen', 'miel': 'almacen', 'mermelada': 'almacen',
    'aceitunas': 'almacen', 'choclo lata': 'almacen', 'arveja lata': 'almacen',
    'levadura': 'almacen', 'bicarbonato': 'almacen', 'maicena': 'almacen', 'fecula de maiz': 'almacen',
    'tostadas de arroz': 'almacen', 'sopa': 'almacen', 'sopa instantanea': 'almacen', 'choclo en lata': 'almacen',

    # Condimentos y salsas
    'mayonesa': 'condimentos', 'ketchup': 'condimentos', 'mostaza': 'condimentos', 'salsa golf': 'condimentos',
    'aji molido': 'condimentos', 'oregano': 'condimentos', 'pimienta': 'condimentos', 'comino': 'condimentos',
    'laurel': 'condimentos', 'nuez moscada': 'condimentos', 'curry': 'condimentos', 'pimenton': 'condimentos',
    'salsa soja': 'condimentos', 'soja': 'condimentos', 'salsa de soja': 'condimentos', 'tabasco': 'condimentos',
    'aderezo': 'condimentos', 'provenzal': 'condimentos', 'condimento': 'condimentos', 'sal de ajo': 'condimentos',
    'canela': 'condimentos', 'vainilla': 'condimentos',

    # Bebidas
    'agua': 'bebidas', 'agua mineral': 'bebidas', 'agua con gas': 'bebidas', 'soda': 'bebidas', 'gaseosa': 'bebidas',
    'coca cola': 'bebidas', 'coca': 'bebidas', 'sprite': 'bebidas', 'fanta': 'bebidas', 'jugo': 'bebidas',
    'jugo exprimido': 'bebidas', 'jugo en polvo': 'bebidas', 'cerveza': 'bebidas', 'vino': 'bebidas',
    'fernet': 'bebidas', 'whisky': 'bebidas', 'vodka': 'bebidas', 'gin': 'bebidas', 'champagne': 'bebidas',
    'sidra': 'bebidas', 'energizante': 'bebidas', 'isotonica': 'bebidas', 'gatorade': 'bebidas', 'tonica': 'bebidas',

    # Congelados
    'helado': 'congelados', 'papas fritas congeladas': 'congelados', 'verdura congelada': 'congelados',
    'nuggets': 'congelados', 'rebozados': 'congelados', 'tarta congelada': 'congelados', 'pizza congelada': 'congelados',
    'medallon': 'congelados', 'empanadas congeladas': 'congelados', 'hielo': 'congelados',

    # Snacks y dulces
    'galletitas': 'snacks', 'galletas': 'snacks', 'papas fritas': 'snacks', 'papas lays': 'snacks', 'chizitos': 'snacks',
    'chocolate': 'snacks', 'alfajor': 'snacks', 'caramelos': 'snacks', 'chicles': 'snacks',
    'turron': 'snacks', 'maní': 'snacks', 'mani': 'snacks', 'frutos secos': 'snacks', 'pasas de uva': 'snacks',
    'palitos salados': 'snacks', 'conitos': 'snacks', 'barrita de cereal': 'snacks', 'budin ingles': 'snacks',
    'vainillas': 'snacks', 'oblea': 'snacks', 'bombones': 'snacks', 'galletitas de agua': 'snacks',

    # Limpieza
    'lavandina': 'limpieza', 'detergente': 'limpieza', 'jabon en polvo': 'limpieza', 'suavizante': 'limpieza',
    'esponja': 'limpieza', 'trapo de piso': 'limpieza', 'rollo de cocina': 'limpieza',
    'servilletas': 'limpieza', 'bolsas de residuo': 'limpieza', 'limpiavidrios': 'limpieza', 'desengrasante': 'limpieza',
    'lustramuebles': 'limpieza', 'insecticida': 'limpieza', 'ambientador': 'limpieza',
    'jabon liquido': 'limpieza', 'jabon para platos': 'limpieza', 'guantes de latex': 'limpieza', 'fibra': 'limpieza',
    'trapo rejilla': 'limpieza', 'pastilla para inodoro': 'limpieza', 'aromatizante': 'limpieza',

    # Higiene y perfumería
    'shampoo': 'higiene', 'champu': 'higiene', 'acondicionador': 'higiene', 'jabon de tocador': 'higiene',
    'pasta dental': 'higiene', 'crema dental': 'higiene', 'cepillo de dientes': 'higiene', 'hilo dental': 'higiene',
    'desodorante': 'higiene', 'protector solar': 'higiene', 'crema corporal': 'higiene', 'crema de manos': 'higiene',
    'algodon': 'higiene', 'hisopos': 'higiene', 'toallitas humedas': 'higiene', 'toallas femeninas': 'higiene',
    'tampones': 'higiene', 'papel higienico': 'higiene', 'maquinita de afeitar': 'higiene', 'afeitadora': 'higiene',
    'espuma de afeitar': 'higiene', 'perfume': 'higiene', 'colonia': 'higiene', 'protector diario': 'higiene',
    'preservativos': 'higiene', 'curitas': 'higiene', 'alcohol en gel': 'higiene',

    # Bebés
    'pañales': 'bebes', 'panales': 'bebes', 'leche en polvo bebe': 'bebes', 'toallitas bebe': 'bebes',
    'papilla': 'bebes', 'compota': 'bebes', 'crema para pañales': 'bebes', 'chupete': 'bebes', 'mamadera': 'bebes',

    # Mascotas
    'alimento para perro': 'mascotas', 'alimento para gato': 'mascotas', 'balanceado': 'mascotas',
    'arena para gato': 'mascotas', 'snacks para perro': 'mascotas', 'snacks para gato': 'mascotas',
}
_SORTED_KEYS = sorted(PRODUCT_MAP.keys(), key=len, reverse=True)


def normalize(text):
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.strip()


def detect_category(raw_text):
    text = normalize(raw_text)
    if text in PRODUCT_MAP:
        return PRODUCT_MAP[text]
    for key in _SORTED_KEYS:
        if key in text:
            return PRODUCT_MAP[key]
    for word in text.split():
        if word in PRODUCT_MAP:
            return PRODUCT_MAP[word]
    return None


def gen_id():
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_sitemap_urls():
    urls = []
    for sm in SITEMAPS:
        resp = requests.get(sm, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        urls += re.findall(r'<loc>(.*?)</loc>', resp.text)
    seen = set()
    ordered = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def fallback_html_ingredients(soup):
    """Heurística de respaldo cuando el JSON-LD no trae recipeIngredient:
    ubica el bloque "Ingredientes" en el HTML y junta líneas hasta el
    próximo heading o marcador de preparación."""
    marker = None
    for tag in soup.find_all(['p', 'h2', 'h3', 'h4', 'strong']):
        if 'ingredient' in normalize(tag.get_text()):
            marker = tag
            break
    if marker is None:
        return []
    container = marker.find_parent('p') if marker.name == 'strong' else marker

    lines = []
    node = container.find_next_sibling() if container else None
    steps = 0
    while node is not None and steps < 40:
        steps += 1
        tag_name = getattr(node, 'name', None)
        if tag_name in ('h2', 'h3', 'h4'):
            break
        block_text = normalize(node.get_text(' ')) if hasattr(node, 'get_text') else ''
        if any(marker_word in block_text for marker_word in STEP_MARKERS):
            break
        if tag_name in ('ul', 'ol'):
            for li in node.find_all('li'):
                text = li.get_text(' ', strip=True)
                if text:
                    lines.append(text)
        elif tag_name == 'p':
            for part in node.get_text('\n', strip=True).split('\n'):
                part = part.strip(' -•\t')
                if part:
                    lines.append(part)
        node = node.find_next_sibling()
    return lines


def extract_recipe(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        return None, f"fetch-error: {e}"

    soup = BeautifulSoup(resp.text, 'html.parser')

    name = None
    raw_ingredients = None

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except Exception:
            continue
        items = list(data) if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get('@graph'), list):
            items += data['@graph']
        for item in items:
            if isinstance(item, dict) and item.get('@type') == 'Recipe':
                name = item.get('name') or name
                ri = item.get('recipeIngredient')
                if ri and not raw_ingredients:
                    if isinstance(ri, list):
                        raw_ingredients = [str(x) for x in ri]
                    elif isinstance(ri, str):
                        raw_ingredients = [p.strip() for p in ri.split(',') if p.strip()]
        if name and raw_ingredients:
            break

    # A veces el JSON-LD trae recipeIngredient como lista de UN solo string
    # con todos los ingredientes separados por coma (en vez de un item por
    # ingrediente) — si pasa eso, partirlo.
    if raw_ingredients and len(raw_ingredients) == 1 and ',' in raw_ingredients[0]:
        raw_ingredients = [p.strip() for p in raw_ingredients[0].split(',') if p.strip()]

    if not raw_ingredients:
        raw_ingredients = fallback_html_ingredients(soup)

    if not name:
        title_tag = soup.find('title')
        if title_tag:
            name = title_tag.get_text(strip=True).split('|')[0].strip()

    if not name or not raw_ingredients:
        return None, "sin-datos"

    ingredients = []
    for line in raw_ingredients:
        line = line.strip()
        if not line:
            continue
        ingredients.append({'id': gen_id(), 'text': line, 'category': detect_category(line)})

    if not ingredients:
        return None, "sin-ingredientes"

    return {'id': gen_id(), 'name': name, 'url': url, 'ingredients': ingredients}, None


def worker(url):
    time.sleep(REQUEST_DELAY)
    return extract_recipe(url)


def main():
    urls = fetch_sitemap_urls()
    print(f"URLs encontradas en sitemaps: {len(urls)}", flush=True)

    results = []
    errors = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(worker, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futures):
            url = futures[fut]
            try:
                recipe, err = fut.result()
            except Exception as e:
                recipe, err = None, f"exception: {e}"
            done += 1
            if recipe:
                results.append(recipe)
            else:
                errors.append((url, err))
            if done % 100 == 0 or done == len(urls):
                print(f"{done}/{len(urls)} procesadas — {len(results)} OK, {len(errors)} sin datos", flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False), encoding='utf-8')
    print(f"Listo: {len(results)} pre-recetas escritas en {OUT_PATH}")

    if errors:
        ERR_PATH.write_text('\n'.join(f"{u}\t{e}" for u, e in errors), encoding='utf-8')
        print(f"{len(errors)} URLs sin datos — detalle en {ERR_PATH}")


if __name__ == '__main__':
    main()
