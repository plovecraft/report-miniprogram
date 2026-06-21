from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile
from io import BytesIO


ALLOWED_SUFFIXES = {".doc", ".docx", ".pdf", ".jpg", ".jpeg", ".png"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
GUIDE_SUFFIXES = {".doc", ".docx", ".pdf"}
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_FILE_COUNT = 200


@dataclass
class MaterialPackageResult:
    report_file: Path | None = None
    guide_file: Path | None = None
    image_files: list[Path] = field(default_factory=list)
    image_metas: list[dict] = field(default_factory=list)


def extract_material_package(content: bytes, target_dir: Path) -> MaterialPackageResult:
    if len(content) > MAX_ZIP_BYTES:
        raise ValueError("ZIP 材料包过大")

    target_dir.mkdir(parents=True, exist_ok=True)
    result = MaterialPackageResult()

    try:
        with ZipFile(BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > MAX_FILE_COUNT:
                raise ValueError("ZIP 内文件数量过多")
            if sum(member.file_size for member in members) > MAX_EXTRACTED_BYTES:
                raise ValueError("ZIP 解压后文件过大")

            for member in members:
                member_name = _repair_zip_member_name(member.filename)
                parts = _safe_member_parts(member_name)
                suffix = Path(parts[-1]).suffix.lower()
                if suffix not in ALLOWED_SUFFIXES:
                    raise ValueError(f"ZIP 中包含不支持的文件类型：{member_name}")

                target = _dedupe_path(target_dir / _safe_output_name(parts))
                target.write_bytes(archive.read(member))

                if suffix in IMAGE_SUFFIXES:
                    result.image_files.append(target)
                    result.image_metas.append(
                        {
                            "filename": target.name,
                            "category": _category_from_folders(parts[:-1]),
                            "sourcePath": "/".join(parts),
                            "sortOrder": len(result.image_files) - 1,
                        }
                    )
                    continue

                if _looks_like_guide(parts[-1], suffix):
                    result.guide_file = result.guide_file or target
                elif suffix == ".docx":
                    result.report_file = result.report_file or target
                elif suffix in GUIDE_SUFFIXES:
                    result.guide_file = result.guide_file or target
    except BadZipFile as exc:
        raise ValueError("ZIP 材料包格式无效") from exc

    return result


def _safe_member_parts(name: str) -> list[str]:
    pure_path = PurePosixPath(name.replace("\\", "/"))
    parts = [part for part in pure_path.parts if part not in {"", "."}]
    if not parts or pure_path.is_absolute() or any(part == ".." for part in parts):
        raise ValueError(f"ZIP 中包含不安全路径：{name}")
    return parts


def _repair_zip_member_name(name: str) -> str:
    try:
        repaired = name.encode("cp437").decode("gbk")
    except UnicodeError:
        return name
    if _name_quality_score(repaired) > _name_quality_score(name):
        return repaired
    return name


def _name_quality_score(name: str) -> int:
    keywords = ["实验", "报告", "指导", "程序", "现象", "接线", "实物", "面板", "图片"]
    keyword_score = sum(8 for keyword in keywords if keyword in name)
    cjk_score = sum(1 for char in name if "\u4e00" <= char <= "\u9fff")
    mojibake_penalty = sum(2 for char in name if char in "╩╡╤Θ▒¿╕µ╜╙╧▀═╝│╠╨≥≤")
    return keyword_score + cjk_score - mojibake_penalty


def _safe_output_name(parts: list[str]) -> str:
    useful_parts = parts[-2:] if len(parts) >= 2 else parts
    return "__".join(_sanitize_filename_part(part) for part in useful_parts)


def _sanitize_filename_part(value: str) -> str:
    sanitized = "".join(char if char not in '<>:"/\\|?*' else "_" for char in value).strip()
    return sanitized or "unnamed"


def _looks_like_guide(filename: str, suffix: str) -> bool:
    name = Path(filename).stem.lower()
    return suffix in GUIDE_SUFFIXES and any(keyword in name for keyword in ["指导", "指导书", "guide", "实验指导"])


def _category_from_folders(folders: list[str]) -> str:
    folder_text = "/".join(folders).lower()
    if any(keyword in folder_text for keyword in ["接线", "面板", "wiring", "wire"]):
        return "wiring"
    if any(keyword in folder_text for keyword in ["实物", "现场", "physical"]):
        return "physical"
    if any(keyword in folder_text for keyword in ["现象", "结果", "result"]):
        return "result"
    if any(keyword in folder_text for keyword in ["程序", "梯形", "program", "ladder"]):
        return "program"
    return "auto"


def _dedupe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
