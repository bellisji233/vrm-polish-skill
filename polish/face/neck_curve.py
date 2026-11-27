"""Reshape a covered neck stump between its collar and jaw attachment rings."""
import numpy as np


def fit_column(points, attachment, vertical, side_weight):
    """Keep both attachment rows and continue the jaw tangent into the loft."""
    result = np.asarray(points, dtype=float).copy()
    start, end = result[0], result[attachment]
    height = end[vertical] - start[vertical]
    if height <= 0 or attachment < 3:
        raise ValueError("Neck collar and jaw rows overlap. Check the assembly height.")
    horizontal = [axis for axis in range(3) if axis != vertical]
    delta = end[horizontal] - start[horizontal]
    # Lateral sections taper above the collar. The front has a shallow throat
    # hollow that gradually opens into the jaw, instead of copying stump ridges.
    for j in range(1, attachment):
        t = j / attachment
        curve = (1 - side_weight) * t + side_weight * (1 - (1 - t) ** 3)
        result[j, horizontal] = start[horizontal] + curve * delta
        forward = (result[attachment + 1, horizontal] - end[horizontal])
        length = np.linalg.norm(forward)
        if length > 1e-7:
            hollow = height * (0.075 + 0.035 * side_weight) * 4 * t * (1 - t)
            result[j, horizontal] -= hollow * forward / length
        result[j, vertical] = start[vertical] + height * (t + 0.18 * t * (1 - t))
    return result
