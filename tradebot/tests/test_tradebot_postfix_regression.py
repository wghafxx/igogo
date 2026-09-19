"""Post-fix regression tests for click safety, queue draining, identity pairing, and read-only modes."""

# Modules/features covered: bot.guarded_click/handle_list/close_list/main, mouse.click release safety,
# configuration migration checks, journal pending-protection, and inspect_offer identity pairing.

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import py_compile
import pytest
import yaml

import bot
import calibrate
import configuration
import debug_vision
import desktop
from identity import RequestIdentity
from journal import Journal
import mouse
import offer
from vision import Frame


class DummyScreen:
    def __init__(self, frames):
        self._frames = list(frames)
        self.hwnd = 123
        self.rect = SimpleNamespace(left=0, top=0, width=300, height=200)

    def snapshot(self):
        if not self._frames:
            raise RuntimeError("No more frames")
        return self._frames.pop(0)


class DummyCfg:
    def __init__(self, template_dir: Path):
        self.tpl = template_dir
        self.max_age = 10
        self.tess = ""
        self.lang = "eng"
        self.only = {"ysrent3", "vashtestnick"}
        self.retry = 0.01
        self.reg = {
            "person": [0.05, 0.05, 0.20, 0.22],
            "row_accept": [0.50, 0.40, 0.80, 0.72],
            "row_decline": [0.22, 0.40, 0.48, 0.72],
            "close": [0.90, 0.05, 0.98, 0.18],
            "accept_trade": [0.50, 0.40, 0.80, 0.72],
            "decline_trade": [0.22, 0.40, 0.48, 0.72],
            "trade_anchor": [0.01, 0.01, 0.08, 0.08],
            "list_anchor": [0.78, 0.05, 0.88, 0.12],
            "row_nick": [0.05, 0.40, 0.48, 0.72],
            "row_display": [0.05, 0.33, 0.48, 0.40],
            "partner_name": [0.05, 0.10, 0.35, 0.18],
            "our_total": [0.05, 0.80, 0.20, 0.90],
            "their_total": [0.70, 0.80, 0.95, 0.90],
            "our_grid": [0.05, 0.20, 0.45, 0.75],
            "their_grid": [0.55, 0.20, 0.95, 0.75],
            "pager": [0.45, 0.92, 0.55, 0.99],
        }

    def T(self, name):
        return self.tpl / f"{name}.png"

    def thr_of(self, _name, default=0.85):
        return default

    def check_size(self, _frame):
        return None


def _mk_frame(image):
    return Frame(image.copy(), left=0, top=0)


def _write(path: Path, image: np.ndarray):
    assert cv2.imwrite(str(path), image)


def _crop_to_template(path: Path, image: np.ndarray, x1: int, y1: int, x2: int, y2: int):
    crop = image[y1:y2, x1:x2].copy()
    assert crop.size > 0
    assert cv2.imwrite(str(path), crop)


def _scene_base():
    scene = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(scene, (20, 66), (120, 82), (40, 40, 40), -1)   # row_display
    cv2.rectangle(scene, (20, 90), (120, 150), (35, 35, 35), -1)  # row_nick
    cv2.rectangle(scene, (235, 8), (264, 26), (180, 180, 180), -1)  # list_anchor
    cv2.rectangle(scene, (16, 10), (52, 38), (30, 150, 220), -1)  # person
    cv2.circle(scene, (34, 18), 5, (220, 220, 220), -1)
    cv2.rectangle(scene, (27, 24), (41, 35), (220, 220, 220), -1)
    return scene


