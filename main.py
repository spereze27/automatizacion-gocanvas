import os
import requests
import gspread
import google.auth
from google.cloud import storage
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# ==========================================
# CONFIGURACIÓN
# ==========================================
GOCANVAS_API_KEY  = os.environ.get("GOCANVAS_API_KEY")
GOCANVAS_PASSWORD = os.environ.get("GOCANVAS_PASSWORD")
FORM_ID           = os.environ.get("FORM_ID")
SPREADSHEET_ID    = "18ArHdNLJYbWf_EKF4rHIXekZ3MHAsa0oJyyUBfoByrg"
USERNAME          = "jsalazar@tysallc.com"
GCS_BUCKET_NAME   = "xxml"

# Columna A = Submission ID (índice 0)
# Esto permite detectar duplicados leyendo solo esa columna
COL_SUBMISSION_ID = 0

# ==========================================
# MAIN
# ==========================================
def main():
    print("🚀 Iniciando Job: Sincronización GoCanvas (XML + Imágenes) -> Google Sheets")

    if not GOCANVAS_API_KEY or not FORM_ID:
        print("❌ Error: Faltan variables GOCANVAS_API_KEY o FORM_ID.")
        return

    if not GOCANVAS_PASSWORD:
        print("❌ Error: Falta variable GOCANVAS_PASSWORD.")
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
            # ✅ Extraer Submission ID del atributo Id="253944490"
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


# ==========================================
# CLOUD STORAGE
# ==========================================
def descargar_imagen_gocanvas(image_id: str):
    """Basic Auth — único método que funciona para /values/{id}."""
    url = f"https://www.gocanvas.com/values/{image_id}"

    try:
        resp = requests.get(
            url,
            auth=(USERNAME, GOCANVAS_PASSWORD),
            timeout=30,
            allow_redirects=True
        )
        content_type = resp.headers.get("Content-Type", "")

        if resp.status_code == 200 and "image" in content_type:
            print(f"   ✅ Imagen {image_id} descargada ({len(resp.content)} bytes)")
            return resp.content
        else:
            print(f"   ⚠️  No se pudo descargar imagen {image_id}: HTTP {resp.status_code} | {content_type}")
            return None
    except Exception as e:
        print(f"   ⚠️  Excepción descargando imagen {image_id}: {e}")
        return None


def subir_imagen_a_gcs(storage_client, image_id: str, imagen_bytes: bytes):
    """Sube al bucket público — no usa make_public() (uniform access)."""
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob_name = f"gocanvas/{image_id}.jpg"
        blob = bucket.blob(blob_name)

        if blob.exists():
            print(f"   ♻️  Imagen {image_id} ya existe en GCS, reutilizando.")
        else:
            blob.upload_from_string(imagen_bytes, content_type="image/jpeg")
            print(f"   ✅ Imagen {image_id} subida a GCS.")

        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/gocanvas/{image_id}.jpg"
    except Exception as e:
        print(f"   ❌ Error subiendo imagen {image_id} a GCS: {e}")
        return None


def procesar_imagen(storage_client, image_id: str) -> str:
    if not image_id or not str(image_id).strip().isdigit():
        return "N/A"

    image_id = str(image_id).strip()
    print(f"   🖼️  Procesando imagen ID: {image_id}")

    imagen_bytes = descargar_imagen_gocanvas(image_id)
    if not imagen_bytes:
        return "N/A"

    url_publica = subir_imagen_a_gcs(storage_client, image_id, imagen_bytes)
    if not url_publica:
        return "N/A"

    return f'=IMAGE("{url_publica}")'


# ==========================================
# GOOGLE SHEETS
# ==========================================
def obtener_ids_existentes(hoja) -> set:
    """
    Lee la columna A del Sheet (Submission ID) y retorna un set
    con todos los IDs ya registrados. Así evitamos duplicados.
    """
    try:
        # Leer solo la columna A (col 1) — mucho más rápido que leer todo el sheet
        ids_col = hoja.col_values(1)  # col 1 = columna A
        # Ignorar el header si existe y filtrar vacíos
        ids_existentes = {v.strip() for v in ids_col if v.strip() and v.strip() != "Submission ID"}
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
        "https://www.googleapis.com/auth/devstorage.read_write",
    ])
    print(f"✅ Proyecto activo: {project}")

    # ── Cliente Cloud Storage ──────────────────────────────────────────────────
    storage_client = storage.Client(credentials=credentials, project=project)
    print(f"🪣 Bucket GCS: {GCS_BUCKET_NAME}")

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

    total     = len(datos_gocanvas)
    nuevos    = len(submissions_nuevos)
    omitidos  = total - nuevos

    print(f"\n📊 Resumen: {total} en GoCanvas | {omitidos} ya existían | {nuevos} nuevos a insertar")

    if not submissions_nuevos:
        print("✅ No hay registros nuevos. Job finalizado sin cambios.")
        return

    # ── Construir filas solo con submissions nuevos ────────────────────────────
    filas_a_insertar = []

    for idx, sub in enumerate(submissions_nuevos, 1):
        v = sub["valores"]
        print(f"\n📝 Procesando submission {idx}/{nuevos} (ID: {sub['submission_id']})...")

        fila = [
            sub["submission_id"],              # ✅ Col A — usado para deduplicación
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
            # ── Imágenes: Basic Auth → GCS → =IMAGE() ────────────────────────
            procesar_imagen(storage_client, v.get("General pole photo", "")),
            procesar_imagen(storage_client, v.get("Top (cables)",       "")),
            procesar_imagen(storage_client, v.get("Pole base",          "")),
            procesar_imagen(storage_client, v.get("Issue",              "")),
            procesar_imagen(storage_client, v.get("Signature",          "")),
        ]
        filas_a_insertar.append(fila)

    # ── Insertar en Sheets ─────────────────────────────────────────────────────
    print(f"\n📤 Insertando {len(filas_a_insertar)} filas nuevas en Sheets...")
    hoja.append_rows(filas_a_insertar, value_input_option="USER_ENTERED")
    print(f"✅ ÉXITO: {len(filas_a_insertar)} registros nuevos añadidos.")


if __name__ == "__main__":
    main()