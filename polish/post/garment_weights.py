"""Weight corrections in the model's metre-based, Y-up bind space."""
import numpy as np


def smoothstep(x):
    t = np.clip(x, 0, 1)
    return t * t * (3 - 2 * t)


def tip_influence(points, center):
    """Measure each angular sector independently, so bangs and nape keep different tip lengths."""
    polar = np.arctan2(points[:, 0] - center[0], points[:, 2] - center[2])
    fractions = []
    for angle in np.arange(16) * (2 * np.pi / 16):
        distance = np.abs(np.angle(np.exp(1j * (polar - angle))))
        sector = points[distance <= np.pi / 8, 1]
        if len(sector) < 8:
            sector = points[:, 1]
        low, high = np.percentile(sector, [1, 99])
        fractions.append((low, high))
    phase = np.mod(polar, 2 * np.pi) * 16 / (2 * np.pi)
    i = phase.astype(int) % 16
    t = (phase - np.floor(phase))[:, None]
    bounds = np.array(fractions)[i] * (1 - t) + np.array(fractions)[(i + 1) % 16] * t
    length = np.maximum(.001, bounds[:, 1] - bounds[:, 0])
    return smoothstep((bounds[:, 0] + .26 * length - points[:, 1]) / (.22 * length))


def blend_crotch(points, center, seam, hip, half_span):
    """Return the affected fraction and anatomical leg/hips mix for a measured trouser seam."""
    lateral = (points[:, 0] - center) / half_span
    rise = max(hip - seam, .01)
    height = (points[:, 1] - seam) / rise
    influence = (1 - smoothstep((abs(lateral) - .16) / .72)) * smoothstep((height + .19) / .28) * (1 - smoothstep((height - .82) / .30))
    pelvis = smoothstep((height + .28) / 1.07)
    left = smoothstep((lateral + .48) / .96)
    return influence, np.c_[pelvis, (1 - pelvis) * left, (1 - pelvis) * (1 - left)]
