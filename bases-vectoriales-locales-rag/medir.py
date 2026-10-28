"""Mide cada base vectorial local con los vectores de preparar.py.

    python medir.py            # todas las repeticiones (orquestador)
    python medir.py --uno MOTOR N REP   # una medida, en un proceso nuevo (lo llama el orquestador)

Por cada motor, tamaño y repetición, en un proceso nuevo y una carpeta temporal nueva:
- indexado: insertar los vectores y dejarlos persistidos en disco, listos para consultar;
- disco: tamaño de la carpeta resultante;
- reapertura: abrir de nuevo lo guardado y hacer la primera consulta;
- consultas: 1.000 consultas de una en una (k = 10) tras 20 de calentamiento; latencia de cada una;
- recall@10 frente a los vecinos exactos;
- memoria: pico de RSS del proceso menos el RSS tras importar la librería y cargar los vectores.

Cada motor usa su configuración por defecto, salvo dos variantes ajustadas en la consulta:
faiss_hnsw_ef64 (efSearch = 64) y lancedb_ivfpq_refine (refine_factor = 10, reordena con los vectores completos). Salida: resultados/medidas.jsonl (una línea por medida).
"""

import gc
import json
import os
import random
import resource
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, "datos")
RESULTADOS = os.path.join(AQUI, "resultados")
MOTORES = ["numpy", "faiss_flat", "faiss_hnsw", "faiss_hnsw_ef64", "sqlite_vec", "duckdb", "chroma", "lancedb",
           "lancedb_ivfpq", "lancedb_ivfpq_refine"]
TAMANOS = [10_000, 100_000]
REPETICIONES = 5
K = 10
CALENTAMIENTO = 20
SEMILLA = 20261024


def tamano_carpeta(ruta: str) -> int:
    total = 0
    for raiz, _, archivos in os.walk(ruta):
        for a in archivos:
            total += os.path.getsize(os.path.join(raiz, a))
    return total


def rss_pico() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes en macOS


# --- Motores: cada uno devuelve (construir, abrir) ---------------------------------------------
# construir(X, carpeta) deja el índice en disco; abrir(carpeta) devuelve buscar(q) -> lista de ids.

def motor_numpy():
    def construir(X, carpeta):
        np.save(os.path.join(carpeta, "x.npy"), X)

    def abrir(carpeta):
        X = np.load(os.path.join(carpeta, "x.npy"))

        def buscar(q):
            s = X @ q
            idx = np.argpartition(-s, K)[:K]
            return idx[np.argsort(-s[idx])].tolist()
        return buscar
    return construir, abrir


def motor_faiss(hnsw: bool, ef_search: int | None = None):
    import faiss

    def construir(X, carpeta):
        d = X.shape[1]
        indice = faiss.IndexHNSWFlat(d, 32, faiss.METRIC_INNER_PRODUCT) if hnsw else faiss.IndexFlatIP(d)
        indice.add(X)
        faiss.write_index(indice, os.path.join(carpeta, "indice.faiss"))

    def abrir(carpeta):
        indice = faiss.read_index(os.path.join(carpeta, "indice.faiss"))
        if ef_search:
            indice.hnsw.efSearch = ef_search

        def buscar(q):
            _, I = indice.search(q.reshape(1, -1), K)
            return I[0].tolist()
        return buscar
    return construir, abrir


