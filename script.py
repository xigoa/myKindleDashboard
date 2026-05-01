import os
import datetime
import json
import pytz
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
# Ancho: 100 (izq) + 1072 (centro) + 100 (der) = 1272px
# Alto: 1072px + 40px (abajo) = 1112px
WIDTH, HEIGHT = 1272, 1112 
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253
MARCO_LATERAL = 100
MARCO_ABAJO = 40

def get_wind_direction(degrees):
    if degrees is None: return ""
    # Puntos cardinales en Euskera: N, NE, E, SE, S, SW, W, NW
    dirs = ["I", "IE", "E", "HE", "H", "HM", "M", "IM"] 
    ix = int((degrees + 22.5) / 45) % 8
    return dirs[ix]

def get_wind_arrow(degrees):
    if degrees is None: return ""
    # Flechas de la fuente Weather Icons (wi-direction-*)
    # 0° (Norte -> Sur), 45° (NE -> SO), 90° (E -> O), etc.
    arrows = [
        "\uf058", # ↓ (Sur)
        "\uf059", # ↙ (Suroeste)
        "\uf056", # ← (Oeste)
        "\uf057", # ↖ (Noroeste)
        "\uf05c", # ↑ (Norte)
        "\uf05d", # ↗ (Noreste)
        "\uf05a", # → (Este)
        "\uf05b"  # ↘ (Sureste)
    ]
    ix = int((degrees + 22.5) / 45) % 8
    return arrows[ix]

def get_weather_bilbao():
    # ¡NUEVA URL! Hemos añadido wind_speed_10m_max y wind_direction_10m_dominant
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,wind_direction_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant&timezone=Europe%2FBerlin"
    data = requests.get(url).json()
    
    daily = data['daily']
    forecast_daily = []
    for i in range(1, 4): 
        forecast_daily.append({
            "fecha": daily['time'][i],
            "max": f"{int(daily['temperature_2m_max'][i])}°",
            "min": f"{int(daily['temperature_2m_min'][i])}°",
            "prob_lluvia": f"{daily['precipitation_probability_max'][i]}%",
            "mm_sum": f"{daily['precipitation_sum'][i]}L",
            "code": daily['weather_code'][i],
            "wind_speed": f"{int(daily['wind_speed_10m_max'][i])} km/h", # Nuevo
            "wind_dir": get_wind_direction(daily['wind_direction_10m_dominant'][i]) # Nuevo
        })

    hourly = data['hourly']
    zona_bilbao = pytz.timezone('Europe/Madrid')
    now_local = datetime.datetime.now(zona_bilbao)
    now_str = now_local.strftime("%Y-%m-%dT%H:00")
    
    start_idx = 0
    for i, t in enumerate(hourly['time']):
        if t >= now_str:
            start_idx = i
            break

    forecast_hourly = []
    for i in range(start_idx, start_idx + 16):
        time_str = hourly['time'][i].split('T')[1] 
        forecast_hourly.append({
            "hora": time_str,
            "temp": f"{int(hourly['temperature_2m'][i])}°",
            "prob_lluvia": f"{hourly['precipitation_probability'][i]}%",
            "mm": hourly['precipitation'][i],
            "code": hourly['weather_code'][i],
            "wind_dir": hourly['wind_direction_10m'][i] # ¡NUEVO DATO RECOGIDO!
        })
        
    return forecast_hourly, forecast_daily

