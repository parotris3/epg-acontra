import re
import json
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

# Configuración básica
TZ = ZoneInfo("Europe/Madrid")
OUTPUT_XML = "acontra_plus.xml"
TARGET_URL = "http://www.primevideo.com/-/es/livetv"

CHANNEL_ID = "acontra+ CINE"
CHANNEL_DISPLAY = "acontra+ CINE"

def load_html_from_web(url: str) -> str:
    print(f"Descargando datos de: {url} ...")
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
        print(f"Error descargando: {e}")
        return ""

def extract_channel_json(html: str):
    # Busca el patrón específico
    pattern = r'"logo":"https[^"]*acontra_plus_16x9_white[^"]*","name":"(acontra\+ CINE)","schedule":\[(.*?)\]'
    match = re.search(pattern, html, re.DOTALL)
    
    if not match:
        raise RuntimeError("No se encontró el JSON. Amazon pudo cambiar la estructura.")
    
    schedule_str = match.group(2).strip()
    schedule_clean = schedule_str.rstrip(",")
    if not schedule_clean.startswith("["): schedule_clean = "[" + schedule_clean
    if not schedule_clean.endswith("]"): schedule_clean += "]"
    
    return json.loads(schedule_clean)

def parse_programs_from_json(schedule):
    programs = []
    for item in schedule:
        end_ms = item.get("end")
        if not end_ms: continue
            
        metadata = item.get("metadata", {})
        synopsis = metadata.get("synopsis", "")
        release_year = str(metadata.get("releaseYear", ""))
        raw_title = metadata.get("title", "") or metadata.get("image", {}).get("alternateText", "")
        rating = metadata.get("contentMaturityRating", {}).get("rating", "")

        # Limpieza
        def clean(s): return str(s).strip().replace("\\", "") if s else ""
        
        title = clean(raw_title)
        if rating == "ALL": rating = "Todas las edades"
        
        image_url = metadata.get("image", {}).get("url", "")
        if image_url:
            image_url = urllib.parse.unquote(image_url)
            image_url = re.sub(r'\\u[\da-fA-F]{4}', '', image_url)
        
        programs.append({
            "title": title,
            "synopsis": clean(synopsis),
            "release_year": release_year,
            "rating": clean(rating),
            "image_url": image_url,
            "end_ms": end_ms,
            "start_ms": None,
        })
    
    programs.sort(key=lambda p: p["end_ms"])
    for i in range(len(programs)):
        if i > 0: programs[i]["start_ms"] = programs[i-1]["end_ms"]
        else: programs[i]["start_ms"] = programs[i]["end_ms"] - 2*3600*1000 # 2h antes si es el primero
    return programs

def ms_to_dt(ms): return datetime.fromtimestamp(ms / 1000, TZ)
def dt_to_xmltv(dt): return dt.strftime("%Y%m%d%H%M%S %z")

def generate_xmltv_for_channel(programs):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="prime_acontra_plus">']
    lines.append(f'  <channel id="{CHANNEL_ID}"><display-name>{CHANNEL_DISPLAY}</display-name></channel>')

    for p in programs:
        start = dt_to_xmltv(ms_to_dt(p["start_ms"]))
        end = dt_to_xmltv(ms_to_dt(p["end_ms"]))
        
        title = f"{p['title']} ({p['release_year']})" if p['release_year'] else p['title']
        
        desc_parts = [p['synopsis']] if p['synopsis'] else []
        if p['rating']: desc_parts.append(f"Edad: {p['rating']}")
        desc = " | ".join(desc_parts)

        lines.append(f'  <programme start="{start}" stop="{end}" channel="{CHANNEL_ID}">')
        lines.append(f'    <title lang="es">{title}</title>')
        if desc: lines.append(f'    <desc lang="es">{desc}</desc>')
        if p['image_url']: lines.append(f'    <icon src="{p["image_url"]}"/>')
        lines.append("  </programme>")

    lines.append("</tv>")
    return "\n".join(lines)

if __name__ == "__main__":
    html = load_html_from_web(TARGET_URL)
    if html:
        try:
            sch = extract_channel_json(html)
            progs = parse_programs_from_json(sch)
            xml = generate_xmltv_for_channel(progs)
            with open(OUTPUT_XML, "w", encoding="utf-8") as f: f.write(xml)
            print(f"Generado {OUTPUT_XML} con {len(progs)} programas.")
        except Exception as e:
            print(f"Error procesando: {e}")
            exit(1)
