import os
import datetime
import pytz
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
WIDTH, HEIGHT = 1072, 1072
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253

def get_weather_bilbao():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&hourly=temperature_2m,precipitation_probability,precipitation,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=Europe%2FBerlin"
    data = requests.get(url).json()
    
    # 1. PRONÓSTICO DIARIO (Próximos 3 días)
    daily = data['daily']
    forecast_daily = []
    for i in range(1, 4): 
        forecast_daily.append({
            "fecha": daily['time'][i],
            "max": f"{int(daily['temperature_2m_max'][i])}°",
            "min": f"{int(daily['temperature_2m_min'][i])}°",
            "prob_lluvia": f"{daily['precipitation_probability_max'][i]}%",
            "mm_sum": f"{daily['precipitation_sum'][i]}L", # ¡Importante!
            "code": daily['weather_code'][i]
        })

    # 2. PRONÓSTICO POR HORAS (16 horas)
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
    if code == 0: return "DESPEJADO"
    if code in [1, 2, 3]: return "NUBES"
    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "LLUVIA"
    return "VARIO"

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
            nombre_limpio = nombre.replace("JONEN LOGELA", "JONEN").replace("EGONGELA", "SALÓN").replace("KALEA", "CALLE")
            res_list.append({
                "nombre": nombre_limpio,
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%"
            })
            
        calle = next((item for item in res_list if "CALLE" in item["nombre"]), None)
        otros = [item for item in res_list if "CALLE" not in item["nombre"]]
        return ([calle] if calle else []) + otros
    except:
        return [{"nombre": "ERROR", "temp": "--", "co2": "400", "hum": "--"}] * 3

def draw_dashboard():
    netatmo = get_netatmo_data()
    hourly, daily = get_weather_bilbao()
    
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    try:
        # --- AJUSTE TAMAÑO FUENTE ---
        # Netatmo reducida de 115 a 105 para que no se salga
        font_huge = ImageFont.truetype("Roboto-Bold.ttf", 105) 
        font_big = ImageFont.truetype("Roboto-Bold.ttf", 55)  
        font_med = ImageFont.truetype("Roboto-Bold.ttf", 35)  
        font_reg = ImageFont.truetype("Roboto-Regular.ttf", 28)
        font_small = ImageFont.truetype("Roboto-Regular.ttf", 22)
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()

    # --- 1. CABECERA ---
    draw.rectangle([0, 0, WIDTH, 90], fill=0)
    zona_bilbao = pytz.timezone('Europe/Madrid')
    ahora_str = datetime.datetime.now(zona_bilbao).strftime("%d %b  |  %H:%M")
    draw.text((30, 20), f"BILBAO - {ahora_str}", fill=255, font=font_big)

    # --- 2. BLOQUE NETATMO (Superior) ---
    for i, e in enumerate(netatmo[:3]):
        x = 30 + (i * 345)
        # Recuadro con borde más grueso (width=5)
        draw.rounded_rectangle([x, 110, x+325, 410], radius=25, outline=0, width=5)
        draw.text((x+25, 130), e['nombre'], fill=0, font=font_med)
        
        # Temperatura con la nueva fuente ajustada
        draw.text((x+25, 175), e['temp'], fill=0, font=font_huge)
        
        if "CALLE" not in e['nombre']:
            draw.text((x+25, 310), f"CO2: {e['co2']} ppm", fill=0, font=font_reg)
            # Barra CO2 visual
            draw.rectangle([x+25, 350, x+300, 362], outline=0, width=2)
            co2_val = int(e['co2']) if e['co2'].isdigit() else 400
            # Escala de CO2 dinámica (empieza en 400ppm)
            bar_w = min(int(((co2_val-400)/1200) * 275), 275)
            if bar_w > 0:
                draw.rectangle([x+25, 350, x+25+bar_w, 362], fill=0)
        
        draw.text((x+25, 370), f"Humedad: {e['hum']}", fill=0, font=font_small)

    # --- 3. PRÓXIMAS 16 HORAS (Centro) ---
    draw.text((30, 440), "PRÓXIMAS 16 HORAS", fill=0, font=font_big)
    draw.line([30, 505, 1042, 505], fill=0, width=4)

    for i, h in enumerate(hourly):
        col = i // 8
        row = i % 8
        x_base = 30 + (col * 520)
        y = 525 + (row * 50)
        
        # --- AJUSTE DE COLUMNAS PARA EVITAR SOLAPE ---
        # Hora y temperatura bien separadas
        draw.text((x_base, y), h['hora'], fill=0, font=font_med)
        draw.text((x_base+120, y), h['temp'], fill=0, font=font_med)
        
        # Icono NUB/LLU con fuente regular para no solapar
        icono = get_weather_icon(h['code'])[:3]
        draw.text((x_base+220, y), icono, fill=0, font=font_reg)
        
        # Probabilidad y litros con la nueva separación
        texto_lluvia = f"{h['prob_lluvia']} ({h['mm']}L)"
        draw.text((x_base+320, y), texto_lluvia, fill=0, font=font_reg)

   # --- 4. PREVISIÓN DIARIA (Inferior) ---
    draw.line([0, 930, WIDTH, 930], fill=0, width=3)
    draw.text((30, 940), "PRÓXIMOS DÍAS", fill=0, font=font_big)

    for i, w in enumerate(daily):
        x = 35 + (i * 345)
        y_base = 1000
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia = ["LUNES", "MARTES", "MIÉRC.", "JUEVES", "VIERN.", "SÁB.", "DOM."][fecha_obj.weekday()]
        
        # Nombre del día e icono
        draw.text((x, y_base), dia, fill=0, font=font_med)
        draw.text((x + 160, y_base + 5), get_weather_icon(w['code'])[:3], fill=0, font=font_small)
        
        # Temperatura Max / Min
        draw.text((x, y_base + 45), f"{w['max']} / {w['min']}", fill=0, font=font_big)
        
        # Lluvia total acumulada
        draw.text((x, y_base + 105), f"Lluvia total: {w['mm_sum']}", fill=0, font=font_small)

    # ESTA LÍNEA DEBE TENER LA MISMA SANGRÍA QUE EL 'FOR'
    img.save("dashboard.png")

if __name__ == "__main__":
    draw_dashboard()
