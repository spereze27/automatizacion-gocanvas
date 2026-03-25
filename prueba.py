import requests
import json
from datetime import datetime, timedelta, timezone
import urllib3

# ==========================================
# CONFIGURACIÓN (Reemplaza con tus datos)
# ==========================================
GOCANVAS_API_KEY = "22pa6bu4U6Yo4UPByA/te0D8q0rkxTuNgI3qljvMIF8="  # Pega tu API Key de GoCanvas
FORM_ID = "5797373"                   # Tu Form ID
USERNAME = "jsalazar@tysallc.com"     # Tu correo administrador

def probar_api():
    print("Iniciando prueba de conexión local a GoCanvas...")
    
    # Usar hora UTC para coincidir con el servidor de GoCanvas
    hoy_utc = datetime.now(timezone.utc)
    
    # Pedir desde ayer hasta mañana asegura que no perdemos registros por cruces de medianoche
    ayer = (hoy_utc - timedelta(days=1)).strftime('%m/%d/%Y')
    manana = (hoy_utc + timedelta(days=1)).strftime('%m/%d/%Y')
    
    # URL de la API v2 con el nuevo rango seguro
    url = f"https://www.gocanvas.com/apiv2/submissions.json?form_id={FORM_ID}&begin_date={ayer}&end_date={manana}&username={USERNAME}"
    
    headers = {
        "Authorization": f"Bearer {GOCANVAS_API_KEY}",
        "Accept": "application/json"
    }
    
    print(f"\nConsultando URL: {url}")
    print("Esperando respuesta del servidor...\n")
    
    try:
        response = requests.get(url, headers=headers)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ ¡Conexión exitosa!")
            
            # Intentar imprimir el JSON bonito para ver la estructura
            try:
                data = response.json()
                print("\n📋 Respuesta JSON de GoCanvas:")
                print(json.dumps(data, indent=4, ensure_ascii=False))
            except Exception as e:
                print("❌ El servidor no devolvió un JSON válido.")
                print(f"Respuesta en texto crudo:\n{response.text}")
                
        elif response.status_code == 401:
            print("❌ Error 401: No Autorizado. Tu API Key podría ser incorrecta o no tiene los permisos necesarios.")
            print(f"Detalle: {response.text}")
            
        elif response.status_code == 404:
            print("❌ Error 404: No Encontrado. La URL es incorrecta o la API de GoCanvas cambió su ruta.")
            print(f"Detalle: {response.text}")
            
        else:
            print(f"❌ Error desconocido.")
            print(f"Respuesta del servidor:\n{response.text}")

    except Exception as e:
        print(f"❌ Error de Python intentando conectar: {e}")

if __name__ == "__main__":
    probar_api()