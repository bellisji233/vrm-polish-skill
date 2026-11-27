"""Find the largest horizontal gain that keeps the entire lip rim within a width."""
import numpy as np


def horizontal_gain(rest, motion, limit):
    if np.ptp(rest + motion) <= limit + 1e-8:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(32):
        mid = (low + high) / 2
        if np.ptp(rest + mid * motion) <= limit:
            low = mid
        else:
            high = mid
    return low
