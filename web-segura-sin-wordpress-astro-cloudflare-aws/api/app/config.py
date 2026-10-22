from pydantic_settings import BaseSettings, SettingsConfigDict


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # En AWS, el usuario de la API solo puede leer e insertar en «contactos» (ver sql/esquema.sql).
    database_url: str = "postgresql+psycopg://app_web:cambia-esto@localhost:5432/web"
    # Únicos orígenes que pueden llamar a la API desde un navegador. Nada de «*».
    cors_origins: list[str] = ["https://tudominio.es", "https://www.tudominio.es"]
    # Cloudflare Turnstile (captcha invisible y gratuito). Vacío = desactivado (solo para desarrollo local).
    turnstile_secret: str = ""
    # Si la API va detrás de Cloudflare: Cloudflare añade esta cabecera y la API rechaza lo que llegue sin ella.
    origen_secreto: str = ""
    # Sal para guardar la IP como hash, nunca en claro.
    ip_salt: str = "cambia-esto"
    max_envios_por_hora: int = 5
    ms_minimo_formulario: int = 3000
    # Aviso opcional por Telegram de cada envío.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


ajustes = Ajustes()
