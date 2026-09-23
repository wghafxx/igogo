"""Offer validation and stability; no input or live screen access."""
from dataclasses import dataclass

from identity import RequestIdentity
from vision import nick_matches, ocr_display_name, ocr_number, ocr_text, slot_empty, visuals_equal


@dataclass
class Observation:
    status: str
    total: int
    message: str
    signature: tuple = ()
    visual: object = None


def grid_cells(frame, cfg, key="their_grid"):
    grid = frame.grab(cfg.reg[key])
    height, width = grid.shape[:2]
    return [grid[round(r*height/3):round((r+1)*height/3), round(c*width/3):round((c+1)*width/3)]
            for r in range(3) for c in range(3)]


def cell_top(cell):
    return cell[:max(1, int(cell.shape[0]*0.35)), :]


def read_total(frame, cfg, key):
    return ocr_number(frame.grab(cfg.reg[key]), cfg.tess)


def inspect_offer(frame, cfg, expected_nick):
    if not isinstance(expected_nick, RequestIdentity) or not expected_nick.complete:
        return Observation("wait", 0, "Нет связки @username + верхнее имя из запроса; ACCEPT запрещён")
    if not nick_matches(expected_nick.username, cfg.only):
        return Observation("decline", 0, f"Username @{expected_nick.username} не разрешён")
    partner = ocr_display_name(frame.grab(cfg.reg["partner_name"]), cfg.tess, cfg.lang)
    if not partner:
        return Observation("wait", 0, "Не читается верхнее имя партнёра; ACCEPT запрещён")
    if partner != expected_nick.display_name:
        return Observation("decline", 0, f"Имя в трейде {partner!r} не совпадает с именем запроса {expected_nick.display_name!r} (@{expected_nick.username})")
    our = read_total(frame, cfg, "our_total")
    if our is None:
        return Observation("wait", 0, "Не читается наша сумма; ACCEPT запрещён")
    if our != 0:
        return Observation("decline", 0, f"НАША СТОРОНА НЕ ПУСТА: {our}")
    if not all(slot_empty(cell, cfg.T("plus"), cfg.thr_of("plus", 0.8)) for cell in grid_cells(frame, cfg, "our_grid")):
        return Observation("wait", 0, "Не подтверждена пустота всех наших слотов")
    page = "unchecked"
    if cfg.strict_page:
        text = ocr_text(frame.grab(cfg.reg["pager"]), None, 7, cfg.tess, cfg.lang)
        page = "".join((text or "").split())
        if not page:
            return Observation("wait", 0, "Пагинация не прочитана; ACCEPT запрещён")
        if page != "1/1":
            return Observation("decline", 0, f"Не подтверждена единственная страница: {page}")
    their = read_total(frame, cfg, "their_total")
    if their is None or their == 0:
        return Observation("wait", 0, "Жду предметы/полную читаемую сумму партнёра")
    values = []
    for cell in grid_cells(frame, cfg):
        if slot_empty(cell, cfg.T("plus"), cfg.thr_of("plus", 0.8)):
            values.append(0)
        else:
            rap = ocr_number(cell_top(cell), cfg.tess)
            if rap is None or rap == 0:
                return Observation("wait", their, "RAP занятого слота не прочитан")
            values.append(rap)
    filled = [value for value in values if value]
    if len(filled) > cfg.max_items:
        return Observation("decline", their, f"Предметов {len(filled)} > {cfg.max_items}")
    bad = [value for value in filled if value not in cfg.white]
    if bad:
        return Observation("decline", their, f"Недопустимые RAP: {bad}")
    total = sum(filled)
    if not filled or total < cfg.min_total:
        return Observation("wait", total, f"Сумма {total} меньше минимума {cfg.min_total}")
    if cfg.match_total and total != their:
        return Observation("wait", their, f"Сумма слотов {total} не совпадает с Total RAP {their}")
    # Keep full resolution; a 72px reduction can hide a same-RAP item substitution.
    visual = frame.grab(cfg.reg["their_grid"]).copy()
    return Observation("ok", total, f"Проверено: {len(filled)} предметов, сумма {total}",
                       (expected_nick.username, partner, our, their, page, tuple(values)), visual)


def same_offer(previous, current):
    return (previous is not None and current is not None and previous.status == current.status == "ok"
            and previous.signature == current.signature and visuals_equal(previous.visual, current.visual))