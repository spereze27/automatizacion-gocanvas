import os
import requests
import gspread
import google.auth
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ==========================================
# CONFIGURACIÓN
# ==========================================
GOCANVAS_API_KEY = os.environ.get("GOCANVAS_API_KEY")
FORM_ID          = os.environ.get("FORM_ID")
SPREADSHEET_ID   = "18ArHdNLJYbWf_EKF4rHIXekZ3MHAsa0oJyyUBfoByrg"
USERNAME         = "jsalazar@tysallc.com"

# ==========================================
# MAIN
# ==========================================
def main():
    print("🚀 Iniciando Job: Sincronización GoCanvas -> Google Sheets")

    if not GOCANVAS_API_KEY or not FORM_ID:
        print("❌ Error: Faltan variables GOCANVAS_API_KEY o FORM_ID.")
        return

    datos = obtener_submissions_gocanvas()

    if not datos:
        print("Empty: No se encontraron envíos en el rango de fechas.")
        return

    try:
        enviar_a_google_sheets(datos)
    except Exception as e:
        print(f"❌ Error crítico en Sheets: {type(e).__name__} - {str(e)}")


# ==========================================
# GOCANVAS
# ==========================================
def obtener_submissions_gocanvas():
    hoy_utc = datetime.now(timezone.utc)
    ayer   = (hoy_utc - timedelta(days=1)).strftime('%m/%d/%Y')
    manana = (hoy_utc + timedelta(days=1)).strftime('%m/%d/%Y')

    url = (
        f"https://www.gocanvas.com/apiv2/submissions.xml"
        f"?form_id={FORM_ID}&begin_date={ayer}&end_date={manana}&username={USERNAME}"
    )
    headers = {"Authorization": f"Bearer {GOCANVAS_API_KEY}"}

    print(f"📡 Consultando GoCanvas (UTC Range: {ayer} - {manana})...")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return parsear_xml_gocanvas(response.text)
    else:
        print(f"❌ Error API GoCanvas: {response.status_code} - {response.text[:200]}")
        return []


def parsear_xml_gocanvas(xml_string):
    try:
        root = ET.fromstring(xml_string)
        lista_submissions = []

        for submission in root.findall('.//Submission'):
            submission_id = submission.get('Id', 'N/A')
            fecha         = submission.find('Date')

            valores = {}
            for response in submission.findall('.//Response'):
                label = response.find('Label')
                value = response.find('Value')
                if label is not None and value is not None:
                    valores[label.text] = value.text if value.text else ""

            lista_submissions.append({
                "submission_id": submission_id,
                "fecha":         fecha.text if fecha is not None else "N/A",
                "valores":       valores
            })

        print(f"📦 Se encontraron {len(lista_submissions)} envíos en GoCanvas.")
        return lista_submissions
    except Exception as e:
        print(f"❌ Error parseando XML: {e}")
        return []


def link_imagen(image_id: str) -> str:
    """
    Retorna el link directo de GoCanvas para la imagen.
    El usuario debe estar logueado en GoCanvas para verla.
    """
    if not image_id or not str(image_id).strip().isdigit():
        return "N/A"
    return f"https://www.gocanvas.com/values/{image_id.strip()}"


# ==========================================
# GOOGLE SHEETS
# ==========================================
def obtener_ids_existentes(hoja) -> set:
    """Lee columna A (Submission ID) para evitar duplicados."""
    try:
        ids_col = hoja.col_values(1)
        ids_existentes = {
            v.strip() for v in ids_col
            if v.strip() and v.strip() != "Submission ID"
        }
        print(f"🔍 IDs ya existentes en el Sheet: {len(ids_existentes)}")
        return ids_existentes
    except Exception as e:
        print(f"⚠️  No se pudo leer IDs existentes: {e}. Se procederá sin filtro.")
        return set()


def enviar_a_google_sheets(datos_gocanvas):

    # ── Autenticación ADC ──────────────────────────────────────────────────────
    print("🔐 Autenticando con ADC...")
    credentials, project = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    print(f"✅ Proyecto activo: {project}")

    # ── Cliente Google Sheets ──────────────────────────────────────────────────
    cliente_google = gspread.authorize(credentials)

    print(f"📂 Abriendo Spreadsheet {SPREADSHEET_ID}...")
    try:
        spreadsheet = cliente_google.open_by_key(SPREADSHEET_ID)
    except gspread.exceptions.SpreadsheetNotFound:
        url_sheet = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
        spreadsheet = cliente_google.open_by_url(url_sheet)

    hoja = spreadsheet.get_worksheet(0)
    print(f"✅ Hoja abierta: '{hoja.title}'")

    # ── Filtrar duplicados ─────────────────────────────────────────────────────
    ids_existentes = obtener_ids_existentes(hoja)

    submissions_nuevos = [
        sub for sub in datos_gocanvas
        if sub["submission_id"] not in ids_existentes
    ]

    total    = len(datos_gocanvas)
    nuevos   = len(submissions_nuevos)
    omitidos = total - nuevos

    print(f"\n📊 Resumen: {total} en GoCanvas | {omitidos} ya existían | {nuevos} nuevos a insertar")

    if not submissions_nuevos:
        print("✅ No hay registros nuevos. Job finalizado sin cambios.")
        return

    # ── Construir filas ────────────────────────────────────────────────────────
    filas_a_insertar = []

    for idx, sub in enumerate(submissions_nuevos, 1):
        v = sub["valores"]
        print(f"📝 Procesando submission {idx}/{nuevos} (ID: {sub['submission_id']})...")

        fila = [
            sub["submission_id"],
            sub["fecha"],
            v.get("Pole ID",                  "N/A"),
            v.get("Lattitude",                "N/A"),
            v.get("Longitude",                "N/A"),
            v.get("Pole status",              "N/A"),
            v.get("Pole location",            "N/A"),
            v.get("Access",                   "N/A"),
            v.get("Complexity",               "N/A"),
            v.get("Issues",                   "N/A"),
            v.get("Additional requeriments",  "N/A"),
            v.get("Especificar / Specify",    "N/A"),
            v.get("Result",                   "N/A"),
            v.get("Technician name",          "N/A"),
            # ── Links directos de GoCanvas (requiere login) ───────────────────
            link_imagen(v.get("General pole photo", "")),
            link_imagen(v.get("Top (cables)",       "")),
            link_imagen(v.get("Pole base",          "")),
            link_imagen(v.get("Issue",              "")),
            link_imagen(v.get("Signature",          "")),
        ]
        filas_a_insertar.append(fila)

    # ── Insertar en Sheets ─────────────────────────────────────────────────────
    print(f"\n📤 Insertando {len(filas_a_insertar)} filas en Sheets...")
    hoja.append_rows(filas_a_insertar, value_input_option="USER_ENTERED")
    print(f"✅ ÉXITO: {len(filas_a_insertar)} registros añadidos.")


if __name__ == "__main__":
    main()