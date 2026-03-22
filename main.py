import comtypes
comtypes.CoInitialize()
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QLockFile, QStandardPaths
from audio_capture import AudioCaptureThread
from visualizer_window import VisualizerWindow
from tray_manager import TrayManager
from config_manager import load_config
from media_monitor import MediaMonitor
from app_resources import get_app_icon


_instance_lock = None


def _acquire_single_instance_lock() -> bool:
    """Prevent launching multiple app instances simultaneously."""
    global _instance_lock

    temp_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    lock_path = Path(temp_dir) / "audio_visualizer.lock"

    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return False

    _instance_lock = lock
    return True


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not _acquire_single_instance_lock():
        return 0

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    config = load_config()

    visualizer = VisualizerWindow(config)

    audio_thread = AudioCaptureThread()
    audio_thread.fft_data_ready.connect(visualizer.update_fft)
    audio_thread.start()

    # Volume scroll hook intentionally disabled.
    visualizer.volume_scroller = None

    # Start media monitor (album art dominant color extraction)
    media_monitor = MediaMonitor(poll_interval=2.0)
    media_monitor.start()
    visualizer.media_monitor = media_monitor

    # Clicking on visualizer area reveals now-playing overlay on demand.
    # Handled by a safe UI-thread polling timer in VisualizerWindow.

    tray = TrayManager(visualizer, audio_thread, config)
    tray.show()

    # Position on taskbar after event loop starts
    QTimer.singleShot(300, visualizer.position_on_taskbar)

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
