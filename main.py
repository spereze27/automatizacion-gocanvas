import os
import requests
import gspread
import google.auth
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# Variables inyectadas por GitHub / Cloud Run
GOCANVAS_API_KEY = os.environ.get("GOCANVAS_API_KEY")
FORM_ID = os.environ.get("FORM_ID")
NOMBRE_DEL_SHEET = os.environ.get("NOMBRE_DEL_SHEET", "Resultados Site Survey TYSA")
USERNAME = os.environ.get("GOCANVAS_USERNAME", "jsalazar@tysallc.com") # Tu correo admin

def main():
    print("Iniciando Job: Sincronización GoCanvas (XML) -> Google Sheets")
    
    if not all([GOCANVAS_API_KEY, FORM_ID]):
        print("Error: Faltan variables GOCANVAS_API_KEY o FORM_ID.")
        return

    # 1. Obtener datos de GoCanvas
    datos_hoy = obtener_submissions_gocanvas()
    if not datos_hoy:
        print("No hay envíos nuevos para procesar hoy.")
        return

    # 2. Enviar a Google Sheets
    try:
        enviar_a_google_sheets(datos_hoy)
    except Exception as e:
        print(f"Error crítico enviando a Sheets: {e}")

def obtener_submissions_gocanvas():
    # Usamos hora UTC y un rango amplio (ayer a mañana) para evitar fallos por zona horaria
    hoy_utc = datetime.now(timezone.utc)
    ayer = (hoy_utc - timedelta(days=1)).strftime('%m/%d/%Y')
    manana = (hoy_utc + timedelta(days=1)).strftime('%m/%d/%Y')
    
    # URL de la API v2 solicitando XML
    url = f"https://www.gocanvas.com/apiv2/submissions.xml?form_id={FORM_ID}&begin_date={ayer}&end_date={manana}&username={USERNAME}"
    
    headers = {
        "Authorization": f"Bearer {GOCANVAS_API_KEY}"
    }
    
    print(f"Consultando API GoCanvas desde {ayer} hasta {manana}")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        # Procesar el XML
        return parsear_xml_gocanvas(response.text)
    else:
        print(f"Fallo en API GoCanvas. Status: {response.status_code}")
        print(response.text)
        return []

def parsear_xml_gocanvas(xml_string):
    """Convierte el laberinto del XML en una lista de diccionarios fácil de usar."""
    try:
        root = ET.fromstring(xml_string)
        lista_submissions = []
        
        # Buscar cada envío en el XML
        for submission in root.findall('.//Submission'):
            fecha = submission.find('Date')
            fecha_texto = fecha.text if fecha is not None else "Sin Fecha"
            
            # Extraer todas las respuestas y meterlas en un diccionario {Label: Value}
            valores = {}
            for response in submission.findall('.//Response'):
                label = response.find('Label')
                value = response.find('Value')
                
                if label is not None and value is not None:
                    # value.text puede ser None si el campo se dejó vacío en la app
                    valores[label.text] = value.text if value.text else ""
            
            # Guardamos el paquete completo
            lista_submissions.append({
                "fecha": fecha_texto,
                "valores": valores
            })
            
        return lista_submissions
    except Exception as e:
        print(f"Error parseando XML: {e}")
        return []

def enviar_a_google_sheets(datos_gocanvas):
    # Autenticación automática de Cloud Run (ADC)
    credentials, project = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    
    cliente_google = gspread.authorize(credentials)
    hoja = cliente_google.open(NOMBRE_DEL_SHEET).sheet1
    
    filas_a_insertar = []
    
    for sub in datos_gocanvas:
        valores = sub["valores"]
        
        # Mapeo exacto basado en el XML que nos devolvió GoCanvas
        fila = [
            sub["fecha"],
            valores.get('Pole ID', 'N/A'),
            valores.get('Lattitude', 'N/A'),
            valores.get('Longitude', 'N/A'),
            valores.get('Pole status', 'N/A'),
            valores.get('Pole location', 'N/A'),
            valores.get('Access', 'N/A'),
            valores.get('Complexity', 'N/A'),
            valores.get('Issues', 'N/A'),
            # Nota: Mantenemos el error de tipeo "requeriments" porque así viene en el XML
            valores.get('Additional requeriments', 'N/A'), 
            valores.get('Especificar / Specify', 'N/A'),
            valores.get('Result', 'N/A'),
            valores.get('Technician name', 'N/A')
        ]
        filas_a_insertar.append(fila)

    if filas_a_insertar:
        hoja.append_rows(filas_a_insertar)
        print(f"✅ Se insertaron {len(filas_a_insertar)} filas en Google Sheets.")