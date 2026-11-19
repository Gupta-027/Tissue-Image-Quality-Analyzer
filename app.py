"""SlideQC web entry point: python -m streamlit run app.py"""
from pathlib import Path

from slideqc.ui.dashboard import main


if __name__ == "__main__":
    main(project_root=Path(__file__).resolve().parent)
