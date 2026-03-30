"""
Service de filigrane automatique — EYE-FONCIER
Applique un watermark sur les images des parcelles :
  - Logo EYE-FONCIER en bas a droite
  - Nom du site "eye-foncier.com" en bas au centre
"""
import logging
import os

from django.conf import settings
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

logger = logging.getLogger(__name__)

# Extensions image supportees
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".jfif"}


def is_image_file(file_path):
    """Verifie si le fichier est une image supportee."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in IMAGE_EXTENSIONS


def _get_logo():
    """Charge le logo EYE-FONCIER depuis les fichiers statiques."""
    logo_path = os.path.join(settings.BASE_DIR, "static", "img", "logo.png")
    if not os.path.isfile(logo_path):
        logo_path = os.path.join(settings.BASE_DIR, "logo.png")
    if os.path.isfile(logo_path):
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception as e:
            logger.warning("Impossible de charger le logo : %s", e)
    return None


def _get_font(size):
    """Retourne une police TTF Bold pour le texte du watermark."""
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
        "ArialBold.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def apply_watermark(image_path):
    """
    Applique le filigrane EYE-FONCIER sur une image (in-place).

    Le filigrane comprend :
    - Un bandeau degrade noir semi-transparent en bas
    - Le logo EYE-FONCIER en bas a droite
    - Le texte "eye-foncier.com" en bas au centre

    Args:
        image_path: Chemin absolu vers le fichier image

    Returns:
        bool: True si le watermark a ete applique, False sinon
    """
    if not os.path.isfile(image_path):
        logger.warning("Fichier introuvable : %s", image_path)
        return False

    if not is_image_file(image_path):
        logger.debug("Fichier non-image ignore : %s", image_path)
        return False

    try:
        original = Image.open(image_path)
        width, height = original.size

        if original.mode != "RGBA":
            image = original.convert("RGBA")
        else:
            image = original.copy()

        # ── Settings ──
        logo_opacity = getattr(settings, "IMAGE_WATERMARK_LOGO_OPACITY", 200)
        logo_ratio = getattr(settings, "IMAGE_WATERMARK_LOGO_RATIO", 0.15)

        # ═══ 1. Bandeau bas semi-transparent ═══
        banner_h = max(int(height * 0.08), 40)
        overlay_bottom = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bottom_draw = ImageDraw.Draw(overlay_bottom)

        # Fond degrade noir semi-transparent en bas
        for i in range(banner_h):
            alpha = int(140 * (i / banner_h))
            bottom_draw.line(
                [(0, height - banner_h + i), (width, height - banner_h + i)],
                fill=(0, 0, 0, alpha),
            )
        image = Image.alpha_composite(image, overlay_bottom)

        # ═══ 2. Logo EYE-FONCIER en bas a droite ═══
        overlay_elements = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        logo = _get_logo()
        margin = max(int(min(width, height) * 0.025), 10)

        if logo:
            logo_width = max(int(width * logo_ratio), 60)
            logo_height = int(logo_width * logo.height / logo.width)
            logo_resized = logo.resize((logo_width, logo_height), Image.LANCZOS)

            # Opacite via canal alpha
            r, g, b, a = logo_resized.split()
            a = ImageEnhance.Brightness(a).enhance(logo_opacity / 255.0)
            logo_semi = Image.merge("RGBA", (r, g, b, a))

            pos_x = width - logo_width - margin
            pos_y = height - logo_height - margin
            overlay_elements.paste(logo_semi, (pos_x, pos_y), logo_semi)

        image = Image.alpha_composite(image, overlay_elements)

        # ═══ 3. Texte "eye-foncier.com" en bas centre ═══
        overlay_url = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        url_draw = ImageDraw.Draw(overlay_url)
        url_font_size = max(int(min(width, height) * 0.03), 12)
        url_font = _get_font(url_font_size)
        url_text = "eye-foncier.com"
        url_bbox = url_draw.textbbox((0, 0), url_text, font=url_font)
        url_w = url_bbox[2] - url_bbox[0]
        url_x = (width - url_w) // 2
        url_y = height - margin - url_font_size
        # Ombre
        url_draw.text(
            (url_x + 1, url_y + 1), url_text, font=url_font,
            fill=(0, 0, 0, 150),
        )
        # Texte blanc
        url_draw.text(
            (url_x, url_y), url_text, font=url_font,
            fill=(255, 255, 255, 230),
        )
        image = Image.alpha_composite(image, overlay_url)

        # ═══ Sauvegarder ═══
        ext = os.path.splitext(image_path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            image.convert("RGB").save(image_path, "JPEG", quality=92, optimize=True)
        elif ext == ".webp":
            image.save(image_path, "WEBP", quality=90)
        else:
            image.save(image_path, "PNG", optimize=True)

        logger.info("Filigrane applique : %s", os.path.basename(image_path))
        return True

    except Exception as e:
        logger.error("Erreur watermark sur %s : %s", image_path, e, exc_info=True)
        return False
