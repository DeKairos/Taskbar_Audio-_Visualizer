import comtypes
comtypes.CoInitialize()
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from audio_capture import AudioCaptureThread
from visualizer_window import VisualizerWindow
from tray_manager import TrayManager
from config_manager import load_config
from media_monitor import MediaMonitor
from input_hooks import VisualizerClickWatcher


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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
    click_watcher = VisualizerClickWatcher(
        visualizer,
        visualizer.request_media_overlay,
    )
    click_watcher.start()
    visualizer.media_click_watcher = click_watcher

    tray = TrayManager(visualizer, audio_thread, config)
    tray.show()

    # Position on taskbar after event loop starts
    QTimer.singleShot(300, visualizer.position_on_taskbar)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
