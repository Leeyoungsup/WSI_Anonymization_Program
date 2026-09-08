from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QProcess, Qt, QUrl, QStandardPaths, QTimer
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QTextEdit, QLineEdit, QProgressBar, QMessageBox,
    QAbstractItemView, QCheckBox, QGroupBox, QGridLayout, QComboBox, QToolButton)

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WSI_Anonymization" if FROZEN else ROOT / "artifacts"
EXTENSIONS = {".svs", ".ndpi", ".tif", ".tiff", ".mrxs", ".scn", ".vms", ".vmu", ".bif", ".svslide", ".dcm", ".czi"}


def configure_qt():
    # yslee contains a qt.conf for another Qt installation. Scope this fix to us.
    plugins = Path(PySide6.__file__).resolve().parent / "plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    QCoreApplication.setLibraryPaths([str(plugins)])


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
        self.setWindowTitle("WSI Anonymization 1.3.0 · Pyramidal TIFF + CSV")
        self.resize(1240, 980)
        self.setMinimumSize(1050, 850)
        self.paths, self.results, self.previews = [], {}, {}
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
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("WSI Anonymization")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("WSI Export  |  내보낼 항목을 선택하고 날짜·시간 폴더에 저장합니다."))
        notice = QLabel("원본 메타데이터·라벨·매크로는 내보내지 않습니다. 조직 영상 안에 적힌 개인정보는 별도 검토가 필요합니다.")
        notice.setObjectName("notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("파일 추가")
        self.folder_button = QPushButton("폴더 추가")
        self.sample_button = QPushButton("샘플 불러오기")
        self.clear_button = QPushButton("목록 비우기")
        for button in (self.add_button, self.folder_button, self.sample_button, self.clear_button):
            toolbar.addWidget(button)
        toolbar.addStretch()
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
        self.table.setColumnWidth(1, 65)
        self.table.setColumnWidth(2, 85)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.show_selection)
        splitter.addWidget(self.table)
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 0, 0, 0)
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
        splitter.addWidget(panel)
        splitter.setSizes([710, 430])
        layout.addWidget(splitter, 1)
        self.options_box = QGroupBox("내보내기 옵션")
        options = QGridLayout(self.options_box)
        options.setHorizontalSpacing(32)
        self.info_buttons = {}

        def option(widget, key, title, explanation, row, column):
            line = QHBoxLayout()
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
            options.addLayout(line, row, column)

        self.export_image = QCheckBox("TIFF 영상")
        self.export_csv = QCheckBox("슬라이드 정보 CSV")
        self.include_filename = QCheckBox("CSV에 원본 파일명 포함")
        self.rename_output = QCheckBox("출력 파일명을 익명 이름으로 변경")
        self.rename_output.setChecked(True)
        self.preserve_mpp = QCheckBox("TIFF에 MPP 보존")
        self.preserve_icc = QCheckBox("원본 ICC 포함 (별도 검토 필요)")
        for control in (self.export_image, self.export_csv, self.include_filename, self.preserve_mpp):
            control.setChecked(True)
        option(self.export_image, "image", "TIFF 영상", "조직 영상을 익명 파일명의 TIFF로 저장합니다. 기본값은 표준 피라미드 TIFF이며 라벨과 매크로는 포함하지 않습니다.\n\n해제하면 TIFF 파일을 만들지 않고 선택한 CSV만 저장합니다.", 0, 0)
        option(self.export_csv, "csv", "슬라이드 정보 CSV", "MPP(픽셀의 실제 크기), 영상 크기, 배율, 입력 형식, 파일 크기와 처리 결과를 CSV에 기록합니다. 환자명·검체 ID·스캔 날짜 등 원본 개인정보 태그는 포함하지 않습니다.\n\nCSV만 선택하면 영상을 변환하거나 픽셀 검증하지 않습니다.", 0, 1)
        option(self.include_filename, "filename", "원본 파일명 포함", "CSV에 원본 파일명을 기록하여 결과와 대응시킵니다. 파일명 자체에 이름이나 환자 ID가 있으면 CSV에도 남습니다.\n\n해제하면 original_filename 열을 빈칸으로 저장합니다. TIFF 내부에는 원본 파일명을 기록하지 않습니다.", 1, 1)
        option(self.preserve_mpp, "mpp", "기술 정보와 MPP 보존", "Magnification: 원본 대물렌즈 배율입니다.\nPixel Size: 전체 영상의 가로 × 세로 픽셀 수입니다.\nMPP: 픽셀 하나의 실제 길이(µm/pixel, X/Y)입니다.\nPhysical Size: 픽셀 수 × MPP로 계산한 전체 영상 영역의 크기(mm)이며 조직만의 크기가 아닙니다.\n\n기술 정보는 숫자만 TIFF에 새로 기록합니다. 원본에 없는 배율·MPP는 추정하지 않습니다. 외부 뷰어의 배율 표시는 뷰어 지원에 따라 다릅니다.\n\nMPP 보존을 해제하면 TIFF의 MPP와 Physical Size를 생략합니다. CSV에는 원본 기술 정보를 기록합니다.", 1, 0)
        self.compression = QComboBox()
        self.compression.addItem("원본 JPEG 압축 유지", "preserve")
        self.compression.addItem("무손실 Deflate로 재저장", "lossless")
        option(self.compression, "compression", "압축 방식", "원본 JPEG 압축 유지: 최대 해상도 영상을 재압축하지 않습니다. 호환되는 원본 축소 레벨도 재사용하고, 추가로 필요한 작은 레벨만 JPEG로 생성합니다.\n\n무손실 Deflate: RGB를 무손실 저장합니다. 파일 크기가 크게 늘 수 있습니다. 추가 축소 레벨도 Deflate로 저장합니다.", 2, 0)
        option(QLabel("개인정보 태그 제거 · ICC 포함 시 별도 검토"), "privacy", "익명화 범위", "TIFF에서 원본 개인정보 태그, 라벨·매크로·원본 썸네일과 JPEG APP/COM 부가정보를 제외합니다. ICC는 기본 제외이며 원본 ICC 포함을 선택하면 프로파일 내부 정보도 함께 복사되어 별도 검토가 필요합니다.\n\n조직 영상에 직접 찍힌 이름이나 식별자는 자동으로 지워지지 않습니다. 아래 검토 확인은 사용자의 확인 기록이며 자동 익명화 인증이 아닙니다.", 2, 1)
        self.structure = QComboBox()
        self.structure.addItem("표준 피라미드 TIFF", True)
        self.structure.addItem("단일 해상도 TIFF", False)
        option(self.structure, "structure", "출력 구조", "표준 피라미드 TIFF: 최대 해상도와 조직 축소 레벨을 함께 저장합니다. OpenSlide의 get_thumbnail()과 확대·축소 보기에 사용할 수 있습니다.\n\n단일 해상도 TIFF: 최대 해상도만 저장합니다. 큰 영상의 get_thumbnail()은 많은 메모리가 필요할 수 있습니다.\n\n두 구조 모두 개인정보 메타데이터 제거를 적용합니다. 영상에 직접 찍힌 식별자는 별도 검토가 필요합니다.", 3, 0)
        self.options_hint = QLabel()
        option(self.rename_output, "rename", "출력 파일명 변경", "체크: anonymous_<임의 ID>.tiff로 저장합니다.\n해제: 원본 이름을 유지하고 확장자만 .tiff로 바꿉니다. 같은 이름이 있으면 _2, _3 등을 붙이며 기존 파일을 덮어쓰지 않습니다.\n\n원본 이름에 환자명·ID가 있으면 해제 시 결과 파일명에도 남습니다. TIFF 내부 메타데이터 제거는 그대로 적용합니다. CSV의 원본 파일명 포함 옵션과는 별개입니다.", 3, 1)
        self.options_hint.setWordWrap(True)
        option(self.preserve_icc, "icc", "ICC 색상 프로파일", "체크하면 원본 조직 영상의 ICC를 TIFF 기본 페이지에 그대로 저장합니다. 색상 변환이나 영상 재압축을 하지 않으며 OpenSlide color_profile로 읽을 수 있습니다.\n\nICC 내부 설명·제조사 정보 등도 그대로 복사되므로 개인정보가 없는지 별도 검토가 필요합니다. 결과는 ICC 검토 필요로 표시합니다. 원본에 ICC가 없으면 추가하지 않습니다. 기본값은 제외입니다.", 4, 0)
        options.addWidget(self.options_hint, 5, 0, 1, 2)
        layout.addWidget(self.options_box)
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
        actions.addWidget(self.copy_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.status = QLabel("준비 · SVS / NDPI 파일을 추가하세요.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.controls = [self.add_button, self.folder_button, self.sample_button,
                         self.clear_button, self.inspect_button, self.copy_button,
                         self.output_button, self.output, self.reviewed, self.options_box]
        self.export_image.toggled.connect(self.update_options)
        self.export_csv.toggled.connect(self.update_options)
        self.update_options()

    def update_options(self):
        images, csv = self.export_image.isChecked(), self.export_csv.isChecked()
        self.include_filename.setEnabled(csv)
        self.preserve_mpp.setEnabled(images)
        self.preserve_icc.setEnabled(images)
        self.rename_output.setEnabled(images)
        self.compression.setEnabled(images)
        self.structure.setEnabled(images)
        self.copy_button.setEnabled(self.process is None and (images or csv))
        self.options_hint.setText("TIFF 또는 CSV를 하나 이상 선택하세요." if not (images or csv)
                                  else "선택한 항목은 같은 날짜·시간 폴더에 저장됩니다. i 버튼에서 설명을 확인하세요.")

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
        if self.paths and self.table.currentRow() < 0:
            self.table.selectRow(0)

    def clear(self):
        self.paths.clear()
        self.results.clear()
        self.previews.clear()
        self.table.setRowCount(0)
        self.preview.clear()
        self.details.clear()
        self.reviewed.setChecked(False)
        self.progress.setValue(0)
        self.status.setText("목록을 비웠습니다.")

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
        self.action = action
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
            prefix = "중지됨" if self.stop_requested else "작업 종료"
            self.status.setText(f"{prefix} · {self.completed}개 처리, {self.failed}개 실패" +
                               (" · 선택 항목의 저장 결과를 확인하세요." if self.action == "copy" else ""))
            return
        row = self.queue.pop(0)
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
                state = ("TIFF 완료 · 영상 확인됨" if data["report"]["pixel_review_asserted_by_caller"]
                         else "TIFF 완료 · 영상 검토 필요")
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

    def show_selection(self):
        row = self.table.currentRow()
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
                self.details.setPlainText("\n".join(["슬라이드 정보 CSV 저장 완료", "영상 변환·픽셀 검증은 수행하지 않았습니다.",
                    *technical_lines(report.get("technical_metadata", {})),
                    f"영상 크기: {report['level_dimensions'][0]}", f"저장 위치: {data['directory']}",
                    f"기술 정보: {Path(data['csv_path']).name}"]))
                return
            self.details.setPlainText("\n".join([
                "형식: " + ("표준 피라미드 TIFF" if report.get("pyramid") else "단일 해상도 TIFF"), f"영상 크기: {report['level_dimensions'][0]}",
                f"영상 레벨 수: {len(report['level_dimensions'])}",
                *technical_lines(report.get("technical_metadata", {})),
                f"원본 압축 유지 레벨: {report.get('preserved_levels', 0)} · 추가 생성 레벨: {report.get('generated_levels', 0)}",
                "출력 OpenSlide Vendor: aperio (호환 형식)",
                "원본 개인정보 태그·라벨·매크로 제외; ICC는 아래 상태 참조",
                "압축: " + ("원본 JPEG 유지" if report["compression"] == "jpeg-preserved" else "무손실 Deflate"),
                f"전체 타일 검증: {report['verified_tiles']:,}개 통과",
                "영상 개인정보 검토: " + ("사용자가 확인함" if report["pixel_review_asserted_by_caller"] else "추가 검토 필요"),
                "", (f"ICC: 원본 포함 ({report.get('icc_profile_bytes', 0):,} bytes) · ICC 내부 정보 별도 검토 필요"
                       if report.get("icc_profile_copied") else "ICC: 미포함 (원본에 없거나 제외 선택)"),
                "", f"저장 위치: {data['directory']}",
                "기술 정보: " + (Path(data['csv_path']).name if data.get("csv_path") else "CSV 저장 안 함")]))
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
QWidget { background: #f3f6fa; color: #1d2c42; font-family: 'Malgun Gothic'; font-size: 13px; }
QLabel#title { font-size: 30px; font-weight: bold; color: #12354a; }
QLabel#notice { background: #fff4db; color: #715215; padding: 12px; border-radius: 8px; }
QPushButton { background: white; border: 1px solid #ced8e3; border-radius: 6px; padding: 10px 16px; }
QPushButton:hover { background: #e5eff5; }
QPushButton:disabled { color: #93a0ad; background: #edf0f3; }
QPushButton#primary { background: #087e83; color: white; border: none; }
QPushButton#primary:disabled { background: #91b8ba; }
QGroupBox { border: 1px solid #ced8e3; border-radius: 8px; margin-top: 12px; padding: 14px 10px 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; font-weight: bold; }
QToolButton#info { background: #e0f0f0; color: #087e83; border: 1px solid #9ac6c7; border-radius: 10px; min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px; font-weight: bold; }
QComboBox { background: white; padding: 5px; border: 1px solid #ced8e3; border-radius: 4px; }
QTableWidget, QTextEdit, QLineEdit { background: white; border: 1px solid #dce3ec; border-radius: 6px; padding: 6px; }
QHeaderView::section { background: #e7edf4; padding: 10px; border: none; font-weight: bold; }
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected { background: #d8eeef; color: #12354a; }
QLabel#preview { background: white; border: 1px solid #dce3ec; border-radius: 8px; }
QProgressBar { border: none; background: #e1e7ee; border-radius: 5px; height: 18px; text-align: center; }
QProgressBar::chunk { background: #28aaa1; border-radius: 5px; }
"""


def main():
    configure_qt()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()
