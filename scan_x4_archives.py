#!/usr/bin/env python3
"""
Scan X4 Foundations CAT/DAT archives for specified cargo-hold sizes in XML files.
"""
import argparse
import os
import re
import sys
import zlib

try:
    import lz4.block
    _HAVE_LZ4 = True
except ImportError:
    _HAVE_LZ4 = False

def parse_cat(cat_path):
    """
    Parse a .cat index file and yield tuples of (name, offset, size).
    """
    entries = []
    offset = 0
    with open(cat_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.rstrip('\n').rsplit(' ', 3)
            if len(parts) < 2:
                continue
            name = parts[0]
            try:
                size = int(parts[1])
            except ValueError:
                continue
            entries.append((name, offset, size))
            offset += size
    return entries

def decompress_block(data):
    """
    Decompress a data block using zlib or LZ4 if needed, or return raw data.
    """
    # Try zlib first
    try:
        return zlib.decompress(data)
    except Exception:
        pass
    # Try LZ4 raw block
    if _HAVE_LZ4:
        try:
            return lz4.block.decompress(data)
        except Exception:
            pass
    # Fallback: return raw
    return data

def scan_archive(cat_path, values, report, debug=False):
    """
    Process a single .cat/.dat pair, searching XML entries for decimal values.
    """
    dat_path = os.path.splitext(cat_path)[0] + '.dat'
    if not os.path.isfile(dat_path):
        if debug:
            print(f"[DEBUG] Missing DAT for CAT: {cat_path}")
        return
    if debug:
        print(f"[DEBUG] Processing CAT: {cat_path}, DAT: {dat_path}")
    entries = parse_cat(cat_path)
    if debug:
        xml_count = sum(1 for name, _, _ in entries if name.lower().endswith('.xml'))
        print(f"[DEBUG]  parsed {len(entries)} entries ({xml_count} XML files)")
    with open(dat_path, 'rb') as dat:
        for name, offset, size in entries:
            if not name.lower().endswith('.xml'):
                continue
            if debug:
                print(f"[DEBUG]   entry: {name} @ {offset} (+{size} bytes)")
            dat.seek(offset)
            blob = dat.read(size)
            data = decompress_block(blob)
            try:
                text = data.decode('utf-8', errors='replace')
            except Exception:
                continue
            if debug:
                # debug preview of this XML entry
                print(f"[DEBUG] {cat_path}:{name} (blob {len(blob)} bytes) ->\n{text[:200]!r}\n")
            for val in values:
                # match standalone decimal, not part of larger number
                if f'{val}' in text:
                    pattern = rf'(?<!\d){val}(?!\d)'
                    if re.search(pattern, text):
                        report.setdefault(val, []).append((cat_path, name))

def main():
    parser = argparse.ArgumentParser(
        description='Scan X4 CAT/DAT archives for cargo-hold sizes in XML.'
    )
    parser.add_argument('x4dir', help='X4 Foundations installation directory')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()

    # warn if LZ4 support missing
    if not _HAVE_LZ4:
        print('Warning: python-lz4 not installed; LZ4-compressed entries may not be decompressed', file=sys.stderr)
    # values to search
    targets = [2300, 36000, 43200, 40000, 50400]
    found = {v: [] for v in targets}

    # enumerate .cat files in root
    roots = []
    try:
        for fn in os.listdir(args.x4dir):
            if fn.lower().endswith('.cat'):
                roots.append(os.path.join(args.x4dir, fn))
    except Exception:
        pass
    # enumerate .cat in immediate subdirs of extensions
    extdir = os.path.join(args.x4dir, 'extensions')
    if os.path.isdir(extdir):
        for sub in os.listdir(extdir):
            p = os.path.join(extdir, sub)
            if os.path.isdir(p):
                for fn in os.listdir(p):
                    if fn.lower().endswith('.cat'):
                        roots.append(os.path.join(p, fn))

    if args.debug:
        print(f"[DEBUG] Found {len(roots)} CAT files to scan:", file=sys.stderr)
        for r in roots:
            print(f"[DEBUG]  {r}", file=sys.stderr)

    # scan each archive
    for cat in roots:
        scan_archive(cat, targets, found, debug=args.debug)

    # summary
    for val in targets:
        entries = found.get(val) or []
        if not entries:
            print(f'{val}: Not found')
        else:
            print(f'{val}: found in {len(entries)} file(s)')
            for cat, name in entries:
                print(f'  {os.path.relpath(cat, args.x4dir)}: {name}')

if __name__ == '__main__':
    main()
