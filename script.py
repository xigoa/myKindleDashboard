import os
import datetime
import pytz
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
# Ancho: 80 (izq) + 1072 (centro) + 80 (der) = 1232px
# Alto: 1072px + 40px (abajo) = 1112px
WIDTH, HEIGHT = 1232, 1112 
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253
MARCO_LATERAL = 80
MARCO_ABAJO = 40

def get_weather_bilbao():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&hourly=temperature_2m,precipitation_probability,precipitation,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=Europe%2FBerlin"
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
            "code": daily['weather_code'][i]
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
            "code": hourly['weather_code'][i]
        })
        
    return forecast_hourly, forecast_daily

def get_weather_icon(code):
    if code == 0: return "SOL"
    if code in [1, 2, 3]: return "NUB"
    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "LLU"
    return "VAR"

def get_netatmo_data():
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
            res_list.append({
                "nombre": nombre_limpio,
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%"
            })
            
        calle = next((item for item in res_list if "KALEA" in item["nombre"]), None)
        otros = [item for item in res_list if "KALEA" not in item["nombre"]]
        return ([calle] if calle else []) + otros
    except:
        return [{"nombre": "ERROR", "temp": "--", "co2": "400", "hum": "--"}] * 3

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
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()

    # --- 0. DIBUJAR MARCO ---
    draw.rectangle([0, 0, MARCO_LATERAL, HEIGHT], fill=0) # Izquierda
    draw.rectangle([WIDTH-MARCO_LATERAL, 0, WIDTH, HEIGHT], fill=0) # Derecha
    draw.rectangle([0, HEIGHT-MARCO_ABAJO, WIDTH, HEIGHT], fill=0) # Abajo

    # --- 1. CABECERA (Negra a todo lo ancho) ---
    draw.rectangle([0, 0, WIDTH, 90], fill=0)
    zona_bilbao = pytz.timezone('Europe/Madrid')
    ahora_dt = datetime.datetime.now(zona_bilbao)
    ahora_str = ahora_dt.strftime("%d %b  |  %H:%M")
    draw.text((MARCO_LATERAL + 30, 20), f"BILBAO - {ahora_str}", fill=255, font=font_big)

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
        draw.text((x_base+220, y), icono, fill=0, font=font_reg)
        texto_lluvia = f"{h['prob_lluvia']} ({h['mm']}L)"
        draw.text((x_base+320, y), texto_lluvia, fill=0, font=font_reg)

    # --- 4. PREVISIÓN DIARIA ---
    y_sep_daily = 840
    draw.line([MARCO_LATERAL, y_sep_daily, WIDTH - MARCO_LATERAL, y_sep_daily], fill=0, width=4)

    for i, w in enumerate(daily):
        x = MARCO_LATERAL + 35 + (i * 345)
        y_text = y_sep_daily + 25
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia = ["ASTELEH", "ASTEART", "ASTEAZK", "OSTEGUN", "OSTIRAL", "LARUNBAT", "IGANDE"][fecha_obj.weekday()]
        
        draw.text((x, y_text), dia, fill=0, font=font_med)
        draw.text((x + 160, y_text + 5), get_weather_icon(w['code']), fill=0, font=font_small)
        
        draw.text((x, y_text + 50), f"{w['max']} / {w['min']}", fill=0, font=font_med)
        draw.text((x, y_text + 105), f"Euria: {w['mm_sum']}", fill=0, font=font_med)

    img.save("dashboard.png")

if __name__ == "__main__":
    draw_dashboard()
