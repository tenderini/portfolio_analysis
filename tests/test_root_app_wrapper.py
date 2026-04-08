import importlib.util
import sys
import types
import unittest
from pathlib import Path


class RootAppWrapperTests(unittest.TestCase):
    def test_root_app_delegates_to_package_main(self) -> None:
        main_calls: list[str] = []

        fake_package_app = types.ModuleType("src.portfolio_analysis_app.app")
        fake_package_app.main = lambda: main_calls.append("called")

        previous_modules = {
            name: sys.modules.get(name)
            for name in [
                "src",
                "src.portfolio_analysis_app",
                "src.portfolio_analysis_app.app",
            ]
        }
        sys.modules["src"] = types.ModuleType("src")
        sys.modules["src.portfolio_analysis_app"] = types.ModuleType("src.portfolio_analysis_app")
        sys.modules["src.portfolio_analysis_app.app"] = fake_package_app

        try:
            spec = importlib.util.spec_from_file_location("test_root_app_module", Path("app.py"))
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        finally:
            for name, previous_module in previous_modules.items():
                if previous_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous_module

        self.assertEqual(main_calls, ["called"])
