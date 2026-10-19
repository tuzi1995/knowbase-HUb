#!/usr/bin/env python3
"""Replace low-resolution workbook thumbnails with clearer linked-image previews."""

from __future__ import annotations

import io
import hashlib
import json
import posixpath
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
INPUT = Path(__file__).resolve().parent / "多媒体图片线下打标清单_20261016.xlsx"
OUTPUT = Path(__file__).resolve().parent / "多媒体图片线下打标清单_高清预览_20261019.xlsx"
CACHE = Path("/tmp/knowbase-image-preview-edit/high-res-cache")
MAX_SIZE = (1200, 900)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAW = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
DRAW_MAIN = "http://schemas.openxmlformats.org/drawingml/2006/main"


def parse_xml(archive: ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def relationship_map(archive: ZipFile, rels_path: str) -> dict[str, str]:
    root = parse_xml(archive, rels_path)
    base = posixpath.dirname(rels_path.replace("/_rels/", "/").removesuffix(".rels"))
    result = {}
    for rel in root.findall(f"{{{PKG_REL}}}Relationship"):
        target = rel.attrib["Target"]
        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(base, target))
        result[rel.attrib["Id"]] = resolved
    return result


def worksheet_paths(archive: ZipFile, wanted_name: str) -> list[str]:
    workbook = parse_xml(archive, "xl/workbook.xml")
    workbook_rels = relationship_map(archive, "xl/_rels/workbook.xml.rels")
    for sheet in workbook.findall(f".//{{{MAIN}}}sheet"):
        if sheet.attrib.get("name") == wanted_name:
            target = workbook_rels[sheet.attrib[f"{{{DOC_REL}}}id"]]
            sheet_path = target if target.startswith("xl/") else posixpath.normpath(posixpath.join("xl", target))
            return [sheet_path]
    raise RuntimeError(f"工作表不存在：{wanted_name}")


def shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = parse_xml(archive, "xl/sharedStrings.xml")
    return ["".join(part.text or "" for part in item.findall(f".//{{{MAIN}}}t")) for item in root]


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(part.text or "" for part in cell.findall(f".//{{{MAIN}}}t"))
    value = cell.find(f"{{{MAIN}}}v")
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        return strings[int(value.text)]
    return value.text


def urls_by_row(archive: ZipFile, sheet_path: str) -> dict[int, str]:
    strings = shared_strings(archive)
    root = parse_xml(archive, sheet_path)
    result = {}
    for cell in root.findall(f".//{{{MAIN}}}c"):
        address = cell.attrib.get("r", "")
        if not address.startswith("D"):
            continue
        match = re.fullmatch(r"D(\d+)", address)
        if not match or int(match.group(1)) < 2:
            continue
        url = cell_text(cell, strings)
        if url.startswith(("http://", "https://")):
            result[int(match.group(1))] = url
    return result


def image_targets_by_row(archive: ZipFile, sheet_path: str) -> dict[int, str]:
    sheet_dir = posixpath.dirname(sheet_path)
    sheet_rels_path = posixpath.join(sheet_dir, "_rels", posixpath.basename(sheet_path) + ".rels")
    sheet_rels = relationship_map(archive, sheet_rels_path)
    sheet = parse_xml(archive, sheet_path)
    drawing_rel_id = sheet.find(f".//{{{MAIN}}}drawing").attrib[f"{{{DOC_REL}}}id"]
    drawing_path = sheet_rels[drawing_rel_id]
    drawing_rels_path = posixpath.join(posixpath.dirname(drawing_path), "_rels", posixpath.basename(drawing_path) + ".rels")
    drawing_rels = relationship_map(archive, drawing_rels_path)
    drawing = parse_xml(archive, drawing_path)
    result = {}
    for anchor in list(drawing):
        marker = anchor.find(f"{{{DRAW}}}from")
        picture = anchor.find(f"{{{DRAW}}}pic")
        if marker is None or picture is None:
            continue
        row_element = marker.find(f"{{{DRAW}}}row")
        blip = picture.find(f".//{{{DRAW_MAIN}}}blip")
        if row_element is None or blip is None:
            continue
        row = int(row_element.text or "0") + 1
        target = drawing_rels[blip.attrib[f"{{{DOC_REL}}}embed"]]
        if row in result:
            raise RuntimeError(f"第 {row} 行存在多张图片，无法安全匹配")
        result[row] = target
    return result


def download_and_encode(item: tuple[int, str, str]) -> tuple[str, bytes]:
    row, url, target = item
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.jpg"
    if cache_path.exists():
        return target, cache_path.read_bytes()
    parts = urlsplit(url)
    encoded_url = urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe="/%:@!$&'()*+,;=-._~%"),
        quote(parts.query, safe="=&%:@/?!$'()*+,;-._~"),
        parts.fragment,
    ))
    last_error = None
    for attempt in range(4):
        try:
            request = Request(encoded_url, headers={"User-Agent": "KMatrix-image-export/1.0"})
            with urlopen(request, timeout=120) as response:
                payload = response.read()
            break
        except Exception as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(0.6 * (attempt + 1))
    with Image.open(io.BytesIO(payload)) as source:
        image = source.convert("RGB")
        image.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95, optimize=True, subsampling=0)
        image_bytes = output.getvalue()
    cache_path.write_bytes(image_bytes)
    return target, image_bytes


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(INPUT)
    with ZipFile(INPUT) as source:
        sheet_path = worksheet_paths(source, "图片清单")[0]
        urls = urls_by_row(source, sheet_path)
        targets = image_targets_by_row(source, sheet_path)
        if len(urls) != len(targets) or set(urls) != set(targets):
            raise RuntimeError(f"图片和链接行数不一致：{len(urls)} 个链接，{len(targets)} 张图片")
        jobs = [(row, urls[row], targets[row]) for row in sorted(urls)]

    replacements = {}
    failures = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(download_and_encode, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                target, payload = future.result()
                replacements[target] = payload
            except Exception as exc:
                failures.append({"row": job[0], "url": job[1], "error": type(exc).__name__})
    if failures:
        raise RuntimeError(json.dumps({"failed": failures}, ensure_ascii=False))
    if len(replacements) != len(jobs):
        raise RuntimeError(f"预览替换数量不符：{len(replacements)} / {len(jobs)}")

    with ZipFile(INPUT) as source, ZipFile(OUTPUT, "w", ZIP_DEFLATED) as target:
        for entry in source.infolist():
            payload = replacements.get(entry.filename, source.read(entry.filename))
            target.writestr(entry, payload)

    with ZipFile(INPUT) as original, ZipFile(OUTPUT) as updated:
        if original.namelist() != updated.namelist():
            raise RuntimeError("输出工作簿结构与原文件不一致")
        for entry in original.namelist():
            if entry not in replacements and original.read(entry) != updated.read(entry):
                raise RuntimeError(f"发现非图片内容发生变化：{entry}")
        checked = 0
        for payload in replacements.values():
            with Image.open(io.BytesIO(payload)) as image:
                if image.width > MAX_SIZE[0] or image.height > MAX_SIZE[1]:
                    raise RuntimeError("输出预览超过设定尺寸")
                checked += 1

    print(json.dumps({"output": str(OUTPUT), "images": checked, "max_size": MAX_SIZE, "quality": 95}, ensure_ascii=False))


if __name__ == "__main__":
    main()
