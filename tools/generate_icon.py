from pathlib import Path
from PIL import Image, ImageDraw


def generate_icon(output_path: Path) -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer glow ring
    draw.ellipse((8, 8, size - 8, size - 8), fill=(20, 180, 230, 64))
    draw.ellipse((18, 18, size - 18, size - 18), fill=(20, 180, 230, 92))

    # Core circle
    draw.ellipse((36, 36, size - 36, size - 36), fill=(10, 36, 52, 255))

    # Equalizer bars
    bars = [56, 94, 132, 170]
    heights = [52, 98, 72, 112]
    bar_w = 20
    baseline = 196
    for x, h in zip(bars, heights):
        draw.rounded_rectangle(
            (x, baseline - h, x + bar_w, baseline),
            radius=7,
            fill=(92, 228, 255, 255),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico"
    generate_icon(target)
    print(f"Generated icon at: {target}")
