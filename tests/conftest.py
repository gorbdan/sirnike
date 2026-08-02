# -*- coding: utf-8 -*-
"""pytest подхватывает conftest.py автоматически до сбора тестов.

Гарантируем, что env/sys.path/импорт SirNike происходят один раз и раньше
любого test_block_*.py — независимо от порядка сбора файлов pytest'ом.
"""
import test_helpers  # noqa: F401
