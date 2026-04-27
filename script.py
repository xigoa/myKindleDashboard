import os
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
WIDTH, HEIGHT = 800, 600
LAT_BILBAO = 43.2627
LON_BILBAO = -2.9253

def get_weather_bilbao():
    # API de Open-Meteo (Gratis, sin registro, excelente para Bilbao)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT_BILBAO}&longitude={LON_BILBAO}&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Europe%2FBerlin"
    data = requests.get(url).json()
    daily = data['daily']
    
    forecast = []
    # Sacamos los próximos 4 días
    for i in range(4):
        forecast.append({
            "fecha": daily['time'][i],
            "max": f"{int(daily['temperature_2m_max'][i])}°",
            "min": f"{int(daily['temperature_2m_min'][i])}°",
            "prob_lluvia": f"{daily['precipitation_probability_max'][i]}%",
            "code": daily['weather_code'][i]
        })
    return forecast

def get_weather_icon(code):
    # Traducción simple de códigos de tiempo a emojis/texto
    # 0=Despejado, 1-3=Nubes, 45-48=Niebla, 51-67=Llovizna/Lluvia, 71-77=Nieve, 80-82=Chubascos
    if code == 0: return "SOL"
    if code in [1, 2, 3]: return "NUBES"
    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]: return "LLUVIA"
    return "VARIO"

def get_netatmo_data():
    # (Mantenemos tu lógica de Netatmo, asegúrate de tener los SECRETS en GitHub)
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
        for e in estaciones[:3]:
            d = e.get('dashboard_data', {})
            res_list.append({
                "nombre": e.get('module_name', 'Principal').replace("Jonen Logela", "JON").replace("Egongela", "SALON").replace("Kalea", "CALLE"),
                "temp": f"{d.get('Temperature', '--')}°",
                "co2": f"{d.get('CO2', '--')}",
                "hum": f"{d.get('Humidity', '--')}%"
            })
        return res_list
    except:
        return [{"nombre": "ERROR", "temp": "--", "co2": "--", "hum": "--"}] * 3

def draw_dashboard():
    # 1. Obtener datos
    netatmo = get_netatmo_data()
    weather = get_weather_bilbao()
    
    # 2. Crear lienzo (Modo L = 8-bit gris)
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)

    # 3. Cargar fuentes (Asegúrate de subirlas a GitHub)
    try:
        font_huge = ImageFont.truetype("Roboto-Bold.ttf", 70)
        font_big = ImageFont.truetype("Roboto-Bold.ttf", 40)
        font_med = ImageFont.truetype("Roboto-Bold.ttf", 25)
        font_reg = ImageFont.truetype("Roboto-Regular.ttf", 18)
    except:
        font_huge = font_big = font_med = font_reg = ImageFont.load_default()

    # --- CABECERA ---
    draw.rectangle([0, 0, 800, 50], fill=0) # Barra negra arriba
    ahora = datetime.datetime.now().strftime("%d %b | %H:%M")
    draw.text((20, 10), f"BILBAO - {ahora}", fill=255, font=font_med)

    # --- BLOQUE NETATMO (TARJETAS) ---
    for i, e in enumerate(netatmo):
        x = 20 + (i * 260)
        # Dibujar tarjeta con borde suave
        draw.rounded_rectangle([x, 70, x+240, 310], radius=15, outline=0, width=3)
        draw.text((x+20, 85), e['nombre'].upper(), fill=0, font=font_reg)
        draw.text((x+20, 110), e['temp'], fill=0, font=font_huge)
        # Iconos textuales o datos extra
        draw.text((x+20, 210), f"CO2: {e['co2']} ppm", fill=0, font=font_reg)
        draw.text((x+20, 245), f"Hum: {e['hum']}", fill=0, font=font_reg)
        # Una pequeña barra visual para el CO2 (si es > 1000 se rellena)
        draw.rectangle([x+20, 235, x+220, 240], outline=0)
        co2_val = int(e['co2']) if e['co2'].isdigit() else 400
        bar_width = min(int((co2_val/1500) * 200), 200)
        draw.rectangle([x+20, 235, x+20+bar_width, 240], fill=0)

    # --- BLOQUE TIEMPO BILBAO ---
    draw.text((20, 340), "PRONÓSTICO BILBAO", fill=0, font=font_med)
    draw.line([20, 375, 780, 375], fill=0, width=2)

    for i, w in enumerate(weather):
        x = 20 + (i * 195)
        fecha_obj = datetime.datetime.strptime(w['fecha'], '%Y-%m-%d')
        dia_sem = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"][fecha_obj.weekday()]
        
        # Caja de día
        draw.text((x+10, 390), dia_sem, fill=0, font=font_med)
        draw.text((x+10, 425), get_weather_icon(w['code']), fill=0, font=font_reg)
        draw.text((x+10, 460), f"MAX: {w['max']}", fill=0, font=font_med)
        draw.text((x+10, 495), f"MIN: {w['min']}", fill=0, font=font_reg)
        draw.text((x+10, 530), f"Lluvia: {w['prob_lluvia']}", fill=0, font=font_reg)

    # Guardar
    img.save("dashboard.png")

if __name__ == "__main__":
    draw_dashboard()
