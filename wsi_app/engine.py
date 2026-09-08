"""Conservative review-copy processing; output always requires human review."""
from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
import uuid
from pathlib import Path

import tifffile
import tifftools

from tools.inspect_samples import inspect

CHUNK = 8 * 1024 * 1024
# Image layout, compression, resolution, and color interpretation only.
SVS_TAGS = {254, 256, 257, 258, 259, 262, 266, 270, 273, 274, 277,
            278, 279, 282, 283, 284, 296, 317, 320, 322, 323, 324, 325,
            338, 339, 347, 529, 530, 531, 532, 34675}


class UnsupportedFormat(ValueError):
    pass


def segments(page, ndpi):
    if ndpi:
        # tifffile synthesizes tiles for NDPI; use the stored JPEG strip instead.
        return list(zip(page.tags[273].value, page.tags[279].value))
    return list(zip(page.dataoffsets, page.databytecounts))


def image_hashes(path):
    hashes = []
    with tifffile.TiffFile(path) as tif, path.open("rb") as stream:
        for page in tif.pages:
            tissue = (page.tags[65421].value > 0) if tif.is_ndpi else page.is_tiled
            if not tissue:
                continue
            digest = hashlib.sha256()
            for offset, count in segments(page, tif.is_ndpi):
                stream.seek(offset)
                while count:
                    data = stream.read(min(CHUNK, count))
                    if not data:
                        raise ValueError("Truncated image payload")
                    digest.update(data)
                    count -= len(data)
            hashes.append((page.imagewidth, page.imagelength, digest.hexdigest()))
    return hashes


def svs_copy(source, target, openslide):
    with openslide.OpenSlide(str(source)) as slide:
        desc = "Aperio Image Library\n"
        for key in ("MPP", "AppMag"):
            value = slide.properties.get("aperio." + key)
            if value is not None:
                number = float(value)
                if not math.isfinite(number) or number <= 0:
                    raise UnsupportedFormat("Invalid SVS calibration")
                desc += f"|{key} = {number:g}"
    with tifffile.TiffFile(source) as tif:
        keep = []
        for index, page in enumerate(tif.pages):
            if page.subifds:
                raise UnsupportedFormat("SVS SubIFD variant is not supported yet")
            if page.is_tiled or index == 1:
                keep.append(index)
            elif page.subfiletype not in (1, 9):
                raise UnsupportedFormat("Unrecognized SVS image directory")
    info = tifftools.read_tiff(str(source))
    removed = set()
    output_ifds = []
    for index in keep:
        ifd = info["ifds"][index]
        removed.update(set(ifd["tags"]) - SVS_TAGS)
        ifd["tags"] = {k: v for k, v in ifd["tags"].items() if k in SVS_TAGS}
        ifd["tags"][270] = {"datatype": 2, "data": desc}
        output_ifds.append(ifd)
    tifftools.write_tiff(output_ifds, str(target), bigEndian=info["bigEndian"],
                         bigtiff=info["bigtiff"])
    return {"policy": "svs-review-v1", "removed_tag_codes": sorted(removed),
            "removed_image_directories": len(info["ifds"]) - len(keep),
            "review_reasons": ["조직·썸네일 내 문자와 ICC/압축 데이터의 내장 정보는 별도 검토가 필요합니다."]}


