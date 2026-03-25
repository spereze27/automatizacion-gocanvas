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
SPREADSHEET_ID = "18ArHdNLJYbWf_EKF4rHIXekZ3MHAsa0oJyyUBfoByrg"
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
    # ══════════════════════════════════════════════
    # PASO 1: Autenticación con diagnóstico
    # ══════════════════════════════════════════════
    print("🔐 Iniciando autenticación ADC...")
    try:
        credentials, project = google.auth.default(scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        print(f"✅ Credenciales obtenidas. Proyecto activo: '{project}'")
        print(f"🔑 Tipo de credencial: {type(credentials).__name__}")
    except Exception as e:
        print(f"❌ FALLO en autenticación ADC: {type(e).__name__} - {str(e)}")
        raise

    # ══════════════════════════════════════════════
    # PASO 2: Cliente gspread con diagnóstico
    # ══════════════════════════════════════════════
    try:
        cliente_google = gspread.authorize(credentials)
        print("✅ Cliente gspread autorizado correctamente.")
    except Exception as e:
        print(f"❌ FALLO al autorizar gspread: {type(e).__name__} - {str(e)}")
        raise

    # ══════════════════════════════════════════════
    # PASO 3: Listar sheets visibles para la SA
    #         Esto revela si el sharing está bien
    # ══════════════════════════════════════════════
    print("📋 Listando spreadsheets visibles para la cuenta de servicio...")
    try:
        sheets_visibles = cliente_google.list_spreadsheet_files()
        if sheets_visibles:
            print(f"   Sheets encontrados ({len(sheets_visibles)}):")
            for s in sheets_visibles:
                coincide = "✅ <- ESTE ES EL TUYO" if s['id'] == SPREADSHEET_ID else ""
                print(f"   - Nombre: '{s['name']}' | ID: {s['id']} {coincide}")
        else:
            print("   ⚠️  La cuenta de servicio NO ve ningún spreadsheet.")
            print("   👉 Solución: Comparte el Sheet con el email de la SA como Editor.")
    except Exception as e:
        print(f"   ⚠️  No se pudo listar sheets (Drive API issue?): {type(e).__name__} - {str(e)}")

    # ══════════════════════════════════════════════
    # PASO 4: Abrir el spreadsheet - dos métodos
    # ══════════════════════════════════════════════
    print(f"\n📂 Intentando abrir Spreadsheet ID: '{SPREADSHEET_ID}'")
    spreadsheet = None

    # Método 1: open_by_key (estándar)
    try:
        spreadsheet = cliente_google.open_by_key(SPREADSHEET_ID)
        print(f"✅ Spreadsheet abierto con open_by_key. Título: '{spreadsheet.title}'")
    except gspread.exceptions.SpreadsheetNotFound:
        print("❌ open_by_key falló con SpreadsheetNotFound. Intentando open_by_url...")
        
        # Método 2: open_by_url (fallback más robusto)
        try:
            url_sheet = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
            spreadsheet = cliente_google.open_by_url(url_sheet)
            print(f"✅ Spreadsheet abierto con open_by_url. Título: '{spreadsheet.title}'")
        except Exception as e2:
            print(f"❌ open_by_url también falló: {type(e2).__name__} - {str(e2)}")
            print("\n══════════════════════════════════════════════")
            print("📌 DIAGNÓSTICO FINAL:")
            print(f"   • SPREADSHEET_ID usado: '{SPREADSHEET_ID}'")
            print(f"   • Verifica que ese ID coincida exactamente con la URL del Sheet.")
            print(f"   • Verifica que el Sheet esté compartido con la SA como Editor.")
            print(f"   • Verifica que Drive API y Sheets API estén habilitadas en GCP.")
            print("══════════════════════════════════════════════")
            raise
    except Exception as e:
        print(f"❌ Error inesperado al abrir spreadsheet: {type(e).__name__} - {str(e)}")
        raise

    # ══════════════════════════════════════════════
    # PASO 5: Obtener worksheet con diagnóstico
    # ══════════════════════════════════════════════
    try:
        hoja = spreadsheet.get_worksheet(0)
        print(f"✅ Worksheet obtenido. Nombre de pestaña: '{hoja.title}'")
    except Exception as e:
        print(f"❌ No se pudo obtener worksheet(0): {type(e).__name__} - {str(e)}")
        print("   👉 Verifica que el spreadsheet tenga al menos una pestaña.")
        raise

    # ══════════════════════════════════════════════
    # PASO 6: Construcción e inserción de filas
    # ══════════════════════════════════════════════
    def formula_imagen(image_id):
        if not image_id or not str(image_id).isdigit():
            return "N/A"
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
            formula_imagen(v.get('General pole photo')),
            formula_imagen(v.get('Top (cables)')),
            formula_imagen(v.get('Pole base')),
            formula_imagen(v.get('Issue')),
            formula_imagen(v.get('Signature'))
        ]
        filas_a_insertar.append(fila)

    if filas_a_insertar:
        print(f"📝 Insertando {len(filas_a_insertar)} filas en la hoja...")
        try:
            hoja.append_rows(filas_a_insertar, value_input_option='USER_ENTERED')
            print(f"✅ ÉXITO: {len(filas_a_insertar)} registros con imágenes añadidos.")
        except Exception as e:
            print(f"❌ Error al insertar filas: {type(e).__name__} - {str(e)}")
            raise
    else:
        print("⚠️  No hay filas para insertar.")

if __name__ == "__main__":
    main()