def get_netatmo_data():
    archivo_cache = "netatmo_cache.json"
    
    try:
        token_url = "https://api.netatmo.com/oauth2/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": os.environ['NETATMO_REFRESH_TOKEN'],
            "client_id": os.environ['NETATMO_CLIENT_ID'],
            "client_secret": os.environ['NETATMO_CLIENT_SECRET']
        }
        resp = requests.post(token_url, data=payload).json()
        access_token = resp['access_token']
        data_url = "https://api.netatmo.com/api/getstationsdata"
        res = requests.get(data_url, headers={"Authorization": f"Bearer {access_token}"}).json()
        devices = res['body']['devices'][0]
        estaciones = [devices] + devices.get('modules', [])
        
        res_list = []
        for e in estaciones:
            d = e.get('dashboard_data', {})
            nombre = e.get('module_name', 'Principal').upper()
            nombre_limpio = nombre.replace("JONEN LOGELA", "JONEN LOGELA").replace("EGONGELA", "EGONGELA").replace("KALEA", "KALEA")
            
            # Sacar la hora exacta de la medición
            ts = d.get('time_utc')
            if ts:
                dt = datetime.datetime.fromtimestamp(ts, pytz.timezone('Europe/Madrid'))
                hora_medicion = dt.strftime("%H:%M")
            else:
                hora_medicion = "--:--"

            res_list.append({
                "nombre": nombre_limpio,
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%",
                "hora": hora_medicion 
            })
            
        calle = next((item for item in res_list if "KALEA" in item["nombre"]), None)
        otros = [item for item in res_list if "KALEA" not in item["nombre"]]
        resultado_final = ([calle] if calle else []) + otros
        
        # ¡ÉXITO! Guardamos los datos en nuestro "cuaderno" por si acaso la próxima vez falla
        with open(archivo_cache, 'w') as f:
            json.dump(resultado_final, f)
            
        return resultado_final
        
    except Exception as error_api:
        # ¡FALLO! La API de Netatmo no responde. Vamos a buscar nuestro cuaderno.
        try:
            with open(archivo_cache, 'r') as f:
                datos_viejos = json.load(f)
                print("Usando datos cacheados de Netatmo.")
                return datos_viejos
        except Exception as error_cache:
            # Fallo catastrófico (ej: es la primera vez que arranca y no existe el archivo aún)
            print("Error total. Sin datos en caché.")
            return [{"nombre": "ERROR", "temp": "--", "co2": "400", "hum": "--", "hora": "--:--"}] * 3
            
def get_weather_icon(code):
    """
    Devuelve el icono Unicode (para una fuente de iconos del tiempo)
    correspondiente a un código meteorológico WMO (0-99).

    Códigos WMO: 
    0: Despejado
    1-3: Nubosidad variable
    45, 48: Niebla
    51-57: Llovizna
    61-67: Lluvia
    71-77: Nieve
    80-82: Chaparrones
    85-86: Chaparrones de nieve
    95-99: Tormenta
    """
    try:
        font_icons = ImageFont.truetype("weathericons-regular-webfont.ttf", 40)
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()
    
    # 0: Despejado (SOL)
    if code == 0:
        return "\uf00d"  # Símbolo de Sol (\uf00d - sol despejado en Weather Icons)
    
    # 1: Principalmente despejado, 2: Nubes dispersas, 3: Nublado (NUBOSIDAD VARIABLE / NUBES Y SOL)
    elif code == 1:
        return "\uf00c"  # Principalmente despejado (\uf00c - pocas nubes sol en Weather Icons)
    elif code == 2:
        return "\uf002"  # Nubes dispersas (\uf002 - nubes sol en Weather Icons)
    elif code == 3:
        return "\uf013"  # Nublado (\uf013 - nublado en Weather Icons)

    # 45: Niebla, 48: Niebla con escarcha (NIEBLA)
    elif code in [45, 48]:
        return "\uf014"  # Niebla (\uf014 - niebla en Weather Icons)

    # 51: Llovizna ligera, 53: moderada, 55: densa, 56: Llovizna helada ligera, 57: densa (LLOVIZNA / ZIRIMIRI)
    elif code in [51, 56]:
        return "\uf019"  # Llovizna ligera (\uf019 - llovizna en Weather Icons)
    elif code in [53, 55, 57]:
        return "\uf01a"  # Llovizna moderada/fuerte (\uf01a - lluvia ligera en Weather Icons, más densa que llovizna)

    # 61: Lluvia ligera, 63: moderada, 65: fuerte, 66: Lluvia helada ligera, 67: fuerte (LLUVIA / EURIA)
    elif code in [61, 66]:
        return "\uf01a"  # Lluvia ligera (\uf01a - lluvia ligera en Weather Icons)
    elif code == 63:
        return "\uf018"  # Lluvia moderada (\uf018 - lluvia en Weather Icons)
    elif code in [65, 67]:
        return "\uf01b"  # Lluvia fuerte (\uf01b - lluvia fuerte en Weather Icons)

    # 71: Nieve ligera, 73: moderada, 75: fuerte, 77: Granos de nieve (NIEVE / ELURRA)
    elif code in [71, 77]:
        return "\uf01b"  # Nieve ligera (\uf01b - nieve ligera en Weather Icons)
    elif code == 73:
        return "\uf076"  # Nieve moderada (\uf076 - nieve en Weather Icons)
    elif code == 75:
        return "\uf064"  # Nieve fuerte (\uf064 - nieve fuerte en Weather Icons)

    # 80: Chaparrones ligeros, 81: moderados, 82: violentos (CHAPARRONES / ZAPARRADA)
    elif code == 80:
        return "\uf01a"  # Chaparrones ligeros (\uf01a - lluvia ligera en Weather Icons, similar a chaparrón ligero)
    elif code in [81, 82]:
        return "\uf01b"  # Chaparrones moderados/fuertes (\uf01b - lluvia fuerte en Weather Icons)

    # 85: Chaparrones de nieve ligeros, 86: fuertes (CHAPARRONES DE NIEVE / ELUR ZAPARRADA)
    elif code == 85:
        return "\uf064"  # Chaparrones de nieve ligeros (\uf064 - nieve ligera en Weather Icons, similar a chaparrón ligero nieve)
    elif code == 86:
        return "\uf064"  # Chaparrones de nieve fuertes (\uf064 - nieve fuerte en Weather Icons)

    # 95: Tormenta ligera/moderada, 96: Tormenta con granizo ligero, 99: fuerte con granizo (TORMENTA / EKAITZA)
    elif code == 95:
        return "\uf01e"  # Tormenta (\uf01e - tormenta en Weather Icons)
    elif code in [96, 99]:
        return "\uf03b"  # Tormenta con granizo (\uf03b - tormenta con granizo en Weather Icons)

    # En caso de código desconocido o no clasificado
    return "\uf07b"  # Icono genérico/desconocido (\uf07b - desconocido en Weather Icons)

