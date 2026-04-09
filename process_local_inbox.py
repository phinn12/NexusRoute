#!/usr/bin/env python3
"""process_local_inbox.py

Yerelden gelen dosyaları (CSV/JSON/GeoJSON/NDJSON/Excel) batch olarak normalleştirir.
Kullanım:
  python3 process_local_inbox.py --inbox yerelden_gelen

Davranış:
- `--inbox` içindeki tüm dosyaları işler.
- Her kaynak dosya için `--out` içinde <orijinadi>_normalized.csv oluşturur (varsayılan: inbox/normalized).
- İşlenen kaynak dosyalar `--processed` içine taşınır (varsayılan: inbox/processed).
"""
import argparse
import os
import shutil
from pathlib import Path
import sys

# normalize_addresses modülünden fonksiyonları kullanıyoruz
from normalize_addresses import detect_and_load, normalize_record, write_csv


def process_file(path: Path, out_dir: Path, processed_dir: Path):
    print(f"İşleniyor: {path}")
    try:
        raw_rows = detect_and_load(str(path))
    except Exception as e:
        print(f"  Yükleme hatası: {e}")
        return False

    normalized = []
    next_id = 1
    for raw in raw_rows:
        rec = normalize_record(raw, next_id)
        normalized.append(rec)
        try:
            _ = int(rec['id'])
            next_id = max(next_id, int(rec['id']) + 1)
        except Exception:
            next_id += 1

    out_name = f"{path.stem}_normalized.csv"
    out_path = out_dir / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(normalized, str(out_path))
    print(f"  -> {len(normalized)} kayıt yazıldı: {out_path}")

    # taşınmışsa processed dizinine taşı
    if processed_dir:
        processed_dir.mkdir(parents=True, exist_ok=True)
        dest = processed_dir / path.name
        shutil.move(str(path), str(dest))
        print(f"  Orijinal {dest} konumuna taşındı")
    return True


def main():
    parser = argparse.ArgumentParser(description='Batch normalize files from a local inbox folder')
    parser.add_argument('--inbox', required=True, help='Yerliden gelen dosyaların olduğu klasör')
    parser.add_argument('--out', help='Normalize edilmiş dosyaların yazılacağı alt klasör (varsayılan: <inbox>/normalized)')
    parser.add_argument('--processed', help='İşlenen orijinal dosyaların taşınacağı klasör (varsayılan: <inbox>/processed)')
    parser.add_argument('--ext', nargs='+', help='İşlenecek dosya uzantıları (varsayılan: csv json geojson ndjson xlsx xls txt)')
    args = parser.parse_args()

    inbox = Path(args.inbox)
    if not inbox.exists() or not inbox.is_dir():
        print(f"Inbox klasörü bulunamadı veya klasör değil: {inbox}")
        sys.exit(1)

    out_dir = Path(args.out) if args.out else (inbox / 'normalized')
    processed_dir = Path(args.processed) if args.processed else (inbox / 'processed')

    exts = args.ext if args.ext else ['csv','json','geojson','ndjson','xlsx','xls','txt']
    exts = [e.lower().lstrip('.') for e in exts]

    files = [p for p in inbox.iterdir() if p.is_file() and p.suffix.lower().lstrip('.') in exts]
    if not files:
        print('İşlenecek dosya bulunamadı.')
        return

    for f in files:
        process_file(f, out_dir, processed_dir)

    print('TAMAMLANDI.')


if __name__ == '__main__':
    main()
