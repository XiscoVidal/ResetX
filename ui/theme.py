"""Glassmorphism Design System v2 — ResetX UI/Pro Max."""
import customtkinter as ctk

BG_PRIMARY = "#080B10"
BG_SECONDARY = "#0C1117"
SURFACE = "#141B24"
SURFACE_HOVER = "#1C2633"
ELEVATED = "#1E2A38"
INSET = "#0A0F15"
BORDER = "#2D3A48"
BORDER_FOCUS = "#4A6180"
TEXT = "#E8EDF4"
TEXT_SEC = "#8899AB"
TEXT_MUTED = "#4D5D6F"
ACCENT = "#4C9AFF"
ACCENT_HOVER = "#6BAEFF"
GREEN = "#34D399"
GREEN_HOVER = "#2BBF87"
AMBER = "#FBBF24"
RED = "#F87171"
PURPLE = "#A78BFA"
ORANGE = "#FB923C"

FONT_UI = "Segoe UI"
FONT_MONO = "Consolas"
RADIUS_XS = 4
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 18
RADIUS_XL = 24
PAD_SM = 8
PAD_MD = 16
PAD_LG = 24


def init_theme():
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
    except Exception:
        pass


def font(size: int, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(
        family=FONT_MONO if mono else FONT_UI,
        size=size, weight=weight,
    )


def theme_scrollable(scroll: ctk.CTkScrollableFrame):
    try:
        scroll.configure(
            fg_color="transparent",
            scrollbar_fg_color=ELEVATED,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=BORDER_FOCUS,
        )
        if hasattr(scroll, "_parent_canvas"):
            scroll._parent_canvas.configure(bg=BG_PRIMARY, highlightthickness=0)
        if hasattr(scroll, "_scrollbar"):
            scroll._scrollbar.configure(
                fg_color=ELEVATED,
                button_color=BORDER,
                button_hover_color=BORDER_FOCUS,
            )
    except Exception:
        pass


def refresh_scroll_region(scroll: ctk.CTkScrollableFrame):
    try:
        scroll.update_idletasks()
        if hasattr(scroll, "_parent_frame"):
            scroll._parent_frame.update_idletasks()
        if hasattr(scroll, "_parent_canvas"):
            canvas = scroll._parent_canvas
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            canvas.yview_moveto(0)
    except Exception:
        pass


def glass_card(master, **kw) -> ctk.CTkFrame:
    defaults = dict(
        fg_color=SURFACE,
        border_color=BORDER,
        border_width=1,
        corner_radius=RADIUS_MD,
    )
    defaults.update(kw)
    return ctk.CTkFrame(master, **defaults)


def glass_panel(master, **kw) -> ctk.CTkFrame:
    defaults = dict(
        fg_color=BG_SECONDARY,
        border_color=BORDER,
        border_width=1,
        corner_radius=RADIUS_LG,
    )
    defaults.update(kw)
    return ctk.CTkFrame(master, **defaults)


def btn_primary(master, text, command=None, **kw) -> ctk.CTkButton:
    defaults = dict(
        text=text, command=command, font=font(13, "bold"),
        fg_color=GREEN, hover_color=GREEN_HOVER, text_color=BG_PRIMARY,
        corner_radius=RADIUS_SM, height=40,
    )
    defaults.update(kw)
    return ctk.CTkButton(master, **defaults)


def btn_secondary(master, text, command=None, **kw) -> ctk.CTkButton:
    defaults = dict(
        text=text, command=command, font=font(13),
        fg_color=ELEVATED, hover_color=SURFACE_HOVER, text_color=TEXT,
        border_width=1, border_color=BORDER, corner_radius=RADIUS_SM, height=36,
    )
    defaults.update(kw)
    return ctk.CTkButton(master, **defaults)


def btn_ghost(master, text, command=None, **kw) -> ctk.CTkButton:
    defaults = dict(
        text=text, command=command, font=font(13),
        fg_color="transparent", hover_color=ELEVATED, text_color=TEXT_SEC,
        corner_radius=RADIUS_SM, height=36, anchor="w",
    )
    defaults.update(kw)
    return ctk.CTkButton(master, **defaults)


def entry(master, placeholder="", width=280, **kw) -> ctk.CTkEntry:
    defaults = dict(
        placeholder_text=placeholder, width=width, height=40,
        fg_color=INSET, border_color=BORDER, text_color=TEXT,
        placeholder_text_color=TEXT_MUTED, corner_radius=RADIUS_MD, font=font(14),
    )
    defaults.update(kw)
    return ctk.CTkEntry(master, **defaults)


def section_label(master, text, **kw) -> ctk.CTkLabel:
    defaults = dict(
        text=text, font=font(10, "bold"), text_color=TEXT_MUTED, anchor="w",
    )
    defaults.update(kw)
    return ctk.CTkLabel(master, **defaults)


def heading(master, text, size=26, **kw) -> ctk.CTkLabel:
    defaults = dict(
        text=text, font=font(size, "bold"), text_color=TEXT, anchor="w",
    )
    defaults.update(kw)
    return ctk.CTkLabel(master, **defaults)