def draw_dashboard():
    netatmo = get_netatmo_data()
    hourly, daily = get_weather_bilbao()
    
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    try:
        font_huge = ImageFont.truetype("Roboto-Bold.ttf", 95)
        font_big = ImageFont.truetype("Roboto-Bold.ttf", 48)
        font_med = ImageFont.truetype("Roboto-Bold.ttf", 35)
        font_reg = ImageFont.truetype("Roboto-Regular.ttf", 28)
        font_small = ImageFont.truetype("Roboto-Regular.ttf", 22)
        font_icons = ImageFont.truetype("weathericons-regular-webfont.ttf", 40)
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()

    # --- 0. DIBUJAR MARCO ---
    draw.rectangle([0, 0, MARCO_LATERAL, HEIGHT], fill=0) # Izquierda
    draw.rectangle([WIDTH-MARCO_LATERAL, 0, WIDTH, HEIGHT], fill=0) # Derecha
    draw.rectangle([0, HEIGHT-MARCO_ABAJO, WIDTH, HEIGHT], fill=0) # Abajo

    # --- 1. CABECERA ---
    draw.rectangle([0, 0, WIDTH, 90], fill=0)
    zona_bilbao = pytz.timezone('Europe/Madrid')
    ahora_dt = datetime.datetime.now(zona_bilbao)
    ahora_str = ahora_dt.strftime("%d %b  |  %H:%M")
    
    # 1.1 Texto principal (Hora de creación del PNG)
    texto_principal = f"BILBAO - {ahora_str}"
    draw.text((MARCO_LATERAL + 30, 20), texto_principal, fill=255, font=font_big)
    
    # 1.2 Calcular dónde poner la hora de Netatmo
    # Calculamos el ancho del texto principal para poner el paréntesis justo a la derecha
    try:
        ancho_principal = int(font_big.getlength(texto_principal))
    except AttributeError:
        # Fallback por si la máquina de GitHub usa una versión antigua de Pillow
        ancho_principal = font_big.getsize(texto_principal)[0] 
        
    # Cogemos la hora de actualización del primer sensor de Netatmo
    hora_netatmo = netatmo[0].get('hora', '--:--') if netatmo else "--:--"
    texto_netatmo = f"({hora_netatmo})"
    
    # Lo dibujamos sumando el ancho del texto principal + 20 píxeles de margen.
    # Bajamos la Y a 30 (en vez de 20) para que la letra pequeña se alinee bien por abajo.
    pos_x_netatmo = MARCO_LATERAL + 30 + ancho_principal + 150
    draw.text((pos_x_netatmo, 30), texto_netatmo, fill=255, font=font_med)

    # --- 2. BLOQUE NETATMO ---
    for i, e in enumerate(netatmo[:3]):
        x = MARCO_LATERAL + 30 + (i * 345)
        draw.rounded_rectangle([x, 110, x+325, 380], radius=25, outline=0, width=5)
        draw.text((x+25, 125), e['nombre'], fill=0, font=font_med)
        draw.text((x+25, 165), e['temp'], fill=0, font=font_huge)
        if "KALEA" not in e['nombre']:
            draw.text((x+25, 290), f"CO2: {e['co2']} ppm", fill=0, font=font_reg)
            draw.rectangle([x+25, 330, x+300, 342], outline=0, width=2)
            co2_val = int(e['co2']) if e['co2'].isdigit() else 400
            bar_w = min(int(((co2_val-400)/1200) * 275), 275)
            if bar_w > 0: draw.rectangle([x+25, 330, x+25+bar_w, 342], fill=0)
        draw.text((x+25, 348), f"Humedad: {e['hum']}", fill=0, font=font_small)

    # --- 3. PRÓXIMAS 16 HORAS ---
    y_sep_hourly = 410
    draw.line([MARCO_LATERAL + 30, y_sep_hourly, WIDTH - MARCO_LATERAL - 30, y_sep_hourly], fill=0, width=4)

    for i, h in enumerate(hourly):
        col = i // 8
        row = i % 8
        x_base = MARCO_LATERAL + 30 + (col * 520)
        y = y_sep_hourly + 20 + (row * 50)
        
        draw.text((x_base, y), h['hora'], fill=0, font=font_med)
        draw.text((x_base+120, y), h['temp'], fill=0, font=font_med)
        
        icono = get_weather_icon(h['code'])
        draw.text((x_base+220, y), icono, fill=0, font=font_icons)
        
        # ¡NUEVA LÍNEA! Dibujamos la flecha en el hueco X=275. 
        # Usamos font_reg (Roboto) que pinta las flechas estándar perfectas.
        # Usamos font_icons para que entienda las flechas de viento
        flecha = get_wind_arrow(h['wind_dir'])
        draw.text((x_base+275, y), flecha, fill=0, font=font_icons)
        
        texto_lluvia = f"{h['prob_lluvia']} ({h['mm']}L)"
        draw.text((x_base+320, y), texto_lluvia, fill=0, font=font_reg)

    # --- 4. PREVISIÓN DIARIA ---
    y_sep_daily = 840
    draw.line([MARCO_LATERAL, y_sep_daily, WIDTH - MARCO_LATERAL, y_sep_daily], fill=0, width=4)

    for i, w in enumerate(daily):
        x = MARCO_LATERAL + 35 + (i * 345)
        y_text = y_sep_daily + 25
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia = ["ASTELEH", "ASTEART", "ASTEAZK", "OSTEGUN", "OSTIRAL", "LARUNB", "IGANDE"][fecha_obj.weekday()]
        
        draw.text((x, y_text), dia, fill=0, font=font_med)
        draw.text((x + 160, y_text + 5), get_weather_icon(w['code']), fill=0, font=font_icons)
        
        draw.text((x, y_text + 50), f"{w['max']} / {w['min']}", fill=0, font=font_med)
        draw.text((x, y_text + 105), f"Euria: {w['mm_sum']}", fill=0, font=font_med)
        
        # ¡NUEVA LÍNEA DEL VIENTO! La ponemos a una altura de Y + 160
        draw.text((x, y_text + 160), f"H: {w['wind_speed']} {w['wind_dir']}", fill=0, font=font_med)

    # 1. Guardar la versión normal (Derecha, para tu ordenador)
    img.save("dashboard.png")

    # 2. Guardar la versión rotada (Tumbada, exclusiva para el Kindle)
    img_rotated = img.rotate(270, expand=True) 
    #img_kindle = img_rotated.resize((600, 720)) # ¡Forzamos el tamaño exacto!
    img_rotated.save("dashboard_rotated.png") # <--- AHORA SÍ GUARDAMOS LA PEQUEÑA

if __name__ == "__main__":
    draw_dashboard()