def motor_sqlite_vec():
    import sqlite3
    import sqlite_vec

    def conectar(carpeta):
        con = sqlite3.connect(os.path.join(carpeta, "vec.db"))
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return con

    def construir(X, carpeta):
        con = conectar(carpeta)
        d = X.shape[1]
        con.execute(f"CREATE VIRTUAL TABLE v USING vec0(embedding float[{d}] distance_metric=cosine)")
        with con:
            con.executemany("INSERT INTO v(rowid, embedding) VALUES (?, ?)",
                            ((i, X[i].tobytes()) for i in range(len(X))))
        con.close()

    def abrir(carpeta):
        con = conectar(carpeta)

        def buscar(q):
            filas = con.execute("SELECT rowid FROM v WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                                (q.tobytes(), K)).fetchall()
            return [f[0] for f in filas]
        return buscar
    return construir, abrir


def motor_duckdb():
    import duckdb
    import pyarrow as pa

    def construir(X, carpeta):
        d = X.shape[1]
        con = duckdb.connect(os.path.join(carpeta, "vec.duckdb"))
        tabla = pa.table({"id": pa.array(np.arange(len(X), dtype=np.int64)),
                          "v": pa.FixedSizeListArray.from_arrays(pa.array(X.reshape(-1)), d)})
        con.register("entrada", tabla)
        con.execute(f"CREATE TABLE t AS SELECT id, v::FLOAT[{d}] AS v FROM entrada")
        con.close()

    def abrir(carpeta):
        con = duckdb.connect(os.path.join(carpeta, "vec.duckdb"))
        d = con.execute("SELECT array_length(v) FROM t LIMIT 1").fetchone()[0]
        sql = f"SELECT id FROM t ORDER BY array_inner_product(v, ?::FLOAT[{d}]) DESC LIMIT {K}"

        def buscar(q):
            return [f[0] for f in con.execute(sql, [q.tolist()]).fetchall()]
        return buscar
    return construir, abrir


def motor_chroma():
    import chromadb
    from chromadb.config import Settings

    ajustes = Settings(anonymized_telemetry=False)

    def construir(X, carpeta):
        cliente = chromadb.PersistentClient(path=carpeta, settings=ajustes)
        col = cliente.create_collection("vectores")
        lote = cliente.get_max_batch_size()
        for i in range(0, len(X), lote):
            fin = min(i + lote, len(X))
            col.add(ids=[str(j) for j in range(i, fin)], embeddings=X[i:fin])
        del col, cliente
        gc.collect()

    def abrir(carpeta):
        cliente = chromadb.PersistentClient(path=carpeta, settings=ajustes)
        col = cliente.get_collection("vectores")

        def buscar(q):
            r = col.query(query_embeddings=q.reshape(1, -1), n_results=K, include=[])
            return [int(i) for i in r["ids"][0]]
        return buscar
    return construir, abrir


def motor_lancedb(indice: bool, refine: int | None = None):
    import lancedb
    import pyarrow as pa

    def construir(X, carpeta):
        d = X.shape[1]
        db = lancedb.connect(carpeta)
        tabla = pa.table({"id": pa.array(np.arange(len(X), dtype=np.int64)),
                          "vector": pa.FixedSizeListArray.from_arrays(pa.array(X.reshape(-1)), d)})
        t = db.create_table("t", data=tabla)
        if indice:
            t.create_index()  # índice por defecto (IVF_PQ)

    def abrir(carpeta):
        t = lancedb.connect(carpeta).open_table("t")

        def buscar(q):
            b = t.search(q).limit(K).select(["id"])
            if refine:
                b = b.refine_factor(refine)
            r = b.to_arrow()
            return r.column("id").to_pylist()
        return buscar
    return construir, abrir


FABRICAS = {
    "numpy": motor_numpy,
    "faiss_flat": lambda: motor_faiss(False),
    "faiss_hnsw": lambda: motor_faiss(True),
    "faiss_hnsw_ef64": lambda: motor_faiss(True, 64),
    "sqlite_vec": motor_sqlite_vec,
    "duckdb": motor_duckdb,
    "chroma": motor_chroma,
    "lancedb": lambda: motor_lancedb(False),
    "lancedb_ivfpq": lambda: motor_lancedb(True),
    "lancedb_ivfpq_refine": lambda: motor_lancedb(True, 10),
}


def una_medida(motor: str, n: int, rep: int) -> dict:
    import psutil

    construir, abrir = FABRICAS[motor]()
    X = np.ascontiguousarray(np.load(os.path.join(DATOS, "corpus.npy"), mmap_mode="r")[:n])
    Q = np.load(os.path.join(DATOS, "consultas.npy"))
    verdad = np.load(os.path.join(DATOS, f"vecinos_{n}.npy"))
    gc.collect()
    rss_base = psutil.Process().memory_info().rss

    carpeta = tempfile.mkdtemp(prefix="vec-")
    try:
        t0 = time.perf_counter()
        construir(X, carpeta)
        t_indexado = time.perf_counter() - t0
        disco = tamano_carpeta(carpeta)

        t0 = time.perf_counter()
        buscar = abrir(carpeta)
        buscar(Q[0])
        t_reapertura = time.perf_counter() - t0

        for q in Q[1 : 1 + CALENTAMIENTO]:
            buscar(q)
        latencias = []
        aciertos = 0
        t0 = time.perf_counter()
        for i, q in enumerate(Q):
            a = time.perf_counter_ns()
            ids = buscar(q)
            latencias.append((time.perf_counter_ns() - a) / 1e6)
            aciertos += len(set(ids[:K]) & set(verdad[i].tolist()))
        t_consultas = time.perf_counter() - t0
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    lat = np.array(latencias)
    return {
        "motor": motor, "n": n, "rep": rep,
        "indexado_s": t_indexado,
        "vectores_por_s": n / t_indexado,
        "disco_bytes": disco,
        "disco_mb": disco / 1e6,
        "reapertura_ms": t_reapertura * 1000,
        "lat_p50_ms": float(np.percentile(lat, 50)),
        "lat_p95_ms": float(np.percentile(lat, 95)),
        "lat_media_ms": float(lat.mean()),
        "consultas_por_s": len(Q) / t_consultas,
        "recall_10": aciertos / (len(Q) * K),
        "memoria_extra_mb": max(0, rss_pico() - rss_base) / 1e6,
    }


def orquestar() -> None:
    os.makedirs(RESULTADOS, exist_ok=True)
    salida = os.path.join(RESULTADOS, "medidas.jsonl")
    hechas = set()
    if os.path.exists(salida):
        for linea in open(salida, encoding="utf-8"):
            m = json.loads(linea)
            hechas.add((m["motor"], m["n"], m["rep"]))
    azar = random.Random(SEMILLA)
    for rep in range(1, REPETICIONES + 1):
        orden = [(m, n) for n in TAMANOS for m in MOTORES]
        azar.shuffle(orden)  # orden intercalado y distinto en cada repetición
        for motor, n in orden:
            if (motor, n, rep) in hechas:
                continue
            r = subprocess.run([sys.executable, __file__, "--uno", motor, str(n), str(rep)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"FALLO {motor} {n} {rep}\n{r.stderr[-2000:]}", flush=True)
                continue
            linea = r.stdout.strip().splitlines()[-1]
            with open(salida, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
            m = json.loads(linea)
            print(f"rep {rep} {motor:14s} {n:>7d}  indexado {m['indexado_s']:7.2f} s  "
                  f"p50 {m['lat_p50_ms']:7.3f} ms  recall {m['recall_10']:.4f}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--uno":
        print(json.dumps(una_medida(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))))
    else:
        orquestar()
