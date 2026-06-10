from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


root = Path(__file__).resolve().parents[1]
target = root / "assets" / "ping.ico"
target.parent.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (256, 256), "#111b2c")
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=52, fill="#111b2c")
draw.ellipse((176, 38, 216, 78), fill="#24a86b")
try:
    font = ImageFont.truetype("segoeuib.ttf", 94)
except OSError:
    font = ImageFont.load_default()
draw.text((37, 78), "PI", fill="white", font=font)
draw.text((140, 86), "ng", fill="#24a86b", font=ImageFont.truetype("segoeuib.ttf", 54) if Path("C:/Windows/Fonts/segoeuib.ttf").exists() else font)
image.save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
