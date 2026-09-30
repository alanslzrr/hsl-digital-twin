"""Preparación temporal, entrenamiento y servicio MQTT de ETA para la flota HSL."""
import json
import os
import math
import sys
import time
import pickle
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction

warnings.simplefilter("ignore", MissingPivotFunction)

URL = os.getenv("INFLUX_URL", "http://localhost:8086")
TOKEN = os.environ["INFLUX_TOKEN"]
ORG = os.getenv("INFLUX_ORG", "lab")
BUCKET = os.getenv("INFLUX_BUCKET", "flota")
FEATURES = ["retraso_s", "spd", "hora", "dia_semana", "dist_parada_m", "retraso_medio_linea", "nieve_cm_h"]
DESDE = os.getenv("ETA_DESDE", "2026-09-29T12:50:00Z")
AQUI = Path(os.getenv("ETA_ARTIFACT_DIR", str(Path(__file__).resolve().parents[1] / "artifacts")))
AQUI.mkdir(parents=True, exist_ok=True)
MODELO = AQUI / "eta_model.pkl"
RESULTADO = AQUI / "eta-resultado.json"
CORRECCION = AQUI / "eta-correccion.json"
VERSION = "piloto-1"
FRESH_S = 15
SKEW_S = 5
METODO = "v2"


def cliente():
    return InfluxDBClient(url=URL, token=TOKEN, org=ORG)


def frame(q):
    df = cliente().query_api().query_data_frame(q)
    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()
    return df


