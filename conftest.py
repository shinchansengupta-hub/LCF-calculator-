import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QMessageBox

from LCF_Life_Calculator import LCFApp


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication(sys.argv)
    yield instance


@pytest.fixture
def window(app):
    widget = LCFApp()
    yield widget
    widget.close()


def _dispatch_warning(parent, title, message):
    for module in list(sys.modules.values()):
        warnings = getattr(module, "warnings_seen", None)
        if isinstance(warnings, list):
            warnings.append((title, message))
    return QMessageBox.Ok


@pytest.fixture(autouse=True)
def capture_qmessagebox_warnings(monkeypatch):
    for module in list(sys.modules.values()):
        warnings = getattr(module, "warnings_seen", None)
        if isinstance(warnings, list):
            warnings.clear()
    monkeypatch.setattr(QMessageBox, "warning", _dispatch_warning)