def _draw_button(scene, x1, y1, x2, y2, bgr, inner=(255, 255, 255), variant="accept"):
    out = scene.copy()
    cv2.rectangle(out, (x1, y1), (x2, y2), bgr, -1)
    if variant == "accept":
        cv2.line(out, (x1 + 8, y1 + 18), (x1 + 20, y2 - 8), inner, 2)
        cv2.line(out, (x1 + 20, y2 - 8), (x2 - 8, y1 + 8), inner, 2)
    elif variant == "decline":
        cv2.line(out, (x1 + 8, y1 + 8), (x2 - 8, y2 - 8), inner, 2)
        cv2.line(out, (x2 - 8, y1 + 8), (x1 + 8, y2 - 8), inner, 2)
    elif variant == "block":
        cv2.circle(out, ((x1 + x2) // 2, (y1 + y2) // 2), 12, inner, 2)
        cv2.line(out, (x1 + 10, y2 - 10), (x2 - 10, y1 + 10), inner, 2)
    elif variant == "close":
        cv2.line(out, (x1 + 4, y1 + 4), (x2 - 4, y2 - 4), inner, 2)
        cv2.line(out, (x2 - 4, y1 + 4), (x1 + 4, y2 - 4), inner, 2)
    else:
        cv2.rectangle(out, (x1 + 4, y1 + 4), (x2 - 4, y2 - 4), inner, 1)
    return out


@pytest.fixture
def patched_click_runtime(monkeypatch):
    events = []
    state = {"x": 0, "y": 0, "displaced": False}

    monkeypatch.setattr(desktop, "pause", lambda *_: None)
    monkeypatch.setattr(desktop, "check_stop", lambda: None)
    monkeypatch.setattr(desktop, "guard_target", lambda *_: True)

    def fake_move(x, y, duration=0.25, guard=None):
        if guard and not guard():
            raise mouse.ClickCancelled("guard failed")
        state["x"], state["y"] = x, y

    def fake_cursor_pos():
        if state["displaced"]:
            return state["x"] + 10, state["y"] + 10
        return state["x"], state["y"]

    monkeypatch.setattr(mouse, "move", fake_move)
    monkeypatch.setattr(mouse, "cursor_pos", fake_cursor_pos)
    monkeypatch.setattr(mouse, "_button", lambda down: events.append("down" if down else "up"))

    return events, state


def test_guarded_click_positive_first_two_actions_send_down_up(tmp_path, monkeypatch, patched_click_runtime):
    events, _state = patched_click_runtime
    cfg = DummyCfg(tmp_path)
    base = _scene_base()
    person_scene = base.copy()
    accept_scene = _draw_button(base, 160, 86, 240, 126, (60, 200, 60), variant="accept")
    _crop_to_template(cfg.T("person"), person_scene, 16, 10, 53, 39)
    _crop_to_template(cfg.T("accept"), accept_scene, 160, 86, 241, 127)
    _crop_to_template(cfg.T("list_anchor"), accept_scene, 235, 8, 265, 27)

    monkeypatch.setattr(bot, "log", lambda *_: None)

    person_hit = bot.locate(_mk_frame(person_scene), cfg, "person")
    assert person_hit is not None
    ok_person = bot.guarded_click(DummyScreen([_mk_frame(person_scene), _mk_frame(person_scene)]), cfg, "person", person_hit,
                                  condition=lambda _f: True)
    assert ok_person is True

    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    accept_hit = bot.locate(_mk_frame(accept_scene), cfg, "accept")
    assert accept_hit is not None
    ok_accept = bot.guarded_click(DummyScreen([_mk_frame(accept_scene), _mk_frame(accept_scene)]), cfg, "accept", accept_hit,
                                  condition=lambda _f: True)
    assert ok_accept is True

    assert events[:4] == ["down", "up", "down", "up"]


def test_guarded_click_brightness_only_hover_accept_allows_click(tmp_path, monkeypatch, patched_click_runtime):
    events, _state = patched_click_runtime
    cfg = DummyCfg(tmp_path)
    normal = _draw_button(_scene_base(), 160, 86, 240, 126, (60, 200, 60), variant="accept")
    hover = _draw_button(_scene_base(), 156, 84, 244, 128, (80, 220, 80), variant="accept")
    _crop_to_template(cfg.T("accept"), normal, 160, 86, 241, 127)
    _crop_to_template(cfg.T("list_anchor"), normal, 235, 8, 265, 27)

    monkeypatch.setattr(bot, "log", lambda *_: None)
    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    hit = bot.locate(_mk_frame(normal), cfg, "accept")
    assert hit is not None

    ok = bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(hover)]), cfg, "accept", hit, condition=lambda _f: True)
    assert ok is True
    assert events == ["down", "up"]


