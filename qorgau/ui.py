from dataclasses import asdict
from pathlib import Path
import time
import cv2
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from .config import Settings, data_root
from .engine import Event, EventEngine, Observation, TITLES, risk_score
from .reports import REVIEWS, STATUSES, clock, export_report, local_time
from .security import SecurityMonitor
from .worker import CameraWorker


STYLE = """
QWidget {font-family:'Segoe UI';font-size:13px;color:#243c3d;}
QMainWindow, #content {background:#edf3f0;}
#sidebar {background:#132c2c;} #sidebar QLabel {color:#a8c3bc;}
#brand {color:#e8fff6;font-size:23px;font-weight:800;letter-spacing:2px;}
#sideTag {color:#67ddb0;font-size:10px;font-weight:700;letter-spacing:3px;}
#sidebar QPushButton {background:transparent;color:#c3d7d1;text-align:left;padding:13px 18px;border:0;border-radius:8px;}
#sidebar QPushButton:checked {background:#2a4743;color:#9ff0cb;font-weight:700;}
#sidebar QPushButton:hover {background:#23403c;}
#title {font-size:28px;font-weight:700;color:#142e2b;}
#subtitle, #muted {color:#667c75;}
#card {background:white;border:1px solid #dae5df;border-radius:14px;}
#cardTitle {font-size:15px;font-weight:700;}
#metricValue {font-size:26px;font-weight:700;color:#143e32;}
#badge {background:#dcefe4;color:#186645;border-radius:10px;padding:8px 14px;font-weight:600;}
#status {color:#355c4c;background:#e1eee5;border:1px solid #cddfd1;border-radius:8px;padding:10px;}
#banner {background:#fff0ce;color:#71531b;border-radius:8px;padding:9px;}
QPushButton {background:#edf3ef;border:1px solid #d6e1db;border-radius:8px;padding:9px 13px;font-weight:600;}
QPushButton:hover {background:#e2ece6;} QPushButton:disabled {color:#91a49a;background:#f1f4f2;}
#primary {background:#177d5e;color:white;border:0;} #primary:hover {background:#11694e;}
#primary:disabled {background:#dce5df;color:#879b90;}
#danger {color:#a84738;background:#fceee9;border:1px solid #edd1c8;}
#danger:disabled {color:#acaaa3;background:#f2f3f0;border:1px solid #e1e5df;}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit {background:#f8faf8;border:1px solid #d6e1db;border-radius:7px;padding:8px;selection-background-color:#177d5e;}
QLineEdit:focus,QTextEdit:focus {border:1px solid #177d5e;}
QTableWidget {background:white;border:0;gridline-color:#edf1ee;alternate-background-color:#f8faf8;selection-background-color:#dcefe4;selection-color:#173c2c;}
QHeaderView::section {background:#f2f6f3;color:#5a7367;border:0;border-bottom:1px solid #dce6df;padding:9px;text-align:left;font-weight:600;}
QTableWidget::item {padding:6px;} QScrollArea {border:0;background:transparent;}
QScrollBar:vertical {width:9px;background:#edf3f0;} QScrollBar::handle:vertical {background:#c5d6cc;border-radius:4px;min-height:25px;}
QToolTip {background:#183d32;color:white;border:0;padding:8px;}
"""


def label(text, name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, handler, name=None):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(handler)
    return widget


