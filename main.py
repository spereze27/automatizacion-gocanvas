import os
import requests
import gspread
import google.auth
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# Configuración directa (Evitamos fallos de variables de entorno)
GOCANVAS_API_KEY = os.environ.get("GOCANVAS_API_KEY")
FORM_ID = os.environ.get("FORM_ID")
# ID extraído de tu URL: https://docs.google.com/spreadsheets/d/18ArHdNLJYbwf_EKF4rHIXekZ3MHAsa0oJyyUBFoByrg/
SPREADSHEET_ID = "18ArHdNLJYbwf_EKF4rHIXekZ3MHAsa0oJyyUBFoByrg"
USERNAME = "jsalazar@tysallc.com"

def main():
    print("🚀 Iniciando Job: Sincronización GoCanvas (XML) -> Google Sheets")
    
    if not GOCANVAS_API_KEY or not FORM_ID:
        print("❌ Error: Faltan variables GOCANVAS_API_KEY o FORM_ID.")
        return

    datos_hoy = obtener_submissions_gocanvas()
    
    if not datos_hoy:
        print("Empty: No hay envíos para procesar.")
        return

    try:
        enviar_a_google_sheets(datos_hoy)
    except Exception as e:
        # Imprimimos el error detallado para saber qué pasa con ese Response [200]
        print(f"❌ Error detallado en Sheets: {type(e).__name__} - {str(e)}")

def obtener_submissions_gocanvas():
    hoy_utc = datetime.now(timezone.utc)
    ayer = (hoy_utc - timedelta(days=1)).strftime('%m/%d/%Y')
    manana = (hoy_utc + timedelta(days=1)).strftime('%m/%d/%Y')
    
    url = f"https://www.gocanvas.com/apiv2/submissions.xml?form_id={FORM_ID}&begin_date={ayer}&end_date={manana}&username={USERNAME}"
    headers = {"Authorization": f"Bearer {GOCANVAS_API_KEY}"}
    
    print(f"📡 Consultando GoCanvas (Rango: {ayer} - {manana})...")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return parsear_xml_gocanvas(response.text)
    return []

def parsear_xml_gocanvas(xml_string):
    root = ET.fromstring(xml_string)
    lista_submissions = []
    for submission in root.findall('.//Submission'):
        fecha = submission.find('Date')
        valores = {res.find('Label').text: (res.find('Value').text if res.find('Value').text else "") 
                   for res in submission.findall('.//Response') if res.find('Label') is not None}
        lista_submissions.append({"fecha": fecha.text if fecha is not None else "N/A", "valores": valores})
    print(f"📦 Se procesaron {len(lista_submissions)} envíos del XML.")
    return lista_submissions

def enviar_a_google_sheets(datos_gocanvas):
    credentials, project = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    
    cliente_google = gspread.authorize(credentials)
    
    # USAMOS EL ID DIRECTO (Mucho más estable que el nombre)
    print(f"Opening: Intentando acceder al Sheet ID: {SPREADSHEET_ID}")
    spreadsheet = cliente_google.open_by_key(SPREADSHEET_ID)
    hoja = spreadsheet.get_worksheet(0) # Primera pestaña
    
    filas_a_insertar = []
    for sub in datos_gocanvas:
        v = sub["valores"]
        fila = [
            sub["fecha"],
            v.get('Pole ID', 'N/A'),
            v.get('Lattitude', 'N/A'),
            v.get('Longitude', 'N/A'),
            v.get('Pole status', 'N/A'),
            v.get('Pole location', 'N/A'),
            v.get('Access', 'N/A'),
            v.get('Complexity', 'N/A'),
            v.get('Issues', 'N/A'),
            v.get('Additional requeriments', 'N/A'), 
            v.get('Especificar / Specify', 'N/A'),
            v.get('Result', 'N/A'),
            v.get('Technician name', 'N/A')
        ]
        filas_a_insertar.append(fila)

    if filas_a_insertar:
        hoja.append_rows(filas_a_insertar, value_input_option='USER_ENTERED')
        print(f"✅ ÉXITO: {len(filas_a_insertar)} registros añadidos.")

if __name__ == "__main__":
    main()