import requests
from bs4 import BeautifulSoup
import time
import logging
import os
import json
from datetime import datetime
from pathlib import Path

# ====================================
# CONFIGURACIÓN
# ====================================
# Telegram - Configura estos valores con tus datos reales
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")

# Configuración del monitoreo
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # 5 minutos por defecto
COUNTRY = os.environ.get("COUNTRY", "Spain")
URL = "https://immi.homeaffairs.gov.au/what-we-do/whm-program/status-of-country-caps"

# Archivos de persistencia
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "visa_status_state.json"
LOG_FILE = SCRIPT_DIR / "visa_checker.log"

# ====================================
# CONFIGURACIÓN DE LOGGING
# ====================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================================
# FUNCIONES AUXILIARES
# ====================================
def load_previous_state():
    """Carga el estado anterior desde el archivo"""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('status'), data.get('last_check')
        return None, None
    except Exception as e:
        logger.error(f"Error cargando estado anterior: {e}")
        return None, None

def save_state(status, timestamp):
    """Guarda el estado actual en el archivo"""
    try:
        data = {
            'status': status,
            'last_check': timestamp,
            'country': COUNTRY
        }
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Estado guardado: {status}")
    except Exception as e:
        logger.error(f"Error guardando estado: {e}")

def send_telegram_message(message):
    """Envía un mensaje por Telegram"""
    try:
        if BOT_TOKEN == "TU_BOT_TOKEN_AQUI" or CHAT_ID == "TU_CHAT_ID_AQUI":
            logger.warning("Telegram no configurado correctamente. Mensaje no enviado.")
            logger.info(f"Mensaje que se habría enviado: {message}")
            return False
        
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        params = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(telegram_url, params=params, timeout=10)
        response.raise_for_status()
        
        logger.info("Mensaje enviado por Telegram exitosamente")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error enviando mensaje por Telegram: {e}")
        return False

def get_visa_status():
    """Obtiene el estado actual de las visas desde el sitio web"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logger.debug(f"Consultando URL: {URL}")
        response = requests.get(URL, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Buscar la fila que contiene el país especificado
        rows = soup.find_all("tr")
        for row in rows:
            row_text = row.get_text(strip=True)
            if COUNTRY in row_text:
                logger.debug(f"Fila encontrada para {COUNTRY}: {row_text}")
                
                # Buscar diferentes tipos de etiquetas de estado
                status_selectors = [
                    "span.label.label-primary",
                    "span.label.label-success", 
                    "span.label.label-warning",
                    "span.label.label-danger",
                    "span.label",
                    ".status",
                    "td:last-child"
                ]
                
                for selector in status_selectors:
                    status_element = row.select_one(selector)
                    if status_element:
                        current_status = status_element.get_text(strip=True)
                        if current_status and current_status.lower() not in ['', 'n/a', '-']:
                            logger.debug(f"Estado encontrado con selector {selector}: {current_status}")
                            return current_status
                
                # Si no encontramos un estado específico, tomamos el último td
                cells = row.find_all("td")
                if cells:
                    last_cell = cells[-1].get_text(strip=True)
                    if last_cell:
                        logger.debug(f"Estado obtenido de última celda: {last_cell}")
                        return last_cell
        
        logger.warning(f"No se encontró información para {COUNTRY}")
        return None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión: {e}")
        return None
    except Exception as e:
        logger.error(f"Error procesando página web: {e}")
        return None

def validate_config():
    """Valida la configuración inicial"""
    issues = []
    
    if BOT_TOKEN == "TU_BOT_TOKEN_AQUI":
        issues.append("- BOT_TOKEN no configurado")
    if CHAT_ID == "TU_CHAT_ID_AQUI":
        issues.append("- CHAT_ID no configurado")
    
    if issues:
        logger.warning("Problemas de configuración detectados:")
        for issue in issues:
            logger.warning(issue)
        logger.warning("El script funcionará pero no enviará notificaciones por Telegram")
    
    logger.info(f"Configuración:")
    logger.info(f"- País monitoreado: {COUNTRY}")
    logger.info(f"- Intervalo de verificación: {CHECK_INTERVAL} segundos")
    logger.info(f"- Archivo de estado: {STATE_FILE}")
    logger.info(f"- Archivo de log: {LOG_FILE}")

# ====================================
# FUNCIÓN PRINCIPAL
# ====================================
def main():
    logger.info("=== Iniciando Monitor de Visas Working Holiday ===")
    
    # Validar configuración
    validate_config()
    
    # Cargar estado anterior
    previous_status, last_check = load_previous_state()
    if previous_status:
        logger.info(f"Estado anterior cargado: {previous_status} (última verificación: {last_check})")
    else:
        logger.info("No se encontró estado anterior, iniciando monitoreo fresh")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Verificando estado... ({timestamp})")
            
            current_status = get_visa_status()
            
            if current_status is None:
                consecutive_errors += 1
                logger.error(f"No se pudo obtener el estado ({consecutive_errors}/{max_consecutive_errors})")
                
                if consecutive_errors >= max_consecutive_errors:
                    error_msg = f"🚨 <b>Error crítico</b>\n\nNo se ha podido verificar el estado de las visas durante {consecutive_errors} intentos consecutivos.\n\nÚltimo estado conocido: {previous_status or 'Desconocido'}"
                    send_telegram_message(error_msg)
                    consecutive_errors = 0  # Reset counter after sending alert
                
            else:
                consecutive_errors = 0  # Reset counter on successful check
                logger.info(f"Estado actual: {current_status}")
                
                # Comparar con estado anterior
                if current_status != previous_status:
                    if previous_status is None:
                        # Primera ejecución
                        message = f"🤖 <b>Monitor iniciado</b>\n\nPaís: {COUNTRY}\nEstado actual: <b>{current_status}</b>\n\nMonitoreando cambios cada {CHECK_INTERVAL//60} minutos..."
                        logger.info("Primera ejecución - enviando estado inicial")
                    else:
                        # Cambio de estado detectado
                        message = f"🔄 <b>¡Cambio detectado!</b>\n\nPaís: {COUNTRY}\nEstado anterior: {previous_status}\nEstado nuevo: <b>{current_status}</b>\n\nFecha: {timestamp}"
                        logger.info(f"¡CAMBIO DETECTADO! {previous_status} → {current_status}")
                    
                    # Enviar notificación
                    send_telegram_message(message)
                    
                    # Actualizar estado
                    previous_status = current_status
                    save_state(current_status, timestamp)
                else:
                    logger.info("Sin cambios detectados")
                    # Actualizar timestamp aunque no haya cambios
                    save_state(current_status, timestamp)
            
        except KeyboardInterrupt:
            logger.info("Deteniendo el monitor por solicitud del usuario...")
            break
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            consecutive_errors += 1
        
        logger.info(f"Esperando {CHECK_INTERVAL} segundos hasta la próxima verificación...")
        time.sleep(CHECK_INTERVAL)

# ====================================
# PUNTO DE ENTRADA
# ====================================
if __name__ == "__main__":
    main()