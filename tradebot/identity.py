"""Bind the unique @username in a request to its non-unique display label."""
from dataclasses import dataclass

from vision import norm_display_name, norm_nick, ocr_display_name, ocr_nick


@dataclass(frozen=True)
class RequestIdentity:
    username: str
    display_name: str

    def __post_init__(self):
        object.__setattr__(self, "username", norm_nick(self.username))
        object.__setattr__(self, "display_name", norm_display_name(self.display_name))

    @property
    def complete(self):
        return bool(self.username and self.display_name)


def read_request(frame, cfg):
    return RequestIdentity(
        ocr_nick(frame.grab(cfg.reg["row_nick"]), cfg.tess, cfg.lang),
        ocr_display_name(frame.grab(cfg.reg["row_display"]), cfg.tess, cfg.lang))