from __future__ import annotations

import base64
import json
import math
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import PySide6
import tifffile
from PySide6.QtCore import QCoreApplication, QProcess, Qt, QUrl, QStandardPaths, QTimer
from PySide6.QtGui import QDesktopServices, QPixmap, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QTextEdit, QLineEdit, QProgressBar, QMessageBox,
    QAbstractItemView, QCheckBox, QGroupBox, QGridLayout, QComboBox, QToolButton, QTabWidget, QScrollArea)

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
ASSET_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "logo"
STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WSI_Anonymization" if FROZEN else ROOT / "artifacts"
EXTENSIONS = {".svs", ".ndpi", ".tif", ".tiff", ".mrxs", ".scn", ".vms", ".vmu", ".bif", ".svslide", ".dcm", ".czi", ".isyntax", ".i2syntax"}

STORAGE_MODES = (
    ("1. 원본 형식 유지", "native"),
    ("2. TIFF 변환 · 원본 압축 유지", "preserve"),
    ("3. TIFF 변환 · 무손실 압축", "jpeg2000"),
)


def storage_support(path):
    """Conservative header preflight; the exporter still validates actual data."""
    from wsi_anonymizer import native_export_supported
    native = "원본 형식 저장은 호환 JPEG 구조의 SVS·NDPI와 Philips만 지원합니다. 이 파일의 구조는 지원 범위에 포함되지 않습니다."
    if path.suffix.lower() in {".isyntax", ".i2syntax"}:
        return {"native": "", "preserve": "Philips 고유 압축은 OpenSlide 호환 TIFF에 재사용할 수 없습니다.", "jpeg2000": ""}
    reasons = {"native": "" if native_export_supported(path) else native,
               "preserve": "원본 압축 재사용은 호환 JPEG 구조의 SVS·NDPI·TIFF만 지원합니다.", "jpeg2000": ""}
    if path.suffix.lower() not in {".svs", ".ndpi", ".tif", ".tiff"}:
        return reasons
    try:
        with tifffile.TiffFile(path) as source:
            page = source.pages[0]
            if page.compression != 7 or page.photometric != 6 or page.planarconfig != 1 or page.jpegtables or not page.is_tiled:
                return reasons
            tw, th = page.tilewidth, page.tilelength
            group = 16 // math.gcd(16, th) if page.is_ndpi else 1
            if page.is_ndpi and (not page.jpegheader or page.imagewidth % tw or page.imagelength % (th * group)):
                return reasons
            if tw % 16 or (th * group) % 16 or max(tw, th * group) > 65535 or tw * th * group > 16 * 1024**2:
                return reasons
            reasons["preserve"] = ""
    except Exception:
        reasons["preserve"] = "파일 헤더를 확인하지 못해 원본 압축 유지 옵션을 사용할 수 없습니다. 전체 검사로 파일을 확인하세요."
    return reasons


def configure_qt():
    # yslee contains a qt.conf for another Qt installation. Scope this fix to us.
    plugins = Path(PySide6.__file__).resolve().parent / "plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    QCoreApplication.setLibraryPaths([str(plugins)])


def source_display_snapshot(path):
    """GUI-memory-only values; never attach this snapshot to worker jobs/reports."""
    values = {"filename": path.name, "csv_filename": path.name}
    if path.suffix.lower() in {".isyntax", ".i2syntax"}:
        values["_notice"] = "Philips 원본 XML 값은 이 표에서 비교하지 않습니다. SDK 부속 이미지 목록과 출력 제외 정책을 표시합니다."
        return values
    try:
        with tifffile.TiffFile(path) as tif:
            fields = {270: "description", 305: "software", 306: "datetime", 269: "document_name",
                      315: "artist", 316: "host", 34675: "icc"}
            for code, name in fields.items():
                parts = []
                for index, page in enumerate(tif.pages):
                    if index >= 64:
                        parts.append("추가 IFD 값은 생략했습니다.")
                        break
                    tag = page.tags.get(code)
                    if tag is None:
                        continue
                    if code == 34675:
                        value = f"ICC 프로파일 {tag.count:,} bytes (바이너리 원문 표시 안 함)"
                    elif int(tag.dtype) == 2:
                        tif.filehandle.seek(tag.valueoffset)
                        value = tif.filehandle.read(min(tag.count, 4096)).decode("utf-8", errors="replace").rstrip("\x00")
                        if tag.count > 4096:
                            value += "\n[4 KiB 이후 생략]"
                    else:
                        value = "문자열 형식이 아닌 태그 · 원문 표시 안 함"
                    parts.append(f"IFD {index}: {value}")
                if parts:
                    values[name] = "\n\n".join(parts)
    except (OSError, ValueError, tifffile.TiffFileError):
        values["_notice"] = "원본 태그 값을 읽지 못했습니다. 존재·처리 상태만 표시합니다."
    return values


def audit_labels():
    names = {"description": "원본 설명문", "software": "소프트웨어 태그 (305)", "datetime": "저장 일시 태그 (306)",
             "document_name": "문서 이름 태그 (269)", "artist": "작성자 태그 (315)", "host": "호스트 태그 (316)", "icc": "ICC 프로파일",
             "label": "라벨 이미지", "macro": "매크로 이미지", "thumbnail": "원본 썸네일", "other": "기타 부속 이미지",
             "filename": "출력 파일명", "csv_filename": "CSV 원본 파일명", "pixels": "영상 속 개인정보",
             "icc_review": "ICC 내부 정보", "jpeg_app_com": "JPEG APP/COM 부가정보", "philips_metadata": "Philips 원본 XML 메타데이터"}
    states = {"removed": "제거 확인", "rewritten": "원본 내용 제외 · 새 기술 정보로 작성",
              "retained": "보존", "not_present": "원본에 없음", "not_checked": "비교 불가",
              "renamed": "익명 이름으로 변경", "excluded": "포함 안 함", "not_exported": "CSV 저장 안 함",
              "user_reviewed": "사용자 검토 확인 (자동 검증 아님)", "review_required": "별도 검토 필요",
              "not_applicable": "해당 없음", "excluded_by_policy": "출력 제외 정책 적용 · 원본 존재 여부 미집계"}
    return names, states