def test_guarded_click_negative_disabled_or_wrong_controls_do_not_press(tmp_path, monkeypatch, patched_click_runtime):
    events, state = patched_click_runtime
    cfg = DummyCfg(tmp_path)
    normal = _draw_button(_scene_base(), 160, 86, 240, 126, (60, 200, 60), variant="accept")
    disabled_gray = _draw_button(_scene_base(), 160, 86, 240, 126, (150, 150, 150), variant="accept")
    red_accept = _draw_button(_scene_base(), 160, 86, 240, 126, (60, 60, 220), variant="accept")
    moved = _draw_button(_scene_base(), 180, 98, 260, 138, (60, 200, 60), variant="accept")
    _crop_to_template(cfg.T("accept"), normal, 160, 86, 241, 127)
    _crop_to_template(cfg.T("list_anchor"), normal, 235, 8, 265, 27)

    monkeypatch.setattr(bot, "log", lambda *_: None)
    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    hit = bot.locate(_mk_frame(normal), cfg, "accept")
    assert hit is not None

    assert bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(disabled_gray)]), cfg, "accept", hit, condition=lambda _f: True) is False
    assert bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(red_accept)]), cfg, "accept", hit, condition=lambda _f: True) is False
    assert bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(moved)]), cfg, "accept", hit, condition=lambda _f: True) is False

    with pytest.raises(mouse.ClickCancelled):
        monkeypatch.setattr(desktop, "guard_target", lambda *_: False)
        bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(normal)]), cfg, "accept", hit, condition=lambda _f: True)

    monkeypatch.setattr(desktop, "guard_target", lambda *_: True)
    state["displaced"] = True
    assert bot.guarded_click(DummyScreen([_mk_frame(normal), _mk_frame(normal)]), cfg, "accept", hit, condition=lambda _f: True) is False
    assert events == []


def test_guarded_click_wrong_decline_label_block_not_pressed(tmp_path, monkeypatch, patched_click_runtime):
    events, _state = patched_click_runtime
    cfg = DummyCfg(tmp_path)
    decline = _draw_button(_scene_base(), 66, 86, 138, 128, (70, 70, 220), variant="decline")
    block = _draw_button(_scene_base(), 66, 86, 138, 128, (70, 70, 220), variant="block")
    _crop_to_template(cfg.T("decline"), decline, 66, 86, 139, 129)
    _crop_to_template(cfg.T("list_anchor"), decline, 235, 8, 265, 27)

    monkeypatch.setattr(bot, "log", lambda *_: None)
    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    hit = bot.locate(_mk_frame(decline), cfg, "decline")
    assert hit is not None
    assert bot.guarded_click(DummyScreen([_mk_frame(decline), _mk_frame(block)]), cfg, "decline", hit, condition=lambda _f: True) is False
    assert events == []