def ndpi_copy(source, target):
    if source.stat().st_size >= 2**32:
        raise UnsupportedFormat("4GB 이상 NDPI는 아직 처리할 수 없습니다.")
    patches, protected, private_codes = [], [], set()
    with tifffile.TiffFile(source) as tif:
        if not tif.is_ndpi or tif.is_bigtiff:
            raise UnsupportedFormat("지원하지 않는 NDPI 구조입니다.")
        for page in tif.pages:
            lens = page.tags[65421].value
            if page.subifds or lens <= 0 and lens != -2:
                raise UnsupportedFormat("라벨·매크로 또는 추가 영상이 있는 NDPI는 아직 처리할 수 없습니다.")
            if 65424 in page.tags and page.tags[65424].value != 0:
                raise UnsupportedFormat("다중 초점면 NDPI는 아직 처리할 수 없습니다.")
            # Permit inline ASCII values, but protect tag headers and offset words.
            protected.append((page.offset, page.offset + 2))
            tail = page.offset + 2 + len(page.tags) * 12
            protected.append((tail, tail + 8 + len(page.tags) * 4))
            for offset, count in segments(page, True):
                protected.append((offset, offset + count))
            for tag in page.tags.values():
                protected.append((tag.offset, tag.offset + 8))
                inline_text = int(tag.dtype) == 2 and tag.valueoffset == tag.offset + 8
                if not inline_text:
                    protected.append((tag.offset + 8, tag.offset + 12))
                if int(tag.dtype) == 2:
                    replacement = b"Hamamatsu" if tag.code == 271 else b""
                    if len(replacement) + 1 > tag.count:
                        raise UnsupportedFormat("NDPI 문자열 필드 길이를 확인해야 합니다.")
                    patches.append((tag.valueoffset, tag.count, replacement.ljust(tag.count, b"\0")))
                else:
                    if tag.code >= 65000:
                        private_codes.add(tag.code)
                    if tag.valueoffset != tag.offset + 8:
                        protected.append((tag.valueoffset, tag.valueoffset + tag.valuebytecount))
    for offset, count, _ in patches:
        if offset < 12 or offset + count > source.stat().st_size:
            raise UnsupportedFormat("NDPI 필드 범위가 올바르지 않습니다.")
        if any(offset < end and offset + count > start for start, end in protected):
            raise UnsupportedFormat("NDPI 필드가 보존 영역과 겹칩니다.")
    patches.sort()
    for left, right in zip(patches, patches[1:]):
        if left[0] + left[1] > right[0] and left != right:
            raise UnsupportedFormat("NDPI 문자열 영역이 서로 겹칩니다.")
    shutil.copyfile(source, target)
    with target.open("r+b") as stream:
        for offset, _, replacement in patches:
            stream.seek(offset)
            stream.write(replacement)
    with target.open("rb") as stream:
        for offset, count, replacement in patches:
            stream.seek(offset)
            if stream.read(count) != replacement:
                raise ValueError("NDPI field verification failed")
    return {"policy": "ndpi-review-v1", "cleared_text_fields": len(patches),
            "retained_private_nontext_tags": sorted(private_codes),
            "review_reasons": [
                "NDPI 전용 비문자 태그와 영역 지도는 보존했습니다. 추가 개인정보 검토가 필요합니다.",
                "파일 내 미참조 영역과 조직 영상 속 문자는 검사하지 않았습니다."]}


def create_review_copy(source: Path, output: Path, openslide, progress=lambda _: None):
    source, output = source.resolve(), output.resolve()
    if output == source.parent or output.is_relative_to(source.parent):
        raise ValueError("출력 폴더는 원본 폴더 밖으로 선택하세요.")
    vendor = openslide.OpenSlide.detect_format(str(source))
    if (source.suffix.lower(), vendor) not in {(".svs", "aperio"), (".ndpi", "hamamatsu")}:
        raise UnsupportedFormat("확장자와 내부 형식이 일치하지 않거나 지원하지 않는 파일입니다.")
    output.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output).free < source.stat().st_size * 1.15 + CHUNK:
        raise OSError("출력 드라이브의 여유 공간이 부족합니다.")
    before = source.stat()
    token = "review_" + uuid.uuid4().hex
    pending = Path(tempfile.mkdtemp(prefix=".pending_", dir=output))
    target = pending / (token + source.suffix.lower())
    try:
        progress("원본 조직 데이터 확인")
        original_hashes = image_hashes(source)
        progress("검토용 사본 생성")
        policy = svs_copy(source, target, openslide) if vendor == "aperio" else ndpi_copy(source, target)
        progress("조직 데이터 보존 검증")
        if image_hashes(target) != original_hashes:
            raise ValueError("조직 영상 압축 데이터가 원본과 일치하지 않습니다.")
        progress("영상 재열기 및 메타데이터 검증")
        original = inspect(source, "original", openslide)
        result = inspect(target, token, openslide)
        if original["errors"] or result["errors"]:
            raise ValueError("영상 읽기 검증을 통과하지 못했습니다.")
        for key in ("dimensions", "level_dimensions", "level_downsamples"):
            if original["openslide"][key] != result["openslide"][key]:
                raise ValueError("영상 피라미드가 원본과 일치하지 않습니다.")
        with openslide.OpenSlide(str(target)) as check:
            if vendor == "aperio":
                if {"label", "macro"} & set(check.associated_images):
                    raise ValueError("라벨 또는 매크로가 남아 있습니다.")
                if any(k.startswith("aperio.") and k not in {"aperio.MPP", "aperio.AppMag"}
                       for k in check.properties):
                    raise ValueError("SVS 메타데이터 검증 실패")
            else:
                with tifffile.TiffFile(target) as tif:
                    if any(tag.value.strip(b"\0") if isinstance(tag.value, bytes) else tag.value
                           for page in tif.pages for tag in page.tags.values()
                           if int(tag.dtype) == 2 and tag.code != 271):
                        raise ValueError("NDPI 문자열 제거 검증 실패")
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("작업 중 원본이 변경되었습니다.")
        result.update(policy)
        result["status"] = "review_required"
        result["compressed_tissue_sha256_match"] = True
        # Deliberately do not persist original filenames, hashes, or ID mappings.
        import json
        (pending / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        final = output / token
        pending.rename(final)
        return {"directory": str(final), "file": str(final / target.name), "report": result}
    finally:
        if pending.exists():
            shutil.rmtree(pending)
