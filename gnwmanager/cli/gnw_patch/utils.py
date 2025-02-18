from math import ceil

def round_down_word(val):
    return (val // 4) * 4


def round_up_word(val):
    return ceil(val / 4) * 4


def round_down_page(val):
    return (val // 4096) * 4096


def round_up_page(val):
    return ceil(val / 4096) * 4096


def seconds_to_frames(seconds):
    return int(round(60 * seconds))
