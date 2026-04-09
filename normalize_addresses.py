#!/usr/bin/env python3
"""
normalize_addresses.py

Çeşitli formatlardaki adres verilerini (CSV, JSON, GeoJSON, NDJSON, plain text) proje formatındaki CSV'ye
(normalize edilmiş sütun: id,mahalle,cadde_sokak,bina_adı,bina_no,kat,daire_no,formatted_address,lat,lng)
dönüştürür.

Kullanım:
  python3 normalize_addresses.py input_file -o output.csv

Script, bilinen alan isimleri için akıllı eşleme (heuristics) yapar. Eksik id alanı varsa otomatik id oluşturur.
"""

import argparse
import csv
import json
import os
import sys
from collections import OrderedDict

EXPECTED_COLUMNS = [
    "id",
    "merkez",
    "mahalle",
    "cadde_sokak",
    "bina_adı",
    "bina_no",
    "kat",
    "daire_no",
    "formatted_address",
    "lat",
    "lng",
]

# Muhtemel alternatif alan isimleri (küçük harfe çevirilmiş)
CANDIDATES = {
    "id": ["id", "identifier", "index", "uid"],
    "mahalle": ["mahalle", "neighbourhood", "neighborhood", "district"],
    "cadde_sokak": ["cadde_sokak", "street", "street_name", "address_street", "road"],
    "bina_adı": ["bina_adı", "building_name", "building", "site"],
    "bina_no": ["bina_no", "house_number", "housenumber", "number"],
    "kat": ["kat", "floor"],
    "daire_no": ["daire_no", "apartment", "apt", "unit", "flat"],
    "formatted_address": ["formatted_address", "address", "full_address", "display_name"],
    "lat": ["lat", "latitude", "y"],
    "lng": ["lng", "lon", "long", "longitude", "x"],
}


def try_parse_json(path):
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        return json.loads(txt)
    except Exception:
        # belki dosya çok büyük; satır satır Ndjson
        objs = []
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                objs.append(json.loads(line))
            except Exception:
                return None
        return objs if objs else None


def extract_from_geojson(obj):
    features = obj.get("features", [])
    rows = []
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry")
        lat = None
        lng = None
        if geom:
            coords = geom.get("coordinates")
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                lng, lat = coords[0], coords[1]
        props_copy = dict(props)
        if lat is not None:
            props_copy["lat"] = lat
        if lng is not None:
            props_copy["lng"] = lng
        rows.append(props_copy)
    return rows


def flatten_dagitim_merkezi_json(obj):
    # eğer DAGITIM JSON formatıysa ("Merkez1": [ {..}, ... ])
    rows = []
    if isinstance(obj, dict):
        for key, lst in obj.items():
            if isinstance(lst, list):
                for entry in lst:
                    e = dict(entry)
                    # orijinal merkez bilgisini tutmak isterseniz e["merkez"] = key
                    rows.append(e)
    return rows


def detect_and_load(input_path):
    _, ext = os.path.splitext(input_path.lower())
    if ext in (".csv",):
        return load_csv(input_path)
    if ext in (".json",):
        obj = try_parse_json(input_path)
        if obj is None:
            raise RuntimeError("JSON parse edilemedi")
        # GeoJSON ise
        if isinstance(obj, dict) and obj.get("type", "").lower() == "featurecollection":
            return extract_from_geojson(obj)
        # Dagitim merkezi tipi olabilir
        if isinstance(obj, dict) and any(isinstance(v, list) for v in obj.values()):
            return flatten_dagitim_merkezi_json(obj)
        # liste ise
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
    if ext in (".geojson",):
        obj = try_parse_json(input_path)
        if obj is None:
            raise RuntimeError("GeoJSON parse edilemedi")
        return extract_from_geojson(obj)
    # ndjson or unknown: try to parse as json lines
    obj = try_parse_json(input_path)
    if obj:
        return obj
    # fallback: try to read csv even without extension
    try:
        return load_csv(input_path)
    except Exception:
        raise RuntimeError("Dosya formatı anlaşılamadı veya okunamadı")


