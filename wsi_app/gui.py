from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QProcess, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QTextEdit, QLineEdit, QProgressBar, QMessageBox,
    QAbstractItemView, QCheckBox)

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = {".svs", ".ndpi", ".tif", ".tiff", ".mrxs", ".scn", ".vms", ".vmu", ".bif", ".svslide", ".dcm", ".czi"}


def configure_qt():
    # yslee contains a qt.conf for another Qt installation. Scope this fix to us.
    plugins = Path(PySide6.__file__).resolve().parent / "plugins"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
    QCoreApplication.setLibraryPaths([str(plugins)])


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WSI Anonymization · Clean TIFF Export")
        self.resize(1240, 820)
        self.setMinimumSize(950, 680)
        self.paths, self.results, self.previews = [], {}, {}
        self.queue = []
        self.process = None
        self.buffer = b""
        self.had_result = False
        self.stop_requested = False
        self.active_row = None
        self.setAcceptDrops(True)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("WSI Anonymization")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("WSI → TIFF  |  조직 영상만 읽어 새로운 무손실 피라미드 TIFF를 만듭니다."))
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
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("출력 폴더"))
        self.output = QLineEdit(str(ROOT / "output"))
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
        layout.addWidget(self.reviewed)
        actions = QHBoxLayout()
        self.inspect_button = QPushButton("전체 검사")
        self.inspect_button.clicked.connect(lambda: self.start("inspect"))
        self.copy_button = QPushButton("비식별 TIFF 내보내기")
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
                         self.output_button, self.output, self.reviewed]

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
        self.status.setText("목록을 비웠습니다.")

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", self.output.text())
        if folder:
            self.output.setText(folder)

    def open_output(self):
        folder = Path(self.output.text())
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))
        else:
            self.status.setText("아직 출력 폴더가 없습니다. 사본 생성 후 열 수 있습니다.")

    def start(self, action):
        if self.process is not None or not self.paths:
            return
        if action == "copy" and not self.output.text().strip():
            self.status.setText("출력 폴더를 선택하세요.")
            return
        self.action = action
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
            prefix = "중지됨" if self.stop_requested else "작업 종료"
            self.status.setText(f"{prefix} · {self.completed}개 처리, {self.failed}개 실패" +
                               (" · TIFF 저장 및 검증 결과를 확인하세요." if self.action == "copy" else ""))
            return
        row = self.queue.pop(0)
        self.active_row = row
        self.had_result = False
        self.buffer = b""
        self.cancel_file = ROOT / "artifacts" / "cancel" / (uuid.uuid4().hex + ".cancel")
        self.table.item(row, 3).setText("처리 중")
        self.process = QProcess(self)
        self.process.setProgram(str(Path(sys.executable).with_name("python.exe"))
                                if sys.platform == "win32" else sys.executable)
        self.process.setArguments([str(ROOT / "app.py"), "--worker"])
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.start()
        job = {"source": str(self.paths[row]), "action": self.action,
               "output": self.output.text(), "pixels_reviewed": self.reviewed.isChecked(),
               "cancel_file": str(self.cancel_file)}
        self.process.write((json.dumps(job) + "\n").encode("utf-8"))
        self.process.closeWriteChannel()

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.handle({"kind": "error", "message": "작업 프로세스를 시작하지 못했습니다."})
            self.finished(1, QProcess.NormalExit)

    def read_output(self):
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
                state = ("TIFF 완료 · 영상 확인됨" if data["report"]["pixel_review_asserted_by_caller"]
                         else "TIFF 완료 · 영상 검토 필요")
            else:
                state = "읽기 검사 통과" if not data["errors"] else "검사 실패"
                if data["errors"]:
                    self.failed += 1
                if event.get("preview"):
                    self.previews[row] = base64.b64decode(event["preview"])
            self.table.item(row, 3).setText(state)
            self.show_selection()

    def finished(self, code, exit_status):
        self.read_output()
        if not self.had_result:
            self.handle({"kind": "error", "message": f"작업 프로세스가 종료되었습니다. (코드 {code})"})
        self.completed += 1
        self.progress.setValue(int(1000 * self.completed / len(self.paths)))
        self.cancel_file.unlink(missing_ok=True)
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
            self.details.setPlainText("\n".join([
                "형식: 무손실 피라미드 BigTIFF", f"영상 크기: {report['level_dimensions'][0]}",
                f"영상 레벨: {len(report['level_dimensions'])}",
                "메타데이터·부속 이미지: 원본에서 복사하지 않음",
                f"전체 타일 픽셀 일치 검증: {report['verified_tiles']:,}개 통과",
                "영상 개인정보 검토: " + ("사용자가 확인함" if report["pixel_review_asserted_by_caller"] else "추가 검토 필요"),
                "", "원본 ICC는 제외되므로 색상 관리 뷰어에서 표시가 달라질 수 있습니다.",
                "", f"저장 위치: {data['directory']}"]))
            return
        slide = report.get("openslide", {})
        lines = [f"영상 크기: {slide.get('dimensions', '-')}",
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