def cargar_posiciones():
    q = f'''
    from(bucket: "{BUCKET}") |> range(start: {DESDE})
      |> filter(fn: (r) => r._measurement == "vehiculo" and not exists r.evento)
      |> filter(fn: (r) => r._field == "spd" or r._field == "retraso_s" or r._field == "dist_parada_m"
          or r._field == "parada_id" or r._field == "jrn" or r._field == "start_hhmm" or r._field == "oday_n")
      |> filter(fn: (r) => r.linea == "4")
      |> pivot(rowKey: ["_time", "veh", "linea"], columnKey: ["_field"], valueColumn: "_value")
    '''
    df = frame(q)
    if df.empty:
        return df
    df = df.rename(columns={"_time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["sec"] = df["ts"].dt.floor("s")
    return df.sort_values("ts").drop_duplicates(["veh", "sec"], keep="last")


def cargar_llegadas():
    q = f'''
    from(bucket: "{BUCKET}") |> range(start: {DESDE})
      |> filter(fn: (r) => r._measurement == "vehiculo" and r.evento == "ars" and r._field == "spd")
      |> keep(columns: ["_time", "veh", "parada", "viaje", "linea"])
    '''
    df = frame(q)
    if df.empty:
        return df
    df = df.rename(columns={"_time": "ts_llegada"})
    df["ts_llegada"] = pd.to_datetime(df["ts_llegada"], utc=True)
    df["sec"] = df["ts_llegada"].dt.floor("s")
    cols = [c for c in ("veh", "parada", "viaje", "sec") if c in df.columns]
    return df.sort_values("ts_llegada").drop_duplicates(cols, keep="last")


def cargar_nieve():
    q = f'''
    from(bucket: "{BUCKET}") |> range(start: -12h)
      |> filter(fn: (r) => r._measurement == "clima" and r._field == "nieve_cm_h")
      |> keep(columns: ["_time", "_value"])
    '''
    df = frame(q)
    if df.empty:
        return df
    df = df.rename(columns={"_time": "ts", "_value": "nieve_cm_h"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts")[["ts", "nieve_cm_h"]]


def viaje_de_fila(row):
    claves = ("parada_id", "jrn", "start_hhmm", "oday_n")
    if any(c not in row or pd.isna(row[c]) for c in claves):
        return None
    oday = f"{int(row['oday_n']):08d}"
    oday = f"{oday[:4]}-{oday[4:6]}-{oday[6:8]}"
    return f"{oday}_{int(row['start_hhmm']):04d}_{int(row['jrn'])}"


def horizonte(y):
    if y < 30:
        return "lt30"
    if y <= 60:
        return "30a60"
    return "gt60"


def construir_dataset(pos, llegadas, nieve):
    vacio = pd.DataFrame()
    if pos.empty or llegadas.empty:
        return vacio
    if not {"parada_id", "jrn", "start_hhmm", "oday_n"}.issubset(pos.columns):
        return vacio
    if "viaje" not in llegadas.columns or "parada" not in llegadas.columns:
        return vacio
    pos = pos.copy()
    pos["viaje"] = pos.apply(viaje_de_fila, axis=1)
    pos["parada"] = pos["parada_id"].apply(lambda v: None if pd.isna(v) else str(int(v)))
    pos = pos.dropna(subset=["viaje", "parada"])
    ll = llegadas.dropna(subset=["viaje", "parada"]).copy()
    ll["parada"] = ll["parada"].astype(str)
    ll["viaje"] = ll["viaje"].astype(str)
    if pos.empty or ll.empty:
        return vacio
    d = pd.merge_asof(
        pos.sort_values("ts"),
        ll.sort_values("ts_llegada")[["veh", "parada", "viaje", "ts_llegada"]],
        left_on="ts",
        right_on="ts_llegada",
        by=["veh", "parada", "viaje"],
        direction="forward",
    )
    d = d.dropna(subset=["ts_llegada"])
    d["y"] = (d["ts_llegada"] - d["ts"]).dt.total_seconds()
    d = d[d["y"] > 0]
    if d.empty:
        return vacio
    d["hora"] = d["ts"].dt.hour + d["ts"].dt.minute / 60
    d["dia_semana"] = d["ts"].dt.dayofweek
    if not nieve.empty:
        d = pd.merge_asof(d.sort_values("ts"), nieve, on="ts", direction="backward")
    else:
        d["nieve_cm_h"] = pd.NA
    trozos = []
    for _, g in d.groupby("linea"):
        g = g.sort_values("ts").copy()
        media = g.set_index("ts")["retraso_s"].shift(1).rolling("600s", min_periods=10).mean()
        g["retraso_medio_linea"] = media.to_numpy()
        trozos.append(g)
    d = pd.concat(trozos, ignore_index=True)
    return d.dropna(subset=FEATURES + ["y"]).sort_values("ts")


def mae_trozo(te, pred, base):
    from sklearn.metrics import mean_absolute_error
    if len(te) == 0:
        return None
    return {
        "n": int(len(te)),
        "mae_base_s": round(float(mean_absolute_error(te["y"], base)), 2),
        "mae_modelo_s": round(float(mean_absolute_error(te["y"], pred)), 2),
    }


def entrenar():
    import lightgbm as lgb

    pos = cargar_posiciones()
    llegadas = cargar_llegadas()
    nieve = cargar_nieve()
    d = construir_dataset(pos, llegadas, nieve)
    info = {
        "metodo": "veh+parada+viaje, etiqueta conocida en el corte",
        "posiciones_1hz": int(len(pos)),
        "llegadas_ars": int(len(llegadas)),
        "filas": int(len(d)),
        "vehiculos": sorted(d["veh"].astype(str).unique().tolist()) if len(d) else [],
        "desde": None if d.empty else d["ts"].min().isoformat(),
        "hasta": None if d.empty else d["ts"].max().isoformat(),
        "version": VERSION,
    }
    if len(d) < 40:
        info["error"] = "aún no hay filas emparejadas por vehículo, parada y viaje para un corte 80/20"
        CORRECCION.write_text(json.dumps(info, indent=2) + "\n")
        print(json.dumps(info, indent=2))
        sys.exit(1)
    corte = d["ts"].quantile(0.8)
    conocidas = d["ts_llegada"] <= corte
    tr = d[(d["ts"] < corte) & conocidas]
    te = d[d["ts"] >= corte]
    info["filas_etiqueta_posterior_al_corte"] = int(((d["ts"] < corte) & ~conocidas).sum())
    info["corte"] = pd.Timestamp(corte).isoformat()
    info["train"] = int(len(tr))
    info["test"] = int(len(te))
    if len(tr) < 20 or len(te) < 10:
        info["error"] = "un lado del corte temporal se quedó sin filas"
        CORRECCION.write_text(json.dumps(info, indent=2) + "\n")
        print(json.dumps(info, indent=2))
        sys.exit(1)
    m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31, verbose=-1)
    m.fit(tr[FEATURES], tr["y"])
    pred = m.predict(te[FEATURES])
    base = (te["dist_parada_m"] / te["spd"].clip(lower=1)).to_numpy()
    info["global"] = mae_trozo(te, pred, base)
    info["importancia"] = {k: int(v) for k, v in zip(FEATURES, m.feature_importances_)}
    parado = te["spd"] < 1
    info["parado"] = mae_trozo(te[parado], pred[parado.to_numpy()], base[parado.to_numpy()])
    info["marcha"] = mae_trozo(te[~parado], pred[(~parado).to_numpy()], base[(~parado).to_numpy()])
    for nombre, mask in (
        ("lt30", te["y"] < 30),
        ("30a60", (te["y"] >= 30) & (te["y"] <= 60)),
        ("gt60", te["y"] > 60),
    ):
        info[nombre] = mae_trozo(te[mask], pred[mask.to_numpy()], base[mask.to_numpy()])
    info["span_horas"] = round((d["ts"].max() - d["ts"].min()).total_seconds() / 3600, 3)
    horizontes = [info.get("30a60"), info.get("gt60")]
    if info["span_horas"] < 1 or not any(h and h["n"] >= 10 for h in horizontes):
        info["error"] = "la ventana emparejada dura menos de una hora o no tiene horizonte de más de un minuto; no sustituye al modelo en servicio"
        CORRECCION.write_text(json.dumps(info, indent=2) + "\n")
        print(json.dumps(info, indent=2))
        sys.exit(1)
    pickle.dump({"modelo": m, "features": FEATURES, "version": VERSION}, open(MODELO, "wb"))
    CORRECCION.write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps(info, indent=2))


def _ts(valor):
    if not isinstance(valor, str) or len(valor) < 10:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def servir():
    import paho.mqtt.client as mqtt
    from influxdb_client import Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    pack = pickle.load(open(MODELO, "rb"))
    modelo = pack["modelo"]
    version = pack.get("version", VERSION)
    write = cliente().write_api(write_options=SYNCHRONOUS)
    estado = {}
    historial = []
    predichos = {}
    nieve = {"nieve_cm_h": None, "ts": None}
    vistos = set()

    def media_linea(linea, ahora):
        corte = ahora - 600
        vals = [r for (t, lin, r) in historial if lin == linea and corte <= t < ahora]
        if len(vals) < 10:
            return None
        return sum(vals) / len(vals)

    def poner(e, clave, valor, ts):
        if valor is None or valor == "":
            e.pop(clave, None)
            return
        e[clave] = (valor, ts)

    def fresco(e, claves, ahora):
        marcas = []
        vals = {}
        for clave in claves:
            par = e.get(clave)
            if not par:
                return None
            valor, ts = par
            if abs(ahora - ts) > FRESH_S:
                return None
            marcas.append(ts)
            vals[clave] = valor
        if max(marcas) - min(marcas) > SKEW_S:
            return None
        return vals

    def on_msg(cli, _, msg):
        try:
            _on_msg(cli, msg)
        except Exception as exc:
            print("msg", exc, flush=True)

    def _on_msg(cli, msg):
        if msg.topic.startswith("contexto/meteo/"):
            try:
                p = json.loads(msg.payload)
            except (TypeError, json.JSONDecodeError):
                return
            if p.get("nieve_cm_h") is None:
                nieve["nieve_cm_h"] = None
                return
            ts = _ts(p.get("ts"))
            if ts is None or abs(time.time() - ts) > 2 * 3600:
                nieve["nieve_cm_h"] = None
                return
            valor = p["nieve_cm_h"]
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
                nieve["nieve_cm_h"] = None
                return
            nieve["nieve_cm_h"] = float(valor)
            nieve["ts"] = ts
            return
        partes = msg.topic.split("/")
        if len(partes) < 6 or partes[0] != "flota":
            return
        veh = partes[4]
        veh_topic = "/".join(partes[2:5])
        try:
            p = json.loads(msg.payload)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(p, dict):
            return
        ts = _ts(p.get("ts"))
        if ts is None:
            return
        e = estado.setdefault(veh, {})
        if "spd" in p or "lat" in p:
            poner(e, "spd", p.get("spd") if isinstance(p.get("spd"), (int, float)) else None, ts)
            dist = p.get("dist_parada_m")
            poner(e, "dist_parada_m", dist if isinstance(dist, (int, float)) else None, ts)
        if "retraso_s" in p or "puertas" in p:
            ret = p.get("retraso_s")
            poner(e, "retraso_s", ret if isinstance(ret, (int, float)) else None, ts)
            if p.get("linea") is not None:
                poner(e, "linea", p.get("linea"), ts)
        if "parada" in p:
            poner(e, "parada", p.get("parada"), ts)
        if "viaje" in p:
            poner(e, "viaje", p.get("viaje"), ts)
        ahora = time.time()
        ret = p.get("retraso_s")
        if isinstance(ret, (int, float)) and p.get("linea") is not None and ahora - ts <= FRESH_S:
            historial.append((ahora, str(p["linea"]), float(ret)))
            del historial[:-8000]
        campos = fresco(e, ("spd", "dist_parada_m", "retraso_s", "linea", "parada", "viaje"), ahora)
        if (campos is None or nieve["nieve_cm_h"] is None
                or nieve["ts"] is None or abs(ahora - nieve["ts"]) > 2 * 3600):
            return
        if ahora - e.get("_pred", 0) < 1:
            return
        media = media_linea(str(campos["linea"]), ahora)
        if media is None:
            return
        e["_pred"] = ahora
        utc = datetime.fromtimestamp(ts, timezone.utc)
        fila = {
            "retraso_s": float(campos["retraso_s"]),
            "spd": float(campos["spd"]),
            "hora": utc.hour + utc.minute / 60,
            "dia_semana": utc.weekday(),
            "dist_parada_m": float(campos["dist_parada_m"]),
            "retraso_medio_linea": media,
            "nieve_cm_h": nieve["nieve_cm_h"],
        }
        eta = float(modelo.predict(pd.DataFrame([fila]))[0])
        base = fila["dist_parada_m"] / max(fila["spd"], 1.0)
        cuerpo = {
            "eta_s": round(eta),
            "base_s": round(base),
            "ts": p.get("ts"),
            "veh": veh,
            "viaje": campos["viaje"],
            "parada": campos["parada"],
            "version": version,
            "sintetico": False,
        }
        cli.publish(f"prediccion/eta/{veh_topic}", json.dumps(cuerpo), retain=True)
        clave = (veh, str(campos["viaje"]), str(campos["parada"]))
        predichos.setdefault(clave, []).append({
            "ts": ts, "eta": eta, "base": base, "spd": fila["spd"], "emit": utc,
        })
        predichos[clave] = [x for x in predichos[clave] if ts - x["ts"] < 1800]
        write.write(bucket=BUCKET, record=Point("prediccion")
                    .tag("veh", veh).tag("viaje", str(campos["viaje"]))
                    .tag("parada", str(campos["parada"])).tag("version", version)
                    .field("eta_s", eta).field("base_s", base).field("spd", fila["spd"])
                    .time(utc))

    def cerrar_errores():
        q = f'''
        from(bucket: "{BUCKET}") |> range(start: -30m)
          |> filter(fn: (r) => r._measurement == "vehiculo" and r.evento == "ars" and r._field == "spd")
          |> keep(columns: ["_time", "veh", "parada", "viaje"])
        '''
        try:
            ars = frame(q)
        except Exception as exc:
            print("ars", exc, flush=True)
            return
        if ars.empty or "viaje" not in ars.columns:
            return
        ars["_time"] = pd.to_datetime(ars["_time"], utc=True)
        puntos = []
        for _, row in ars.dropna(subset=["viaje", "parada"]).iterrows():
            veh = str(row["veh"])
            parada = str(row["parada"])
            viaje = str(row["viaje"])
            llegada = row["_time"].timestamp()
            clave_ars = (veh, viaje, parada, int(llegada))
            if clave_ars in vistos:
                continue
            pendientes = [p for p in predichos.get((veh, viaje, parada), []) if p["ts"] < llegada - 1]
            if not pendientes:
                continue
            vistos.add(clave_ars)
            predichos[(veh, viaje, parada)] = [
                p for p in predichos.get((veh, viaje, parada), []) if p["ts"] >= llegada - 1
            ]
            for p in pendientes:
                y = llegada - p["ts"]
                if y <= 0 or y > 1800:
                    continue
                marcha = "parado" if p["spd"] < 1 else "marcha"
                puntos.append(Point("error_eta")
                              .tag("veh", veh).tag("viaje", viaje).tag("parada", parada)
                              .tag("metodo", METODO).tag("horizonte", horizonte(y))
                              .tag("marcha", marcha).tag("version", version)
                              .field("error_modelo", abs(p["eta"] - y))
                              .field("error_base", abs(p["base"] - y))
                              .field("y_s", y)
                              .time(p["emit"]))
        if puntos:
            write.write(bucket=BUCKET, record=puntos)
            print(f"errores v2 escritos {len(puntos)}", flush=True)

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="eta-ml")
    def on_connect(cli, _, flags, reason_code, properties):
        if reason_code == 0:
            # Reponer también las suscripciones tras reiniciar el broker.
            cli.subscribe("flota/hsl/#")
            cli.subscribe("contexto/meteo/actual")

    cli.on_message = on_msg
    cli.on_connect = on_connect
    cli.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
    cli.loop_start()
    print("sirviendo", version, flush=True)
    try:
        while True:
            time.sleep(20)
            cerrar_errores()
    finally:
        cli.loop_stop()


if __name__ == "__main__":
    if sys.argv[1:] == ["servir"]:
        servir()
    else:
        entrenar()
