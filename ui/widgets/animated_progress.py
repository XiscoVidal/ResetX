"""Barra de progreso con interpolación suave y modo indeterminado."""
import customtkinter as ctk
from ui import theme as T


class AnimatedProgressBar(ctk.CTkFrame):
    """Progreso determinado/indeterminado con easing y colores por estado."""

    STATE_COLORS = {
        "running": T.ACCENT,
        "success": T.GREEN,
        "error": T.RED,
        "idle": T.TEXT_MUTED,
    }

    def __init__(self, master, height: int = 10, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._bar = ctk.CTkProgressBar(
            self, height=height, progress_color=T.ACCENT, fg_color=T.ELEVATED, corner_radius=height // 2,
        )
        self._bar.grid(row=0, column=0, sticky="ew")

        self._label = ctk.CTkLabel(self, text="", font=T.font(12, mono=True), text_color=T.TEXT_SEC, anchor="w")
        self._label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self._target = 0.0
        self._display = 0.0
        self._state = "idle"
        self._indeterminate = False
        self._pulse_dir = 1
        self._pulse_val = 0.12
        self._anim_id = None
        self._finish_cb = None

    def _cancel_anim(self):
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

    def _set_color(self, state: str, smooth: bool = True):
        self._state = state
        from ui import theme as T
        colors = {
            "running": T.ACCENT,
            "success": T.GREEN,
            "error": T.RED,
            "idle": T.TEXT_MUTED,
        }
        self._bar.configure(progress_color=colors.get(state, T.ACCENT), fg_color=T.ELEVATED)

    def set_indeterminate(self, active: bool, text: str = "Preparando…"):
        self._indeterminate = active
        self._cancel_anim()
        if active:
            self._set_color("running")
            self._label.configure(text=text)
            self._pulse_anim()
        else:
            self._bar.set(self._display)

    def _pulse_anim(self):
        if not self._indeterminate or not self.winfo_exists():
            return
        self._pulse_val += 0.04 * self._pulse_dir
        if self._pulse_val >= 0.42:
            self._pulse_dir = -1
        elif self._pulse_val <= 0.1:
            self._pulse_dir = 1
        self._bar.set(self._pulse_val)
        self._anim_id = self.after(80, self._pulse_anim)

    def set_progress(
        self,
        value: float,
        text: str = "",
        state: str = "running",
    ):
        self._indeterminate = False
        self._cancel_anim()
        self._target = max(0.0, min(1.0, value))
        self._set_color(state)
        if text:
            self._label.configure(text=text)
        self._ease_anim()

    def _ease_anim(self):
        if not self.winfo_exists():
            return
        diff = self._target - self._display
        if abs(diff) < 0.004:
            self._display = self._target
            self._bar.set(self._display)
            return
        self._display += diff * 0.38
        self._bar.set(self._display)
        self._anim_id = self.after(45, self._ease_anim)

    def finish(self, success: bool, text: str = "", on_complete=None):
        """Micro-animación al completar antes del resumen."""
        self._indeterminate = False
        self._cancel_anim()
        self._finish_cb = on_complete
        self._set_color("success" if success else "error")
        self._target = 1.0 if success else self._display
        self._label.configure(text=text or ("Completado" if success else "Finalizado con errores"))

        def _final_step():
            self._display = self._target
            self._bar.set(self._display)
            if self._finish_cb:
                self.after(200, self._finish_cb)

        steps = 4

        def _snap(i=0):
            if i >= steps:
                _final_step()
                return
            self._display += (self._target - self._display) * 0.5
            self._bar.set(self._display)
            self.after(40, lambda: _snap(i + 1))

        _snap()

    def reset(self):
        self._cancel_anim()
        self._indeterminate = False
        self._target = 0.0
        self._display = 0.0
        self._bar.set(0)
        self._set_color("idle")
        self._label.configure(text="")

    def apply_theme(self):
        self._label.configure(text_color=T.TEXT_SEC)
        self._set_color(self._state)