def audit_lines(audit):
    if not audit:
        return []
    names, states = audit_labels()
    lines = ["", "익명화 처리 내역"]
    for entry in audit["entries"]:
        lines.append(f"• {names[entry['item']]}: {states[entry['status']]}")
    codes = audit.get("removed_tag_codes", [])
    if audit.get("tag_comparison_available"):
        lines.append("출력에 없는 원본 TIFF 태그: " + (", ".join(map(str, codes)) or "없음"))
    lines.extend(["", "※ '원본에 없음'은 해당 TIFF 태그/OpenSlide 항목 기준입니다. 설명문 안의 개별 환자정보는 분석하지 않습니다. 완전한 익명화 인증이 아닙니다."])
    return lines


def technical_lines(data):
    def number(value):
        return f"{value:.6g}" if value is not None else "정보 없음"
    return [f"원본 Vendor: {data.get('source_vendor') or '정보 없음'}",
            f"Magnification: {number(data.get('objective_power'))} × (대물렌즈)",
            f"Pixel Size: {data.get('width_px', '-')} × {data.get('height_px', '-')} px",
            f"MPP: {number(data.get('mpp_x_um'))} × {number(data.get('mpp_y_um'))} µm/pixel (X/Y)",
            f"Physical Size: {number(data.get('physical_width_mm'))} × {number(data.get('physical_height_mm'))} mm"]


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MeDIAuto Anonymization · 1.10.1 · 내부 연구용")
        self.setWindowIcon(QIcon(str(ASSET_ROOT / "icon.png")))
        self.resize(1240, 900)
        self.setMinimumSize(1050, 760)
        self.paths, self.results, self.previews = [], {}, {}
        self.source_display_values = {}
        self.queue = []
        self.process = None
        self.buffer = b""
        self.had_result = False
        self.stop_requested = False
        self.active_row = None
        self.event_timer = QTimer(self)
        self.event_timer.setInterval(100)
        self.event_timer.timeout.connect(self.read_output)
        self.setAcceptDrops(True)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        self.brand = QLabel()
        logo = QPixmap(str(ASSET_ROOT / "logo.png"))
        self.brand.setPixmap(logo.scaled(270, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.brand.setAccessibleName("MeDIAuto Anonymization")
        header.addWidget(self.brand)
        header.addStretch()
        subtitle = QLabel("WSI 익명화 및 내보내기\nSVS · NDPI · Philips 지원 · 원본 유지 / TIFF 변환")
        subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtitle.setObjectName("subtitle")
        header.addWidget(subtitle)
        layout.addLayout(header)
        self.runtime_status = QLabel()
        self.runtime_status.setObjectName("hint")
        self.runtime_status.setWordWrap(True)
        bundled = ROOT / "philips"
        if (bundled / "python.exe").is_file() and (bundled / "RUNTIME.json").is_file():
            self.runtime_status.setText("내부 연구용 · Philips SDK 동봉 · 별도 Python/Conda 설치 불필요")
        elif os.environ.get("PHILIPS_PYTHON") or (Path.home() / ".conda/envs/philips-sdk-py37/python.exe").is_file():
            self.runtime_status.setText("개발 환경 · Philips는 별도 SDK 런타임 사용")
        else:
            self.runtime_status.setText("Philips 런타임을 찾지 못했습니다. EXE 옆의 philips 폴더를 확인하세요.")
        layout.addWidget(self.runtime_status)
        notice = QLabel("원본 메타데이터·라벨·매크로는 내보내지 않습니다. 조직 영상 안에 적힌 개인정보는 별도 검토가 필요합니다.")
        notice.setObjectName("notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("슬라이드 목록"))
        toolbar.addStretch()
        self.add_button = QPushButton("파일 추가")
        self.folder_button = QPushButton("폴더 추가")
        self.sample_button = QPushButton("샘플 불러오기")
        self.clear_button = QPushButton("목록 비우기")
        for button in (self.add_button, self.folder_button, self.sample_button, self.clear_button):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.add_button.clicked.connect(self.pick_files)
        self.folder_button.clicked.connect(self.pick_folder)
        self.sample_button.clicked.connect(lambda: self.add_folder(ROOT / "data"))
        if FROZEN and not (ROOT / "data").is_dir():
            self.sample_button.hide()
        self.clear_button.clicked.connect(self.clear)
        splitter = QSplitter()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["파일", "형식", "용량", "상태"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(1, 95)
        self.table.setColumnWidth(2, 85)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.empty_state = QLabel("슬라이드를 추가하세요\n\nSVS · NDPI · Philips iSyntax / i2syntax\n파일 또는 폴더를 이곳에 끌어다 놓으세요.", self.table.viewport())
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setAttribute(Qt.WA_TransparentForMouseEvents)
        empty_layout = QVBoxLayout(self.table.viewport())
        empty_layout.addWidget(self.empty_state)
        self.table.itemSelectionChanged.connect(self.show_selection)
        splitter.addWidget(self.table)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.addWidget(QLabel("선택한 슬라이드"))
        self.preview = QLabel("검사하면 조직 썸네일이 표시됩니다.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(200)
        self.preview.setObjectName("preview")
        panel_layout.addWidget(self.preview)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("파일을 추가하고 '전체 검사'를 누르세요.\n파일과 폴더를 창에 끌어다 놓을 수도 있습니다.")
        panel_layout.addWidget(self.details)
        self.side_tabs = QTabWidget()
        self.side_tabs.setMinimumWidth(440)
        splitter.addWidget(self.side_tabs)
        splitter.setSizes([660, 530])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.options_box = QGroupBox()
        options = QGridLayout(self.options_box)
        options.setContentsMargins(18, 10, 18, 14)
        options.setVerticalSpacing(14)
        self.info_buttons = {}
        self.advanced_box = QGroupBox()
        advanced = QGridLayout(self.advanced_box)
        advanced.setContentsMargins(0, 4, 0, 4)
        advanced.setVerticalSpacing(12)
        self.advanced_box.hide()

        def option(widget, key, title, explanation, row, column):
            order = {"image": 0, "csv": 1, "preset": 2,
                     "rename": 4, "filename": 5, "privacy": 8}
            advanced_order = {"structure": 0, "compression": 1, "mpp": 2, "icc": 3}
            line = QHBoxLayout()
            if key in ("structure", "compression", "preset"):
                line.addWidget(QLabel(title))
            line.addWidget(widget)
            info = QToolButton()
            info.setText("i")
            info.setObjectName("info")
            info.setAccessibleName(title + " 설명")
            info.setToolTip(title + " 설명 보기")
            info.clicked.connect(lambda: QMessageBox.information(self, title, explanation))
            self.info_buttons[key] = info
            line.addWidget(info)
            line.addStretch()
            if key in advanced_order:
                advanced.addLayout(line, advanced_order[key], 0)
            else:
                options.addLayout(line, order[key], 0)

        self.export_image = QCheckBox("영상 파일 저장")
        self.export_csv = QCheckBox("처리 내역과 슬라이드 정보 저장 (CSV)")
        self.include_filename = QCheckBox("CSV에 원본 파일명 포함")
        self.rename_output = QCheckBox("출력 파일명을 익명 이름으로 변경")
        self.rename_output.setChecked(True)
        self.preserve_mpp = QCheckBox("실제 크기 정보 유지")
        self.preserve_icc = QCheckBox("원본 색상 프로파일 유지 (별도 검토)")
        self.preserve_icc.setChecked(True)
        for control in (self.export_image, self.export_csv, self.include_filename, self.preserve_mpp):
            control.setChecked(True)
        option(self.export_image, "image", "영상 파일 저장", "1번은 호환 SVS·NDPI·Philips의 원본 형식(.svs / .ndpi / .isyntax)을 유지합니다. 2번은 호환 JPEG를 재사용한 TIFF, 3번은 읽은 RGB를 무손실 압축한 TIFF로 저장합니다. 목록 전체에서 지원되는 방식만 선택할 수 있습니다.\n\n조직 영상만 포함하며 원본의 라벨·매크로와 개인정보 메타데이터는 제외합니다. 해제하면 선택한 CSV만 저장합니다.", 0, 0)
        option(self.export_csv, "csv", "슬라이드 정보 CSV", "MPP(픽셀의 실제 크기), 영상 크기, 배율, 입력 형식, 파일 크기와 처리 결과를 CSV에 기록합니다. 환자명·검체 ID·스캔 날짜 등 원본 개인정보 태그는 포함하지 않습니다.\n\nCSV만 선택하면 영상을 변환하거나 픽셀 검증하지 않습니다.", 0, 1)
        option(self.include_filename, "filename", "원본 파일명 포함", "CSV에 원본 파일명을 기록하여 결과와 대응시킵니다. 파일명 자체에 이름이나 환자 ID가 있으면 CSV에도 남습니다.\n\n해제하면 original_filename 열을 빈칸으로 저장합니다. TIFF 내부에는 원본 파일명을 기록하지 않습니다.", 1, 1)
        option(self.preserve_mpp, "mpp", "기술 정보와 MPP 보존", "Magnification: 원본 대물렌즈 배율입니다.\nPixel Size: 전체 영상의 가로 × 세로 픽셀 수입니다.\nMPP: 픽셀 하나의 실제 길이(µm/pixel, X/Y)입니다.\nPhysical Size: 픽셀 수 × MPP로 계산한 전체 영상 영역의 크기(mm)이며 조직만의 크기가 아닙니다.\n\n기술 정보는 숫자만 TIFF에 새로 기록합니다. 원본에 없는 배율·MPP는 추정하지 않습니다. 외부 뷰어의 배율 표시는 뷰어 지원에 따라 다릅니다.\n\nMPP 보존을 해제하면 TIFF의 MPP와 Physical Size를 생략합니다. CSV에는 원본 기술 정보를 기록합니다.", 1, 0)
        self.storage_choice = QComboBox()
        for label, mode in STORAGE_MODES:
            self.storage_choice.addItem(label, mode)
        self.storage_choice.setCurrentIndex(0)
        self.compression = self.storage_choice  # Existing job API uses compression.
        option(self.storage_choice, "preset", "저장 방식", "", 0, 0)
        self.info_buttons["preset"].clicked.disconnect()
        self.info_buttons["preset"].clicked.connect(self.show_storage_info)
        self.storage_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.storage_choice.setMinimumContentsLength(15)
        self._storage_support_cache = {}
        option(QLabel("개인정보 항목 제외 · 영상 속 글자는 직접 확인"), "privacy", "익명화 범위", "원본 메타데이터와 라벨·매크로 이미지를 제외하고 새 파일을 만듭니다. Philips 원본 유지에서는 조직 압축 블록만 복사하고 기술 정보만 새로 기록합니다.\n\n원본 색상 프로파일을 유지하면 프로파일 내부 설명도 복사되므로 별도 검토가 필요합니다. 조직 영상에 직접 찍힌 이름이나 식별자는 자동으로 지워지지 않습니다.", 2, 1)
        self.structure = QComboBox()
        self.structure.addItem("확대·축소 보기 지원", True)
        self.structure.addItem("최대 해상도만 저장", False)
        option(self.structure, "structure", "출력 구조", "표준 피라미드 TIFF: 최대 해상도와 조직 축소 레벨을 함께 저장합니다. OpenSlide의 get_thumbnail()과 확대·축소 보기에 사용할 수 있습니다.\n\n단일 해상도 TIFF: 최대 해상도만 저장합니다. 큰 영상의 get_thumbnail()은 많은 메모리가 필요할 수 있습니다.\n\n두 구조 모두 개인정보 메타데이터 제거를 적용합니다. 영상에 직접 찍힌 식별자는 별도 검토가 필요합니다.", 3, 0)
        self.options_hint = QLabel()
        option(self.rename_output, "rename", "출력 파일명 변경", "체크: anonymous_<임의 ID> 이름으로 저장합니다.\n해제: 원본 이름을 유지합니다. 원본 형식 저장은 .svs / .ndpi / .isyntax, TIFF 변환은 .tiff 확장자를 사용합니다. 같은 이름이 있으면 _2, _3 등을 붙이며 기존 파일을 덮어쓰지 않습니다.\n\n원본 이름에 환자명·ID가 있으면 해제 시 결과 파일명에도 남습니다. 내부 메타데이터 제거는 그대로 적용합니다. CSV의 원본 파일명 포함 옵션과는 별개입니다.", 3, 1)
        self.options_hint.setWordWrap(True)
        option(self.preserve_icc, "icc", "ICC 색상 프로파일", "기본값은 유지입니다. 원본 색상을 해석하는 ICC를 영상과 함께 저장하며 Philips 원본 형식 저장에도 적용합니다. 제외하면 압축 데이터가 같아도 색상이 달라질 수 있습니다. 원본에 ICC가 없으면 임의로 추가하지 않습니다. 원본에 있는데 보존할 수 없는 경우 오류로 안내합니다.\n\nICC 내부 설명·제조사 정보도 복사되므로 기존과 같이 별도 검토 상태로 기록합니다. 이 옵션은 프로파일 보존 여부이며 조직 픽셀을 다른 색공간으로 변환하지 않습니다.", 4, 0)
        self.options_hint.setObjectName("hint")
        options.addWidget(self.options_hint, 3, 0)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("세부 설정 보기")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self.advanced_box.setVisible)
        self.advanced_toggle.toggled.connect(lambda checked: self.advanced_toggle.setText("세부 설정 접기" if checked else "세부 설정 보기"))
        options.addWidget(self.advanced_toggle, 6, 0)
        options.addWidget(self.advanced_box, 7, 0)
        options.setRowStretch(9, 1)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(self.options_box)
        self.side_tabs.addTab(settings_scroll, "내보내기 설정")
        self.side_tabs.addTab(panel, "슬라이드 정보")
        audit_panel = QWidget()
        audit_layout = QVBoxLayout(audit_panel)
        self.audit_notice = QLabel("원본 값은 화면에만 표시하며 CSV에는 저장하지 않습니다.")
        self.audit_notice.setWordWrap(True)
        audit_layout.addWidget(self.audit_notice)
        self.audit_table = QTableWidget(0, 3)
        self.audit_table.setHorizontalHeaderLabels(["항목", "원본", "익명화 결과"])
        self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.audit_table.verticalHeader().setVisible(False)
        self.audit_table.verticalHeader().setDefaultSectionSize(40)
        self.audit_table.setWordWrap(False)
        self.audit_table.setShowGrid(False)
        self.audit_table.setAlternatingRowColors(True)
        self.audit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.audit_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.audit_table.itemSelectionChanged.connect(self.show_audit_row)
        audit_layout.addWidget(self.audit_table, 1)
        self.audit_details = QTextEdit()
        self.audit_details.setReadOnly(True)
        self.audit_details.setMaximumHeight(160)
        self.audit_details.setPlaceholderText("TIFF 내보내기가 완료되면 파일별 제거·보존 내역을 표시합니다.")
        audit_layout.addWidget(self.audit_details)
        self.side_tabs.addTab(audit_panel, "익명화 내역")
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("출력 폴더"))
        default_output = Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)) / "WSI Exports" if FROZEN else ROOT / "output"
        self.output = QLineEdit(str(default_output))
        output_row.addWidget(self.output)
        self.output_button = QPushButton("변경")
        self.output_button.clicked.connect(self.pick_output)
        output_row.addWidget(self.output_button)
        self.open_button = QPushButton("결과 폴더 열기")
        self.open_button.clicked.connect(self.open_output)
        output_row.addWidget(self.open_button)
        layout.addLayout(output_row)
        self.reviewed = QCheckBox("목록의 모든 조직 영상을 검토했으며 영상 속 개인정보가 없음을 확인했습니다.")
        self.reviewed.setToolTip("사용자의 검토 확인을 기록합니다. 자동 개인정보 검출이나 인증을 의미하지 않습니다.")
        review_line = QHBoxLayout()
        review_line.addWidget(self.reviewed)
        review_info = QToolButton()
        review_info.setText("i")
        review_info.setObjectName("info")
        review_info.setAccessibleName("영상 검토 확인 설명")
        review_info.setToolTip("영상 검토 확인 설명 보기")
        review_info.clicked.connect(lambda: QMessageBox.information(self, "영상 검토 확인",
            "사용자가 목록의 모든 조직 영상을 직접 검토했다는 확인을 결과에 기록합니다. 자동 개인정보 검출이나 인증을 의미하지 않습니다.\n\n확인하지 않아도 내보낼 수 있으며 TIFF 결과는 영상 검토 필요 상태로 기록됩니다."))
        self.info_buttons["review"] = review_info
        review_line.addWidget(review_info)
        review_line.addStretch()
        layout.addLayout(review_line)
        actions = QHBoxLayout()
        self.inspect_button = QPushButton("전체 검사")
        self.inspect_button.clicked.connect(lambda: self.start("inspect"))
        self.copy_button = QPushButton("선택 항목 내보내기")
        self.copy_button.setObjectName("primary")
        self.copy_button.clicked.connect(lambda: self.start("copy"))
        self.cancel_button = QPushButton("중지")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        actions.addWidget(self.inspect_button)
        actions.addStretch()
        actions.addWidget(self.copy_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("준비 · SVS / NDPI / Philips 파일을 추가하세요.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.controls = [self.add_button, self.folder_button, self.sample_button,
                         self.clear_button, self.inspect_button, self.copy_button,
                         self.output_button, self.output, self.reviewed, self.options_box]
        self.export_image.toggled.connect(self.update_options)
        self.export_csv.toggled.connect(self.update_options)
        self.preserve_icc.toggled.connect(self.update_options)
        self.storage_choice.currentIndexChanged.connect(self.update_options)
        self.update_options()

    def storage_reasons(self):
        reasons = {mode: [] for _, mode in STORAGE_MODES}
        for path in self.paths:
            try:
                stat = path.stat()
                key = (path, stat.st_size, stat.st_mtime_ns)
            except OSError:
                key = (path, None, None)
            if key not in self._storage_support_cache:
                self._storage_support_cache[key] = storage_support(path)
            for mode, reason in self._storage_support_cache[key].items():
                if reason:
                    summary = path.suffix.upper() + ": " + reason
                    if summary not in reasons[mode]:
                        reasons[mode].append(summary)
        return reasons

    def show_storage_info(self):
        descriptions = {
            "native": "호환 SVS는 .svs, NDPI는 .ndpi로 저장하고 Philips는 .isyntax로 저장합니다(.i2syntax 포함). 조직 압축과 원본 피라미드 단계를 유지하며 식별 메타데이터와 라벨·매크로는 제외합니다.\nSVS·NDPI는 OpenSlide로 읽을 수 있습니다. Philips는 Philips 호환 도구가 필요합니다. NDPI는 단일 초점면의 호환 JPEG만 지원하며 ICC 보존은 지원하지 않습니다.",
            "preserve": "호환 SVS·NDPI·TIFF의 JPEG 데이터를 재사용해 TIFF로 저장합니다. 최대 해상도 조직 영상에는 추가 압축 손실이 없습니다. 파일 크기나 압축률이 같아지는 것은 아닙니다. 작은 축소 레벨은 새로 생성할 수 있습니다.",
            "jpeg2000": "모든 입력을 JPEG 2000 무손실 TIFF로 저장합니다. 읽어낸 최대 해상도 RGB 픽셀을 보존하며 기존 손실을 복구하지 않습니다. 원본보다 커지고 처리 시간이 길어질 수 있습니다. 축소 레벨은 리사이즈됩니다.",
        }
        reasons = self.storage_reasons()
        sections = []
        for label, mode in STORAGE_MODES:
            state = "사용 가능" if not reasons[mode] else "사용 불가: " + " / ".join(reasons[mode])
            sections.append(label + "\n" + descriptions[mode] + "\n현재 목록: " + (state if self.paths else "파일을 추가하세요."))
        QMessageBox.information(self, "저장 방식 · 지원 범위", "\n\n".join(sections) +
            "\n\n목록 전체에 적용 가능한 방식만 선택할 수 있습니다. 헤더로 사전 확인하며, 실제 읽기 지원과 압축 데이터의 유효성은 검사·내보내기에서 최종 확인합니다.")

    def update_options(self):
        images, csv = self.export_image.isChecked(), self.export_csv.isChecked()
        reasons = self.storage_reasons()
        self.storage_choice.blockSignals(True)
        for index, (label, mode) in enumerate(STORAGE_MODES):
            item = self.storage_choice.model().item(index)
            item.setEnabled(not reasons[mode])
            item.setText(label + (" (사용 불가)" if reasons[mode] else ""))
            item.setToolTip(" / ".join(reasons[mode]) or "현재 목록에 사용할 수 있습니다.")
        if reasons[self.storage_choice.currentData()]:
            index = next(i for i, (_, mode) in enumerate(STORAGE_MODES) if not reasons[mode])
            self.storage_choice.setCurrentIndex(index)
        self.storage_choice.blockSignals(False)
        self.include_filename.setEnabled(csv)
        self.preserve_mpp.setEnabled(images)
        self.preserve_icc.setEnabled(images)
        self.rename_output.setEnabled(images)
        self.storage_choice.setEnabled(images)
        self.structure.setEnabled(images)
        native = self.storage_choice.currentData() == "native"
        if images and native:
            self.structure.setCurrentIndex(self.structure.findData(True))
            self.structure.setEnabled(False)
            self.preserve_mpp.setChecked(True)
            self.preserve_mpp.setEnabled(False)
        self.copy_button.setEnabled(self.process is None and bool(self.paths) and (images or csv))
        descriptions = {
            "native": "원본 형식과 조직 압축 유지: SVS → .svs / NDPI → .ndpi / Philips → .isyntax",
            "preserve": "호환 JPEG 압축을 재사용해 .tiff로 저장합니다. 원본과 파일 크기가 같지는 않습니다.",
            "jpeg2000": "목록의 모든 파일을 무손실 TIFF로 저장합니다. 용량과 처리 시간이 크게 늘어날 수 있습니다.",
        }
        if not (images or csv):
            hint = "영상 또는 처리 내역을 하나 이상 선택하세요."
        elif not images:
            hint = "CSV 정보만 저장합니다. 영상 변환·압축·익명화 검증은 수행하지 않습니다."
        else:
            hint = descriptions[self.storage_choice.currentData()]
            hint += "\n원본 색상 프로파일: " + ("유지 (원본에 있는 경우)" if self.preserve_icc.isChecked() else "제외 · 표시 색상이 달라질 수 있음")
            blocked = [str(i + 1) + "번" for i, (_, mode) in enumerate(STORAGE_MODES) if reasons[mode]]
            if blocked:
                hint += "\n현재 목록: " + ", ".join(blocked) + " 사용 불가 · ⓘ에서 이유 확인"
            if native and any(p.suffix.lower() in {".isyntax", ".i2syntax"} for p in self.paths) and not self.preserve_icc.isChecked():
                hint += "\n색상 프로파일을 제외하면 보이는 색상이 달라질 수 있습니다. 세부 설정에서 유지할 수 있습니다."
        self.options_hint.setText(hint + "\n목록 전체를 같은 날짜·시간 폴더에 저장합니다.")

    def export_options(self):
        return {"export_image": self.export_image.isChecked(), "export_csv": self.export_csv.isChecked(),
                "rename_output": self.rename_output.isChecked(),
                "preserve_icc": self.preserve_icc.isChecked(),
                "include_filename": self.include_filename.isChecked(), "preserve_mpp": self.preserve_mpp.isChecked(),
                "compression": self.compression.currentData(), "pyramid": self.structure.currentData()}

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "WSI 파일 선택", str(ROOT / "data"),
                                               "WSI (" + " ".join("*" + e for e in sorted(EXTENSIONS)) + ");;모든 파일 (*)")
        self.add_paths(map(Path, files))

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "입력 폴더 선택")
        if folder:
            self.add_folder(Path(folder))

    def add_folder(self, folder):
        self.add_paths(p for p in folder.rglob("*") if p.is_file())

    def add_paths(self, paths):
        if self.process is not None:
            return
        for path in paths:
            path = path.resolve()
            if path in self.paths or path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            row = len(self.paths)
            self.paths.append(path)
            if hasattr(self, "reviewed"):
                self.reviewed.setChecked(False)
            self.table.insertRow(row)
            for column, value in enumerate((path.name, path.suffix[1:].upper(), f"{size / 1e9:.2f} GB", "대기")):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.status.setText(f"{len(self.paths)}개 파일 · 전체 검사를 시작할 수 있습니다.")
        self.update_options()
        self.empty_state.setVisible(not self.paths)
        if self.paths and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def clear(self):
        self.paths.clear()
        self._storage_support_cache.clear()
        self.results.clear()
        self.previews.clear()
        self.source_display_values.clear()
        self.table.setRowCount(0)
        self.empty_state.show()
        self.preview.clear()
        self.details.clear()
        self.audit_details.clear()
        self.audit_table.setRowCount(0)
        self.reviewed.setChecked(False)
        self.progress.setValue(0)
        self.status.setText("목록을 비웠습니다.")
        self.update_options()

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", self.output.text())
        if folder:
            self.output.setText(folder)

    def open_output(self):
        folder = getattr(self, "last_export_folder", Path(self.output.text()))
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))
        else:
            self.status.setText("아직 출력 폴더가 없습니다. 사본 생성 후 열 수 있습니다.")

    def start(self, action):
        if self.process is not None or not self.paths:
            return
        if action == "copy" and not (self.export_image.isChecked() or self.export_csv.isChecked()):
            self.update_options()
            return
        if action == "copy" and not self.output.text().strip():
            self.status.setText("출력 폴더를 선택하세요.")
            return
        self.update_options()
        self.action = action
        self.source_display_values.clear()
        self.audit_table.setRowCount(0)
        self.audit_details.clear()
        self.side_tabs.setCurrentIndex(1)
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") if action == "copy" else None
        self.queue = list(range(len(self.paths)))
        self.stop_requested = False
        self.completed = 0
        self.failed = 0
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        for control in self.controls:
            control.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.next_file()

    def next_file(self):
        if self.stop_requested or not self.queue:
            self.process = None
            for control in self.controls:
                control.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.update_options()
            if self.action == "copy" and self.completed:
                self.side_tabs.setCurrentIndex(2)
            prefix = "중지됨" if self.stop_requested else "작업 종료"
            self.status.setText(f"{prefix} · {self.completed}개 처리, {self.failed}개 실패" +
                               (" · 선택 항목의 저장 결과를 확인하세요." if self.action == "copy" else ""))
            return
        row = self.queue.pop(0)
        if self.action == "copy" and self.export_image.isChecked():
            self.source_display_values[row] = source_display_snapshot(self.paths[row])
        self.active_row = row
        self.had_result = False
        self.buffer = b""
        self.cancel_file = STATE_ROOT / "cancel" / (uuid.uuid4().hex + ".cancel")
        if FROZEN:
            self.cancel_file.parent.mkdir(parents=True, exist_ok=True)
            self.job_file = self.cancel_file.with_suffix(".job.json")
            self.events_file = self.cancel_file.with_suffix(".events.jsonl")
            self.event_offset = 0
        self.table.item(row, 3).setText("처리 중")
        self.process = QProcess(self)
        self.process.setProgram(sys.executable if FROZEN else
                                (str(Path(sys.executable).with_name("python.exe")) if sys.platform == "win32" else sys.executable))
        self.process.setArguments(["--worker", "--job-file", str(self.job_file), "--events-file", str(self.events_file)]
                                  if FROZEN else [str(ROOT / "app.py"), "--worker"])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        job = {"source": str(self.paths[row]), "action": self.action,
               "output": self.output.text(), "pixels_reviewed": self.reviewed.isChecked(),
               "run_id": self.run_id,
               "cancel_file": str(self.cancel_file)}
        job.update(self.export_options())
        if FROZEN:
            self.job_file.write_text(json.dumps(job) + "\n", encoding="utf-8")
            self.event_timer.start()
        self.process.start()
        if not FROZEN:
            self.process.write((json.dumps(job) + "\n").encode("utf-8"))
            self.process.closeWriteChannel()

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.handle({"kind": "error", "message": "작업 프로세스를 시작하지 못했습니다."})
            self.finished(1, QProcess.NormalExit)

    def read_output(self):
        if self.process is None:
            return
        if FROZEN:
            if not self.events_file.exists():
                return
            with self.events_file.open("rb") as stream:
                stream.seek(self.event_offset)
                self.buffer += stream.read()
                self.event_offset = stream.tell()
        else:
            self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                self.handle(json.loads(line))
            except (ValueError, KeyError):
                self.status.setText("작업 응답을 해석하지 못했습니다.")

    def handle(self, event):
        row = self.active_row
        if event["kind"] == "progress":
            self.status.setText(f"{row + 1}/{len(self.paths)} · {event['message']}")
            if "percent" in event:
                self.progress.setValue(int(1000 * (self.completed + event["percent"] / 100) / len(self.paths)))
        elif event["kind"] == "cancelled":
            self.had_result = True
            self.table.item(row, 3).setText("중지됨")
            self.results[row] = {"error": event["message"]}
            self.show_selection()
        elif event["kind"] == "error":
            self.had_result = True
            self.failed += 1
            self.table.item(row, 3).setText("실패")
            self.results[row] = {"error": event["message"]}
            self.show_selection()
        elif event["kind"] == "result":
            self.had_result = True
            data = event["data"]
            self.results[row] = data
            if event["action"] == "copy":
                self.last_export_folder = Path(data["directory"])
                state = ("저장 완료 · 영상 확인됨" if data["report"]["pixel_review_asserted_by_caller"]
                         else "저장 완료 · 영상 검토 필요")
                if data["report"]["format"] == "csv-only":
                    state = "CSV 완료 · 영상 변환 없음"
            else:
                state = "읽기 검사 통과" if not data["errors"] else "검사 실패"
                if data["errors"]:
                    self.failed += 1
                if event.get("preview"):
                    self.previews[row] = base64.b64decode(event["preview"])
            self.table.item(row, 3).setText(state)
            self.show_selection()

    def finished(self, code, exit_status):
        self.event_timer.stop()
        self.read_output()
        if not self.had_result:
            self.handle({"kind": "error", "message": f"작업 프로세스가 종료되었습니다. (코드 {code})"})
        self.completed += 1
        self.progress.setValue(int(1000 * self.completed / len(self.paths)))
        self.cancel_file.unlink(missing_ok=True)
        if FROZEN:
            self.job_file.unlink(missing_ok=True)
            self.events_file.unlink(missing_ok=True)
        old = self.process
        self.process = None
        old.deleteLater()
        self.next_file()

    def populate_audit(self, report, row):
        audit = report.get("anonymization_audit")
        if not audit:
            return
        names, states = audit_labels()
        source_values = self.source_display_values.get(row, {})
        descriptions = {"present": "있음", "absent": "없음", "unknown": "비교 불가",
                        "source_filename": "원본 파일명", "not_assessed": "자동 분석하지 않음",
                        "not_counted": "존재 여부 미집계"}
        self.audit_notice.setText("원본 값은 화면에만 표시합니다. 항목을 선택하면 아래에서 자세히 볼 수 있습니다.\n"
                                 + source_values.get("_notice", "'없음'은 해당 TIFF 태그/OpenSlide 항목 기준입니다."))
        for entry in audit["entries"]:
            name = entry["item"]
            original = descriptions.get(entry.get("before"), "이전 결과 · 원본 상태 미기록")
            if entry.get("before") in ("present", "source_filename") and name in source_values:
                original = source_values[name]
            outcome = states[entry["status"]]
            if entry.get("after") == "absent":
                outcome = "없음 · 제거 확인" if entry["status"] == "removed" else "없음"
            if entry.get("after") == "technical_metadata":
                outcome = "기술 정보로 재작성\n" + json.dumps(report.get("technical_metadata", {}), ensure_ascii=False, indent=2)
            if name == "filename" and report.get("output_path"):
                outcome += "\n" + Path(report["output_path"]).name
            if name == "csv_filename":
                if entry.get("after") == "source_filename" and name in source_values:
                    outcome += "\n" + source_values[name]
                elif entry.get("after") == "empty":
                    outcome = "빈칸으로 저장"
            index = self.audit_table.rowCount()
            self.audit_table.insertRow(index)
            for column, value in enumerate((names[name], original, outcome)):
                cell = QTableWidgetItem(value.replace("\n", " ")[:100])
                cell.setData(Qt.UserRole, value)
                self.audit_table.setItem(index, column, cell)
        known_codes = {entry.get("tag_code") for entry in audit["entries"]}
        extra_codes = [code for code in audit.get("removed_tag_codes", []) if code not in known_codes]
        if extra_codes:
            index = self.audit_table.rowCount()
            self.audit_table.insertRow(index)
            for column, value in enumerate(("추가 TIFF 태그", ", ".join(map(str, extra_codes)), "출력에서 제거 확인 (태그 번호 기준)")):
                cell = QTableWidgetItem(value[:100])
                cell.setData(Qt.UserRole, value)
                self.audit_table.setItem(index, column, cell)
        if self.audit_table.rowCount():
            self.audit_table.selectRow(0)

    def show_audit_row(self):
        row = self.audit_table.currentRow()
        if row < 0 or any(self.audit_table.item(row, col) is None for col in range(3)):
            self.audit_details.clear()
            return
        name, original, outcome = [self.audit_table.item(row, col).data(Qt.UserRole) for col in range(3)]
        self.audit_details.setPlainText(f"{name}\n\n원본\n{original}\n\n익명화 결과\n{outcome}")

    def show_selection(self):
        row = self.table.currentRow()
        self.audit_details.clear()
        self.audit_table.setRowCount(0)
        self.preview.clear()
        if row in self.previews:
            pixmap = QPixmap()
            pixmap.loadFromData(self.previews[row])
            self.preview.setPixmap(pixmap.scaled(380, 235, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("검사하면 조직 썸네일이 표시됩니다.")
        data = self.results.get(row)
        if data is None:
            self.details.setPlainText("아직 검사하지 않은 파일입니다.")
            return
        if "error" in data:
            self.details.setPlainText(data["error"])
            return
        report = data.get("report", data)
        if "report" in data:
            if report["format"] == "csv-only":
                self.audit_details.setPlainText("CSV 전용 저장: 영상 익명화·제거 검증을 수행하지 않았습니다.")
                self.details.setPlainText("\n".join(["슬라이드 정보 CSV 저장 완료", "영상 변환·픽셀 검증은 수행하지 않았습니다.",
                    *technical_lines(report.get("technical_metadata", {})),
                    f"영상 크기: {report['level_dimensions'][0]}", f"저장 위치: {data['directory']}",
                    f"기술 정보: {Path(data['csv_path']).name}"]))
                return
            self.details.setPlainText("\n".join([
                "형식: " + ({"philips-isyntax": "Philips iSyntax · 원본 압축 유지", "aperio-svs": "Aperio SVS · 원본 압축 유지", "hamamatsu-ndpi": "Hamamatsu NDPI · 원본 압축 유지"}.get(report["format"], "표준 피라미드 TIFF" if report.get("pyramid") else "단일 해상도 TIFF")), f"영상 크기: {report['level_dimensions'][0]}",
                f"영상 레벨 수: {len(report['level_dimensions'])}",
                *technical_lines(report.get("technical_metadata", {})),
                f"원본 압축 유지 레벨: {report.get('preserved_levels', 0)} · 추가 생성 레벨: {report.get('generated_levels', 0)}",
                "이 프로그램 또는 Philips 호환 도구로 열 수 있습니다." if report["format"] == "philips-isyntax" else "OpenSlide로 열 수 있는 영상입니다.",
                *((["Philips SDK 표시 RGB · 원시 내부 샘플과 다릅니다.",
                    f"SDK 표시 영역 시작 좌표: {report.get('philips_display_origin')}"])
                  if report.get("source_vendor") == "philips" and report["format"] != "philips-isyntax" and "philips_display_origin" in report else []),
                "원본 개인정보 태그·라벨·매크로 제외; ICC는 아래 상태 참조",
                "압축: " + ({"philips-native-preserved": "Philips 원본 압축 유지", "jpeg2000-lossless": "JPEG 2000 무손실", "jpeg-preserved": "원본 JPEG 유지", "deflate-lossless": "무손실 Deflate", "jpeg-reencoded-q90": "JPEG 재압축 Q90 (손실)"}.get(report["compression"], report["compression"])),
                (f"전체 JPEG 데이터 일치 · {report['verified_tiles']:,}개 구간 인덱스 재생성 · 모든 레벨의 표본 영역 검사" if report["format"] == "hamamatsu-ndpi" else f"전체 압축 블록 일치: {report['verified_tiles']:,}개 · 영상 읽기는 일부 영역 검사" if report["format"] == "philips-isyntax" else f"전체 타일 검증: {report['verified_tiles']:,}개 통과"),
                "영상 개인정보 검토: " + ("사용자가 확인함" if report["pixel_review_asserted_by_caller"] else "추가 검토 필요"),
                "", (f"ICC: 원본 포함 ({report.get('icc_profile_bytes', 0):,} bytes) · ICC 내부 정보 별도 검토 필요"
                       if report.get("icc_profile_copied") else "ICC: 미포함 (원본에 없거나 제외 선택)"),
                "", f"저장 위치: {data['directory']}",
                "기술 정보: " + (Path(data['csv_path']).name if data.get("csv_path") else "CSV 저장 안 함")]))
            self.populate_audit(report, row)
            return
        slide = report.get("openslide", {})
        if slide.get("thumbnail_skip_reason"):
            self.preview.setText("대용량 단일 영상은 썸네일을 생략합니다.\n메모리 사용을 제한하기 위한 동작입니다.")
        lines = [f"영상 크기: {slide.get('dimensions', '-')}",
                 *technical_lines(slide.get("technical_metadata", {})),
                 f"영상 레벨: {len(slide.get('level_dimensions', []))}",
                 f"부속 이미지: {', '.join(slide.get('associated_images', {})) or 'OpenSlide 목록 없음'}",
                 f"검사 영역: {len(slide.get('decoded_regions', []))}개"]
        lines += ["", "전체 개인정보 검사는 아닙니다.", "", "메타데이터 항목 (값은 표시하지 않음)",
                  *slide.get("property_keys", [])]
        if report.get("errors"):
            lines += ["", "오류: " + str(report["errors"])]
        self.details.setPlainText("\n".join(lines))

    def cancel(self):
        self.stop_requested = True
        self.cancel_button.setEnabled(False)
        if self.action == "copy":
            self.cancel_file.parent.mkdir(parents=True, exist_ok=True)
            self.cancel_file.touch()
            self.status.setText("중지를 요청했습니다. 현재 타일 처리 후 임시 파일을 정리합니다.")
        else:
            self.status.setText("현재 파일의 검사가 끝나면 중지합니다.")

    def closeEvent(self, event):
        if self.process is not None:
            self.cancel()
            self.status.setText("현재 파일 완료 후 닫을 수 있습니다. 중지를 요청했습니다.")
            event.ignore()
        else:
            self.source_display_values.clear()
            self.audit_table.setRowCount(0)
            self.audit_details.clear()
            event.accept()

    def dragEnterEvent(self, event):
        if self.process is None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    self.add_folder(path)
                elif path.is_file():
                    self.add_paths([path])


STYLE = """
QWidget { background: #f5f6fb; color: #26314a; font-family: 'Malgun Gothic'; font-size: 13px; }
QLabel { background: transparent; }
QLabel#subtitle { color: #6a748a; font-size: 12px; }
QLabel#notice { background: #edf0ff; color: #576083; padding: 10px 14px; border-radius: 8px; font-size: 12px; }
QLabel#hint, QLabel#emptyState { color: #8a93a6; font-size: 12px; }
QPushButton { background: white; border: 1px solid #dce0ec; border-radius: 7px; padding: 9px 16px; font-weight: 500; }
QPushButton:hover { border-color: #8c81ed; background: #f3f0ff; }
QPushButton:pressed { background: #e9e4ff; }
QPushButton:disabled { color: #a1a7b6; background: #eef0f5; }
QPushButton#primary { background: #6250db; color: white; border: 1px solid #6250db; font-weight: bold; }
QPushButton#primary:hover { background: #5040be; }
QPushButton#primary:disabled { background: #b8b0e3; border-color: #b8b0e3; }
QGroupBox { background: white; border: none; margin-top: 0; padding-top: 4px; }
QGroupBox::title { subcontrol-origin: margin; left: 18px; padding: 0 4px; color: #586582; font-weight: bold; }
QGroupBox QCheckBox, QGroupBox QToolButton { background: white; }
QCheckBox { spacing: 9px; padding: 3px 0; }
QCheckBox:disabled { color: #a1a7b6; }
QToolButton#info { color: #7a74a0; border: 1px solid #dce0ec; border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; font-size: 11px; font-weight: bold; }
QToolButton#info:hover { background: #eeeaff; color: #6250db; }
QComboBox { background: white; padding: 8px 10px; border: 1px solid #dce0ec; border-radius: 5px; min-width: 230px; }
QComboBox QAbstractItemView::item:disabled { color: #a1a7b6; }
QTableWidget, QTextEdit, QLineEdit { background: white; border: 1px solid #e0e4ef; border-radius: 8px; padding: 8px; selection-background-color: #eeeaff; selection-color: #3c3279; }
QTableWidget { alternate-background-color: #fafbfe; }
QHeaderView::section { background: #eef0f7; color: #64708a; padding: 12px 8px; border: none; font-weight: bold; font-size: 12px; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #f0f2f7; }
QTableWidget::item:selected { background: #eeebff; color: #3c3279; }
QTableWidget::item:focus { outline: none; }
QLabel#preview { background: white; border: 1px solid #e0e4ef; border-radius: 8px; color: #8a93a6; }
QTabWidget::pane { background: white; border: 1px solid #e0e4ef; border-radius: 8px; }
QTabBar::tab { background: transparent; padding: 12px 24px; color: #858da0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #6250db; border-bottom: 2px solid #6250db; font-weight: bold; }
QScrollArea { background: white; border: none; }
QSplitter::handle { background: transparent; width: 14px; }
QProgressBar { border: none; background: #e7e9f2; border-radius: 4px; min-height: 8px; max-height: 8px; color: transparent; }
QProgressBar::chunk { background: #8070e8; border-radius: 4px; }
QScrollBar:vertical { background: #f4f5fa; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #ced3e2; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def main():
    configure_qt()
    app = QApplication(sys.argv)
    app.setApplicationName("MeDIAuto Anonymization")
    app.setWindowIcon(QIcon(str(ASSET_ROOT / "icon.png")))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()