def test_guarded_click_rechecks_both_names_and_offer_visual(tmp_path, monkeypatch, patched_click_runtime):
    events, _state = patched_click_runtime
    cfg = DummyCfg(tmp_path)
    accept = _draw_button(_scene_base(), 160, 86, 240, 126, (60, 200, 60), variant="accept")
    _crop_to_template(cfg.T("accept"), accept, 160, 86, 241, 127)
    _crop_to_template(cfg.T("list_anchor"), accept, 235, 8, 265, 27)
    _crop_to_template(cfg.T("accept_trade"), accept, 160, 86, 241, 127)

    changed_names = accept.copy()
    cv2.rectangle(changed_names, (20, 66), (120, 82), (190, 190, 190), -1)
    hit = bot.locate(_mk_frame(accept), cfg, "accept")
    assert hit is not None
    monkeypatch.setattr(bot, "log", lambda *_: None)
    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    assert bot.guarded_click(DummyScreen([_mk_frame(accept), _mk_frame(changed_names)]), cfg, "accept", hit, condition=lambda _f: True) is False

    class TradeCfg(DummyCfg):
        def __init__(self, template_dir):
            super().__init__(template_dir)
            self.reg["trade_anchor"] = [0.01, 0.01, 0.08, 0.08]
            self.reg["their_grid"] = [0.55, 0.20, 0.95, 0.75]

    trade_cfg = TradeCfg(tmp_path)
    trade_before = accept.copy()
    cv2.rectangle(trade_before, (5, 5), (23, 18), (120, 220, 220), -1)  # trade anchor
    trade_after = trade_before.copy()
    cv2.rectangle(trade_after, (170, 90), (230, 120), (10, 10, 10), -1)  # offer changed
    trade_hit = bot.locate(_mk_frame(trade_before), trade_cfg, "accept_trade")
    assert trade_hit is not None
    assert bot.guarded_click(DummyScreen([_mk_frame(trade_before), _mk_frame(trade_after)]), trade_cfg,
                             "accept_trade", trade_hit, condition=lambda _f: True) is False
    assert events == []


def test_handle_list_drains_25_rows_until_empty_and_retries_transient_failures(monkeypatch):
    cfg = SimpleNamespace(retry=0.001, only={"ysrent3"})
    screen = SimpleNamespace()
    actions = []
    state = {"idx": 0, "captures": 0}

    rows = [
        RequestIdentity("", ""),  # unreadable
        RequestIdentity("bad1", "d1"),  # missing button retry
        RequestIdentity("bad1", "d1"),  # guard cancelled retry
    ] + [RequestIdentity(f"bad{i}", f"name{i}") for i in range(2, 25)]

    def capture_bounded(*_):
        state["captures"] += 1
        assert state["captures"] < 100, "Test scene did not advance; do not leave a never-ending fake queue"
        return object()

    monkeypatch.setattr(bot, "capture", capture_bounded)
    monkeypatch.setattr(bot, "list_open", lambda *_: True)

    empty_counter = {"n": 0}
    transient = {"missing_done": False}

    def fake_row_empty(_frame, _cfg, identity=None):
        if state["idx"] < len(rows):
            return False
        empty_counter["n"] += 1
        return True

    def fake_read_request(_frame, _cfg):
        if state["idx"] < len(rows):
            return rows[state["idx"]]
        return RequestIdentity("", "")

    def fake_locate(_frame, _cfg, name, region=None):
        if name == "accept":
            return (100, 100, 0.9)
        if name == "decline":
            if state["idx"] == 1 and not transient["missing_done"]:
                transient["missing_done"] = True
                return None
            return (70, 100, 0.9)
        return None

    def fake_guarded_click(_screen, _cfg, action, hit, condition=None, on_press=None):
        actions.append((state["idx"], action, bool(hit)))
        if state["idx"] == 2:
            state["idx"] += 1
            return False
        state["idx"] += 1
        return True

    monkeypatch.setattr(bot, "row_empty", fake_row_empty)
    monkeypatch.setattr(bot, "read_request", fake_read_request)
    monkeypatch.setattr(bot, "locate", fake_locate)
    monkeypatch.setattr(bot, "nick_matches", lambda nick, allowed: nick if nick in allowed else None)
    monkeypatch.setattr(bot, "guarded_click", fake_guarded_click)
    monkeypatch.setattr(bot, "wait_state", lambda *_args, **_kwargs: object())
    def advance_unreadable_frame(*_):
        if state["idx"] == 0:
            state["idx"] = 1

    monkeypatch.setattr(desktop, "pause", advance_unreadable_frame)
    monkeypatch.setattr(bot, "log", lambda *_: None)

    result = bot.handle_list(screen, cfg)
    assert result == "empty"
    assert state["idx"] == len(rows)
    assert empty_counter["n"] >= 3
    assert len([a for a in actions if a[1] == "decline"]) >= 23


