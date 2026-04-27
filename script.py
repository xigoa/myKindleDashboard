import os
import json
import datetime
from PIL import Image, ImageDraw, ImageFont
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- CONFIGURACIÓN DE DIMENSIONES (Kindle Keyboard) ---
WIDTH, HEIGHT = 800, 600

def get_netatmo_data():
    # Autenticación OAuth2 de Netatmo
    token_url = "https://api.netatmo.com/oauth2/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ['NETATMO_REFRESH_TOKEN'],
        "client_id": os.environ['NETATMO_CLIENT_ID'],
        "client_secret": os.environ['NETATMO_CLIENT_SECRET']
    }
    
    resp = requests.post(token_url, data=payload).json()
    access_token = resp['access_token']
    
    # Obtener datos de las estaciones
    data_url = "https://api.netatmo.com/api/getstationsdata"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get(data_url, headers=headers).json()
    
    devices = res['body']['devices'][0]
    # Estación principal + módulos adicionales
    estaciones = [devices] + devices.get('modules', [])
    
    resultados = []
    for e in estaciones:
        dashboard = e.get('dashboard_data', {})
        resultados.append({
            "nombre": e.get('module_name', 'Principal'),
            "temp": f"{dashboard.get('Temperature', '--')}°",
            "co2": f"{dashboard.get('CO2', '--')}",
            "hum": f"{dashboard.get('Humidity', '--')}%"
        })
    return resultados[:3] # Nos aseguramos de tomar solo 3

def get_calendar_events():
    # Autenticación Google (usa el secreto guardado como JSON)
    info = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
    creds = service_account.Credentials.from_service_account_info(info)
    service = build('calendar', 'v3', credentials=creds)
    
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(calendarId=os.environ['CALENDAR_ID'], timeMin=now,
                                        maxResults=5, singleEvents=True,
                                        orderBy='startTime').execute()
    return events_result.get('items', [])

def draw_dashboard(netatmo, events):
    # Crear imagen en escala de grises (8-bit, luego convertiremos a 4-bit)
    img = Image.new('L', (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    
    # Intentar cargar una fuente, si no, usar la por defecto
    try:
        font_title = ImageFont.truetype("arial.ttf", 24)
        font_data = ImageFont.truetype("arial.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 18)
    except:
        font_title = font_data = font_small = ImageFont.load_default()

    # --- DIBUJAR NETATMO (3 Columnas) ---
    for i, e in enumerate(netatmo):
        x = 20 + (i * 260)
        draw.rectangle([x, 20, x + 240, 240], outline=0, width=3)
        draw.text((x + 20, 30), e['nombre'].upper(), fill=0, font=font_title)
        draw.text((x + 20, 70), e['temp'], fill=0, font=font_data)
        draw.text((x + 20, 130), f"CO2: {e['co2']} ppm", fill=0, font=font_small)
        draw.text((x + 20, 160), f"Hum: {e['hum']}", fill=0, font=font_small)

    # --- DIBUJAR CALENDARIO (Parte inferior) ---
    draw.line([20, 260, 780, 260], fill=0, width=2)
    draw.text((20, 275), "PRÓXIMOS EVENTOS", fill=0, font=font_title)
    
    for i, event in enumerate(events):
        start = event['start'].get('dateTime', event['start'].get('date'))
        start_dt = start.split('T')[0] if 'T' in start else start
        summary = event.get('summary', 'Sin título')
        y = 310 + (i * 45)
        draw.text((30, y), f"• {start_dt}: {summary[:40]}", fill=0, font=font_small)

    # Fecha de actualización (esquina inferior derecha)
    ahora = datetime.datetime.now().strftime("%H:%M")
    draw.text((650, 560), f"Actualizado: {ahora}", fill=0, font=font_small)

    # Guardar optimizado para Kindle
    img.convert('L').save("dashboard.png", "PNG")

if __name__ == "__main__":
    try:
        n_data = get_netatmo_data()
        c_data = get_calendar_events()
        draw_dashboard(n_data, c_data)
    except Exception as e:
        print(f"Error: {e}")