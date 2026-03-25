import os
import requests
import gspread
import google.auth
from datetime import datetime

# Variables inyectadas por GitHub / Cloud Run 
GOCANVAS_API_KEY = os.environ.get("GOCANVAS_API_KEY")
FORM_ID = os.environ.get("FORM_ID")
NOMBRE_DEL_SHEET = os.environ.get("NOMBRE_DEL_SHEET", "Resultados Site Survey TYSA")

def main():
    print("Iniciando Job: Sincronización GoCanvas -> Google Sheets")
    
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
    hoy = datetime.now().strftime('%Y-%m-%dT00:00:00Z')
    url = f"https://www.gocanvas.com/apiv3/submissions?form_id={FORM_ID}&begin_date={hoy}"
    headers = {
        "Authorization": f"Bearer {GOCANVAS_API_KEY}",
        "Accept": "application/json"
    }
    
    print(f"Consultando API GoCanvas desde: {hoy}")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get('submissions', [])
    else:
        print(f"Fallo en API GoCanvas. Status: {response.status_code}")
        return []

def enviar_a_google_sheets(datos_gocanvas):
    # MAGIA DE GCP: Application Default Credentials (ADC)
    # Autentica automáticamente usando la identidad de Cloud Run, sin archivos JSON.
    credentials, project = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    
    cliente_google = gspread.authorize(credentials)
    hoja = cliente_google.open(NOMBRE_DEL_SHEET).sheet1
    
    filas_a_insertar = []
    
    for sub in datos_gocanvas:
        valores = {item['label']: item['value'] for item in sub.get('item_values', [])}
        fila = [
            sub.get('date'),
            valores.get('Power Pole Number', 'N/A'),
            valores.get('Latitud Esperada', 'N/A'),
            valores.get('Longitud Esperada', 'N/A'),
            valores.get('ESTADO DEL POSTE / POLE STATUS', 'N/A'),
            valores.get('UBICACIÓN DEL POSTE / POLE LOCATION', 'N/A'),
            valores.get('ACCESO / ACCESS', 'N/A'),
            valores.get('COMPLEJIDAD / COMPLEXITY', 'N/A'),
            valores.get('PROBLEMAS / ISSUES', 'N/A'),
            valores.get('REQUERIMIENTOS ADICIONALES', 'N/A'),
            valores.get('Especificar', 'N/A'),
            valores.get('RESULTADO / RESULT', 'N/A'),
            valores.get('Nombre técnico / Technician name', 'N/A')
        ]
        filas_a_insertar.append(fila)

    if filas_a_insertar:
        hoja.append_rows(filas_a_insertar)
        print(f"✅ Se insertaron {len(filas_a_insertar)} filas en Sheets.")

if __name__ == "__main__":
    # Cloud Run Job ejecutará el script directamente
    main()