from PIL import Image
import os

SRC = r"Assets\\Instant Icon.png"            # 高解析度 PNG（建議正方形，或會自動補邊）
DST = r"Assets\\Instant Icon.ico"

# 讀圖、補成正方形（透明底）
img = Image.open(SRC).convert("RGBA")
w, h = img.size
m = max(w, h)
canvas = Image.new("RGBA", (m, m), (0, 0, 0, 0))
canvas.paste(img, ((m - w) // 2, (m - h) // 2))

# 輸出多尺寸 ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
canvas.save(DST, format="ICO", sizes=[(s, s) for s in sizes])

print("ICO written:", os.path.abspath(DST))