def card(title=None):
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, "cardTitle"))
    return widget, layout


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.message = "Камера ещё не подключена"
        self.setMinimumSize(320, 235)
        self.setAccessibleName("Видеопоток камеры")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1a3432"))
        if self.image is not None:
            scaled = self.image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width()-scaled.width())//2, (self.height()-scaled.height())//2, scaled)
        else:
            painter.setPen(QColor("#adc9be"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect().adjusted(25, 25, -25, -25), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)


class MainWindow(QMainWindow):
    def __init__(self, db, settings):
        super().__init__()
        self.db, self.settings = db, settings
        self.worker = None
        self.worker_ready = False
        self.session_id = None
        self.engine = None
        self.session_start = 0.0
        self.last_frame = 0.0
        self.session_events = []
        self.raw_frame = None
        self.last_observation = Observation(camera_ok=False)
        self.security = SecurityMonitor()
        self.selected_session = None
        self.displayed_sessions = []
        self.bind_countdown = 0
        self.stopping = False
        self.setWindowTitle("QORGAU AI · Мониторинг экзамена")
        self.resize(1280, 860)
        self.setMinimumSize(1000, 740)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.last_heartbeat = 0
        self.refresh_sessions()

    def build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(208)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 30, 20, 22)
        side.setSpacing(10)
        side.addWidget(label("QORGAU AI", "brand"))
        side.addWidget(label("EXAM INTEGRITY", "sideTag"))
        side.addSpacing(34)
        self.nav = []
        self.pages = QStackedWidget()
        for index, title in enumerate(("01   Мониторинг", "02   Сессии и отчёты", "03   Настройки", "04   Как это работает")):
            nav = button(title, lambda checked=False, i=index: self.navigate(i))
            nav.setCheckable(True)
            self.nav.append(nav)
            side.addWidget(nav)
        self.nav[0].setChecked(True)
        side.addStretch()
        side.addWidget(label("Локальная обработка\nYOLO11n + MediaPipe"))
        side.addSpacing(10)
        side.addWidget(label("v1.0  /  Windows", "sideTag"))
        layout.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(26, 24, 26, 20)
        body.setSpacing(18)
        heading = QHBoxLayout()
        texts = QVBoxLayout()
        self.title = label("Мониторинг экзамена", "title")
        self.subtitle = label("Наблюдайте за сессией. Проверяйте события в контексте.", "subtitle")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        heading.addLayout(texts, 1)
        self.badge = label("●  ГОТОВ К РАБОТЕ", "badge")
        self.badge.setFixedHeight(42)
        heading.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        body.addLayout(heading)
        body.addWidget(self.pages, 1)
        self.pages.addWidget(self.monitor_page())
        self.pages.addWidget(self.archive_page())
        self.pages.addWidget(self.settings_page())
        self.pages.addWidget(self.help_page())
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.title.setText(("Мониторинг экзамена", "Сессии и отчёты", "Настройки наблюдения", "Как это работает")[index])
        self.subtitle.setText(("Наблюдайте за сессией. Проверяйте события в контексте.",
            "История экзаменов, проверка эпизодов и экспорт отчётов.",
            "Настройки применяются к следующему подключению камеры.",
            "Пять наблюдаемых сигналов. Окончательное решение — за человеком.")[index])
        if index == 1:
            self.refresh_sessions()

    def monitor_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        metrics = QHBoxLayout()
        self.metrics = []
        self.metric_captions = []
        for heading, value, caption in (("ДЛИТЕЛЬНОСТЬ", "00:00:00", "Сессия ещё не началась"),
            ("СОБЫТИЯ", "0", "Эпизоды для проверки"), ("ПРИОРИТЕТ ПРОВЕРКИ", "0 / 100", "Индекс, не вердикт"),
            ("ЛЮДИ В КАДРЕ", "—", "Данные YOLO11n")):
            widget, box = card()
            box.setSpacing(4)
            box.addWidget(label(heading, "muted"))
            metric = label(value, "metricValue")
            box.addWidget(metric)
            caption_label = label(caption, "muted")
            box.addWidget(caption_label)
            self.metric_captions.append(caption_label)
            self.metrics.append(metric)
            metrics.addWidget(widget)
        layout.addLayout(metrics)
        middle = QHBoxLayout()
        camera, camera_layout = card()
        camera_top = QHBoxLayout()
        camera_top.addWidget(label("Видеопоток", "cardTitle"))
        camera_top.addStretch()
        self.camera_info = label("Отключено", "muted")
        camera_top.addWidget(self.camera_info)
        camera_layout.addLayout(camera_top)
        self.preview = Preview()
        camera_layout.addWidget(self.preview, 1)
        self.demo_banner = label("ДЕМО · Синтетические кадры и события. Цикл 48 секунд.", "banner")
        self.demo_banner.hide()
        camera_layout.addWidget(self.demo_banner)
        self.pipeline_info = label("Модели загружаются при подключении реальной камеры.", "muted")
        camera_layout.addWidget(self.pipeline_info)
        middle.addWidget(camera, 3)
        controls, controls_layout = card("Параметры сессии")
        controls_layout.setSpacing(6)
        controls.setMinimumWidth(276)
        controls.setMaximumWidth(345)
        self.candidate = QLineEdit()
        self.candidate.setMaxLength(120)
        self.candidate.setPlaceholderText("ФИО или ID участника")
        self.candidate.setAccessibleName("Участник экзамена")
        self.exam = QLineEdit()
        self.exam.setMaxLength(160)
        self.exam.setPlaceholderText("Например, Математика / 01")
        self.exam.setAccessibleName("Название экзамена")
        self.mode = QComboBox()
        self.mode.addItems(["Реальная камера", "Демонстрация"])
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.mode.setAccessibleName("Режим наблюдения")
        session_form = QFormLayout()
        session_form.setSpacing(8)
        for title, widget in (("Участник", self.candidate), ("Экзамен", self.exam), ("Источник", self.mode)):
            session_form.addRow(label(title, "muted"), widget)
        controls_layout.addLayout(session_form)
        self.connect_button = button("Подключить камеру", self.connect_camera)
        controls_layout.addWidget(self.connect_button)
        self.bind_button = button("Закрепить окно экзамена", self.bind_window)
        self.bind_button.setToolTip("После нажатия переключитесь в окно экзамена за 5 секунд")
        controls_layout.addWidget(self.bind_button)
        self.window_info = label("Окно не закреплено · контроль окон выключен", "muted")
        controls_layout.addWidget(self.window_info)
        self.start_button = button("Начать экзамен  →", self.start_session, "primary")
        self.start_button.setEnabled(False)
        controls_layout.addWidget(self.start_button)
        self.stop_button = button("Завершить экзамен", self.stop_session, "danger")
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch()
        middle.addWidget(controls, 2)
        layout.addLayout(middle, 3)
        self.status = label("Введите участника и экзамен, подключите камеру и начните сессию.", "status")
        layout.addWidget(self.status)
        journal, journal_layout = card("Журнал событий")
        self.event_table = table(["Время", "Наблюдение", "Длительность", "Состояние"])
        self.event_table.setMinimumHeight(130)
        self.event_table.setMaximumHeight(200)
        journal_layout.addWidget(self.event_table)
        layout.addWidget(journal, 1)
        scroll.setWidget(page)
        return scroll

    def archive_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по участнику или экзамену…")
        self.search.textChanged.connect(self.refresh_sessions)
        top.addWidget(self.search)
        top.addWidget(button("Обновить", self.refresh_sessions))
        top.addWidget(button("Папка данных", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_root())))))
        layout.addLayout(top)
        sessions, box = card()
        self.sessions_table = table(["№", "Участник / экзамен", "Начало", "Режим", "События", "Статус"])
        self.sessions_table.setMinimumHeight(120)
        self.sessions_table.setMaximumHeight(220)
        self.sessions_table.itemSelectionChanged.connect(self.select_session)
        box.addWidget(self.sessions_table)
        layout.addWidget(sessions)
        events, box = card("Проверка событий")
        self.review_summary = label("Выберите сессию в списке", "muted")
        box.addWidget(self.review_summary)
        self.review_table = table(["Время", "Наблюдение", "Длительность", "Проверка", "Детали"])
        box.addWidget(self.review_table, 1)
        actions = QHBoxLayout()
        for caption, verdict in (("Подтвердить", "confirmed"), ("Отклонить", "dismissed"), ("Сбросить", "pending")):
            actions.addWidget(button(caption, lambda checked=False, v=verdict: self.review_event(v)))
        actions.addWidget(button("Открыть кадр", self.open_evidence))
        actions.addStretch()
        box.addLayout(actions)
        self.note = QTextEdit()
        self.note.setPlaceholderText("Комментарий проверяющего…")
        self.note.setMaximumHeight(76)
        box.addWidget(self.note)
        footer = QHBoxLayout()
        footer.addWidget(button("Сохранить комментарий", self.save_note))
        footer.addStretch()
        self.export_button = button("Экспорт отчёта  ↓", self.export_selected, "primary")
        footer.addWidget(self.export_button)
        box.addLayout(footer)
        layout.addWidget(events, 1)
        return page

    def settings_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        widget, box = card("Камера и детекция")
        form = QFormLayout()
        form.setSpacing(18)
        self.setting_fields = {}
        options = [("camera_index", "Номер камеры", 0, 9, 1),
            ("confidence", "YOLO — уверенность: человек", 0.1, 0.95, 0.05),
            ("phone_confidence", "YOLO — уверенность: телефон", 0.1, 0.95, 0.05),
            ("head_angle", "Порог поворота головы, °", 10, 80, 5),
            ("phone_seconds", "Телефон — задержка, с", 0.5, 60, 0.5),
            ("multiple_seconds", "Несколько людей — задержка, с", 0.5, 60, 0.5),
            ("absence_seconds", "Отсутствие — задержка, с", 0.5, 60, 0.5),
            ("head_seconds", "Поворот головы — задержка, с", 0.5, 60, 0.5),
            ("window_seconds", "Переключение окна — задержка, с", 0.5, 60, 0.5)]
        for key, caption, minimum, maximum, step in options:
            field = QSpinBox() if key == "camera_index" else QDoubleSpinBox()
            field.setRange(minimum, maximum)
            field.setSingleStep(step)
            field.setValue(getattr(self.settings, key))
            field.setAccessibleName(caption)
            field.setMaximumWidth(160)
            self.setting_fields[key] = field
            form.addRow(caption, field)
        box.addLayout(form)
        self.evidence_check = QCheckBox("Сохранять один кадр при открытии визуального события")
        self.evidence_check.setChecked(self.settings.save_evidence)
        box.addWidget(self.evidence_check)
        box.addWidget(label("По умолчанию кадры не сохраняются. Данные и выбранные кадры остаются на этом компьютере; полная видеозапись не ведётся.", "muted"))
        self.save_settings_button = button("Сохранить настройки", self.save_settings, "primary")
        box.addWidget(self.save_settings_button)
        layout.addWidget(widget)
        layout.addWidget(label("Для нового угла камеры сначала завершите текущую сессию. Поворот головы — оценка ориентации лица, а не направления взгляда. Слабое освещение и закрытое лицо могут ухудшать детекцию.", "muted"))
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def help_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        sections = [
            ("01 / Подготовьте сессию", "Введите участника и название экзамена. Выберите реальную камеру и нажмите «Подключить камеру». Дождитесь видеопотока. Камера и обе модели должны работать до начала сессии."),
            ("02 / Закрепите окно", "Нажмите «Закрепить окно экзамена» и за 5 секунд перейдите в нужное окно. Затем вернитесь в QORGAU AI и начните экзамен. После начала перейдите в окно экзамена. Любое другое активное окно, включая QORGAU AI, считается переключением. Вкладки внутри одного окна браузера не отслеживаются. Без привязки контроль окон выключен."),
            ("03 / Наблюдайте", "YOLO11n обнаруживает людей и телефоны, MediaPipe — лица и угол головы. Событие появляется только после установленной задержки. Непрерывное наблюдение создаёт один эпизод; возврат к норме закрывает его. Потеря камеры записывается как техническое событие и не считается отсутствием человека."),
            ("04 / Проверьте и экспортируйте", "Завершите экзамен, откройте «Сессии и отчёты», выберите сессию. Подтвердите или отклоните каждый эпизод и добавьте комментарий. Экспорт доступен в HTML, CSV и JSON. HTML можно открыть в браузере и распечатать или сохранить в PDF."),
            ("Индекс проверки", "Вес каждого эпизода: телефон 20, несколько людей 15, отсутствие 10, поворот головы 5, переключение окна 10. Сумма ограничена 100; технические события дают 0. Это приоритет просмотра, не вероятность нарушения. Исходный индекс включает отклонённые события; решения проверяющего показаны отдельно."),
            ("Демонстрация и хранение", "Деморежим запускает синтетический 48-секундный цикл всех пяти событий без камеры и моделей. Такие сессии помечены ДЕМО в истории и отчёте. Рабочие данные: %LOCALAPPDATA%\\QorgauAI. Приложение не отправляет видео или журнал в сеть и не перехватывает клавиатуру, экран или буфер обмена.")]
        for title, text in sections:
            widget, box = card(title)
            box.addWidget(label(text))
            layout.addWidget(widget)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def mode_changed(self):
        demo = self.mode.currentIndex() == 1
        self.connect_button.setText("Запустить демонстрацию" if demo else "Подключить камеру")
        self.bind_button.setEnabled(not demo)
        self.window_info.setText("ДЕМО · переключение окна синтетическое" if demo else (self.security.title or "Окно не закреплено · контроль окон выключен"))

    def connect_camera(self):
        if self.worker is not None:
            self.stop_preview()
            return
        self.mode.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.save_settings_button.setEnabled(False)
        self.worker_ready = False
        self.preview.message = "Подготовка источника…"
        self.preview.image = None
        self.preview.update()
        demo = self.mode.currentIndex() == 1
        self.demo_banner.setVisible(demo)
        self.worker = CameraWorker(self.settings, demo)
        self.worker.frame.connect(self.on_frame)
        self.worker.status.connect(self.status.setText)
        self.worker.failed.connect(self.on_failure)
        self.worker.ready.connect(self.on_ready)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def on_ready(self):
        self.worker_ready = True
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Отключить источник")
        self.status.setText("Источник готов. Введите данные участника и начните экзамен.")

    def on_frame(self, image, observation, raw):
        if self.stopping or self.worker is None:
            return
        self.last_observation = observation
        self.raw_frame = raw
        self.last_frame = time.monotonic()
        if not image.isNull():
            self.preview.image = QPixmap.fromImage(image)
            self.start_button.setEnabled(self.session_id is None and self.worker_ready and not self.bind_countdown)
        else:
            self.preview.image = None
            self.preview.message = "Нет кадра · анализ приостановлен"
        self.preview.update()
        self.metrics[3].setText(str(observation.people) if observation.people is not None else "—")
        self.camera_info.setText("ДЕМО" if self.mode.currentIndex() == 1 else "● Камера подключена")
        self.pipeline_info.setText("Синтетические наблюдения · модели не используются" if self.mode.currentIndex() == 1 else
            f"YOLO11n + MediaPipe · CPU · {observation.inference_ms:.0f} мс / кадр · лица: {observation.faces}" + (f" · угол: {observation.yaw:.0f}°" if observation.yaw is not None else ""))
        if self.session_id is not None:
            self.consume_observation(observation)

    def consume_observation(self, observation):
        if self.mode.currentIndex() == 0:
            observation.window_away = self.security.away()
        elapsed = time.monotonic() - self.session_start
        opened, closed = self.engine.update(observation, elapsed)
        for event in opened:
            if self.settings.save_evidence and self.raw_frame is not None and event.kind in ("phone", "multiple", "absence", "head") and self.mode.currentIndex() == 0:
                folder = data_root() / "evidence" / str(self.session_id)
                folder.mkdir(parents=True, exist_ok=True)
                destination = folder / f"{event.kind}-{int(elapsed*1000)}.jpg"
                ok, encoded = cv2.imencode(".jpg", self.raw_frame)
                if ok:
                    encoded.tofile(str(destination))
                    event.evidence = str(destination)
            self.db.add_event(self.session_id, event)
            self.session_events.append(event)
        for event in closed:
            self.db.close_event(event)
        if opened or closed:
            self.refresh_journal(elapsed)

    def start_session(self):
        if self.bind_countdown or self.session_id is not None or self.stopping:
            return
        candidate, exam = self.candidate.text().strip(), self.exam.text().strip()
        if not candidate or not exam:
            self.status.setText("Заполните участника и название экзамена.")
            (self.candidate if not candidate else self.exam).setFocus()
            return
        if not self.worker_ready or time.monotonic() - self.last_frame > 2:
            self.status.setText("Дождитесь доступного видеопотока.")
            return
        mode = "demo" if self.mode.currentIndex() == 1 else "live"
        self.session_id = self.db.start(candidate, exam, mode, self.settings)
        self.engine = EventEngine(self.settings)
        self.session_events = []
        self.session_start = time.monotonic()
        self.metrics[0].setText("00:00:00")
        self.metric_captions[0].setText("Наблюдение активно")
        self.refresh_journal(0)
        self.last_heartbeat = 0
        self.event_table.setRowCount(0)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.connect_button.setEnabled(False)
        self.bind_button.setEnabled(False)
        self.candidate.setEnabled(False)
        self.exam.setEnabled(False)
        self.badge.setText("●  ДЕМО СЕССИЯ" if mode == "demo" else "●  ЭКЗАМЕН ИДЁТ")
        self.status.setText(f"Сессия #{self.session_id} записывается локально." + (" Контроль окон выключен: окно не закреплено." if mode == "live" and self.security.target is None else ""))

    def stop_session(self, checked=False, interrupted=False):
        if self.session_id is not None:
            elapsed = time.monotonic()-self.session_start
            for event in self.engine.finish(elapsed):
                self.db.close_event(event)
            ended_id = self.session_id
            self.db.finish(ended_id, elapsed, "interrupted" if interrupted else "completed")
            self.session_id = None
            self.refresh_journal(elapsed)
            self.metrics[0].setText(clock(elapsed))
            self.metric_captions[0].setText("Сессия прервана" if interrupted else "Сессия завершена")
            self.selected_session = ended_id
            self.status.setText(f"Сессия #{ended_id} {'прервана' if interrupted else 'завершена'}. Откройте «Сессии и отчёты» для проверки и экспорта.")
        self.stop_preview()
        self.stop_button.setEnabled(False)
        self.candidate.setEnabled(True)
        self.exam.setEnabled(True)
        self.badge.setText("●  СЕССИЯ СОХРАНЕНА")
        self.refresh_sessions()

    def stop_preview(self):
        if self.worker is not None:
            self.stopping = True
            self.start_button.setEnabled(False)
            self.connect_button.setEnabled(False)
            self.worker.requestInterruption()
            # No blocking wait on the GUI thread: finished signal releases the worker.
        else:
            self.worker_finished()

    def worker_finished(self):
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self.worker_ready = False
        self.stopping = False
        self.raw_frame = None
        self.metrics[3].setText("—")
        self.mode.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.save_settings_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.preview.image = None
        self.preview.message = "Источник отключён"
        self.preview.update()
        self.camera_info.setText("Отключено")
        self.pipeline_info.setText("Подключите источник для наблюдения.")
        self.mode_changed()

    def on_failure(self, message):
        if self.session_id is not None:
            elapsed = time.monotonic()-self.session_start
            self.consume_observation(Observation(camera_ok=False))
            event = Event("system", elapsed, elapsed, message)
            self.db.add_event(self.session_id, event)
            self.session_events.append(event)
            self.stop_session(interrupted=True)
        self.status.setText(message)
        self.preview.message = message
        self.preview.image = None
        self.preview.update()

    def tick(self):
        if self.bind_countdown:
            if time.monotonic() >= self.bind_deadline:
                self.bind_countdown = 0
                try:
                    title = self.security.bind_foreground()
                    self.window_info.setText(f"Закреплено: {title}")
                    self.status.setText("Окно экзамена закреплено. Начните сессию и перейдите в него.")
                except RuntimeError as error:
                    self.status.setText(str(error))
                self.bind_button.setEnabled(True)
                self.bind_button.setText("Закрепить окно экзамена")
            else:
                self.bind_button.setText(f"Переключитесь в окно: {int(self.bind_deadline-time.monotonic())+1} с")
        if self.session_id is None:
            return
        elapsed = time.monotonic()-self.session_start
        self.metrics[0].setText(clock(elapsed))
        if self.mode.currentIndex() == 0 and time.monotonic()-self.last_frame > 2:
            self.consume_observation(Observation(camera_ok=False))
            self.preview.image = None
            self.preview.message = "Поток задерживается · визуальный анализ приостановлен"
            self.preview.update()
        elif self.mode.currentIndex() == 0:
            # Sample window identity independently of inference; reuse only fresh vision.
            self.consume_observation(self.last_observation)
        if elapsed - self.last_heartbeat >= 1:
            self.db.heartbeat(self.session_id, elapsed)
            self.refresh_journal(elapsed)
            self.last_heartbeat = elapsed

    def bind_window(self):
        if self.session_id is not None or self.bind_countdown:
            return
        self.bind_countdown = 5
        self.bind_deadline = time.monotonic()+5
        self.bind_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.status.setText("За 5 секунд переключитесь в окно, в котором участник будет сдавать экзамен.")

    def refresh_journal(self, elapsed):
        self.metrics[1].setText(str(len(self.session_events)))
        self.metrics[2].setText(f"{risk_score(self.session_events)} / 100")
        self.event_table.setRowCount(len(self.session_events))
        for row, event in enumerate(reversed(self.session_events)):
            duration = max(0, (event.end if event.end is not None else elapsed)-event.start)
            cells = [clock(event.start), TITLES.get(event.kind, event.kind), f"{duration:.1f} с", "Идёт" if event.end is None else "Для проверки"]
            for col, value in enumerate(cells):
                self.event_table.setItem(row, col, QTableWidgetItem(value))

    def refresh_sessions(self):
        if not hasattr(self, "sessions_table"):
            return
        query = self.search.text().strip().casefold()
        self.displayed_sessions = [s for s in self.db.sessions() if query in f"{s['candidate']} {s['exam']}".casefold()]
        self.sessions_table.blockSignals(True)
        self.sessions_table.setRowCount(len(self.displayed_sessions))
        selected_row = None
        for row, session in enumerate(self.displayed_sessions):
            values = [str(session["id"]), f"{session['candidate']} / {session['exam']}", local_time(session["started"]),
                "ДЕМО" if session["mode"] == "demo" else "Камера", str(session["event_count"]), STATUSES[session["status"]]]
            for col, value in enumerate(values):
                self.sessions_table.setItem(row, col, QTableWidgetItem(value))
            if session["id"] == self.selected_session:
                selected_row = row
        self.sessions_table.blockSignals(False)
        if selected_row is not None:
            self.sessions_table.selectRow(selected_row)
            self.select_session()
        elif not self.displayed_sessions:
            self.selected_session = None
            self.review_table.setRowCount(0)
            self.review_summary.setText("Сессии не найдены")
            self.note.clear()

    def select_session(self):
        row = self.sessions_table.currentRow()
        if row < 0 or row >= len(self.displayed_sessions):
            return
        self.selected_session = self.displayed_sessions[row]["id"]
        session = self.db.session(self.selected_session)
        self.note.setPlainText(session["note"])
        self.refresh_review()

    def refresh_review(self):
        if self.selected_session is None:
            return
        session = self.db.session(self.selected_session)
        self.review_events = self.db.events(self.selected_session)
        self.review_summary.setText(f"Сессия #{session['id']} · {'ДЕМО · ' if session['mode']=='demo' else ''}{clock(session['duration'])} · {len(self.review_events)} событий · индекс {risk_score(self.review_events)}/100")
        self.review_table.setRowCount(len(self.review_events))
        for row, event in enumerate(self.review_events):
            duration = max(0, (event["end"] if event["end"] is not None else session["duration"])-event["start"])
            cells = [clock(event["start"]), TITLES.get(event["kind"], event["kind"]), f"{duration:.1f} с", REVIEWS[event["review"]], event["detail"]]
            for col, value in enumerate(cells):
                self.review_table.setItem(row, col, QTableWidgetItem(value))

    def review_event(self, verdict):
        row = self.review_table.currentRow()
        if self.selected_session is None or row < 0:
            return
        self.db.review(self.review_events[row]["id"], verdict)
        self.refresh_review()
        self.review_table.selectRow(row)

    def open_evidence(self):
        row = self.review_table.currentRow()
        if self.selected_session is None or row < 0:
            return
        path = self.review_events[row]["evidence"]
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.information(self, "Кадр события", "Кадр для этого события не сохранялся.")

    def save_note(self):
        if self.selected_session is not None:
            self.db.note(self.selected_session, self.note.toPlainText())
            self.status.setText("Комментарий сохранён.")

    def export_selected(self):
        if self.selected_session is None:
            QMessageBox.information(self, "Экспорт", "Выберите сессию в списке.")
            return
        self.save_note()
        destination, selected_filter = QFileDialog.getSaveFileName(self, "Сохранить отчёт", str(data_root()/f"exam-{self.selected_session}.html"), "HTML (*.html);;CSV (*.csv);;JSON (*.json)")
        if not destination:
            return
        path = Path(destination)
        wanted = ".csv" if selected_filter.startswith("CSV") else ".json" if selected_filter.startswith("JSON") else ".html"
        if path.suffix.lower() != wanted:
            path = path.with_suffix(wanted)
        try:
            export_report(self.db, self.selected_session, path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось сохранить", str(error))
            return
        QMessageBox.information(self, "Отчёт сохранён", str(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save_settings(self):
        if self.worker is not None:
            return
        values = {key: field.value() for key, field in self.setting_fields.items()}
        values["save_evidence"] = self.evidence_check.isChecked()
        settings = Settings(**values)
        settings.save(data_root()/"settings.json")
        self.settings = settings
        self.status.setText("Настройки сохранены и будут применены при следующем подключении.")
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def closeEvent(self, event):
        if self.session_id is not None:
            answer = QMessageBox.question(self, "Завершить экзамен?", "Текущая сессия будет завершена и сохранена.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_session()
        if self.worker is not None:
            self.worker.requestInterruption()
            event.ignore()
            # Keep Qt alive until native camera/model cleanup completes.
            self.worker.finished.connect(self.close)
            self.status.setText("Отключение камеры…")
            return
        self.timer.stop()
        event.accept()
