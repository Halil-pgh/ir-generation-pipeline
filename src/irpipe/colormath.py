"""Color arithmetic: luminance and contrast (WCAG), blending, and color difference (CIEDE2000).

Colors are ``"#RRGGBB"`` sRGB, as in the LIR. Contrast follows WCAG 2:
relative luminance from linearized sRGB, and the ratio (L1 + 0.05) /
(L2 + 0.05), from 1:1 to 21:1. Color difference is CIEDE2000 (ΔE00) on CIE
Lab under D65: about 1 is the smallest difference people notice side by
side, and colors that should name different things need far more.
"""

import math

type RGB = tuple[float, float, float]
"""Channels from 0 to 1."""


def rgb(hex_color: str) -> RGB:
    """``"#RRGGBB"`` -> channels from 0 to 1."""
    value = hex_color.lstrip("#")
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)


def hex_of(color: RGB) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in color)


def luminance(color: RGB) -> float:
    """WCAG relative luminance, 0 (black) to 1 (white)."""

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: RGB, second: RGB) -> float:
    """WCAG contrast ratio of two colors, from 1 to 21."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def blend(top: RGB, bottom: RGB, alpha: float) -> RGB:
    """``top`` painted over ``bottom`` with opacity ``alpha`` (channel by channel, as SVG does)."""
    r1, g1, b1 = top
    r2, g2, b2 = bottom
    return (
        r1 * alpha + r2 * (1 - alpha),
        g1 * alpha + g2 * (1 - alpha),
        b1 * alpha + b2 * (1 - alpha),
    )


def lab(color: RGB) -> tuple[float, float, float]:
    """CIE Lab (D65) of an sRGB color."""

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in color)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """CIEDE2000 difference of two Lab colors (Sharma, Wu and Dalal, 2005)."""
    l1, a1, b1 = first
    l2, a2, b2 = second
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_mean = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_mean**7 / (c_mean**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0

    dl = l2 - l1
    dc = c2p - c1p
    if c1p * c2p == 0:
        dh_angle = 0.0
    elif abs(h2p - h1p) <= 180:
        dh_angle = h2p - h1p
    else:
        dh_angle = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dh = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh_angle / 2))

    l_mean = (l1 + l2) / 2
    cp_mean = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_mean = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_mean = (h1p + h2p) / 2
    else:
        h_mean = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_mean - 30))
        + 0.24 * math.cos(math.radians(2 * h_mean))
        + 0.32 * math.cos(math.radians(3 * h_mean + 6))
        - 0.20 * math.cos(math.radians(4 * h_mean - 63))
    )
    d_theta = 30 * math.exp(-(((h_mean - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_mean**7 / (cp_mean**7 + 25**7))
    s_l = 1 + 0.015 * (l_mean - 50) ** 2 / math.sqrt(20 + (l_mean - 50) ** 2)
    s_c = 1 + 0.045 * cp_mean
    s_h = 1 + 0.015 * cp_mean * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt(
        (dl / s_l) ** 2 + (dc / s_c) ** 2 + (dh / s_h) ** 2 + r_t * (dc / s_c) * (dh / s_h)
    )