def test_close_list_blocked_when_new_request_arrives(monkeypatch):
    cfg = SimpleNamespace(reg={})
    screen = SimpleNamespace()
    clicks = []

    monkeypatch.setattr(bot, "capture", lambda *_: object())
    monkeypatch.setattr(bot, "list_open", lambda *_: True)
    monkeypatch.setattr(bot, "locate", lambda _f, _c, name, region=None: (10, 10, 0.9) if name in {"close", "accept"} else None)
    monkeypatch.setattr(bot, "row_empty", lambda *_: True)
    monkeypatch.setattr(bot, "wait_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "guarded_click", lambda *_args, **_kwargs: clicks.append("close") or False)
    monkeypatch.setattr(bot, "log", lambda *_: None)

    bot.close_list(screen, cfg)
    assert clicks == ["close"]


def test_offer_identity_pairing_username_authorizes_but_display_mismatch_declines(monkeypatch):
    frame = SimpleNamespace(grab=lambda _r: np.zeros((20, 20, 3), dtype=np.uint8))
    cfg = SimpleNamespace(
        reg={"partner_name": [0, 0, 1, 1], "our_total": [0, 0, 1, 1], "their_total": [0, 0, 1, 1],
             "our_grid": [0, 0, 1, 1], "their_grid": [0, 0, 1, 1], "pager": [0, 0, 1, 1]},
        tess="", lang="eng", only={"ysrent3"}, strict_page=False, max_items=9,
        white={100}, min_total=10, match_total=False, T=lambda _name: Path("/tmp/x.png"), thr_of=lambda *_a, **_k: 0.8,
    )
    monkeypatch.setattr(offer, "ocr_display_name", lambda *_: "cool panda")
    monkeypatch.setattr(offer, "read_total", lambda *_: 0)
    monkeypatch.setattr(offer, "grid_cells", lambda *_args, **_kwargs: [np.zeros((10, 10, 3), dtype=np.uint8)] * 9)
    monkeypatch.setattr(offer, "slot_empty", lambda *_args, **_kwargs: True)

    ok_identity = RequestIdentity("ysrent3", "Cool Panda")
    mismatch_display = RequestIdentity("ysrent3", "Other")
    same_display_other_user = RequestIdentity("another_user", "Cool Panda")

    a = offer.inspect_offer(frame, cfg, ok_identity)
    b = offer.inspect_offer(frame, cfg, mismatch_display)
    c = offer.inspect_offer(frame, cfg, same_display_other_user)
    d = offer.inspect_offer(frame, cfg, RequestIdentity("", "Cool Panda"))

    assert a.status == "wait" and "жду предметы" in a.message.lower()
    assert b.status == "decline" and "не совпадает" in b.message.lower()
    assert c.status == "decline" and "не разрешён" in c.message.lower()
    assert d.status == "wait" and "accept запрещён" in d.message.lower()


def test_offer_identity_pairing_authorized_safe_offer_reaches_ok(monkeypatch):
    frame = SimpleNamespace(grab=lambda _r: np.zeros((20, 20, 3), dtype=np.uint8))
    cfg = SimpleNamespace(
        reg={"partner_name": [0, 0, 1, 1], "our_total": [0, 0, 1, 1], "their_total": [0, 0, 1, 1],
             "our_grid": [0, 0, 1, 1], "their_grid": [0, 0, 1, 1], "pager": [0, 0, 1, 1]},
        tess="", lang="eng", only={"whitelisted42"}, strict_page=False, max_items=9,
        white={42}, min_total=1, match_total=True, T=lambda _name: Path("/tmp/x.png"), thr_of=lambda *_a, **_k: 0.8,
    )

    empty_cell = np.zeros((10, 10, 3), dtype=np.uint8)
    occupied_cell = np.full((10, 10, 3), 255, dtype=np.uint8)
    our_cells = [empty_cell.copy() for _ in range(9)]
    their_cells = [occupied_cell.copy()] + [empty_cell.copy() for _ in range(8)]

    monkeypatch.setattr(offer, "ocr_display_name", lambda *_: "cool panda")
    monkeypatch.setattr(offer, "read_total", lambda _f, _c, key: 0 if key == "our_total" else 42)
    monkeypatch.setattr(offer, "grid_cells", lambda _f, _c, key="their_grid": our_cells if key == "our_grid" else their_cells)
    monkeypatch.setattr(offer, "slot_empty", lambda cell, *_args, **_kwargs: bool(np.array_equal(cell, empty_cell)))
    monkeypatch.setattr(offer, "ocr_number", lambda *_: 42)

    observed = offer.inspect_offer(frame, cfg, RequestIdentity("whitelisted42", "Cool Panda"))
    assert observed.status == "ok"
    assert observed.total == 42


def test_journal_stores_both_names_and_blocks_pending(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("only_nicks: [ysrent3]\n", encoding="utf-8")
    journal = Journal(cfg_path)

    journal.begin("ysrent3", 123, "Cool Panda")
    state = journal.read()
    assert state["pending"] is True
    assert state["nick"] == "ysrent3"
    assert state["display_name"] == "Cool Panda"

    with pytest.raises(RuntimeError):
        journal.ensure_clear()

    journal.complete("ui_success")
    assert journal.read()["pending"] is False


def test_mouse_click_exception_while_down_always_releases(monkeypatch):
    events = []
    monkeypatch.setattr(desktop, "check_stop", lambda: None)
    monkeypatch.setattr(desktop, "pause", lambda *_: None)
    monkeypatch.setattr(mouse, "move", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mouse, "cursor_pos", lambda: (50, 50))

    state = {"raised": False}

    def flaky_button(down):
        events.append("down" if down else "up")
        if down and not state["raised"]:
            state["raised"] = True
            raise RuntimeError("driver error")

    monkeypatch.setattr(mouse, "_button", flaky_button)
    monkeypatch.setattr(mouse, "_mode", "interception")

    with pytest.raises(RuntimeError):
        mouse.click(50, 50, guard=lambda: True, before_press=lambda: True)
    assert events == ["down", "up"]


def test_cfg_v2_migration_message_and_invalid_fields(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir(parents=True)
    for name in configuration.REQUIRED_TEMPLATES:
        _write(template_dir / f"{name}.png", np.full((20, 40, 3), 180, dtype=np.uint8))

    cfg_v2 = {
        "only_nicks": ["ysrent3"],
        "whitelist_rap": [42],
        "calibration_version": 2,
        "screen": {"w": 300, "h": 200, "coordinate_space": "client"},
        "regions": {k: [0.1, 0.1, 0.2, 0.2] for k in configuration.REQUIRED_REGIONS},
        "templates_dir": "templates",
    }
    path_v2 = tmp_path / "v2.yaml"
    path_v2.write_text(yaml.safe_dump(cfg_v2, allow_unicode=True), encoding="utf-8")
    with pytest.raises(configuration.ConfigError, match="--names-only"):
        configuration.Cfg(path_v2)

    cfg_bad = cfg_v2 | {"calibration_version": 3, "only_nicks": "ysrent3"}
    path_bad = tmp_path / "bad.yaml"
    path_bad.write_text(yaml.safe_dump(cfg_bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(configuration.ConfigError, match="only_nicks"):
        configuration.Cfg(path_bad)


def test_calibrate_names_cancel_preserves_original_files(tmp_path, monkeypatch):
    source_tpl = tmp_path / "templates" / "old"
    source_tpl.mkdir(parents=True)
    for name in (*configuration.REQUIRED_TEMPLATES, "badge"):
        _write(source_tpl / f"{name}.png", np.full((20, 40, 3), 180, dtype=np.uint8))

    cfg_path = tmp_path / "config.yaml"
    cfg = {
        "only_nicks": ["ysrent3"],
        "whitelist_rap": [42],
        "calibration_version": 3,
        "screen": {"w": 300, "h": 200, "coordinate_space": "client"},
        "regions": {k: [0.1, 0.1, 0.2, 0.2] for k in configuration.REQUIRED_REGIONS},
        "templates_dir": "templates/old",
    }
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    original = cfg_path.read_text(encoding="utf-8")

    monkeypatch.setattr(desktop, "require_windows", lambda: None)
    monkeypatch.setattr(desktop, "activate_roblox", lambda *_: True)

    class FakeScreen:
        hwnd = 123

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(calibrate, "Screen", lambda: FakeScreen())
    monkeypatch.setattr(calibrate, "snap", lambda *_args, **_kwargs: SimpleNamespace(w=300, h=200, image=np.zeros((200, 300, 3), dtype=np.uint8)))

    def cancel_select(*_args, **_kwargs):
        raise calibrate.CalibrationCancelled("cancel")

    monkeypatch.setattr(calibrate, "select", cancel_select)

    with pytest.raises(calibrate.CalibrationCancelled):
        calibrate.calibrate_names(cfg_path)

    assert cfg_path.read_text(encoding="utf-8") == original
    assert (tmp_path / "templates" / "old").exists()


def test_main_check_and_dry_run_are_read_only(monkeypatch, tmp_path):
    events = {"mouse_configure": 0, "inspect": 0}

    class FakeCfg:
        path = tmp_path / "config.yaml"
        tess = ""
        lang = "eng"
        only = {"ysrent3"}

        def T(self, name):
            return tmp_path / f"{name}.png"

    class FakeScreen:
        hwnd = 1
        rect = (0, 0, 300, 200)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    class FakeSI:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(bot, "setup_logging", lambda: None)
    monkeypatch.setattr(bot, "Cfg", lambda _p: FakeCfg())
    monkeypatch.setattr(bot.desktop, "SingleInstance", FakeSI)
    monkeypatch.setattr(bot, "focus", lambda _cfg: None)
    monkeypatch.setattr(bot, "Screen", lambda: FakeScreen())
    monkeypatch.setattr(bot, "capture", lambda *_: object())
    monkeypatch.setattr(bot, "trade_open", lambda *_: True)
    monkeypatch.setattr(bot, "check_ocr", lambda *_: "ok")
    monkeypatch.setattr(bot, "log", lambda *_: None)
    monkeypatch.setattr(bot.mouse, "configure", lambda *_args, **_kwargs: events.__setitem__("mouse_configure", events["mouse_configure"] + 1))
    monkeypatch.setattr(bot, "inspect_offer", lambda *_args, **_kwargs: events.__setitem__("inspect", events["inspect"] + 1) or SimpleNamespace(status="wait", message="x"))

    assert bot.main(["--check"]) == 0
    assert events["mouse_configure"] == 0

    assert bot.main(["--dry-run", "--expected-username", "ysrent3", "--expected-display-name", "Cool Panda"]) == 0
    assert events["inspect"] == 1
    assert events["mouse_configure"] == 0


def test_imports_help_and_compile(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        bot.main(["--help"])
    assert exc.value.code == 0

    monkeypatch.setattr(desktop, "require_windows", lambda: None)
    monkeypatch.setattr(configuration, "Cfg", lambda *_: SimpleNamespace(reg={}, tess="", lang="eng", check_size=lambda *_: None))
    assert callable(debug_vision.main)

    for name in (
        "bot.py",
        "vision.py",
        "mouse.py",
        "identity.py",
        "offer.py",
        "configuration.py",
        "calibrate.py",
        "journal.py",
        "debug_vision.py",
    ):
        py_compile.compile(str(Path(__file__).resolve().parents[1] / name), doraise=True)