def load_csv(path):
    rows = []
    with open(path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for r in reader:
            rows.append(r)
    return rows


def get_candidate_value(record, target):
    # record keys küçük harfe çevrilmiş map
    lower_keys = {k.lower(): k for k in record.keys()}
    for cand in CANDIDATES.get(target, []):
        if cand in lower_keys:
            return record[lower_keys[cand]]
    # Ayrıca bazen adresler nested olabilir
    return None


def normalize_record(raw, next_id):
    # raw: dict-like, anahtarlar herhangi bir isimde olabilir
    # döndür: OrderedDict ile EXPECTED_COLUMNS sırada
    rec = OrderedDict()
    # normalize keys to lower mapping
    if not isinstance(raw, dict):
        # eğer geojson feature ise properties olabilir
        try:
            raw = dict(raw)
        except Exception:
            raw = {}
    lower_map = {k.lower(): k for k in raw.keys()}

    # helper to pick
    def pick(target):
        # doğrudan target varsa
        if target in lower_map:
            return raw[lower_map[target]]
        # aday listesine bak
        for cand in CANDIDATES.get(target, []):
            if cand in lower_map:
                return raw[lower_map[cand]]
        # bazen property içinde nested 'address' dict var
        if 'address' in lower_map and isinstance(raw[lower_map['address']], dict):
            addr = raw[lower_map['address']]
            for cand in CANDIDATES.get(target, []):
                if cand in {k.lower() for k in addr.keys()}:
                    # return original key's value
                    for ak in addr.keys():
                        if ak.lower() == cand:
                            return addr[ak]
        return None

    # id
    id_val = pick('id')
    if id_val is None:
        id_val = str(next_id)
    rec['id'] = str(id_val)

    for col in EXPECTED_COLUMNS[1:]:
        val = pick(col)
        if val is None:
            # özel: lat/lng bazen geometry altında
            if col in ('lat', 'lng'):
                # check geometry -> coordinates
                if 'geometry' in lower_map and isinstance(raw[lower_map['geometry']], dict):
                    coords = raw[lower_map['geometry']].get('coordinates')
                    if coords and len(coords) >= 2:
                        if col == 'lng':
                            val = coords[0]
                        else:
                            val = coords[1]
                # bazen 'location' alanı var: {lat:..., lng:...}
                if 'location' in lower_map and isinstance(raw[lower_map['location']], dict):
                    loc = raw[lower_map['location']]
                    if col == 'lat' and 'lat' in {k.lower():k for k in loc.keys()}:
                        val = loc.get('lat') or loc.get('latitude')
                    if col == 'lng' and 'lng' in {k.lower():k for k in loc.keys()}:
                        val = loc.get('lng') or loc.get('longitude')
        if val is None:
            val = ''
        # normalize floats
        if col in ('lat','lng') and val != '':
            try:
                val = str(float(val))
            except Exception:
                # bazen koordinatlar string içinde 'lat,lng' şeklinde
                if isinstance(val, str) and ',' in val:
                    parts = [p.strip() for p in val.split(',') if p.strip()]
                    if len(parts) >= 2:
                        if col == 'lat':
                            val = parts[0]
                        else:
                            val = parts[1]
                else:
                    val = ''
        rec[col] = val

    return rec


def write_csv(rows, out_path):
    with open(out_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main():
    parser = argparse.ArgumentParser(description='Normalize address files to project CSV schema')
    parser.add_argument('input', help='Input path (csv, json, geojson, ndjson, txt)')
    parser.add_argument('-o', '--output', help='Output CSV path (defaults to normalized_addresses.csv)', default='normalized_addresses.csv')
    parser.add_argument('--preview', action='store_true', help='Sadece ilk 5 kaydı göster')
    args = parser.parse_args()

    input_path = args.input
    out_path = args.output

    if not os.path.exists(input_path):
        print(f"Girdi dosyası bulunamadı: {input_path}")
        sys.exit(1)

    try:
        raw_rows = detect_and_load(input_path)
    except Exception as e:
        print(f"Veri yüklenemedi: {e}")
        sys.exit(1)

    normalized = []
    next_id = 1
    for raw in raw_rows:
        try:
            rec = normalize_record(raw, next_id)
            normalized.append(rec)
            # next_id sadece otomatik id için artırılıyor: eğer kayıtta id varsa bunu değiştirmez
            try:
                _ = int(rec['id'])
                next_id = max(next_id, int(rec['id']) + 1)
            except Exception:
                next_id += 1
        except Exception as e:
            print(f"Kayıt normalize edilemedi: {e}")

    if args.preview:
        print("İlk 5 normalize edilmiş kayıt:")
        for r in normalized[:5]:
            print(json.dumps(r, ensure_ascii=False))
        return

    write_csv(normalized, out_path)
    print(f"{len(normalized)} kayıt normalleştirildi ve '{out_path}' olarak kaydedildi.")


if __name__ == '__main__':
    main()
