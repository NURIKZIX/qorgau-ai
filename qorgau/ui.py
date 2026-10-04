from dataclasses import asdict
from pathlib import Path
import time
import cv2
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from .config import Settings, data_root
from . import __version__
from .engine import Event, EventEngine, Observation, TITLES, risk_score
from .reports import REVIEWS, STATUSES, clock, export_report, local_time
from .security import KeyboardMonitor, SecurityMonitor
from .worker import CameraWorker
from .design import STYLE, EVENT_COLORS, button, card, icon, label, table
from .product import event_matches, overview_stats, preset_settings, review_stats
from . import screens


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.message = "Камера ещё не подключена"
        self.setMinimumSize(320, 280)
        self.setAccessibleName("Видеопоток камеры")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101b30"))
        if self.image is not None:
            scaled = self.image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((self.width()-scaled.width())//2, (self.height()-scaled.height())//2, scaled)
        else:
            painter.setPen(QPen(QColor("#1d2c45"), 1))
            for x in range(0, self.width(), 36):
                painter.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), 36):
                painter.drawLine(0, y, self.width(), y)
            cx, cy = self.width() / 2, self.height() / 2 - 22
            painter.setPen(QPen(QColor("#304766"), 1))
            painter.drawEllipse(QPointF(cx, cy), 54, 54)
            painter.drawEllipse(QPointF(cx, cy), 74, 74)
            painter.setPen(QPen(QColor("#83a9ee"), 2))
            painter.drawRoundedRect(QRectF(cx - 24, cy - 17, 42, 34), 7, 7)
            painter.drawPolyline([QPointF(cx + 18, cy - 10), QPointF(cx + 30, cy - 17), QPointF(cx + 30, cy + 17), QPointF(cx + 18, cy + 10)])
            painter.setPen(QColor("#99adcb"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(QRectF(22, cy + 85, self.width() - 44, 75), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.message)


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
        self.keyboard = KeyboardMonitor()
        self.demo_shortcuts = set()
        self.selected_session = None
        self.displayed_sessions = []
        self.bind_countdown = 0
        self.stopping = False
        self.auto_demo = False
        self.displayed_events = []
        self.note_dirty = False
        self.note_session = None
        self.note_draft = ""
        self.setWindowTitle("QORGAU AI · Мониторинг экзамена")
        self.resize(1280, 860)
        self.setMinimumSize(1000, 740)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.note_timer = QTimer(self)
        self.note_timer.setSingleShot(True)
        self.note_timer.timeout.connect(self.flush_note)
        self.note.textChanged.connect(self.queue_note_save)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.last_heartbeat = 0
        self.refresh_sessions()
        self.navigate(4)
        self.update_readiness()

    def build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(208)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 28, 16, 22)
        side.setSpacing(10)
        side.addWidget(label("QORGAU AI", "brand"))
        side.addWidget(label("EXAM INTELLIGENCE", "sideTag"))
        side.addSpacing(24)
        side.addWidget(label("РАБОЧЕЕ ПРОСТРАНСТВО", "sideTag"))
        self.nav = [None] * 5
        self.pages = QStackedWidget()
        for index, title, symbol in ((4, "Обзор", "home"), (0, "Мониторинг", "monitor"), (1, "Сессии и отчёты", "archive"), (2, "Настройки", "settings"), (3, "О продукте", "info")):
            nav = button(title, lambda checked=False, i=index: self.navigate(i))
            nav.setIcon(icon(symbol))
            nav.setCheckable(True)
            self.nav[index] = nav
            side.addWidget(nav)
        self.nav[0].setChecked(True)
        side.addStretch()
        side_panel = QFrame()
        side_panel.setObjectName("sidePanel")
        panel_box = QVBoxLayout(side_panel)
        panel_box.setSpacing(7)
        panel_box.addWidget(label("ГОТОВО К ДЕМОНСТРАЦИИ", "sideTag"))
        panel_box.addWidget(label("Посмотрите все 9 сигналов\nна синтетическом сценарии."))
        self.side_demo = button("Запустить демо   →", self.launch_demo, "sideDemo")
        panel_box.addWidget(self.side_demo)
        side.addWidget(side_panel)
        side.addSpacing(10)
        side.addWidget(label("●  Обработка на устройстве\nДанные остаются у вас"))
        side.addWidget(label(f"v{__version__}  /  Windows", "sideTag"))
        layout.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(28, 24, 28, 20)
        body.setSpacing(20)
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
        self.pages.addWidget(screens.overview_page(self))
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.title.setText(("Центр наблюдения", "Сессии и отчёты", "Настройки наблюдения", "О продукте", "Обзор рабочего пространства")[index])
        self.subtitle.setText(("Наблюдайте за сессией. Проверяйте события в контексте.",
            "История экзаменов, проверка эпизодов и экспорт отчётов.",
            "Настройки применяются к следующему подключению камеры.",
            "Девять сигналов. Окончательное решение — за человеком.", "От подготовки экзамена до прозрачного отчёта.")[index])
        if index == 1:
            self.refresh_sessions()
        elif index == 4:
            self.refresh_overview()

    def monitor_page(self):
        return screens.monitor_page(self, Preview)

    def archive_page(self):
        return screens.archive_page(self)

    def settings_page(self):
        return screens.settings_page(self)

    def set_badge(self, text, state="idle"):
        self.badge.setText(text)
        self.badge.setProperty("state", state)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def update_readiness(self):
        if not hasattr(self, "start_button"):
            return
        details = bool(self.candidate.text().strip() and self.exam.text().strip())
        source = self.worker_ready and time.monotonic() - self.last_frame <= 2 and self.last_observation.camera_ok
        ready = details and source and not self.bind_countdown and not self.stopping
        active = self.session_id is not None
        self.start_button.setEnabled(ready and not active)
        if active:
            text = "● Сессия идёт · события сохраняются"
        elif self.bind_countdown:
            text = "Выберите окно за время отсчёта"
        elif not details:
            text = "01  Укажите участника и экзамен"
        elif not source:
            text = "02  Подключите источник и дождитесь кадра"
        else:
            text = "● Данные и источник готовы к старту"
        self.readiness.setText(text)
        if self.readiness.property("ready") != ready:
            self.readiness.setProperty("ready", ready)
            self.readiness.style().unpolish(self.readiness)
            self.readiness.style().polish(self.readiness)
        if hasattr(self, "side_demo"):
            self.side_demo.setEnabled(self.worker is None and not active and not self.stopping)
        if hasattr(self, "preset_buttons"):
            editable = self.worker is None and not active
            for field in list(self.setting_fields.values()) + self.preset_buttons + [self.evidence_check]:
                field.setEnabled(editable)

    def launch_demo(self):
        if self.worker is not None or self.session_id is not None or self.stopping:
            self.navigate(0)
            self.status.setText("Завершите текущую сессию и отключите источник перед запуском демонстрации.")
            return
        self.navigate(0)
        if not self.candidate.text().strip():
            self.candidate.setText("Демонстрационный участник")
        if not self.exam.text().strip():
            self.exam.setText("Презентация QORGAU AI")
        self.mode.setCurrentIndex(1)
        self.auto_demo = True
        self.connect_camera()

    def apply_preset(self, preset):
        if self.worker is not None or self.session_id is not None:
            return
        current = Settings(**{key: field.value() for key, field in self.setting_fields.items()}, save_evidence=self.evidence_check.isChecked())
        values = asdict(preset_settings(current, preset))
        for key, field in self.setting_fields.items():
            field.setValue(values[key])
        from .product import PRESETS
        self.preset_hint.setText(f"Выбран профиль «{PRESETS[preset][0]}». Нажмите «Сохранить настройки».")

    def open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_root())))

    def refresh_overview(self):
        if not hasattr(self, "overview_values"):
            return
        sessions = self.db.sessions()
        stats = overview_stats(sessions)
        values = [str(stats["live"]), str(stats["completed"]), f"{int(stats['duration'] // 60)} мин", str(stats["events"])]
        for label_widget, value in zip(self.overview_values, values):
            label_widget.setText(value)
        self.recent_sessions = sessions[:4]
        self.recent_table.setRowCount(len(self.recent_sessions))
        for row, session in enumerate(self.recent_sessions):
            for col, text in enumerate((f"{session['candidate']} / {session['exam']}", "ДЕМО" if session["mode"] == "demo" else "Камера", str(session["event_count"]), STATUSES[session["status"]])):
                self.recent_table.setItem(row, col, QTableWidgetItem(text))
        self.recent_empty.setVisible(not sessions)
        self.recent_table.setVisible(bool(sessions))
        self.overview_note.setText(f"Демо-сессий: {stats['demo']}. Они не входят в статистику реальных экзаменов. Двойной щелчок по сессии открывает её отчёт.")

    def open_recent(self, row, column=0):
        if not 0 <= row < len(self.recent_sessions):
            return
        self.search.clear()
        self.archive_filter.setCurrentIndex(0)
        self.selected_session = self.recent_sessions[row]["id"]
        self.navigate(1)

    def filter_journal(self):
        elapsed = time.monotonic() - self.session_start if self.session_id is not None else getattr(self, "journal_elapsed", 0)
        self.refresh_journal(elapsed)

    def select_timeline_event(self, index):
        if not 0 <= index < len(self.session_events):
            return
        event = self.session_events[index]
        self.journal_search.clear()
        self.journal_filter.setCurrentIndex(0)
        self.filter_journal()
        row = next((i for i, candidate in enumerate(self.displayed_events) if candidate is event), None)
        if row is not None:
            self.event_table.selectRow(row)
            self.event_table.scrollToItem(self.event_table.item(row, 0))
            self.pages.widget(0).ensureWidgetVisible(self.event_table)

    def review_table_select(self, index):
        if 0 <= index < self.review_table.rowCount():
            self.review_table.selectRow(index)
            self.review_table.scrollToItem(self.review_table.item(index, 0))
            self.pages.widget(1).ensureWidgetVisible(self.review_table)

    def update_review_actions(self):
        selected = self.selected_session is not None and 0 <= self.review_table.currentRow() < len(getattr(self, "review_events", []))
        for action in self.review_actions:
            action.setEnabled(selected)
        if selected:
            event = self.review_events[self.review_table.currentRow()]
            self.evidence_button.setEnabled(bool(event["evidence"] and Path(event["evidence"]).is_file()))
        available = self.selected_session is not None
        self.export_button.setEnabled(available)
        self.save_note_button.setEnabled(available)
        self.note.setEnabled(available)

    def queue_note_save(self):
        if self.selected_session is not None:
            self.note_session = self.selected_session
            self.note_draft = self.note.toPlainText()
            self.note_dirty = True
            self.note_timer.start(700)

    def flush_note(self):
        self.note_timer.stop()
        if self.note_dirty and self.note_session is not None:
            self.db.note(self.note_session, self.note_draft)
            self.note_dirty = False
            self.archive_status.setText("Вывод сохранён автоматически на этом компьютере.")

    def help_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        sections = [
            ("01 / Подготовьте сессию", "Введите участника и название экзамена. Выберите реальную камеру и нажмите «Подключить камеру». Дождитесь видеопотока. Камера и обе модели должны работать до начала сессии."),
            ("02 / Выберите окно", "Без привязки контролируется выход из QORGAU AI. Для экзамена во внешней программе нажмите «Закрепить окно экзамена» и за 5 секунд перейдите в нужное окно. Вернитесь в QORGAU AI, начните экзамен и перейдите в закреплённое окно. Любое другое активное окно считается переключением. Окна проверяются каждые 250 мс; вкладки внутри одного окна браузера не отслеживаются. Задержка окна настраивается, 0 — без дополнительного ожидания."),
            ("Контроль клавиш", "Во время реальной сессии фиксируются Alt+Tab, Ctrl+C, Ctrl+V и Print Screen в любой программе текущего рабочего стола Windows. Нажатие записывается сразу; удержание клавиши не создаёт повторов. Текст, буфер обмена и снимки экрана не собираются; сочетания не блокируются. Для проверки начните экзамен и попробуйте сочетания, затем откройте журнал событий."),
            ("03 / Наблюдайте", "YOLO11n обнаруживает людей и телефоны, MediaPipe — лица и угол головы. Событие появляется только после установленной задержки. Непрерывное наблюдение создаёт один эпизод; возврат к норме закрывает его. Потеря камеры записывается как техническое событие и не считается отсутствием человека."),
            ("04 / Проверьте и экспортируйте", "Завершите экзамен, откройте «Сессии и отчёты», выберите сессию. Подтвердите или отклоните каждый эпизод и добавьте комментарий. Экспорт доступен в HTML, CSV и JSON. HTML можно открыть в браузере и распечатать или сохранить в PDF."),
            ("Индекс проверки", "Вес события: телефон 20, несколько людей 15, отсутствие 10, поворот головы 5, окно 10, Alt+Tab 5, Ctrl+C 5, Ctrl+V 5, Print Screen 10. Alt+Tab и выход из окна могут регистрироваться одновременно. Сумма ограничена 100; технические события дают 0. Это приоритет просмотра, не вероятность нарушения. Исходный индекс включает отклонённые события; решения проверяющего показаны отдельно."),
            ("Демонстрация и хранение", "Деморежим запускает синтетический 48-секундный цикл девяти событий без камеры, моделей и перехвата клавиш. Такие сессии помечены ДЕМО в истории и отчёте. Рабочие данные: %LOCALAPPDATA%\\QorgauAI. Приложение не отправляет видео или журнал в сеть. В реальной сессии записываются только указанные сочетания клавиш.")]
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
        self.window_info.setText("ОКНА · синтетические события" if demo else (f"ОКНА · {self.security.title}" if self.security.external else "ОКНА · выход из QORGAU AI"))
        self.keyboard_info.setText("КЛАВИШИ · синтетические события" if demo else "КЛАВИШИ · включатся с началом экзамена")
        self.update_readiness()

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
        self.update_readiness()

    def on_ready(self):
        self.worker_ready = True
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Отключить источник")
        self.status.setText("Источник готов. Введите данные участника и начните экзамен.")
        self.update_readiness()

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
        self.update_readiness()
        self.metric_captions[3].setText("Синтетическое наблюдение" if self.mode.currentIndex() == 1 else "На доступном кадре")
        if self.auto_demo and self.start_button.isEnabled():
            self.auto_demo = False
            self.start_session()

    def consume_observation(self, observation):
        if self.mode.currentIndex() == 0:
            observation.window_away = self.security.away()
        elapsed = time.monotonic() - self.session_start
        if self.mode.currentIndex() == 1:
            # Same point events as live monitoring, without installing a hook.
            for cycle in range(int(elapsed // 48) + 1):
                for at, kind, chord in ((8, "copy", "Ctrl+C"), (18, "paste", "Ctrl+V"), (35, "screenshot", "Print Screen"), (42, "alt_tab", "Alt+Tab")):
                    moment = cycle * 48 + at
                    key = (cycle, kind)
                    if moment <= elapsed and key not in self.demo_shortcuts:
                        self.demo_shortcuts.add(key)
                        self.record_shortcut(kind, chord, moment, demo=True)
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
        self.demo_shortcuts.clear()
        self.keyboard_error_reported = False
        if mode == "live":
            self.security.bind_application(self.winId())
            self.window_info.setText(f"Контроль окна: {self.security.title}")
            try:
                self.keyboard.start()
                self.keyboard_info.setText("● Клавиши: Alt+Tab · Ctrl+C/V · Print Screen")
            except RuntimeError as error:
                self.keyboard_error_reported = True
                self.keyboard_info.setText(str(error))
                event = Event("system", 0, 0, str(error))
                self.db.add_event(self.session_id, event)
                self.session_events.append(event)
        self.metrics[0].setText("00:00:00")
        self.metric_captions[0].setText("Наблюдение активно")
        self.refresh_journal(0)
        self.last_heartbeat = 0
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.connect_button.setEnabled(False)
        self.bind_button.setEnabled(False)
        self.candidate.setEnabled(False)
        self.exam.setEnabled(False)
        self.set_badge("●  ДЕМО СЕССИЯ" if mode == "demo" else "●  ЭКЗАМЕН ИДЁТ", mode)
        self.status.setText(f"Сессия #{self.session_id} записывается локально. " + ("Записываются только указанные сочетания клавиш; текст и буфер обмена не читаются." if mode == "live" else "Демонстрационные события синтетические."))
        self.update_readiness()

    def record_shortcut(self, kind, chord, elapsed, demo=False, refresh=True):
        if self.session_id is None:
            return
        detail = f"{'ДЕМО · ' if demo else ''}Нажато {chord}; содержимое буфера и экрана не фиксируется"
        event = Event(kind, max(0.0, elapsed), max(0.0, elapsed), detail)
        self.db.add_event(self.session_id, event)
        self.session_events.append(event)
        if refresh:
            self.refresh_journal(max(0.0, elapsed))

    def drain_shortcuts(self):
        shortcuts = self.keyboard.drain()
        for shortcut in shortcuts:
            self.record_shortcut(shortcut.kind, shortcut.chord, shortcut.at - self.session_start, refresh=False)
        if shortcuts and self.session_id is not None:
            self.refresh_journal(time.monotonic() - self.session_start)

    def stop_session(self, checked=False, interrupted=False):
        self.keyboard.stop()
        if self.session_id is not None:
            self.drain_shortcuts()
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
        self.keyboard_info.setText("Контроль клавиш остановлен")
        self.auto_demo = False
        self.stop_preview()
        self.stop_button.setEnabled(False)
        self.candidate.setEnabled(True)
        self.exam.setEnabled(True)
        self.set_badge("●  СЕССИЯ СОХРАНЕНА")
        self.refresh_sessions()
        self.refresh_overview()
        self.update_readiness()

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
        self.update_readiness()

    def on_failure(self, message):
        self.auto_demo = False
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
        self.update_readiness()
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
                self.bind_button.setText("Выбрать окно экзамена")
            else:
                self.bind_button.setText(f"Переключитесь в окно: {int(self.bind_deadline-time.monotonic())+1} с")
        if self.session_id is None:
            return
        elapsed = time.monotonic()-self.session_start
        if self.mode.currentIndex() == 0:
            self.drain_shortcuts()
            if self.keyboard.error and not getattr(self, "keyboard_error_reported", False):
                self.keyboard_error_reported = True
                message = f"Мониторинг клавиш недоступен: {self.keyboard.error}"
                self.keyboard_info.setText(message)
                event = Event("system", elapsed, elapsed, message)
                self.db.add_event(self.session_id, event)
                self.session_events.append(event)
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
            if self.pages.currentIndex() == 4:
                self.refresh_overview()

    def bind_window(self):
        if self.session_id is not None or self.bind_countdown:
            return
        self.bind_countdown = 5
        self.bind_deadline = time.monotonic()+5
        self.bind_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.status.setText("За 5 секунд переключитесь в окно, в котором участник будет сдавать экзамен.")

    def refresh_journal(self, elapsed):
        self.journal_elapsed = elapsed
        self.metrics[1].setText(str(len(self.session_events)))
        self.metrics[2].setText(f"{risk_score(self.session_events)} / 100")
        self.metrics[2].setStyleSheet("color:#ba7850;" if risk_score(self.session_events) >= 50 else "color:#17253d;")
        self.timeline.set_events(self.session_events, elapsed)
        self.displayed_events = [e for e in reversed(self.session_events) if event_matches(e, self.journal_filter.currentData(), self.journal_search.text())]
        signature = tuple((e.id, e.end) for e in self.displayed_events)
        rebuild = signature != getattr(self, "journal_signature", None)
        if rebuild:
            self.event_table.setRowCount(len(self.displayed_events))
            self.journal_signature = signature
        self.journal_empty.setVisible(not self.displayed_events)
        self.journal_empty.setText("По этому фильтру событий нет. Измените категорию или поисковый запрос." if self.session_events else "Пока всё спокойно. Зарегистрированные события появятся здесь.")
        for row, event in enumerate(self.displayed_events):
            duration = max(0, (event.end if event.end is not None else elapsed)-event.start)
            length = "Нажатие" if event.kind in {"copy", "paste", "alt_tab", "screenshot"} else f"{duration:.1f} с"
            if not rebuild:
                if event.end is None:
                    self.event_table.item(row, 2).setText(length)
                continue
            cells = [clock(event.start), TITLES.get(event.kind, event.kind), length, "Идёт" if event.end is None else "Для проверки"]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col == 1:
                    item.setForeground(QColor(EVENT_COLORS.get(event.kind, "#526482")))
                    item.setToolTip(event.detail)
                self.event_table.setItem(row, col, item)

    def refresh_sessions(self):
        if not hasattr(self, "sessions_table"):
            return
        query = self.search.text().strip().casefold()
        category = self.archive_filter.currentData()
        self.displayed_sessions = [s for s in self.db.sessions() if query in f"{s['candidate']} {s['exam']}".casefold() and (category == "all" or s["mode"] == category or s["status"] == category)]
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
        self.archive_empty.setVisible(not self.displayed_sessions)
        self.archive_empty.setText("Ничего не найдено. Измените запрос или фильтр." if query or category != "all" else "Нет сохранённых сессий. Начните экзамен или запустите демонстрацию.")
        if selected_row is not None:
            self.sessions_table.selectRow(selected_row)
            self.select_session()
        else:
            self.flush_note()
            self.selected_session = None
            self.review_table.setRowCount(0)
            self.review_summary.setText("Выберите сессию в списке" if self.displayed_sessions else "Нет сессий по выбранному запросу")
            self.note.blockSignals(True)
            self.note.clear()
            self.note.blockSignals(False)
            self.note_session = None
            self.review_events = []
            self.review_timeline.set_events([], 0)
            self.review_counts.setText("Проверено 0 из 0")
            self.review_progress.setValue(0)
        self.update_review_actions()
        self.refresh_overview()

    def select_session(self):
        row = self.sessions_table.currentRow()
        if row < 0 or row >= len(self.displayed_sessions):
            return
        self.flush_note()
        self.selected_session = self.displayed_sessions[row]["id"]
        session = self.db.session(self.selected_session)
        self.note.blockSignals(True)
        self.note.setPlainText(session["note"])
        self.note.blockSignals(False)
        self.note_session = self.selected_session
        self.refresh_review()

    def refresh_review(self):
        if self.selected_session is None:
            return
        session = self.db.session(self.selected_session)
        self.review_events = self.db.events(self.selected_session)
        summary = review_stats(self.review_events)
        done = summary["confirmed"] + summary["dismissed"]
        total = len(self.review_events)
        self.review_progress.setValue(round(100 * done / total) if total else 0)
        self.review_counts.setText(f"Проверено {done} из {total} · подтверждено {summary['confirmed']} · отклонено {summary['dismissed']} · ожидает {summary['pending']}")
        self.review_timeline.set_events(self.review_events, session["duration"])
        self.review_summary.setText(f"Сессия #{session['id']} · {'ДЕМО · ' if session['mode']=='demo' else ''}{clock(session['duration'])} · {len(self.review_events)} событий · индекс {risk_score(self.review_events)}/100")
        self.review_table.setRowCount(len(self.review_events))
        for row, event in enumerate(self.review_events):
            duration = max(0, (event["end"] if event["end"] is not None else session["duration"])-event["start"])
            length = "Нажатие" if event["kind"] in {"copy", "paste", "alt_tab", "screenshot"} else f"{duration:.1f} с"
            cells = [clock(event["start"]), TITLES.get(event["kind"], event["kind"]), length, REVIEWS[event["review"]], event["detail"]]
            for col, value in enumerate(cells):
                self.review_table.setItem(row, col, QTableWidgetItem(value))
        self.update_review_actions()

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
        self.flush_note()
        if self.selected_session is not None:
            self.db.note(self.selected_session, self.note.toPlainText())
            self.archive_status.setText("Вывод проверяющего сохранён и будет включён в отчёт.")

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
        self.archive_status.setText(f"Отчёт сохранён: {path}")
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
        self.preset_hint.setText("Настройки сохранены. Будут применены при следующем подключении источника.")

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
        self.flush_note()
        event.accept()
