import os
import requests
import gspread
import google.auth
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ==========================================
# CONFIGURACIÓN (ID de tu proyecto TYSA)
# ==========================================
GOCANVAS_API_KEY = os.environ.get("GOCANVAS_API_KEY")
FORM_ID = os.environ.get("FORM_ID")
SPREADSHEET_ID = "18ArHdNLJYbwf_EKF4rHIXekZ3MHAsa0oJyyUBFoByrg"
USERNAME = "jsalazar@tysallc.com"

def main():
    print("🚀 Iniciando Job: Sincronización GoCanvas (XML + Imágenes) -> Google Sheets")
    
    if not GOCANVAS_API_KEY or not FORM_ID:
        print("❌ Error: Faltan variables GOCANVAS_API_KEY o FORM_ID.")
        return

    # 1. Obtener datos de GoCanvas
    datos_hoy = obtener_submissions_gocanvas()
    
    if not datos_hoy:
        print("Empty: No se encontraron envíos nuevos en el rango de fechas.")
        return

    # 2. Enviar a Google Sheets
    try:
        enviar_a_google_sheets(datos_hoy)
    except Exception as e:
        print(f"❌ Error crítico en Sheets: {type(e).__name__} - {str(e)}")

def obtener_submissions_gocanvas():
    # Rango seguro de 3 días en UTC para no perder nada por cruces de medianoche
    hoy_utc = datetime.now(timezone.utc)
    ayer = (hoy_utc - timedelta(days=1)).strftime('%m/%d/%Y')
    manana = (hoy_utc + timedelta(days=1)).strftime('%m/%d/%Y')
    
    url = f"https://www.gocanvas.com/apiv2/submissions.xml?form_id={FORM_ID}&begin_date={ayer}&end_date={manana}&username={USERNAME}"
    headers = {"Authorization": f"Bearer {GOCANVAS_API_KEY}"}
    
    print(f"📡 Consultando GoCanvas (UTC Range: {ayer} - {manana})...")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return parsear_xml_gocanvas(response.text)
    else:
        print(f"❌ Error API GoCanvas: {response.status_code}")
        return []

def parsear_xml_gocanvas(xml_string):
    try:
        root = ET.fromstring(xml_string)
        lista_submissions = []
        
        for submission in root.findall('.//Submission'):
            fecha = submission.find('Date')
            
            # Mapeo de respuestas {Label: Value}
            valores = {}
            for response in submission.findall('.//Response'):
                label = response.find('Label')
                value = response.find('Value')
                if label is not None and value is not None:
                    valores[label.text] = value.text if value.text else ""
            
            lista_submissions.append({
                "fecha": fecha.text if fecha is not None else "N/A", 
                "valores": valores
            })
            
        print(f"📦 Se procesaron {len(lista_submissions)} envíos del XML.")
        return lista_submissions
    except Exception as e:
        print(f"❌ Error parseando XML: {e}")
        return []

def enviar_a_google_sheets(datos_gocanvas):
    # Autenticación automática de Google Cloud (ADC)
    credentials, project = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    
    cliente_google = gspread.authorize(credentials)
    
    print(f"Opening: Conectando al Spreadsheet {SPREADSHEET_ID}...")
    spreadsheet = cliente_google.open_by_key(SPREADSHEET_ID)
    hoja = spreadsheet.get_worksheet(0) # Primera pestaña
    
    # --- Función para construir la URL de imagen de GoCanvas ---
    def formula_imagen(image_id):
        if not image_id or not image_id.isdigit():
            return "N/A"
        # Construimos la URL que permite a Google Sheets "descargar" la imagen
        url = f"https://www.gocanvas.com/apiv2/images/{image_id}.jpg?username={USERNAME}&password={GOCANVAS_API_KEY}"
        return f'=IMAGE("{url}")'

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
            v.get('Technician name', 'N/A'),
            # Imágenes y Firma
            formula_imagen(v.get('General pole photo')),
            formula_imagen(v.get('Top (cables)')),
            formula_imagen(v.get('Pole base')),
            formula_imagen(v.get('Issue')),
            formula_imagen(v.get('Signature'))
        ]
        filas_a_insertar.append(fila)

    if filas_a_insertar:
        # USER_ENTERED es clave para que Google reconozca el =IMAGE() como fórmula
        hoja.append_rows(filas_a_insertar, value_input_option='USER_ENTERED')
        print(f"✅ ÉXITO: {len(filas_a_insertar)} registros con imágenes añadidos.")

if __name__ == "__main__":
    main()