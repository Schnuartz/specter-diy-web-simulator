import importlib.util
from pathlib import Path
import unittest

module_path = Path(__file__).resolve().parents[1] / "browser" / "source-project.py"
spec = importlib.util.spec_from_file_location("source_project", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceProjectTests(unittest.TestCase):
    def test_specter_diy_forks_are_recognized_by_project_name(self):
        for repository in (
            "cryptoadvance/specter-diy",
            "Schnuartz/specter-diy",
            "randomcontributor/specter-diy",
        ):
            with self.subTest(repository=repository):
                self.assertTrue(module.is_specter_diy_repository(repository))

    def test_playground_is_not_specter_diy(self):
        self.assertFalse(module.is_specter_diy_repository("randomcontributor/specter-playground"))


if __name__ == "__main__":
    unittest.main()
