"""Volume por App — controla o volume de cada programa separadamente, com perfis
("Jogo", "Reunião", "Noite") e bandeja. Offline (usa o mixer de áudio do Windows via pycaw).
"""
import os
import sys

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog,
                             QLabel, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider,
                             QSystemTrayIcon, QMenu, QVBoxLayout, QWidget)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import va_core  # noqa: E402

ACCENT = "#7c5cff"
QSS = """
QWidget { background:#11131a; color:#e7e9f0; font:10pt 'Segoe UI'; }
#title { font:700 18pt 'Segoe UI'; }
#info { color:#8a93a8; }
#row { background:#1b202b; border-radius:10px; }
#row QWidget { background:transparent; }
QComboBox { background:#1b202b; border:1px solid #2d3550; border-radius:8px; padding:6px; }
QPushButton { background:#222a38; border:0; border-radius:10px; padding:9px 14px; }
QPushButton:hover { background:#2d3550; }
#go { background:#7c5cff; color:#fff; font-weight:600; padding:12px 16px; font-size:12pt; }
#go:hover { background:#8f74ff; }
QSlider::groove:horizontal { height:6px; background:#2d3550; border-radius:3px; }
QSlider::sub-page:horizontal { background:#7c5cff; border-radius:3px; }
QSlider::handle:horizontal { background:#fff; width:14px; margin:-5px 0; border-radius:7px; }
QProgressBar { background:#0c0e14; border:0; border-radius:3px; max-height:6px; }
QProgressBar::chunk { background:#79e0a8; border-radius:3px; }
QScrollArea { border:0; }
"""


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor("transparent"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(8, 22, 14, 20, 3, 3)
    p.drawPolygon(*[QPoint(*q) for q in [(20, 22), (36, 8), (36, 56), (20, 42)]])
    p.setPen(QColor(ACCENT))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(34, 20, 14, 24, -60 * 16, 120 * 16)
    p.drawArc(38, 12, 20, 40, -60 * 16, 120 * 16)
    p.end()
    return QIcon(pm)


class Row(QFrame):
    """Uma linha: nome, slider, mudo, medidor. Mantém o estado enquanto o usuário arrasta."""

    def __init__(self, key, name, backend, master=False):
        super().__init__()
        self.setObjectName("row")
        self.key, self.backend, self.master = key, backend, master
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self.name = QLabel(name)
        top.addWidget(self.name, 1)
        self.pct = QLabel("0%")
        self.pct.setMinimumWidth(40)
        top.addWidget(self.pct)
        self.mute = QCheckBox("Mudo")
        self.mute.toggled.connect(self._mute)
        top.addWidget(self.mute)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.valueChanged.connect(self._vol)
        lay.addWidget(self.slider)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        if not master:
            lay.addWidget(self.meter)
        self._updating = False

    def _vol(self, v):
        self.pct.setText(f"{v}%")
        if self._updating:
            return
        if self.master:
            self.backend.set_master(v)
        else:
            self.backend.set_volume(self.key, v)

    def _mute(self, m):
        if self._updating:
            return
        if self.master:
            self.backend.set_master_mute(m)
        else:
            self.backend.set_mute(self.key, m)

    def update_state(self, vol, muted, peak=0):
        self._updating = True
        if not self.slider.isSliderDown():
            self.slider.setValue(vol)
            self.pct.setText(f"{vol}%")
        self.mute.setChecked(muted)
        self.meter.setValue(peak)
        self._updating = False


class TrayPopup(QWidget):
    """Mini janela com o slider do volume geral, perto da bandeja."""

    def __init__(self, backend):
        super().__init__(None, Qt.WindowType.Popup)
        self.backend = backend
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Volume geral"))
        self.row = Row("master", "Geral", backend, master=True)
        lay.addWidget(self.row)
        self.setFixedWidth(280)

    def show_near_cursor(self):
        v, m = self.backend.get_master()
        self.row.update_state(v, m)
        self.adjustSize()
        pos = QCursor.pos()
        self.move(pos.x() - self.width() // 2, pos.y() - self.height() - 16)
        self.show()


class VolumeApps(QWidget):
    def __init__(self, backend=None, profiles_path=None, error=None):
        super().__init__()
        self.backend = backend
        self.profiles_path = profiles_path or va_core.PERFIS_PATH
        self.rows = {}
        self.tray = None
        self._really_quit = False
        self.setWindowTitle("Volume por App")
        self.setWindowIcon(app_icon())
        self.resize(560, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(9)
        root.addWidget(QLabel("🔊 Volume por App", objectName="title"))
        self.dev = QLabel("", objectName="info")
        root.addWidget(self.dev)

        if backend is None:
            msg = QLabel("Não consegui acessar o áudio do Windows.\n\n"
                         "Verifique se há uma saída de áudio ativa e se as bibliotecas estão "
                         "instaladas:\n  pip install pycaw comtypes\n\nDetalhe: " + str(error))
            msg.setWordWrap(True)
            root.addWidget(msg)
            root.addStretch(1)
            return

        self.master_row = Row("master", "🔈 Volume geral", backend, master=True)
        root.addWidget(self.master_row)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setSpacing(6)
        self.lay.addStretch(1)
        self.area.setWidget(inner)
        root.addWidget(self.area, 1)
        self.empty = QLabel("Nenhum programa tocando áudio agora.", objectName="info")
        self.lay.insertWidget(0, self.empty)

        pr = QHBoxLayout()
        pr.addWidget(QLabel("Perfil:"))
        self.combo = QComboBox()
        pr.addWidget(self.combo, 1)
        b = QPushButton("Aplicar")
        b.setObjectName("go")
        b.clicked.connect(self.apply_selected)
        pr.addWidget(b)
        for txt, fn in (("Salvar atual…", self.save_current), ("Apagar", self.delete_selected)):
            bt = QPushButton(txt)
            bt.clicked.connect(fn)
            pr.addWidget(bt)
        root.addLayout(pr)
        self.status = QLabel("", objectName="info")
        root.addWidget(self.status)

        self.reload_profiles()
        self.popup = TrayPopup(backend)
        self._setup_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    # ----- bandeja -----
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Volume por App")
        menu = QMenu()
        a = QAction("Abrir", self)
        a.triggered.connect(self.show_normal)
        menu.addAction(a)
        q = QAction("Sair", self)
        q.triggered.connect(self._quit)
        menu.addAction(q)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_click)
        self.tray.show()

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.popup.show_near_cursor()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.popup.hide()
            self.show_normal()

    def show_normal(self):
        self.showNormal()
        self.activateWindow()

    def _quit(self):
        self._really_quit = True
        self.close()
        QApplication.quit()

    def changeEvent(self, e):
        if self.tray and self.isMinimized():
            QTimer.singleShot(0, self.hide)
        super().changeEvent(e)

    def closeEvent(self, e):
        if self.tray and not getattr(self, "_really_quit", False):
            e.ignore()
            self.hide()
        else:
            e.accept()

    # ----- atualização -----
    def refresh(self):
        try:
            v, m = self.backend.get_master()
            self.master_row.update_state(v, m)
            self.dev.setText("Saída: " + self.backend.get_device_name())
            sessions = self.backend.list_sessions()
        except Exception as ex:
            self.status.setText(f"Erro de áudio: {ex}")
            return
        seen = set()
        for s in sessions:
            seen.add(s.key)
            r = self.rows.get(s.key)
            if r is None:
                r = Row(s.key, s.name, self.backend)
                self.rows[s.key] = r
                self.lay.insertWidget(self.lay.count() - 1, r)
            r.update_state(s.volume, s.muted, s.peak)
        for k in list(self.rows):
            if k not in seen:
                self.rows.pop(k).deleteLater()
        self.empty.setVisible(not self.rows)

    # ----- perfis -----
    def reload_profiles(self, select=None):
        self.profiles = va_core.load_profiles(self.profiles_path)
        self.combo.clear()
        self.combo.addItems(sorted(self.profiles))
        if select:
            self.combo.setCurrentText(select)

    def save_current(self):
        name, ok = QInputDialog.getText(self, "Salvar perfil", "Nome do perfil (ex.: Jogo, Reunião, Noite):")
        name = name.strip()
        if not ok or not name:
            return
        v, _ = self.backend.get_master()
        self.profiles[name] = va_core.make_profile(self.backend.list_sessions(), v)
        va_core.save_profiles(self.profiles, self.profiles_path)
        self.reload_profiles(name)
        self.status.setText(f"Perfil “{name}” salvo.")

    def apply_selected(self):
        name = self.combo.currentText()
        if name not in self.profiles:
            self.status.setText("Escolha ou salve um perfil primeiro.")
            return
        done, missing = va_core.apply_profile(self.profiles[name], self.backend)
        self.refresh()
        txt = f"Perfil “{name}” aplicado a {len(done)} app(s)."
        if missing:
            txt += " Fora do ar: " + ", ".join(missing)
        self.status.setText(txt)

    def delete_selected(self):
        name = self.combo.currentText()
        if name in self.profiles:
            del self.profiles[name]
            va_core.save_profiles(self.profiles, self.profiles_path)
            self.reload_profiles()
            self.status.setText(f"Perfil “{name}” apagado.")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    backend, err = None, None
    try:
        backend = va_core.PycawBackend()
    except Exception as ex:  # pycaw/COM ausente ou sem dispositivo
        err = ex
    w = VolumeApps(backend, error=err)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
