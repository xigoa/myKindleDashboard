import os
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
WIDTH, HEIGHT = 800, 600
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253

def get_weather_bilbao():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&hourly=temperature_2m,precipitation_probability,precipitation,weather_code&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum&timezone=Europe%2FBerlin"
    data = requests.get(url).json()
    
    # 1. PRONÓSTICO DIARIO (Próximos 2 días)
    daily = data['daily']
    forecast_daily = []
    for i in range(1, 3): 
        forecast_daily.append({
            "fecha": daily['time'][i],
            "max": f"{int(daily['temperature_2m_max'][i])}°",
            "min": f"{int(daily['temperature_2m_min'][i])}°",
            "prob_lluvia": f"{daily['precipitation_probability_max'][i]}%",
            "mm_sum": f"{daily['precipitation_sum'][i]}L",
            "code": daily['weather_code'][i]
        })

    # 2. PRONÓSTICO POR HORAS (¡Ahora 16 horas!)
    hourly = data['hourly']
    now_local = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    now_str = now_local.strftime("%Y-%m-%dT%H:00")
    
    start_idx = 0
    for i, t in enumerate(hourly['time']):
        if t >= now_str:
            start_idx = i
            break

    forecast_hourly = []
    for i in range(start_idx, start_idx + 16): # <--- CAMBIO A 16
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
            nombre_limpio = e.get('module_name', 'Principal').replace("Jonen Logela", "JONEN LOGELA").replace("Egongela", "SALON").replace("Kalea", "CALLE")
            res_list.append({
                "nombre": nombre_limpio,
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%"
            })
            
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
        # Hemos reducido la fuente huge de 75 a 65 para comprimir las cajas
        font_huge = ImageFont.truetype("Roboto-Bold.ttf", 65) 
        font_big = ImageFont.truetype("Roboto-Bold.ttf", 35)
        font_med = ImageFont.truetype("Roboto-Bold.ttf", 22)
        font_reg = ImageFont.truetype("Roboto-Regular.ttf", 18)
        font_small = ImageFont.truetype("Roboto-Regular.ttf", 15)
    except:
        font_huge = font_big = font_med = font_reg = font_small = ImageFont.load_default()

    # --- CABECERA ---
    draw.rectangle([0, 0, 800, 45], fill=0)
    ahora = datetime.datetime.now().strftime("%d %b | %H:%M")
    draw.text((20, 10), f"BILBAO - {ahora}", fill=255, font=font_med)

    # --- BLOQUE NETATMO (COMPRIMIDO) ---
    for i, e in enumerate(netatmo):
        x = 20 + (i * 260)
        # Altura de la caja reducida: ahora termina en 245 (antes 290)
        draw.rounded_rectangle([x, 55, x+240, 245], radius=15, outline=0, width=3)
        draw.text((x+20, 65), e['nombre'].upper(), fill=0, font=font_reg)
        draw.text((x+20, 95), e['temp'], fill=0, font=font_huge)
        
        if "CALLE" not in e['nombre'].upper():
            draw.text((x+20, 180), f"CO2: {e['co2']} ppm", fill=0, font=font_small)
            draw.rectangle([x+20, 205, x+220, 210], outline=0)
            co2_val = int(e['co2']) if e['co2'].isdigit() else 400
            bar_width = min(int((co2_val/1500) * 200), 200)
            draw.rectangle([x+20, 205, x+20+bar_width, 210], fill=0)
            
        y_hum = 220 if "CALLE" not in e['nombre'].upper() else 180
        draw.text((x+20, y_hum), f"Hum: {e['hum']}", fill=0, font=font_small)

    # --- BLOQUE TIEMPO: HORAS (Izquierda, 2 Columnas de 8 filas) ---
    # Subimos los títulos a la altura 275 (antes 320)
    draw.text((15, 275), "PRÓXIMAS 16 HORAS", fill=0, font=font_med)
    draw.line([15, 305, 500, 305], fill=0, width=2) 

    for i, h in enumerate(hourly):
        col = i // 8   # 8 filas por columna
        row = i % 8    
        
        # Separación GIGANTE entre columnas (x250) para que nada se monte
        x = 15 + (col * 250) 
        y = 315 + (row * 33) # Más juntitas verticalmente (salto de 33px)
        
        icono = get_weather_icon(h['code'])[:3] 
        texto_lluvia = f"{h['prob_lluvia']} ({h['mm']}L)"
        
        draw.text((x, y), h['hora'], fill=0, font=font_reg)
        draw.text((x + 55, y), icono, fill=0, font=font_small)
        draw.text((x + 95, y), h['temp'], fill=0, font=font_reg)    
        draw.text((x + 135, y), texto_lluvia, fill=0, font=font_small)

    # --- BLOQUE TIEMPO: PRÓXIMOS 2 DÍAS (Derecha) ---
    draw.text((530, 275), "PRÓXIMAS PREVISIONES", fill=0, font=font_med)
    draw.line([530, 305, 785, 305], fill=0, width=2)

    for i, w in enumerate(daily):
        x = 530 + (i * 135) # Juntamos los dos días en el lado derecho
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia_sem = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"][fecha_obj.weekday()]
        
        draw.text((x, 320), dia_sem, fill=0, font=font_med)
        draw.text((x, 360), get_weather_icon(w['code']), fill=0, font=font_reg)
        draw.text((x, 400), f"Max: {w['max']}", fill=0, font=font_med)
        draw.text((x, 435), f"Min: {w['min']}", fill=0, font=font_reg)
        draw.text((x, 480), f"Lluvia: {w['prob_lluvia']}", fill=0, font=font_reg)
        draw.text((x, 505), f"Total: {w['mm_sum']}", fill=0, font=font_reg)

    img.save("dashboard.png")

if __name__ == "__main__":
    draw_dashboard()
