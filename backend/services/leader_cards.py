"""Картинки лидеров турнира для соцсетей: «ТОП-5. БОМБАРДИРЫ» и «ЛУЧШИЕ ИГРОКИ».

Чистое рисование на Pillow: на вход — готовые строки (имя, клуб, число, фото, эмблема),
на выход — PIL.Image. Данные собирает app.py.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BLUE_TOP = (22, 72, 230)
BLUE_BOTTOM = (16, 56, 214)
PILL = (44, 140, 255)
NAVY = (18, 30, 72)
WHITE = (255, 255, 255)
MUTED = (60, 72, 110)
ORANGE = (242, 78, 36)
TEAL = (52, 214, 196)

WIDTH = 1280


class Fonts:
    """Unbounded — заголовки и имена, Onest — подписи. Оба файла вариативные."""

    def __init__(self, display_path, body_path):
        self.display_path = display_path
        self.body_path = body_path
        self._cache = {}

    def get(self, kind, size, weight):
        key = (kind, size, weight)
        if key not in self._cache:
            path = self.display_path if kind == 'display' else self.body_path
            font = ImageFont.truetype(path, size)
            try:
                font.set_variation_by_axes([weight])
            except Exception:
                pass
            self._cache[key] = font
        return self._cache[key]

    def fit(self, draw, text, max_width, size, weight, kind='display', minimum=16):
        while size > minimum:
            font = self.get(kind, size, weight)
            if draw.textlength(text, font=font) <= max_width:
                return font
            size -= 2
        return self.get(kind, minimum, weight)


def _background(height):
    """Синий фон с диагональными бликами и цветными «осколками» по углам."""
    # Вертикальный градиент: столбец в 1 пиксель, растянутый на ширину.
    column = Image.new('RGB', (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        column.putpixel((0, y), tuple(int(BLUE_TOP[i] + (BLUE_BOTTOM[i] - BLUE_TOP[i]) * t) for i in range(3)))
    base = column.resize((WIDTH, height))

    overlay = Image.new('RGBA', (WIDTH, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Светлые диагональные полосы — фактура как на примерах.
    for index, offset in enumerate(range(-height, WIDTH, 170)):
        alpha = 22 if index % 2 else 12
        draw.polygon([(offset, height), (offset + 90, height), (offset + 90 + height * .55, 0),
                      (offset + height * .55, 0)], fill=(255, 255, 255, alpha))

    def shard(points, color, alpha=255):
        draw.polygon(points, fill=color + (alpha,))

    # Оранжевые и бирюзовые осколки по краям.
    shard([(WIDTH - 170, 0), (WIDTH, 0), (WIDTH, 120), (WIDTH - 60, 200)], ORANGE)
    shard([(WIDTH - 40, 150), (WIDTH, 120), (WIDTH, 260)], ORANGE, 230)
    shard([(0, 30), (70, 0), (130, 0), (0, 110)], TEAL, 210)
    shard([(0, height - 160), (150, height - 60), (40, height), (0, height)], ORANGE)
    shard([(170, height - 70), (330, height - 110), (300, height), (210, height)], ORANGE, 240)
    shard([(WIDTH, height - 300), (WIDTH, height - 120), (WIDTH - 120, height - 190)], TEAL, 220)
    shard([(WIDTH - 260, height), (WIDTH - 90, height - 120), (WIDTH, height - 40), (WIDTH, height)], TEAL)
    overlay = overlay.filter(ImageFilter.GaussianBlur(.6))
    return Image.alpha_composite(base.convert('RGBA'), overlay)


def _header(canvas, fonts, eyebrow, title, top=40):
    draw = ImageDraw.Draw(canvas)
    x = 52
    font = fonts.get('display', 34, 800)
    left, right = eyebrow
    draw.text((x, top), left, font=font, fill=WHITE)
    x2 = x + draw.textlength(left, font=font) + 18
    draw.rectangle((x2, top + 6, x2 + 4, top + 38), fill=(170, 200, 255))
    draw.text((x2 + 22, top), right, font=font, fill=WHITE)

    title_font = fonts.fit(draw, title, WIDTH - 220, 58, 900)
    width = draw.textlength(title, font=title_font)
    box = (50, top + 56, 50 + width + 52, top + 56 + 92)
    draw.rounded_rectangle(box, radius=18, fill=PILL)
    draw.text((box[0] + 26, box[1] + (92 - title_font.size) / 2 - 6), title, font=title_font, fill=WHITE)
    return box[3]


def _badge_mask(size):
    """Фигурная рамка под фото: скруглённый «щит», как на примерах."""
    scale = 4
    big = size * scale
    mask = Image.new('L', (big, big), 0)
    draw = ImageDraw.Draw(mask)
    pad = big * .04
    points = [
        (big * .5, pad), (big - pad * 1.4, big * .2), (big - pad, big * .72),
        (big * .5, big - pad), (pad, big * .72), (pad * 1.4, big * .2),
    ]
    draw.polygon(points, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(big * .03))
    mask = mask.point(lambda value: 255 if value > 110 else 0)
    return mask.resize((size, size), Image.LANCZOS)


def _square(image, size):
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGBA')
        plate = Image.new('RGBA', image.size, (236, 240, 248, 255))
        image = Image.alpha_composite(plate, image)
    image = image.convert('RGB')
    width, height = image.size
    side = min(width, height)
    # Портрет обрезаем ближе к верху, чтобы не резать голову.
    top = 0 if height > width else (height - side) // 2
    image = image.crop(((width - side) // 2, top, (width - side) // 2 + side, top + side))
    return image.resize((size, size), Image.LANCZOS)


def _badge(fonts, photo, size, initials):
    """Фото в рамке: белая окантовка + синий кант."""
    outer = _badge_mask(size)
    inner = _badge_mask(size - 12)
    badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ring = Image.new('RGBA', (size, size), PILL + (255,))
    badge.paste(ring, (0, 0), outer)
    white = Image.new('RGBA', (size - 6, size - 6), WHITE + (255,))
    badge.paste(white, (3, 3), _badge_mask(size - 6))
    if photo is not None:
        face = _square(photo, size - 12).convert('RGBA')
    else:
        face = Image.new('RGBA', (size - 12, size - 12), (226, 233, 248, 255))
        draw = ImageDraw.Draw(face)
        font = fonts.get('display', int(size * .3), 800)
        width = draw.textlength(initials, font=font)
        draw.text(((size - 12 - width) / 2, (size - 12) * .32), initials, font=font, fill=PILL)
    badge.paste(face, (6, 6), inner)
    return badge


def _logo(image, size):
    if image is None:
        return None
    image = image.convert('RGBA')
    image.thumbnail((size, size), Image.LANCZOS)
    plate = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    plate.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
    return plate


def _initials(name):
    parts = [part for part in (name or '').split() if part]
    return ''.join(part[0] for part in parts[:2]).upper() or '?'


def render_top_list(fonts, eyebrow, title, rows):
    """Одна колонка: ТОП-5 или ТОП-10. rows — dict(name, team, value, photo, logo)."""
    count = max(1, len(rows))
    compact = count > 6
    row_h = 104 if compact else 116
    gap = 22 if compact else 35
    top_pad = 200
    height = top_pad + count * row_h + (count - 1) * gap + 110
    canvas = _background(height)
    _header(canvas, fonts, eyebrow, title)
    draw = ImageDraw.Draw(canvas)

    badge_size = row_h + 18
    for index, row in enumerate(rows):
        y = top_pad + index * (row_h + gap)
        card = (110, y, WIDTH - 50, y + row_h)
        draw.rounded_rectangle((card[0] + 4, card[1] + 6, card[2] + 4, card[3] + 6), radius=10, fill=(10, 30, 120))
        draw.rounded_rectangle(card, radius=10, fill=WHITE)

        badge = _badge(fonts, row.get('photo'), badge_size, _initials(row['name']))
        canvas.alpha_composite(badge, (46, int(y + row_h / 2 - badge_size / 2)))

        value = str(row['value'])
        value_font = fonts.get('display', 58 if not compact else 50, 900)
        value_w = draw.textlength(value, font=value_font)
        divider_x = WIDTH - 50 - 130
        draw.line((divider_x, y + 18, divider_x, y + row_h - 18), fill=(40, 52, 90), width=3)
        draw.text((divider_x + (130 - value_w) / 2, y + (row_h - value_font.size) / 2 - 8),
                  value, font=value_font, fill=NAVY)

        text_x = 46 + badge_size + 16
        name = row['name'].upper()
        name_font = fonts.fit(draw, name, divider_x - text_x - 24, 36 if not compact else 32, 800)
        draw.text((text_x, y + row_h * .2), name, font=name_font, fill=NAVY)

        team_y = y + row_h * .2 + name_font.size + 12
        logo = _logo(row.get('logo'), 30)
        team_x = text_x
        if logo is not None:
            canvas.alpha_composite(logo, (int(team_x), int(team_y - 2)))
            team_x += 40
        draw.text((team_x, team_y), row.get('team') or '', font=fonts.get('body', 22, 650), fill=MUTED)
    return canvas.convert('RGB')


def render_columns(fonts, eyebrow, title, columns):
    """«ЛУЧШИЕ ИГРОКИ»: три столбика Goals / Assists / Points по 10 строк."""
    rows_per = max(1, max((len(items) for _, items in columns), default=1))
    row_h, gap = 64, 15
    top_pad = 290
    height = top_pad + rows_per * row_h + (rows_per - 1) * gap + 120
    canvas = _background(height)
    _header(canvas, fonts, eyebrow, title, top=58)
    draw = ImageDraw.Draw(canvas)

    col_w = 364
    col_gap = (WIDTH - 52 * 2 - col_w * 3) / 2
    for col, (heading, items) in enumerate(columns):
        x0 = 52 + col * (col_w + col_gap)
        draw.text((x0, top_pad - 66), heading, font=fonts.get('display', 40, 800), fill=WHITE)
        for index, row in enumerate(items):
            y = top_pad + index * (row_h + gap)
            card = (x0 + 32, y, x0 + col_w, y + row_h)
            draw.rounded_rectangle(card, radius=6, fill=WHITE)
            badge = _badge(fonts, row.get('photo'), row_h + 10, _initials(row['name']))
            canvas.alpha_composite(badge, (int(x0), int(y - 5)))

            value = str(row['value'])
            value_font = fonts.get('display', 26, 900)
            value_w = draw.textlength(value, font=value_font)
            draw.text((card[2] - 18 - value_w, y + (row_h - 26) / 2 - 4), value, font=value_font, fill=NAVY)

            text_x = x0 + row_h + 16
            name = row['short'].upper()
            name_font = fonts.fit(draw, name, card[2] - 40 - value_w - text_x, 19, 800, minimum=12)
            draw.text((text_x, y + 11), name, font=name_font, fill=NAVY)
            logo = _logo(row.get('logo'), 16)
            team_x = text_x
            if logo is not None:
                canvas.alpha_composite(logo, (int(team_x), int(y + 38)))
                team_x += 22
            team_font = fonts.get('body', 14, 650)
            team = row.get('team') or ''
            while team and draw.textlength(team, font=team_font) > card[2] - 40 - value_w - team_x:
                team = team[:-1]
            draw.text((team_x, y + 37), team, font=team_font, fill=MUTED)
    return canvas.convert('RGB')
