import os
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
WIDTH, HEIGHT = 800, 600
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253

def get_weather_bilbao():
    # Añadimos precipitation_sum en la parte de daily
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&hourly=temperature_2m,precipitation_probability,precipitation,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=Europe%2FBerlin"
    data = requests.get(url).json()
    
    # 1. PRONÓSTICO DIARIO (Ajustado a los 2 próximos días)
    daily = data['daily']
    forecast_daily = []
    for i in range(1, 3): # De 1 a 3 para pillar mañana y pasado
        forecast_daily.append({
            "fecha": daily['time'][i],
            "max": f"{int(daily['temperature_2m_max'][i])}°",
            "min": f"{int(daily['temperature_2m_min'][i])}°",
            "prob_lluvia": f"{daily['precipitation_probability_max'][i]}%",
            "mm_sum": f"{daily['precipitation_sum'][i]}L", # Nuevo dato
            "code": daily['weather_code'][i]
        })

    # 2. PRONÓSTICO POR HORAS (Mantenemos las 12 horas)
    hourly = data['hourly']
    now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    now_str = now_local.strftime("%Y-%m-%dT%H:00")
    
    start_idx = 0
    for i, t in enumerate(hourly['time']):
        if t >= now_str:
            start_idx = i
            break

    forecast_hourly = []
    for i in range(start_idx, start_idx + 12):
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
            # Limpiamos nombres
            nombre_limpio = e.get('module_name', 'Principal').replace("Jonen Logela", "JONEN LOGELA").replace("Egongela", "SALON").replace("Kalea", "CALLE")
            res_list.append({
                "nombre": nombre_limpio,
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%"
            })
            
        # Forzar que CALLE sea el primero
        calle = next((item for item in res_list if item["nombre"] == "CALLE"), None)
        otros = [item for item in res_list if item["nombre"] != "CALLE"]
        final_list = ([calle] if calle else []) + otros
        
        return final_list[:3]
    except Exception as e:
        print(f"Error Netatmo: {e}")
        return [{"nombre": "ERROR", "temp": "--", "co2": "--", "hum": "--"}] * 3

def draw_dashboard():
    netatmo = get_netatmo_data()
    hourly, daily = get_weather_bilbao()
    
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    try:
        font_huge = ImageFont.truetype("Roboto-Bold.ttf", 75)
        font_big = ImageFont.truetype("Roboto-Bold.ttf", 35)
        font_med = ImageFont.truetype("Roboto-Bold.ttf", 22)
        font_reg = ImageFont.truetype("Roboto-Regular.ttf", 20)
        font_small = ImageFont.truetype("Roboto-Regular.ttf", 15)
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()

    # --- CABECERA ---
    draw.rectangle([0, 0, 800, 45], fill=0)
    ahora = datetime.datetime.now().strftime("%d %b | %H:%M")
    draw.text((20, 10), f"BILBAO - {ahora}", fill=255, font=font_med)

    # --- BLOQUE NETATMO ---
    for i, e in enumerate(netatmo):
        x = 20 + (i * 260)
        draw.rounded_rectangle([x, 65, x+240, 290], radius=15, outline=0, width=3)
        draw.text((x+20, 80), e['nombre'].upper(), fill=0, font=font_reg)
        draw.text((x+20, 110), e['temp'], fill=0, font=font_huge)
        
        # Limpiar CO2 en CALLE de forma segura
        if "CALLE" not in e['nombre'].upper():
            draw.text((x+20, 205), f"CO2: {e['co2']} ppm", fill=0, font=font_reg)
            draw.rectangle([x+20, 230, x+220, 235], outline=0)
            co2_val = int(e['co2']) if e['co2'].isdigit() else 400
            bar_width = min(int((co2_val/1500) * 200), 200)
            draw.rectangle([x+20, 230, x+20+bar_width, 235], fill=0)
            
        # La humedad sí la dejamos para todos (ajustando la altura si es CALLE)
        y_hum = 250 if "CALLE" not in e['nombre'].upper() else 205
        draw.text((x+20, y_hum), f"Hum: {e['hum']}", fill=0, font=font_reg)

    # --- BLOQUE TIEMPO: HORAS (Izquierda, 2 Columnas) ---
    draw.text((15, 320), "PRÓXIMAS 12 HORAS", fill=0, font=font_med)
    draw.line([15, 350, 440, 350], fill=0, width=2) # Alargamos la línea

    for i, h in enumerate(hourly):
        col = i // 6   
        row = i % 6    
        
        # Aumentamos la separación entre las dos columnas a 220px (antes 185)
        x = 15 + (col * 220) 
        y = 365 + (row * 35) 
        
        icono = get_weather_icon(h['code'])[:3] 
        texto_lluvia = f"{h['prob_lluvia']} ({h['mm']}L)"
        
        # Ajustamos los espacios internos
        draw.text((x, y), h['hora'], fill=0, font=font_reg)
        draw.text((x + 55, y), icono, fill=0, font=font_small)
        draw.text((x + 90, y), h['temp'], fill=0, font=font_reg)    
        draw.text((x + 125, y), texto_lluvia, fill=0, font=font_small)

    # --- BLOQUE TIEMPO: PRÓXIMOS 2 DÍAS (Derecha) ---
    # Empujamos todo este bloque al píxel 470 (antes estaba en el 380)
    draw.text((470, 320), "PRÓXIMOS DÍAS", fill=0, font=font_med)
    draw.line([470, 350, 785, 350], fill=0, width=2)

    for i, w in enumerate(daily):
        # Juntamos los días a 160px de separación (antes 210)
        x = 470 + (i * 160) 
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia_sem = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"][fecha_obj.weekday()]
        
        draw.text((x, 370), dia_sem, fill=0, font=font_med)
        draw.text((x, 410), get_weather_icon(w['code']), fill=0, font=font_reg)
        draw.text((x, 450), f"Max: {w['max']}", fill=0, font=font_med)
        draw.text((x, 485), f"Min: {w['min']}", fill=0, font=font_reg)
        draw.text((x, 520), f"Lluvia: {w['prob_lluvia']}", fill=0, font=font_reg)
        draw.text((x, 545), f"Total: {w['mm_sum']}", fill=0, font=font_reg)
        
    img.save("dashboard.png")

if __name__ == "__main__":
    draw_dashboard()
