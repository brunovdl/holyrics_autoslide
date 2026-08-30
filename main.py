"""Ponto de entrada principal para execução do Holyrics AutoSlide."""
from __future__ import annotations

import sys
import warnings

# Suprime avisos de depreciação de terceiros para manter o console limpo
warnings.filterwarnings("ignore", category=DeprecationWarning)

import flet as ft
from app.ui.app import HolyricsAutoSlideApp


def main(page: ft.Page) -> None:
    HolyricsAutoSlideApp(page)


if __name__ == "__main__":
    if "--web" in sys.argv:
        print("[INFO] Abrindo Holyrics AutoSlide no navegador padrão (porta 8550)...")
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8550)
    else:
        try:
            ft.app(target=main)
        except Exception as e:
            print(f"\n[AVISO] Falha ao inicializar janela nativa GTK: {e}")
            print("[INFO] Abrindo automaticamente no navegador padrão (http://localhost:8550)...\n")
            ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=8550)
