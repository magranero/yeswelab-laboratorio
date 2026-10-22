-- Se ejecuta UNA vez con el usuario administrador de la base de datos (nunca con el de la API).
-- La API se conecta con «app_web», que solo puede insertar y contar contactos: si alguien la compromete,
-- no puede borrar, modificar ni leer otras tablas.

CREATE TABLE IF NOT EXISTS contactos (
    id       SERIAL PRIMARY KEY,
    creado   TIMESTAMPTZ NOT NULL DEFAULT now(),
    nombre   VARCHAR(200) NOT NULL,
    email    VARCHAR(320) NOT NULL,
    mensaje  TEXT NOT NULL,
    ip_hash  VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS contactos_ip_hash_creado ON contactos (ip_hash, creado);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_web') THEN
        -- Cambia esta contraseña antes de ejecutarlo (en AWS, guárdala en Secrets Manager).
        CREATE ROLE app_web LOGIN PASSWORD 'cambia-esto';
    END IF;
END $$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_web;
GRANT SELECT (id, creado, ip_hash), INSERT ON contactos TO app_web;
GRANT USAGE ON SEQUENCE contactos_id_seq TO app_web;
