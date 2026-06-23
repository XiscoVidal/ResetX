"""Hardware spec card with glassmorphism styling and copy support."""
import tkinter as tk
import customtkinter as ctk
from ui import theme as T


class SpecCard(ctk.CTkFrame):
    def __init__(self, master, icon_img, title, value, sub_value="", color=T.ACCENT):
        super().__init__(
            master, fg_color=T.SURFACE, border_color=T.BORDER,
            border_width=1, corner_radius=T.RADIUS_MD,
        )
        self.grid_columnconfigure(1, weight=1)
        self._accent = color
        self._default_border = T.BORDER
        self._sub_value = sub_value

        self._icon = ctk.CTkLabel(self, text="", image=icon_img)
        self._icon.grid(row=0, column=0, rowspan=3, padx=(20, 15), pady=20)

        self._title_lbl = ctk.CTkLabel(
            self, text=title, font=T.font(11, "bold"),
            text_color=T.TEXT_SEC,
        )
        self._title_lbl.grid(row=0, column=1, sticky="sw", padx=(0, 20), pady=(15, 2))

        self._val_lbl = ctk.CTkLabel(
            self, text=value, font=T.font(15, "bold"), text_color=T.TEXT,
        )
        self._val_lbl.grid(row=1, column=1, sticky="nw", padx=(0, 20))

        self._sub_lbl = ctk.CTkLabel(
            self, text=sub_value, font=T.font(11), text_color=T.TEXT_SEC,
        )
        self._sub_lbl.grid(row=2, column=1, sticky="nw", padx=(0, 20), pady=(0, 15))

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-3>", self._on_right_click)
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)
            child.bind("<Button-3>", self._on_right_click)

    def _on_enter(self, _):
        self.configure(border_color=self._accent)

    def _on_leave(self, _):
        self.configure(border_color=self._default_border)

    def _on_right_click(self, event):
        menu = tk.Menu(self, tearoff=0, bg=T.SURFACE, fg=T.TEXT, activebackground=T.ELEVATED)
        title = self._title_lbl.cget("text")
        value = self._val_lbl.cget("text")
        sub = self._sub_lbl.cget("text")
        menu.add_command(
            label=f"Copiar {title.lower()}",
            command=lambda: self._copy(f"{value} \u2014 {sub}"),
        )
        menu.add_command(
            label=f"Copiar modelo",
            command=lambda: self._copy(sub),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def update_values(self, value, sub_value="", title=None):
        self._val_lbl.configure(text=value)
        self._sub_lbl.configure(text=sub_value)
        self._sub_value = sub_value
        if title:
            self._title_lbl.configure(text=title)
