import re
import json
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
OUTPUT_XML = "acontra_plus.xml"
TARGET_URL = "http://www.primevideo.com/-/es/livetv"

CHANNEL_ID = "acontra+ CINE"
CHANNEL_DISPLAY = "acontra+ CINE"

def load_html_from_web(url: str) -> str:
    print(f"Descargando datos de: {url} ...")
    # Simulamos ser un navegador real para evitar bloqueos
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9',
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        raise RuntimeError(f"Error al descargar la web: {e}")

def extract_channel_json(html: str):
    # Buscamos el patrón específico del canal acontra+
    pattern = r'"logo":"https[^"]*acontra_plus_16x9_white[^"]*","name":"(acontra\+ CINE)","schedule":\[(.*?)\]'
    match = re.search(pattern, html, re.DOTALL)
    
    if not match:
        raise RuntimeError("No encontré el JSON de 'acontra+ CINE' en el HTML descargado. Amazon puede haber cambiado la estructura.")
    
    schedule_str = match.group(2).strip()
    schedule_clean = schedule_str.rstrip(",")
    if not schedule_clean.startswith("["):
        schedule_clean = "[" + schedule_clean
    if not schedule_clean.endswith("]"):
        schedule_clean += "]"
    
    try:
        schedule = json.loads(schedule_clean)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Error parseando schedule JSON: {e}")
    
    return schedule

def parse_programs_from_json(schedule):
    programs = []
    
    for item in schedule:
        end_ms = item.get("end")
        if not end_ms:
            continue
            
        metadata = item.get("metadata", {})
        
        # Extracción de datos desde metadata
        synopsis = metadata.get("synopsis", "")
        release_year = metadata.get("releaseYear", "")
        raw_title = metadata.get("title", "")
        
        image_obj = metadata.get("image", {})
        if not raw_title:
            raw_title = image_obj.get("alternateText", "")

        content_rating = metadata.get("contentMaturityRating", {})
        rating = content_rating.get("rating", "")
        
        def clean(s: str) -> str:
            if s is None: return ""
            return str(s).strip().replace("\\", "")
        
        title = clean(raw_title)
        synopsis = clean(synopsis)
        rating = clean(rating)

        # Traducir "ALL" a "Todas las edades"
        if rating == "ALL":
            rating = "Todas las edades"
        
        if release_year:
            release_year = str(release_year)
        
        image_url = image_obj.get("url", "")
        if image_url:
            image_url = urllib.parse.unquote(image_url)
            image_url = re.sub(r'\\u[\da-fA-F]{4}', '', image_url)
        
        programs.append({
            "title": title or "Sin título",
            "synopsis": synopsis,
            "release_year": release_year,
            "rating": rating,
            "image_url": image_url,
            "end_ms": end_ms,
            "start_ms": None,
        })
    
    # Calcular start_ms
    programs.sort(key=lambda p: p["end_ms"])
    for i in range(len(programs)):
        if i > 0:
            programs[i]["start_ms"] = programs[i-1]["end_ms"]
        else:
            programs[i]["start_ms"] = programs[i]["end_ms"] - 2*3600*1000
    
    return programs

def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, TZ)

def dt_to_xmltv(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S %z")

def generate_xmltv_for_channel(programs):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<tv generator-info-name="prime_acontra_plus">')

    lines.append(f'  <channel id="{CHANNEL_ID}">')
    lines.append(f'    <display-name>{CHANNEL_DISPLAY}</display-name>')
    lines.append("  </channel>")

    for p in programs:
        start_dt = ms_to_dt(p["start_ms"])
        end_dt = ms_to_dt(p["end_ms"])
        start_str = dt_to_xmltv(start_dt)
        end_str = dt_to_xmltv(end_dt)

        title = p["title"]
        synopsis = p["synopsis"]
        year = p["release_year"]
        rating = p["rating"]
        image = p["image_url"]

        # 1. Poner año en el título
        if year:
            title = f"{title} ({year})"

        desc_parts = []
        if synopsis:
            desc_parts.append(synopsis)
        
        # 2. Añadir la edad (ya traducida) a la descripción
        if rating:
            desc_parts.append(f"Edad: {rating}")
        
        desc = " | ".join(desc_parts)

        lines.append(f'  <programme start="{start_str}" stop="{end_str}" channel="{CHANNEL_ID}">')
        lines.append(f'    <title lang="es">{title}</title>')
        if desc:
            lines.append(f'    <desc lang="es">{desc}</desc>')
        if image:
            lines.append(f'    <icon src="{image}"/>')
        lines.append("  </programme>")

    lines.append("</tv>")
    return "\n".join(lines)

def main():
    # 1. Descargar HTML de la web
    html = load_html_from_web(TARGET_URL)

    # 2. Extraer y procesar
    schedule = extract_channel_json(html)
    programs = parse_programs_from_json(schedule)
    
    if not programs:
        raise RuntimeError("No se encontraron programas en el schedule de acontra+ CINE.")

    # 3. Generar XML
    xml = generate_xmltv_for_channel(programs)
    with open(OUTPUT_XML, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"ÉXITO: Generado {OUTPUT_XML} con {len(programs)} emisiones.")
    print("Características: Web en vivo, Año en título, Sinopsis completa, Edad corregida.")

if __name__ == "__main__":
    main()
