from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from color_themes import artwork_accent, artwork_theme, get_theme, ThemeTransition
from media_monitor import MediaMonitor


def poll(monitor):
    # Fake WinRT awaits complete synchronously. Drive the coroutine directly so
    # these unit tests don't open an asyncio socketpair in the Windows sandbox.
    coroutine = monitor._poll_once()
    try:
        with pytest.raises(StopIteration):
            coroutine.send(None)
    finally:
        coroutine.close()


def encode(image):
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_white_border_does_not_wash_out_the_artwork_color():
    image = Image.new("RGB", (64, 64), "white")
    image.paste((20, 50, 220), (12, 12, 52, 52))
    red, green, blue = artwork_accent(encode(image))
    assert blue > red * 2 and blue > green * 2


def test_tiny_bright_detail_does_not_replace_the_main_color():
    image = Image.new("RGB", (64, 64), (30, 160, 60))
    image.putpixel((32, 32), (255, 0, 255))
    red, green, blue = artwork_accent(encode(image))
    assert green > red * 2 and green > blue * 2


@pytest.mark.parametrize("color", [0, 40, 180, 255])
def test_monochrome_art_stays_neutral_and_visible(color):
    accent = artwork_accent(encode(Image.new("RGB", (32, 32), (color,) * 3)))
    assert accent[0] == accent[1] == accent[2]
    assert 140 <= accent[0] <= 255


def test_transparent_pixels_do_not_contribute_to_the_palette():
    image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
    assert artwork_accent(encode(image)) is None
    image.paste((0, 40, 220, 255), (8, 8, 24, 24))
    assert artwork_accent(encode(image))[2] > 200
    assert artwork_accent(b"not an image") is None


def test_artwork_palette_keeps_hue_and_does_not_mutate_builtin_themes():
    original = dict(get_theme("album_art"))
    theme = artwork_theme((220, 20, 40))
    for key in ("base", "peak", "glow", "bg"):
        assert theme[key][0] > theme[key][1]
        assert all(0 <= channel <= 255 for channel in theme[key])
    assert theme["peak"] != (255, 255, 255)
    assert get_theme("album_art") == original


def test_transition_is_continuous_when_retargeted_mid_fade():
    transition = ThemeTransition(duration=1.0)
    cyan = get_theme("cyan")
    sunset = get_theme("sunset")
    assert transition.resolve(cyan, 0) == cyan
    assert transition.resolve(sunset, 1) == cyan
    halfway = transition.resolve(sunset, 1.5)
    assert halfway != cyan and halfway != sunset
    assert transition.resolve(get_theme("matrix"), 1.5) == halfway
    assert transition.resolve(get_theme("matrix"), 2.5) == get_theme("matrix")


def test_resolver_uses_default_palette_without_art_and_keeps_manual_theme():
    from visualizer_window import VisualizerWindow
    media = SimpleNamespace(accent_rgb=(255, 0, 0), cover_bytes=None)
    vis = SimpleNamespace(cfg={"theme": "album_art"}, media_monitor=SimpleNamespace(info=media),
                          _theme_cache_key=None, _theme_cache=None, _theme_transition=ThemeTransition(0))
    assert VisualizerWindow._resolve_theme(vis) == get_theme("album_art")
    media.cover_bytes = b"art"
    assert VisualizerWindow._resolve_theme(vis) == artwork_theme((255, 0, 0))
    vis.cfg["theme"] = "sunset"
    assert VisualizerWindow._resolve_theme(vis) == get_theme("sunset")


def test_new_track_snapshot_is_published_after_artwork_finishes(monkeypatch):
    import media_monitor
    monitor = MediaMonitor()
    monitor.info.title = "Previous track"
    monitor.info.cover_bytes = b"old artwork"
    monitor.info.accent_rgb = (255, 0, 0)
    class Thumbnail:
        async def open_read_async(self):
            assert monitor.info.title == "Previous track"
            raise OSError("Artwork unavailable")
    async def properties():
        return SimpleNamespace(title="Next track", artist="Artist", album_title="Album", thumbnail=Thumbnail())
    session = SimpleNamespace(try_get_media_properties_async=properties, source_app_user_model_id="player")
    async def manager():
        return SimpleNamespace(get_current_session=lambda: session)
    monkeypatch.setattr(media_monitor, "SessionManager", SimpleNamespace(request_async=manager))
    poll(monitor)
    assert monitor.info.title == "Next track"
    assert monitor.info.cover_bytes is None
    assert monitor.info.accent_rgb != (255, 0, 0)
    assert monitor.info.changed


def test_source_switch_with_same_metadata_refreshes_the_snapshot(monkeypatch):
    import media_monitor
    monitor = MediaMonitor()
    async def properties():
        return SimpleNamespace(title="Track", artist="Artist", album_title="", thumbnail=None)
    session = SimpleNamespace(try_get_media_properties_async=properties, source_app_user_model_id="first")
    async def manager():
        return SimpleNamespace(get_current_session=lambda: session)
    monkeypatch.setattr(media_monitor, "SessionManager", SimpleNamespace(request_async=manager))
    poll(monitor)
    previous = monitor.info
    session.source_app_user_model_id = "second"
    poll(monitor)
    assert monitor.info is not previous


def test_thumbnail_metadata_and_palette_are_published_together(monkeypatch):
    import media_monitor
    monitor = MediaMonitor()
    monitor.info.title = "Previous track"
    raw = encode(Image.new("RGB", (32, 32), (10, 40, 220)))
    class Stream:
        size = len(raw)
        async def read_async(self, buffer, capacity, options):
            assert monitor.info.title == "Previous track"
            buffer.length = len(raw)
            return buffer
    class Thumbnail:
        async def open_read_async(self):
            return Stream()
    async def properties():
        return SimpleNamespace(title="Blue track", artist="Artist", album_title="", thumbnail=Thumbnail())
    session = SimpleNamespace(try_get_media_properties_async=properties, source_app_user_model_id="player")
    async def manager():
        return SimpleNamespace(get_current_session=lambda: session)
    def read_bytes(target):
        target[:] = raw
    monkeypatch.setattr(media_monitor, "SessionManager", SimpleNamespace(request_async=manager))
    monkeypatch.setattr(media_monitor, "Buffer", lambda size: SimpleNamespace(capacity=size, length=0))
    monkeypatch.setattr(media_monitor, "DataReader", SimpleNamespace(
        from_buffer=lambda buffer: SimpleNamespace(read_bytes=read_bytes)))
    poll(monitor)
    assert monitor.info.title == "Blue track"
    assert monitor.info.cover_bytes == raw
    assert monitor.info.accent_rgb[2] > 200
    assert monitor.info.changed


def test_no_session_clears_stale_art_even_without_a_title(monkeypatch):
    import media_monitor
    monitor = MediaMonitor()
    monitor.info.cover_bytes = b"old artwork"
    async def manager():
        return SimpleNamespace(get_current_session=lambda: None)
    monkeypatch.setattr(media_monitor, "SessionManager", SimpleNamespace(request_async=manager))
    poll(monitor)
    assert monitor.info.cover_bytes is None
    assert monitor.info.changed
